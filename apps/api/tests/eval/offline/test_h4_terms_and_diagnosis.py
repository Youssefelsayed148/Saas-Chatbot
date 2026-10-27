"""H4 (offline): filler terms leave the term COUNT only; refusals say which rule failed."""

from dataclasses import replace
from typing import Any
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.retrieval.evaluation import page_sweep
from app.retrieval.gate import relevance_gate
from app.retrieval.query import (
    ARABIC_FILLER_TERMS,
    ARABIC_STOP_WORDS,
    ENGLISH_FILLER_TERMS,
    ENGLISH_STOP_WORDS,
    build_tsquery,
    normalise_ignore_terms,
    term_labels,
    term_queries,
)
from app.retrieval.service import RetrievalResult, RetrievedChunk
from app.retrieval.trace import candidate_trace, refusal_diagnosis

# Words that carry the topic in a shop FAQ; none may ever be treated as a filler.
CONTENT_WORDS = {
    "price", "cost", "fee", "refund", "return", "returns", "shipping", "delivery", "hours",
    "open", "policy", "free", "days", "order", "payment", "warranty", "cancel", "track",
    "سعر", "رسوم", "استرجاع", "استرداد", "شحن", "الشحن", "توصيل", "التوصيل", "مواعيد",
    "ساعات", "سياسة", "ضمان", "الغاء", "تتبع", "دفع", "الدفع", "طلب", "الطلب",
}  # fmt: skip
MODEL = "openai:text-embedding-3-large"


def make_chunk(**kwargs: Any) -> RetrievedChunk:
    base = RetrievedChunk(uuid4(), uuid4(), "Doc", None, "text", "en", 0, 0, None, "2", 4, 0)
    return replace(base, **kwargs)


def settings(**overrides: Any) -> Settings:
    return Settings.model_construct(**{"environment": "test", "database_url": None, **overrides})


def test_filler_lists_never_overlap_the_stop_lists_or_topic_words() -> None:
    assert not ENGLISH_FILLER_TERMS & ENGLISH_STOP_WORDS
    assert not ARABIC_FILLER_TERMS & ARABIC_STOP_WORDS
    assert not (ENGLISH_FILLER_TERMS | ARABIC_FILLER_TERMS) & CONTENT_WORDS


@pytest.mark.parametrize(
    ("question", "language", "labels"),
    [
        ("Could you please tell me the opening hours?", "en", ["you", "opening", "hours"][1:]),
        ("I want to know the return window", "en", ["return", "window"]),
        ("ايه مواعيد الشغل عندكم؟", "ar", ["مواعيد", "الشغل"]),
        ("عايز اعرف سياسة الاسترجاع ممكن", "ar", ["سياسة", "الاسترجاع"]),
        ("بدي اعرف شو سعر الشحن", "ar", ["سعر", "الشحن"]),
        ("ممكن تقولي وش مدة الضمان على الجوالات؟", "ar", ["تقولي", "مدة", "الضمان", "الجوالات"]),
        ("ازاي اتابع شحنتي فين رقم التتبع", "ar", ["اتابع", "شحنتي", "رقم", "التتبع"]),
    ],
)
def test_fillers_leave_the_term_count(question: str, language: str, labels: list[str]) -> None:
    assert term_labels(question, language) == labels
    assert len(term_queries(question, language)) == len(labels)


def test_fillers_stay_in_the_ranking_query() -> None:
    assert "please" in (build_tsquery("please tell me the opening hours", "en") or "")
    ranking = build_tsquery("عايز اعرف سياسة الاسترجاع", "ar") or ""
    assert "عايز" in ranking and "اعرف" in ranking and "سياسة" in ranking


def test_a_filler_only_question_has_no_countable_terms() -> None:
    assert term_labels("please, hi", "en") == []
    assert term_labels("ممكن؟", "ar") == []


def test_configured_ignore_terms_still_apply_on_top_of_the_fillers() -> None:
    ignore = normalise_ignore_terms(["NileCart", "نايل", "كارت"])
    assert term_labels("Please tell me about NileCart shipping", "en", ignore) == ["shipping"]
    assert term_labels("ممكن اعرف مين المدير بتاع نايل كارت", "ar", ignore) == [
        "مين",
        "المدير",
        "بتاع",
    ]


def test_zero_countable_terms_cannot_pass_on_keywords() -> None:
    cfg = settings()
    one_left = RetrievalResult(
        "en", "en", False, evidence=[make_chunk(fts_match=0.2, matched_terms=1, query_terms=1)]
    )
    # one real term left after the fillers: the rule asks for min(2, 1) = 1 match
    assert relevance_gate(one_left, cfg).verdicts[0].required_terms == 1
    none_left = RetrievalResult(
        "en", "en", False, evidence=[make_chunk(fts_match=0.2, matched_terms=0, query_terms=0)]
    )
    assert relevance_gate(none_left, cfg).passed == []


