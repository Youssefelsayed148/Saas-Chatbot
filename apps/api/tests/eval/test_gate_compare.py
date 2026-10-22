"""B.5: retrieval-only gate comparison on the Nile corpus (needs the disposable DB).

Environment (process only):
  GATE_CANDIDATES=path/to/candidates.json   extra candidates (see gate_compare.py)
  GATE_COMPARE_MODE=fts_only|hybrid         retrieval mode (default fts_only)
  GATE_COMPARE_WRITE=1                      write gate-compare-<date>.md/json into
                                            tests/eval/results
Uses the test embedder in hybrid mode (mechanics only); never calls a provider.
"""

import os
import tempfile
from pathlib import Path

from fastapi import FastAPI
from sqlalchemy.orm import Session as OrmSession

from tests.eval import gate_compare, nile_metrics, nile_runner
from tests.retrieval_helpers import retrieval_settings


def test_gate_candidates_report(app: FastAPI, db: OrmSession) -> None:
    raw = os.environ.get("GATE_CANDIDATES")
    candidates = gate_compare.load_candidates(Path(raw) if raw else None)
    mode = os.environ.get("GATE_COMPARE_MODE", "fts_only")
    assert mode in nile_runner.MODES
    cases = nile_metrics.load_cases()
    with tempfile.TemporaryDirectory() as tmp:
        seeded = nile_runner.seed_nile_bot(app, db, Path(tmp))
        if mode == "hybrid":
            assert nile_runner.prepare_hybrid(db, seeded) > 0
        nile_runner.set_mode(db, seeded, mode)
        base = retrieval_settings(storage_root=str(tmp))
        results = gate_compare.collect(db, seeded, cases, candidates, base)
    out_dir = nile_metrics.RESULTS_DIR
    if os.environ.get("GATE_COMPARE_WRITE") != "1":
        out_dir = Path(tempfile.mkdtemp(prefix="gate-compare-"))
    md_path, json_path = gate_compare.write_report(
        out_dir, mode=mode, cases=cases, candidates=candidates, results=results
    )
    print("REPORT:", md_path, json_path)
    assert md_path.exists() and json_path.exists()
    assert set(results) == {case["id"] for case in cases}
    for per_case in results.values():
        assert set(per_case) == {candidate["name"] for candidate in candidates}
