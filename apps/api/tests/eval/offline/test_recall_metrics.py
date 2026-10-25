"""H4: arithmetic of the recall scoring, with hand-built facts."""

from tests.eval import recall_metrics as rm

GROUNDED = {
    "id": "g",
    "language": "ar",
    "category": "dialect",
    "expected_behavior": "grounded",
    "expected_sources": [{"file": "01-shipping-ar_1.pdf", "page": 1}],
}
ABSTAIN = {
    "id": "a",
    "language": "en",
    "category": "gap",
    "expected_behavior": "abstain",
    "expected_sources": [],
}
HIT = ("01-shipping-ar_1", 1)
OTHER = ("02-delivery-ar_1", 2)


def test_rank_is_over_unique_pages_and_cutoffs_apply() -> None:
    ranked = [OTHER, OTHER, ("03-terms-ar_1", 1), ("04-returns-ar_1", 1), HIT]
    row = rm.score_case(GROUNDED, ranked, {HIT})
    assert row["rank"] == 4 and row["hit_at_3"] is False and row["hit_at_8"] is True
    assert row["wrong_refusal"] is False and row["wrong_evidence_only"] is False


def test_wrong_refusal_and_wrong_evidence_are_distinct() -> None:
    refused = rm.score_case(GROUNDED, [HIT], set())
    assert refused["hit_at_3"] and refused["wrong_refusal"] and not refused["wrong_evidence_only"]
    wrong = rm.score_case(GROUNDED, [OTHER, HIT], {OTHER})
    assert not wrong["wrong_refusal"] and wrong["wrong_evidence_only"]


def test_abstain_cases_only_count_leaks() -> None:
    clean = rm.score_case(ABSTAIN, [OTHER], set())
    leak = rm.score_case(ABSTAIN, [OTHER], {OTHER})
    assert clean["leak"] is False and leak["leak"] is True
    assert clean["hit_at_8"] is None and clean["wrong_refusal"] is None


def test_summary_excludes_inapplicable_cases_from_each_rate() -> None:
    rows = [
        rm.score_case(GROUNDED, [HIT], {HIT}),
        rm.score_case(GROUNDED, [OTHER], set()),
        rm.score_case(ABSTAIN, [OTHER], {OTHER}),
    ]
    summary = rm.summarize(rows)
    assert summary["overall"]["hit_at_8"] == [1, 2]
    assert summary["overall"]["wrong_refusals"] == [1, 2]
    assert summary["overall"]["unanswerable_leaks"] == [1, 1]
    assert summary["by_language"]["ar"]["cases"] == 2
    table = rm.render_table({"fts_only": summary})
    assert "| dialect |" in table and "1/2" in table
