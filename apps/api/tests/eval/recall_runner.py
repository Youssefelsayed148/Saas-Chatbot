"""H4: retrieval + gate over the recall set and the Nile set, in both modes (DB-backed).

Retrieval only: no chat model, no provider. Hybrid mode uses the deterministic
test embedder, which is a token hash and NOT semantic, so its cosine column proves
plumbing and lexical overlap only; do not read it as embedding quality.

Outputs plain per-case facts that ``recall_metrics`` scores and ``page_sweep``
replays, and a markdown/JSON report that applies nothing.
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session as OrmSession

from app.core.config import Settings
from app.knowledge.language import detect_language
from app.retrieval.evaluation import page_sweep
from app.retrieval.gate import relevance_gate, select_evidence
from app.retrieval.hybrid import retrieve_hybrid
from app.retrieval.service import RetrievedChunk
from app.retrieval.trace import refusal_diagnosis
from tests.eval import nile_metrics, nile_runner, recall_metrics
from tests.eval.nile_metrics import Source, expected_sources, locate_source

EMBEDDER_NOTE = (
    "Hybrid mode used the deterministic test embedder (token hash). It is NOT a semantic "
    "model: cosine values here say nothing about real embedding recall."
)
CURRENT = {"cosine_floor": 0.50, "fts_floor": 0.01, "min_matched_terms": 2}


def _page(chunk: RetrievedChunk) -> Source | None:
    return locate_source(chunk.title, chunk.page_ref)


def _ranked(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    return sorted(
        chunks,
        key=lambda c: (
            -c.rrf_score,
            -(c.vector_similarity if c.vector_similarity is not None else -2.0),
            -c.fts_match,
        ),
    )


def run_case(
    db: OrmSession, seeded: dict[str, Any], case: dict[str, Any], settings: Settings
) -> dict[str, Any]:
    from tests.retrieval_helpers import published_revision_id

    users = seeded["users"]
    revision = UUID(published_revision_id(db, users.tenant_id, seeded["bot_id"]))
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
    ranked_chunks = _ranked(retrieval.evidence)
    ranked = [page for page in map(_page, ranked_chunks) if page is not None]
    passed = {page for page in map(_page, select_evidence(decision, settings)) if page is not None}
    diagnosis = refusal_diagnosis(retrieval, decision) if not decision.passed else None
    candidates = [
        {
            "page": list(page) if (page := _page(c)) is not None else None,
            "cosine": c.vector_similarity,
            "fts_match": c.fts_match,
            "matched_terms": c.matched_terms,
            "query_terms": c.query_terms,
        }
        for c in ranked_chunks
    ]
    return {
        "score": recall_metrics.score_case(case, ranked, passed),
        "candidates": candidates,
        "diagnosis": diagnosis,
        "mode_effective": retrieval.mode,
        "term_labels": ranked_chunks[0].query_term_labels if ranked_chunks else [],
    }


def sweep_records(
    cases: list[dict[str, Any]], outputs: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Plain records for ``page_sweep``; cases with history (needs a rewrite) are skipped."""
    records = []
    for case, out in zip(cases, outputs, strict=True):
        if case.get("history"):
            continue
        sources = sorted(expected_sources(case)) if "expected_sources" in case else []
        behaviour = case.get("expected_behavior", "abstain")
        records.append(
            {
                "id": case["id"],
                "behavior": "grounded" if behaviour == "grounded" or sources else "abstain",
                "language": case["language"],
                "expected": [list(page) for page in sources],
                "candidates": out["candidates"],
            }
        )
    return records


def collect(
    app: Any, db: OrmSession, tmp_root: Path, *, modes: tuple[str, ...] = nile_runner.MODES
) -> dict[str, Any]:
    from tests.retrieval_helpers import retrieval_settings

    seeded = nile_runner.seed_nile_bot(app, db, tmp_root)
    settings = retrieval_settings(storage_root=str(tmp_root))
    if "hybrid" in modes:
        assert nile_runner.prepare_hybrid(db, seeded) > 0
    recall_cases = recall_metrics.load_cases()
    nile_cases = nile_metrics.load_cases()
    result: dict[str, Any] = {"modes": {}}
    for mode in modes:
        nile_runner.set_mode(db, seeded, mode)
        recall_out = [run_case(db, seeded, case, settings) for case in recall_cases]
        nile_out = [run_case(db, seeded, case, settings) for case in nile_cases]
        records = sweep_records(recall_cases, recall_out) + sweep_records(nile_cases, nile_out)
        result["modes"][mode] = {
            "recall_rows": [out["score"] for out in recall_out],
            "recall_summary": recall_metrics.summarize([out["score"] for out in recall_out]),
            "refusals": [
                {
                    "id": case["id"],
                    "expected": case["expected_behavior"],
                    "diagnosis": out["diagnosis"],
                    "terms": out["term_labels"],
                }
                for case, out in zip(recall_cases, recall_out, strict=True)
                if out["diagnosis"] is not None
            ],
            "sweep_records": records,
            "sweep": page_sweep(
                records,
                cosines=(None,) if mode == "fts_only" else page_sweep_cosines(),
                current=CURRENT if mode != "fts_only" else {**CURRENT, "cosine_floor": None},
            ),
        }
    return result


