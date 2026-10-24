"""B.5: retrieval-only comparison of candidate gate settings on the Nile cases.

For every case and every candidate setting, retrieval runs (no model call, no
answer) and the relevance gate decides; the report says whether the expected
page passed the gate (grounded cases) or whether anything leaked through
(abstain and injection-only cases). It does NOT pick values: the owner reads the
table and decides (see ``docs/rag-phase/THRESHOLDS.md``).

Candidate file (JSON), a list; the repository defaults are always added first:

    [
      {"name": "one-term", "settings": {"retrieval_min_matched_terms": 1}},
      {"name": "no-store-name",
       "settings": {"retrieval_gate_ignore_terms": ["nilecart", "نايل", "كارت"]}},
      {"name": "top-result",
       "settings": {"retrieval_top_result_cosine_floor": 0.35,
                    "retrieval_top_result_margin": 0.05}}
    ]

Allowed setting keys: retrieval_vector_floors, retrieval_min_matched_terms,
retrieval_min_fts_match, retrieval_gate_ignore_terms,
retrieval_top_result_cosine_floor, retrieval_top_result_margin.
"""

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session as OrmSession

from app.core.config import Settings
from app.knowledge.language import detect_language
from app.retrieval.gate import relevance_gate, select_evidence
from app.retrieval.hybrid import retrieve_hybrid
from tests.eval.nile_metrics import expected_sources, locate_source

ALLOWED_KEYS = {
    "retrieval_vector_floors",
    "retrieval_min_matched_terms",
    "retrieval_min_fts_match",
    "retrieval_gate_ignore_terms",
    "retrieval_top_result_cosine_floor",
    "retrieval_top_result_margin",
}
DEFAULT_CANDIDATE: dict[str, Any] = {"name": "defaults", "settings": {}}


def load_candidates(path: Path | None) -> list[dict[str, Any]]:
    """Defaults first, then the candidates from the JSON file (validated)."""
    candidates = [DEFAULT_CANDIDATE]
    if path is None:
        return candidates
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, list):
        raise ValueError("The candidate file must be a JSON list.")
    seen = {"defaults"}
    for item in loaded:
        name = str(item["name"])
        if name in seen:
            raise ValueError(f"Duplicate candidate name: {name}")
        unknown = set(item.get("settings", {})) - ALLOWED_KEYS
        if unknown:
            raise ValueError(f"Candidate {name}: unknown setting(s) {sorted(unknown)}")
        seen.add(name)
        candidates.append({"name": name, "settings": dict(item.get("settings", {}))})
    return candidates


def apply_candidate(base: Settings, candidate: dict[str, Any]) -> Settings:
    """A copy of ``base`` with the candidate's gate settings; ``base`` is untouched."""
    values = dict(candidate["settings"])
    return base.model_copy(update=values)


def evaluate_case(
    case: dict[str, Any], passed_pages: set[tuple[str, int]], any_candidates: bool
) -> dict[str, Any]:
    """Pure: did the expected page pass (grounded) or did anything leak (abstain)?"""
    wanted = expected_sources(case)
    row: dict[str, Any] = {
        "passed_pages": sorted(f"{name} p{page}" for name, page in passed_pages),
        "retrieved_anything": any_candidates,
    }
    if case["expected_behavior"] == "abstain":
        row["leak"] = bool(passed_pages)
        row["expected_page_passed"] = None
    else:
        row["leak"] = None
        # Injection cases without a page (pure injections) have nothing to retain.
        row["expected_page_passed"] = bool(wanted & passed_pages) if wanted else None
    return row


def totals(case_rows: list[dict[str, Any]]) -> dict[str, Any]:
    kept = [r for r in case_rows if r["expected_page_passed"] is not None]
    abstain = [r for r in case_rows if r["leak"] is not None]
    return {
        "expected_page_kept": sum(1 for r in kept if r["expected_page_passed"]),
        "expected_page_total": len(kept),
        "leaks": sum(1 for r in abstain if r["leak"]),
        "abstain_total": len(abstain),
    }


