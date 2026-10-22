"""B.5: candidate loading, settings overlay and the comparison report (pure)."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from app.core.config import Settings
from tests.eval import gate_compare, nile_metrics


def test_defaults_candidate_leaves_settings_identical() -> None:
    base = Settings.model_construct(environment="test", database_url=None)
    applied = gate_compare.apply_candidate(base, gate_compare.DEFAULT_CANDIDATE)
    assert applied.model_dump() == base.model_dump()
    changed = gate_compare.apply_candidate(
        base, {"name": "x", "settings": {"retrieval_min_matched_terms": 1}}
    )
    assert changed.retrieval_min_matched_terms == 1 and base.retrieval_min_matched_terms == 2


def test_candidate_file_validation(tmp_path: Path) -> None:
    good = tmp_path / "ok.json"
    good.write_text(
        json.dumps([{"name": "one-term", "settings": {"retrieval_min_matched_terms": 1}}]),
        encoding="utf-8",
    )
    names = [c["name"] for c in gate_compare.load_candidates(good)]
    assert names == ["defaults", "one-term"]
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps([{"name": "x", "settings": {"database_url": "nope"}}]), "utf-8")
    with pytest.raises(ValueError, match="unknown setting"):
        gate_compare.load_candidates(bad)
    dup = tmp_path / "dup.json"
    dup.write_text(json.dumps([{"name": "defaults", "settings": {}}]), "utf-8")
    with pytest.raises(ValueError, match="Duplicate"):
        gate_compare.load_candidates(dup)


def test_report_marks_dropped_pages_and_leaks(tmp_path: Path) -> None:
    cases: list[dict[str, Any]] = [
        {
            "id": "g1",
            "expected_behavior": "grounded",
            "expected_sources": [{"file": "01-shipping-en_1.pdf", "page": 1}],
        },
        {"id": "a1", "expected_behavior": "abstain", "expected_sources": []},
        {"id": "i1", "expected_behavior": "injection", "expected_sources": []},
    ]
    page = {("01-shipping-en_1", 1)}
    results = {
        "g1": {
            "defaults": gate_compare.evaluate_case(cases[0], set(), True),
            "loose": gate_compare.evaluate_case(cases[0], page, True),
        },
        "a1": {
            "defaults": gate_compare.evaluate_case(cases[1], set(), True),
            "loose": gate_compare.evaluate_case(cases[1], page, True),
        },
        "i1": {
            "defaults": gate_compare.evaluate_case(cases[2], set(), True),
            "loose": gate_compare.evaluate_case(cases[2], page, True),
        },
    }
    assert results["g1"]["defaults"]["expected_page_passed"] is False
    assert results["a1"]["loose"]["leak"] is True
    assert results["i1"]["loose"]["expected_page_passed"] is None
    names = ["defaults", "loose"]
    report = gate_compare.build_report(cases, names, results, mode="fts_only", generated="now")
    assert "| defaults | 0/1 | 0/1 |" in report
    assert "| loose | 1/1 | 1/1 |" in report
    assert "| g1 | grounded | DROPPED | kept |" in report
    assert "| a1 | abstain | ok | LEAK |" in report
    md_path, json_path = gate_compare.write_report(
        tmp_path,
        mode="fts_only",
        cases=cases,
        candidates=[{"name": n, "settings": {}} for n in names],
        results=results,
        now=datetime(2026, 10, 22, 9, 30, tzinfo=UTC),
    )
    assert md_path.name == "gate-compare-2026-10-22-0930-fts-only.md"
    assert json.loads(json_path.read_text(encoding="utf-8"))["mode"] == "fts_only"


def test_the_real_cases_feed_the_report_shape() -> None:
    cases = nile_metrics.load_cases()
    row = gate_compare.evaluate_case(cases[0], set(), False)
    assert row["expected_page_passed"] is False and row["retrieved_anything"] is False
