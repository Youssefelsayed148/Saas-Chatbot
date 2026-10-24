"""B.3 / B.5: gate explanation, trace rows and no behaviour change at defaults."""

import itertools
import math
from dataclasses import replace
from typing import Any
from uuid import uuid4

from app.core.config import Settings
from app.retrieval.gate import relevance_gate
from app.retrieval.query import normalise_ignore_terms, term_labels, term_queries
from app.retrieval.service import RetrievalResult, RetrievedChunk
from app.retrieval.trace import candidate_trace


def make_chunk(**kwargs: Any) -> RetrievedChunk:
    base = RetrievedChunk(uuid4(), uuid4(), "Doc", None, "text", "en", 0, 0, None, "2", 4, 0)
    return replace(base, **kwargs)


def settings(**overrides: Any) -> Settings:
    return Settings.model_construct(**{"environment": "test", "database_url": None, **overrides})


def legacy_gate(result: RetrievalResult, cfg: Settings) -> tuple[list[Any], list[str]]:
    """The gate exactly as it was before B.3/B.5 (reference implementation)."""
    floor = cfg.retrieval_vector_floors.get(result.embedding_model or "")
    if floor is not None and (not math.isfinite(floor) or not -1 <= floor <= 1):
        floor = None
    keyword_gate = cfg.retrieval_keyword_gates.get(result.embedding_model or "")
    min_fts = keyword_gate.min_fts_match if keyword_gate else cfg.retrieval_min_fts_match
    min_terms = keyword_gate.min_matched_terms if keyword_gate else cfg.retrieval_min_matched_terms
    passed, rejected = [], []
    for chunk in result.evidence:
        vector_ok = (
            floor is not None
            and chunk.vector_similarity is not None
            and math.isfinite(chunk.vector_similarity)
            and chunk.vector_similarity >= floor
        )
        required = min(min_terms, chunk.query_terms) if chunk.query_terms else min_terms
        keyword_ok = chunk.matched_terms >= max(1, required) and (
            math.isfinite(chunk.fts_match) and chunk.fts_match > 0 and chunk.fts_match >= min_fts
        )
        if vector_ok or keyword_ok:
            passed.append(chunk)
        else:
            rejected.append(str(chunk.chunk_id))
    return passed, rejected


def test_defaults_are_unchanged() -> None:
    cfg = settings()
    assert cfg.retrieval_min_matched_terms == 2
    assert cfg.retrieval_min_fts_match == 0.01
    assert cfg.retrieval_vector_floors == {
        "openai:text-embedding-3-large": 0.50,
        "ollama:bge-m3": 0.50,
    }
    assert cfg.retrieval_gate_ignore_terms == []
    assert cfg.retrieval_top_result_cosine_floor is None
    assert cfg.retrieval_top_result_margin == 0.0


def test_gate_matches_legacy_over_a_grid_at_defaults() -> None:
    sims = [None, -0.2, 0.0, 0.3, 0.49, 0.5, 0.51, 0.9, float("nan")]
    fts = [0.0, 0.005, 0.01, 0.2, float("nan")]
    matched = [0, 1, 2, 3]
    query_terms = [0, 1, 2, 4]
    chunks = [
        make_chunk(
            vector_similarity=s, fts_match=f, matched_terms=m, query_terms=q, rrf_score=7.0 * m
        )
        for s, f, m, q in itertools.product(sims, fts, matched, query_terms)
    ]
    cfg = settings()
    for model in ("openai:text-embedding-3-large", "ollama:bge-m3", "unknown:model", None):
        result = RetrievalResult("en", "en", False, evidence=chunks, embedding_model=model)
        decision = relevance_gate(result, cfg)
        legacy_passed, legacy_rejected = legacy_gate(result, cfg)
        # Every chunk is its own document here; only the order is now by relevance.
        assert {c.chunk_id for c in decision.passed} == {c.chunk_id for c in legacy_passed}
        assert len(decision.passed) == len(legacy_passed)
        assert decision.rejected_ids == legacy_rejected
        assert len(decision.verdicts) == len(chunks)
        assert [v.accepted for v in decision.verdicts] == [
            chunk in legacy_passed for chunk in chunks
        ]


