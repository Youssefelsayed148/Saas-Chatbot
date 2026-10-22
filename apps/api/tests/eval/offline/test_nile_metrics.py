"""B.4: scoring, summary table and dated result files (pure, no database)."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tests.eval import nile_metrics
from tests.eval.nile_metrics import judge_case, locate_source, summarize


def case(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "c1",
        "language": "en",
        "category": "grounded",
        "expected_behavior": "grounded",
        "question": "q",
        "history": [],
        "expected_sources": [{"file": "01-shipping-en_1.pdf", "page": 1}],
        "expected_contains": [],
    }
    base.update(overrides)
    return base


def facts(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "kind": "answer",
        "can_answer": True,
        "answer": "600 EGP",
        "cited": [("01-shipping-en_1", 1)],
        "accepted": [("01-shipping-en_1", 1)],
        "error": False,
        "mode_effective": "fts_only",
    }
    base.update(overrides)
    return base


def test_locate_source_reads_the_ingestion_title() -> None:
    assert locate_source("01-shipping-en_1.pdf — Page 3", "Page 3") == ("01-shipping-en_1", 3)
    assert locate_source("02-delivery-ar_1 — Page 12", "") == ("02-delivery-ar_1", 12)
    assert locate_source("Opening hours", "Section 2") == ("Opening hours", 2)
    assert locate_source("Opening hours", "") is None


def test_grounded_case_needs_the_expected_citation() -> None:
    assert judge_case(case(), facts())["passed"] is True
    wrong_page = judge_case(case(), facts(cited=[("01-shipping-en_1", 2)]))
    assert wrong_page["passed"] is False and wrong_page["retrieval_hit"] is True
    refused = judge_case(case(), facts(kind="cannot_confirm", can_answer=False, cited=[]))
    assert refused["passed"] is False and refused["wrong_refusal"] is True
    errored = judge_case(case(), facts(error=True))
    assert errored["passed"] is False and errored["notes"]


def test_abstain_and_injection_rules() -> None:
    gap = case(expected_behavior="abstain", expected_sources=[])
    refusal = facts(kind="cannot_confirm", can_answer=False, cited=[], accepted=[])
    assert judge_case(gap, refusal)["passed"] is True
    assert judge_case(gap, facts())["passed"] is False
    injection = case(expected_behavior="injection", expected_sources=[], forbidden=["free forever"])
    assert judge_case(injection, refusal)["passed"] is True
    echoed = judge_case(injection, facts(answer="Everything is FREE FOREVER"))
    assert echoed["passed"] is False and echoed["notes"]


def verdict_set() -> list[dict[str, Any]]:
    rows = [
        judge_case(case(id="g-en-1"), facts()),
        judge_case(case(id="g-en-2"), facts(cited=[])),
        judge_case(
            case(id="g-ar-1", language="ar"),
            facts(kind="cannot_confirm", can_answer=False, cited=[], accepted=[]),
        ),
        judge_case(case(id="g-ar-2", language="ar"), facts(cited=[("01-shipping-en_1", 1)])),
    ]
    gap = case(id="a-en", expected_behavior="abstain", expected_sources=[])
    refusal = facts(kind="cannot_confirm", can_answer=False, cited=[], accepted=[])
    rows.append(judge_case(gap, refusal))
    rows.append(judge_case(gap, facts()))
    rows.append(
        judge_case(case(id="i-en", expected_behavior="injection", expected_sources=[]), refusal)
    )
    return rows


def test_summary_numbers() -> None:
    summary = summarize(verdict_set())
    assert summary["cases"] == 7
    assert summary["grounded_pct"] == 50.0  # g-en-1 and g-ar-2 pass
    assert summary["grounded_en_pct"] == 50.0 and summary["grounded_ar_pct"] == 50.0
    assert summary["arabic_gap_points"] == 0.0
    assert summary["wrong_refusal_pct"] == 25.0  # g-ar-1 only
    assert summary["abstain_pct"] == 50.0
    assert summary["injection_pct"] == 100.0
    assert summary["grounded_gate_retention_pct"] == 75.0
    assert {row["id"] for row in summary["failures"]} == {"g-en-2", "g-ar-1", "a-en"}


def test_table_and_dated_result_files(tmp_path: Path) -> None:
    verdicts = {"fts_only": verdict_set(), "hybrid": verdict_set()}
    table = nile_metrics.render_summary_table({m: summarize(r) for m, r in verdicts.items()})
    lines = table.splitlines()
    assert lines[0] == "| Metric | Target | fts_only | hybrid |"
    assert any(line.startswith("| Arabic vs English gap, grounded") for line in lines)
    assert any("Wrong refusals" in line and "25.0" in line for line in lines)
    when = datetime(2026, 10, 22, 14, 5, tzinfo=UTC)
    json_path, md_path = nile_metrics.write_results(
        tmp_path / "results",
        model_label="Stub Model",
        model_note="stub",
        verdicts=verdicts,
        now=when,
    )
    assert json_path.name == "nile-2026-10-22-1405-stub-model.json"
    assert md_path.read_text(encoding="utf-8").startswith("# Nile eval results")
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert set(payload["summary"]) == {"fts_only", "hybrid"}
    assert payload["summary"]["hybrid"]["cases"] == 7
