"""H4: pure scoring for the recall/dialect/typo set (retrieval + gate only).

No database and no network. ``recall_runner`` extracts, per case, the ranked
pages the retrieval returned and the pages that survived the gate; this module
judges and aggregates them. Honest scope: the test embedder is a deterministic
token hash, not a semantic model, so hybrid numbers from it measure plumbing and
lexical overlap only. Real semantic recall needs the owner-approved Part B run.
"""

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from tests.eval.nile_metrics import EVAL_DIR, Source, stem

CASES_PATH = EVAL_DIR / "nile_recall_eval.jsonl"
HIT_CUTOFFS = (3, 8)


def load_cases(path: Path = CASES_PATH) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]


def wanted(case: dict[str, Any]) -> set[Source]:
    return {(stem(row["file"]), int(row["page"])) for row in case["expected_sources"]}


def score_case(case: dict[str, Any], ranked: list[Source], passed: set[Source]) -> dict[str, Any]:
    """``ranked``: pages in retrieval rank order (before the gate); ``passed``: after it."""
    expected = wanted(case)
    unique: list[Source] = list(dict.fromkeys(ranked))
    rank = next((i + 1 for i, page in enumerate(unique) if page in expected), None)
    row: dict[str, Any] = {
        "id": case["id"],
        "language": case["language"],
        "category": case["category"],
        "behavior": case["expected_behavior"],
        "retrieved": len(unique),
        "passed_pages": sorted(f"{name} p{page}" for name, page in passed),
    }
    if case["expected_behavior"] == "abstain":
        row.update(leak=bool(passed), rank=None)
        for cutoff in HIT_CUTOFFS:
            row[f"hit_at_{cutoff}"] = None
        row.update(wrong_refusal=None, wrong_evidence_only=None)
        return row
    row["rank"] = rank
    row["leak"] = None
    for cutoff in HIT_CUTOFFS:
        row[f"hit_at_{cutoff}"] = rank is not None and rank <= cutoff
    row["wrong_refusal"] = not passed
    row["wrong_evidence_only"] = bool(passed) and not (expected & passed)
    return row


def _rate(rows: list[dict[str, Any]], key: str) -> list[int]:
    """[count, total] over the rows where the metric applies (not None)."""
    applicable = [row for row in rows if row[key] is not None]
    return [sum(bool(row[key]) for row in applicable), len(applicable)]


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def block(items: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "cases": len(items),
            "hit_at_3": _rate(items, "hit_at_3"),
            "hit_at_8": _rate(items, "hit_at_8"),
            "wrong_refusals": _rate(items, "wrong_refusal"),
            "wrong_evidence_only": _rate(items, "wrong_evidence_only"),
            "unanswerable_leaks": _rate(items, "leak"),
        }

    groups: dict[str, dict[str, list[dict[str, Any]]]] = {"category": defaultdict(list)}
    groups["language"] = defaultdict(list)
    for row in rows:
        groups["category"][row["category"]].append(row)
        groups["language"][row["language"]].append(row)
    return {
        "overall": block(rows),
        "by_category": {key: block(items) for key, items in sorted(groups["category"].items())},
        "by_language": {key: block(items) for key, items in sorted(groups["language"].items())},
    }


def _cell(pair: list[int]) -> str:
    return f"{pair[0]}/{pair[1]}" if pair[1] else "n/a"


def render_table(by_mode: dict[str, dict[str, Any]]) -> str:
    """One markdown table per grouping, one row per group, one column block per mode."""
    modes = list(by_mode)
    lines: list[str] = []
    for title, key in (
        ("Overall", None),
        ("By category", "by_category"),
        ("By language", "by_language"),
    ):
        lines += ["", f"### {title}", ""]
        head = (
            "| Group | "
            + " | ".join(
                f"{m}: hit@3 | {m}: hit@8 | {m}: wrong refusals | {m}: leaks" for m in modes
            )
            + " |"
        )
        lines += [head, "|---|" + "|".join("---:" for _ in range(4 * len(modes))) + "|"]
        names = ["all"] if key is None else sorted(by_mode[modes[0]][key])
        for name in names:
            cells = []
            for mode in modes:
                data = by_mode[mode]["overall"] if key is None else by_mode[mode][key][name]
                cells += [
                    _cell(data["hit_at_3"]),
                    _cell(data["hit_at_8"]),
                    _cell(data["wrong_refusals"]),
                    _cell(data["unanswerable_leaks"]),
                ]
            lines.append(f"| {name} | " + " | ".join(cells) + " |")
    return "\n".join(lines)
