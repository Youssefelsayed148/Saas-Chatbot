"""P3-05: run the evaluation suite and write PHASE-03/EVAL-REPORT.md.

The eval runs the deliberate chat pipeline against the real retrieval corpus
with the deterministic stub model and records REAL numbers against the
docs/14 §10 targets (see tests/eval/runner.py). Verdicts gate this file."""

import os
import tempfile
from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy.orm import Session as OrmSession

from tests.eval import runner

TD = tempfile.TemporaryDirectory()


@pytest.fixture(scope="module", autouse=True)
def _tmp_root() -> Any:
    TD.__enter__()
    yield
    TD.__exit__(None, None, None)


def test_eval_report_meets_targets(app: FastAPI, db: OrmSession, tmp_path: Any) -> None:
    _rerun = os.environ.get("EVAL_REAL_RERUN") == "1"
    run_output = runner.run_all(app, db, tmp_path, rerun_with_owner_key=_rerun)
    summary = run_output["summary"]
    report = runner.render_report(run_output)

    runner.REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    runner.REPORT_PATH.write_text(report, encoding="utf-8")

    import json as _json

    print("CASES:", _json.dumps(summary, indent=2, default=str))
    for bucket in ("grounded", "unanswerable", "injection", "cross_language"):
        fails = [
            (row["id"], row["pipeline_kind"])
            for row in summary[bucket + "_cases"]
            if not row["passed"]
        ]
        if fails:
            print(f"{bucket.upper()}-FAILS:", fails)
    # The docs/14 §10 default thresholds gate the phase report.
    for bucket in ("grounded", "unanswerable", "injection", "cross_language"):
        fails = [
            (row["id"], row["pipeline_kind"])
            for row in summary[bucket + "_cases"]
            if not row["passed"]
        ]
        print(f"{bucket.upper()}-FAILS:", fails)
    assert summary["grounded"]["total"] >= 5
    assert summary["grounded"]["rate"] >= runner.TARGETS["grounded_correct_citation"]
    assert summary["unanswerable"]["total"] >= 7
    assert summary["unanswerable"]["rate"] >= runner.TARGETS["unanswerable_abstained"]
    assert summary["injection"]["total"] >= 4
    assert summary["injection"]["rate"] == runner.TARGETS["injection_resisted"]
    assert summary["cross_language"]["total"] >= 5
    # P4-00 additions must pass individually with precise diagnostics:
    new_unanswerable = {"screens-install", "staff-vacations-ar", "office-chairs"}
    new_cross = {"cross-gift-cost", "cross-gift-materials", "cross-gift-timing"}
    new_injection = {"doc-injection-en", "doc-injection-ar"}
    for bucket in ("grounded", "unanswerable", "injection", "cross_language"):
        by_id = {row["id"]: row for row in summary[bucket + "_cases"]}
        for case_id in new_unanswerable | new_cross | new_injection:
            if case_id in by_id:
                assert by_id[case_id]["passed"], (bucket, case_id, by_id[case_id])
    # cross_tenant leakage is always 0 (schema-level guards proven in test_retrieval)
    assert summary["cross_tenant_leakage"] == 0.0
    # NOTE: the two cross-language cases ask real Arabic-script questions over
    # EN-only content. The deterministic stub cannot translate, so the stub
    # run records its measured rate without a hard target — that question is
    # part of the P3 gate decision (docs/14 §10) with a real model.


def test_eval_jsonl_cases_are_valid() -> None:
    cases = runner.load_cases()
    assert len(cases) >= 15
    kinds = {case["kind"] for case in cases}
    assert kinds == {"grounded", "unanswerable", "injection", "cross_language"}
    languages = {case["language"] for case in cases}
    assert languages == {"en", "ar"}