def test_rejected_verdicts_name_the_failed_rules() -> None:
    cfg = settings()
    chunk = make_chunk(vector_similarity=0.31, fts_match=0.0, matched_terms=0, query_terms=3)
    result = RetrievalResult("en", "en", False, evidence=[chunk], embedding_model=MODEL)
    assert relevance_gate(result, cfg).verdicts[0].failed_rules == ("cosine", "terms", "fts")
    ok = RetrievalResult(
        "en", "en", False, evidence=[make_chunk(vector_similarity=0.9)], embedding_model=MODEL
    )
    assert relevance_gate(ok, cfg).verdicts[0].failed_rules == ()
    unknown_model = RetrievalResult("en", "en", False, evidence=[chunk])
    assert "cosine_disabled" in relevance_gate(unknown_model, cfg).verdicts[0].failed_rules


def test_refusal_diagnosis_reports_nearest_candidate_and_shortfalls() -> None:
    cfg = settings()
    near = make_chunk(
        vector_similarity=0.44, fts_match=0.3, matched_terms=1, query_terms=3, rrf_score=0.03
    )
    far = make_chunk(vector_similarity=0.10, fts_match=0.0, matched_terms=0, query_terms=3)
    result = RetrievalResult("en", "en", False, evidence=[far, near], embedding_model=MODEL)
    decision = relevance_gate(result, cfg)
    assert decision.passed == []
    diagnosis = refusal_diagnosis(result, decision)
    assert diagnosis["outcome"] == "gate_rejected_all" and diagnosis["candidates"] == 2
    nearest = diagnosis["nearest"]
    assert nearest["chunk_id"] == str(near.chunk_id)
    assert diagnosis["failed_rules"] == ["cosine", "terms"]
    assert nearest["shortfall"] == {"cosine": 0.06, "terms": 1, "fts": 0.0}
    assert diagnosis["best"] == {"cosine": 0.44, "fts_match": 0.3, "matched_terms": 1}
    assert diagnosis["rule_counts"]["cosine"] == 2 and diagnosis["rule_counts"]["fts"] == 1
    assert "text" not in nearest
    assert candidate_trace(result, decision, [])[0]["gate"]["failed_rules"]


def test_refusal_diagnosis_without_candidates() -> None:
    result = RetrievalResult("en", "en", False, evidence=[])
    diagnosis = refusal_diagnosis(result, relevance_gate(result, settings()))
    assert diagnosis["outcome"] == "no_candidates" and diagnosis["nearest"] is None


def _candidate(page: list[Any] | None, cosine: float, fts: float, matched: int) -> dict[str, Any]:
    return {
        "page": page,
        "cosine": cosine,
        "fts_match": fts,
        "matched_terms": matched,
        "query_terms": 3,
    }


def test_page_sweep_counts_leaks_and_wrong_refusals_without_applying_anything() -> None:
    page = ["01-shipping-en_1", 1]
    records: list[dict[str, Any]] = [
        {
            "behavior": "grounded",
            "language": "en",
            "expected": [page],
            "candidates": [_candidate(page, 0.55, 0.2, 2)],
        },
        {
            "behavior": "grounded",
            "language": "ar",
            "expected": [page],
            "candidates": [_candidate(page, 0.35, 0.2, 1)],
        },
        {
            "behavior": "abstain",
            "language": "en",
            "expected": [],
            "candidates": [_candidate(None, 0.42, 0.0, 0)],
        },
    ]
    sweep = page_sweep(records, cosines=(None, 0.5, 0.3), fts_floors=(0.01,), min_terms=(1, 2))
    by_key = {(r["cosine_floor"], r["min_matched_terms"]): r for r in sweep["rows"]}
    assert by_key[(0.5, 2)]["wrong_refusals"] == 1  # the Arabic case is refused
    assert by_key[(0.5, 2)]["wrong_refusals_by_language"] == {"ar": 1}
    assert by_key[(0.3, 2)]["wrong_refusals"] == 0
    assert by_key[(0.3, 2)]["unanswerable_leaks"] == 1  # cosine 0.42 >= 0.3 leaks
    assert by_key[(None, 1)]["wrong_refusals"] == 0  # keyword path, 1 required term
    assert sweep["automatically_applied"] is False
    assert sweep["ranked"][0]["unanswerable_leaks"] == 0


def test_threshold_sweep_script_prints_a_table_and_applies_nothing(
    tmp_path: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    import json

    from scripts import rag_threshold_sweep

    page = ["01-shipping-en_1", 1]
    records = [
        {
            "behavior": "grounded",
            "language": "en",
            "expected": [page],
            "candidates": [_candidate(page, 0.55, 0.2, 2)],
        },
        {
            "behavior": "abstain",
            "language": "en",
            "expected": [],
            "candidates": [_candidate(None, 0.42, 0.0, 0)],
        },
    ]
    path = tmp_path / "recall.json"
    path.write_text(
        json.dumps(
            {"embedder_note": "test embedder", "modes": {"hybrid": {"sweep_records": records}}}
        ),
        encoding="utf-8",
    )
    assert rag_threshold_sweep.main([str(path), "--top", "3", "--cosines", "none,0.5"]) == 0
    out = capsys.readouterr().out
    assert "test embedder" in out and "hybrid: 1 answerable, 1 unanswerable" in out
    assert "<- current default" in out and "nothing applied" in out
    assert rag_threshold_sweep.main([str(path), "--mode", "nope"]) == 2
