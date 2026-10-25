"""Print a gate-threshold sweep over recorded eval candidates. Applies nothing.

Offline and read-only: it replays the gate rule (cosine floor OR matched terms plus
FTS floor) on the numbers recorded by the recall eval. No database, no provider,
no settings are read or written.

Produce the records (disposable DB only, retrieval and gate only, no provider):

    RECALL_EVAL_WRITE=1 python -m pytest tests/eval/test_recall_eval.py -q -s

then, from apps/api:

    python scripts/rag_threshold_sweep.py tests/eval/results/recall-<date>.json
    python scripts/rag_threshold_sweep.py <records.json> --mode hybrid --top 10 \
        --cosines none,0.4,0.5 --fts 0.01,0.05 --terms 1,2

The hybrid cosine column is only meaningful for a real embedder; records made with
the test embedder (the default) are a token hash and say nothing about semantics.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.retrieval.evaluation import (  # noqa: E402
    SWEEP_COSINES,
    SWEEP_FTS,
    SWEEP_TERMS,
    page_sweep,
)

CURRENT = {"cosine_floor": 0.50, "fts_floor": 0.01, "min_matched_terms": 2}


def _floats(raw: str | None, default: tuple[Any, ...]) -> tuple[Any, ...]:
    if not raw:
        return default
    return tuple(None if item.strip().lower() == "none" else float(item) for item in raw.split(","))


def _ints(raw: str | None, default: tuple[int, ...]) -> tuple[int, ...]:
    return tuple(int(item) for item in raw.split(",")) if raw else default


def render(mode: str, sweep: dict[str, Any], top: int) -> str:
    lines = [
        f"== {mode}: {sweep['answerable_cases']} answerable, "
        f"{sweep['unanswerable_cases']} unanswerable ==",
        f"{'cosine':>7} {'fts':>6} {'terms':>5} {'wrong refusals':>15} "
        f"{'wrong-evidence':>15} {'leaks':>6}",
    ]
    ordered = sorted(
        sweep["rows"],
        key=lambda r: (
            r["unanswerable_leaks"],
            r["wrong_refusals"],
            r["wrong_evidence_only"],
            -r["min_matched_terms"],
            -r["fts_floor"],
            r["cosine_floor"] if r["cosine_floor"] is not None else 2,
        ),
    )[:top]
    shown = list(ordered)
    if sweep["current"] and sweep["current"] not in shown:
        shown.append(sweep["current"])
    for row in shown:
        cosine = "off" if row["cosine_floor"] is None else f"{row['cosine_floor']:.2f}"
        mark = "  <- current default" if row is sweep["current"] else ""
        by_language = ",".join(f"{k}:{v}" for k, v in row["wrong_refusals_by_language"].items())
        lines.append(
            f"{cosine:>7} {row['fts_floor']:>6} {row['min_matched_terms']:>5} "
            f"{row['wrong_refusals']:>15} {row['wrong_evidence_only']:>15} "
            f"{row['unanswerable_leaks']:>6}{mark}" + (f"  [{by_language}]" if by_language else "")
        )
    lines.append(f"({sweep['selection_rule']}; {sweep['status']}; nothing applied)")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("records", type=Path, help="recall-<date>.json written by the recall eval")
    parser.add_argument("--mode", help="one mode (default: every mode in the file)")
    parser.add_argument("--top", type=int, default=8, help="rows to print per mode")
    parser.add_argument("--cosines", help="comma list, 'none' = cosine off")
    parser.add_argument("--fts", help="comma list of FTS floors")
    parser.add_argument("--terms", help="comma list of minimum matched terms")
    args = parser.parse_args(argv)
    payload = json.loads(args.records.read_text(encoding="utf-8"))
    note = payload.get("embedder_note")
    if note:
        print(f"NOTE: {note}\n")
    modes = payload["modes"]
    if args.mode:
        if args.mode not in modes:
            print(f"mode {args.mode!r} not in file (have {sorted(modes)})", file=sys.stderr)
            return 2
        modes = {args.mode: modes[args.mode]}
    for mode, data in modes.items():
        sweep = page_sweep(
            data["sweep_records"],
            cosines=_floats(args.cosines, (None,) if mode == "fts_only" else SWEEP_COSINES),
            fts_floors=_floats(args.fts, SWEEP_FTS),
            min_terms=_ints(args.terms, SWEEP_TERMS),
            current={**CURRENT, "cosine_floor": None} if mode == "fts_only" else CURRENT,
        )
        print(render(mode, sweep, args.top))
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