def page_sweep_cosines() -> tuple[float | None, ...]:
    from app.retrieval.evaluation import SWEEP_COSINES

    return SWEEP_COSINES


def render_report(result: dict[str, Any], generated: str) -> str:
    modes = result["modes"]
    by_mode = {mode: data["recall_summary"] for mode, data in modes.items()}
    lines = [
        "# H4 recall and gate diagnostics (retrieval + gate only)",
        "",
        f"Generated {generated} (UTC). No provider and no chat model were called. "
        "Nothing here is applied.",
        "",
        f"**Caveat:** {EMBEDDER_NOTE}",
        "",
        "## Recall set (`nile_recall_eval.jsonl`)",
        "",
        "hit@k: expected page among the first k distinct retrieved pages. Wrong refusal: "
        "answerable case where no chunk survived the gate. Leaks: unanswerable cases that "
        "kept evidence.",
        recall_metrics.render_table(by_mode),
        "",
        "## Refusal diagnostics (cases the gate refused)",
        "",
        "| mode | case | expected | failed rules | nearest cosine / floor | terms | fts |",
        "|---|---|---|---|---|---|---|",
    ]
    for mode, data in modes.items():
        for row in data["refusals"]:
            diagnosis = row["diagnosis"]
            nearest = diagnosis["nearest"]
            if nearest is None:
                lines.append(f"| {mode} | {row['id']} | {row['expected']} | no candidates | | | |")
                continue
            cosine = "n/a" if nearest["cosine"] is None else f"{nearest['cosine']:.3f}"
            floor = nearest.get("cosine_floor")
            lines.append(
                f"| {mode} | {row['id']} | {row['expected']} | "
                f"{', '.join(diagnosis['failed_rules']) or '-'} | "
                f"{cosine} / {'n/a' if floor is None else f'{floor:.2f}'} | "
                f"{nearest['matched_terms']}/{nearest.get('required_terms', '?')} | "
                f"{nearest['fts_match']:.3f} (min {nearest.get('fts_minimum', '?')}) |"
            )
    lines += ["", "## Threshold sweep (recommendation only)", ""]
    for mode, data in modes.items():
        sweep = data["sweep"]
        lines += [
            f"### {mode}: {sweep['answerable_cases']} answerable, "
            f"{sweep['unanswerable_cases']} unanswerable (recall set + Nile cases without history)",
            "",
            "| cosine floor | fts floor | min terms | wrong refusals | wrong-evidence only "
            "| leaks |",
            "|---:|---:|---:|---:|---:|---:|",
        ]
        shown = list(sweep["ranked"])
        if sweep["current"] and sweep["current"] not in shown:
            shown.append(sweep["current"])
        for row in shown:
            tag = " (current default)" if row is sweep["current"] else ""
            cosine = "off" if row["cosine_floor"] is None else f"{row['cosine_floor']:.2f}"
            lines.append(
                f"| {cosine}{tag} | {row['fts_floor']} | {row['min_matched_terms']} | "
                f"{row['wrong_refusals']} | {row['wrong_evidence_only']} | "
                f"{row['unanswerable_leaks']} |"
            )
        lines.append("")
    return "\n".join(lines)


def write_report(out_dir: Path, result: dict[str, Any]) -> tuple[Path, Path]:
    moment = datetime.now(UTC)
    base = f"recall-{moment.strftime('%Y-%m-%d-%H%M')}"
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path, json_path = out_dir / f"{base}.md", out_dir / f"{base}.json"
    md_path.write_text(render_report(result, moment.strftime("%Y-%m-%d %H:%M")), encoding="utf-8")
    json_path.write_text(
        json.dumps(
            {"generated_utc": moment.isoformat(), "embedder_note": EMBEDDER_NOTE, **result},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return md_path, json_path