def build_report(
    cases: list[dict[str, Any]],
    names: list[str],
    results: dict[str, dict[str, dict[str, Any]]],
    *,
    mode: str,
    generated: str,
) -> str:
    """Markdown: totals per candidate, then one row per case."""
    lines = [
        f"# Gate candidate comparison ({mode}, retrieval only)",
        "",
        f"Generated {generated} (UTC). No model calls. The owner chooses; nothing here is applied.",
        "",
        "| Candidate | Expected page kept | Leaks (abstain cases) |",
        "|---|---:|---:|",
    ]
    for name in names:
        total = totals([results[case["id"]][name] for case in cases])
        lines.append(
            f"| {name} | {total['expected_page_kept']}/{total['expected_page_total']} | "
            f"{total['leaks']}/{total['abstain_total']} |"
        )
    lines += ["", "## Per case", "", "| case | expects | " + " | ".join(names) + " |"]
    lines.append("|---|---|" + "|".join("---" for _ in names) + "|")
    for case in cases:
        expects = case["expected_behavior"]
        cells = []
        for name in names:
            row = results[case["id"]][name]
            if expects == "abstain":
                cells.append("LEAK" if row["leak"] else "ok")
            elif row["expected_page_passed"] is None:
                cells.append("passed: " + (", ".join(row["passed_pages"]) or "none"))
            else:
                cells.append("kept" if row["expected_page_passed"] else "DROPPED")
        lines.append(f"| {case['id']} | {expects} | " + " | ".join(cells) + " |")
    lines.append("")
    return "\n".join(lines)


def collect(
    db: OrmSession,
    seeded: dict[str, Any],
    cases: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    base_settings: Settings,
) -> dict[str, dict[str, dict[str, Any]]]:
    """Run retrieval + gate + evidence slice for every candidate and case (DB-backed)."""
    from tests.retrieval_helpers import published_revision_id

    users = seeded["users"]
    revision = UUID(published_revision_id(db, users.tenant_id, seeded["bot_id"]))
    results: dict[str, dict[str, dict[str, Any]]] = {case["id"]: {} for case in cases}
    for candidate in candidates:
        settings = apply_candidate(base_settings, candidate)
        for case in cases:
            retrieval = retrieve_hybrid(
                db,
                tenant_id=users.tenant_id,
                bot_id=UUID(seeded["bot_id"]),
                revision_id=revision,
                question=case["question"],
                question_language=detect_language(case["question"]) or case["language"],
                settings=settings,
            )
            decision = relevance_gate(retrieval, settings)
            pages = set()
            # What the model would actually receive (the real evidence slice), not
            # everything the gate passed: a passed document can still be cut.
            for chunk in select_evidence(decision, settings):
                located = locate_source(chunk.title, chunk.page_ref)
                if located:
                    pages.add(located)
            results[case["id"]][candidate["name"]] = evaluate_case(
                case, pages, bool(retrieval.evidence)
            )
    return results


def write_report(
    out_dir: Path,
    *,
    mode: str,
    cases: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    results: dict[str, dict[str, dict[str, Any]]],
    now: datetime | None = None,
) -> tuple[Path, Path]:
    moment = now or datetime.now(UTC)
    base = f"gate-compare-{moment.strftime('%Y-%m-%d-%H%M')}-{re.sub(r'[^a-z0-9]+', '-', mode)}"
    names = [candidate["name"] for candidate in candidates]
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path, json_path = out_dir / f"{base}.md", out_dir / f"{base}.json"
    md_path.write_text(
        build_report(cases, names, results, mode=mode, generated=moment.strftime("%Y-%m-%d %H:%M")),
        encoding="utf-8",
    )
    json_path.write_text(
        json.dumps(
            {"mode": mode, "candidates": candidates, "results": results},
            ensure_ascii=False,
            indent=2,
            default=list,
        ),
        encoding="utf-8",
    )
    return md_path, json_path