def test_verdict_names_the_rule_that_decided() -> None:
    by_cosine = make_chunk(vector_similarity=0.62, fts_match=0.0, matched_terms=0, query_terms=3)
    by_keyword = make_chunk(vector_similarity=0.2, fts_match=0.3, matched_terms=2, query_terms=3)
    one_term = make_chunk(vector_similarity=0.2, fts_match=0.3, matched_terms=1, query_terms=3)
    result = RetrievalResult(
        "en",
        "en",
        False,
        evidence=[by_cosine, by_keyword, one_term],
        embedding_model="openai:text-embedding-3-large",
    )
    decision = relevance_gate(result, settings())
    first, second, third = decision.verdicts
    assert (first.accepted_by, second.accepted_by, third.accepted_by) == ("cosine", "keyword", None)
    assert "cosine 0.620 >= floor 0.50" in first.reason
    assert "matched terms 2 >= 2" in second.reason
    assert third.reason.startswith("rejected:")
    assert "cosine 0.200 < floor 0.50" in third.reason
    assert "matched terms 1 < required 2" in third.reason
    assert third.terms_pass is False and third.fts_pass is True and third.cosine_pass is False


def test_uncalibrated_model_reports_disabled_cosine() -> None:
    result = RetrievalResult(
        "en",
        "en",
        False,
        evidence=[
            make_chunk(vector_similarity=0.99, fts_match=0.0, matched_terms=0, query_terms=2)
        ],
        embedding_model="other:model",
    )
    verdict = relevance_gate(result, settings()).verdicts[0]
    assert verdict.cosine_pass is None
    assert "cosine floor disabled" in verdict.reason


def test_top_result_rule_is_off_by_default_and_gated_by_margin() -> None:
    top = make_chunk(vector_similarity=0.42, fts_match=0.0, matched_terms=0, query_terms=3)
    other = make_chunk(vector_similarity=0.30, fts_match=0.0, matched_terms=0, query_terms=3)
    result = RetrievalResult(
        "en", "en", False, evidence=[other, top], embedding_model="ollama:bge-m3"
    )
    assert relevance_gate(result, settings()).passed == []
    on = settings(retrieval_top_result_cosine_floor=0.40, retrieval_top_result_margin=0.10)
    decision = relevance_gate(result, on)
    assert decision.passed == [top]
    assert decision.verdicts[1].accepted_by == "top_result"
    narrow = settings(retrieval_top_result_cosine_floor=0.40, retrieval_top_result_margin=0.20)
    assert relevance_gate(result, narrow).passed == []
    below = settings(retrieval_top_result_cosine_floor=0.45, retrieval_top_result_margin=0.0)
    assert relevance_gate(result, below).passed == []


def test_ignore_terms_drop_store_names_from_the_term_count_only() -> None:
    question = "Does NileCart sell laptops?"
    assert term_queries(question, "en") == ["nilecart", "sell", "laptops"]
    ignore = normalise_ignore_terms(["NileCart", "sell"])
    assert term_queries(question, "en", ignore) == ["laptops"]
    assert term_labels(question, "en", ignore) == ["laptops"]
    arabic = normalise_ignore_terms(["نايل", "كارت"])
    assert term_labels("هل تبيع نايل كارت لابتوب؟", "ar", arabic) == ["تبيع", "لابتوب"]
    assert term_labels("هل تبيع النايل لابتوب؟", "ar", arabic) == ["تبيع", "لابتوب"]


def test_candidate_trace_rows_carry_terms_and_gate_rule() -> None:
    chunk = make_chunk(
        vector_similarity=0.31,
        fts_match=0.2,
        matched_terms=1,
        query_terms=3,
        rrf_score=0.03,
        query_term_labels=["card", "refund", "days"],
        matched_term_labels=["refund"],
    )
    result = RetrievalResult(
        "en", "en", False, evidence=[chunk], embedding_model="openai:text-embedding-3-large"
    )
    decision = relevance_gate(result, settings())
    rows = candidate_trace(result, decision, decision.passed)
    row = rows[0]
    assert row["query_terms"] == ["card", "refund", "days"]
    assert row["matched_terms"] == ["refund"]
    assert row["locator"] == "2" and row["accepted"] is False
    assert row["gate"]["passed"] is False
    assert row["gate"]["terms"] == {"matched": 1, "required": 2, "passed": False}
    assert row["gate"]["cosine"] == {"value": 0.31, "floor": 0.5, "passed": False}
    assert row["gate"]["fts"]["passed"] is True
    # the pre-existing trace keys stay in place
    for key in ("chunk_id", "document_id", "title", "vector_similarity", "fts_match", "rrf_score"):
        assert key in row
