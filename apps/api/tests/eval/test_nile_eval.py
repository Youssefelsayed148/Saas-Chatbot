"""B.4: run the Nile eval in fts_only and hybrid and write dated results.

Needs the disposable test database (like every test). Defaults to the offline
stub model and the deterministic test embedder; nothing here calls a provider
unless the owner opts in below.

Environment (all optional, set in the process only):
  NILE_EVAL_WRITE_RESULTS=1   write nile-<date>-<model>.json/.md into tests/eval/results
  NILE_EVAL_MODEL=real        use the configured real chat model (owner key in the
                              environment; this spends money) instead of the stub
  NILE_EVAL_MODES=fts_only    comma list of modes (default: fts_only,hybrid)

The stub run does not assert the exit targets: calibration is pending, and the
extractive stub only exercises retrieval, the gate and citations. It asserts the
run is complete and well formed so a broken harness cannot pass silently.
"""

import os
import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from sqlalchemy.orm import Session as OrmSession

from app.chat.providers import ChatModel
from tests.eval import nile_metrics, nile_runner


def _model() -> tuple[ChatModel | None, str, str]:
    if os.environ.get("NILE_EVAL_MODEL") != "real":
        return None, "stub", "ExtractiveStubModel (offline, deterministic) with the test embedder"
    from app.chat.models import model_from_settings
    from app.core.config import get_settings

    model = model_from_settings(get_settings())
    if model is None:
        raise RuntimeError("NILE_EVAL_MODEL=real but no chat model could be built from settings.")
    ids = [str(getattr(model, "model", ""))] + list(getattr(model, "fallback_models", []) or [])
    name = ",".join(item for item in ids if item) or "configured-model"
    return model, name, f"real chat model chain: {name}; embeddings are still the test embedder"


def test_nile_eval_both_modes(app: FastAPI, db: OrmSession) -> None:
    modes = tuple(
        item.strip()
        for item in os.environ.get("NILE_EVAL_MODES", ",".join(nile_runner.MODES)).split(",")
        if item.strip()
    )
    model, label, note = _model()
    with tempfile.TemporaryDirectory() as tmp:
        verdicts = nile_runner.run_nile(app, db, Path(tmp), modes=modes, model=model)
    cases = nile_metrics.load_cases()
    summaries: dict[str, Any] = {}
    for mode, rows in verdicts.items():
        assert [row["id"] for row in rows] == [case["id"] for case in cases]
        summaries[mode] = nile_metrics.summarize(rows)
        assert summaries[mode]["cases"] == len(cases)
    print(nile_metrics.render_summary_table(summaries))
    out_dir = nile_metrics.RESULTS_DIR
    if os.environ.get("NILE_EVAL_WRITE_RESULTS") != "1":
        out_dir = Path(tempfile.mkdtemp(prefix="nile-eval-"))
    json_path, md_path = nile_metrics.write_results(
        out_dir, model_label=label, model_note=note, verdicts=verdicts
    )
    print("RESULTS:", json_path, md_path)
    assert json_path.exists() and md_path.exists()
    # fts_only must never run the vector leg; a hybrid request that silently
    # degraded is reported in the file (mode_effective) rather than failing.
    for row in verdicts.get("fts_only", []):
        assert not str(row["mode_effective"]).startswith("hybrid"), row
