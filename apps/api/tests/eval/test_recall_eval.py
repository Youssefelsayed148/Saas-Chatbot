"""H4: recall, wrong-refusal, refusal diagnostics and threshold sweep (needs the disposable DB).

Retrieval and gate only; never calls a provider. Hybrid mode uses the deterministic
test embedder, which is not semantic (see ``recall_runner.EMBEDDER_NOTE``).

Environment (process only):
  RECALL_EVAL_WRITE=1   write recall-<date>.md/json into tests/eval/results
                        (the JSON feeds ``scripts/rag_threshold_sweep.py``)
  RECALL_EVAL_MODES=fts_only,hybrid   comma list (default both)
"""

import os
import tempfile
from pathlib import Path

from fastapi import FastAPI
from sqlalchemy.orm import Session as OrmSession

from tests.eval import nile_metrics, nile_runner, recall_metrics, recall_runner


def test_recall_eval_both_modes(app: FastAPI, db: OrmSession) -> None:
    modes = tuple(
        item.strip()
        for item in os.environ.get("RECALL_EVAL_MODES", ",".join(nile_runner.MODES)).split(",")
        if item.strip()
    )
    with tempfile.TemporaryDirectory() as tmp:
        result = recall_runner.collect(app, db, Path(tmp), modes=modes)
    cases = recall_metrics.load_cases()
    by_mode = {}
    for mode, data in result["modes"].items():
        assert [row["id"] for row in data["recall_rows"]] == [case["id"] for case in cases]
        by_mode[mode] = data["recall_summary"]
        assert data["sweep"]["automatically_applied"] is False
        # every refusal explains itself
        for refusal in data["refusals"]:
            assert refusal["diagnosis"]["outcome"] in ("no_candidates", "gate_rejected_all")
            if refusal["diagnosis"]["nearest"] is not None:
                assert refusal["diagnosis"]["failed_rules"], refusal["id"]
    print(recall_metrics.render_table(by_mode))
    out_dir = nile_metrics.RESULTS_DIR
    if os.environ.get("RECALL_EVAL_WRITE") != "1":
        out_dir = Path(tempfile.mkdtemp(prefix="recall-eval-"))
    md_path, json_path = recall_runner.write_report(out_dir, result)
    print("REPORT:", md_path, json_path)
    assert md_path.exists() and json_path.exists()
