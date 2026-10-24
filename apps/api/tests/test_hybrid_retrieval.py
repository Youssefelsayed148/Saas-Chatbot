"""Actual pgvector isolation/underfill checks; vectors are synthetic, not semantic."""

import json
from dataclasses import replace
from pathlib import Path
from threading import Event, get_ident
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

import tests.retrieval_helpers as helpers
from app.db.models import Bot, Chunk, Job
from app.embeddings.providers import EmbeddingBatch, EmbeddingError
from app.retrieval import hybrid
from app.retrieval.service import RetrievedChunk, retrieve

corpus = helpers.corpus
VECTOR = [1.0] + [0.0] * 1023


@pytest.fixture(autouse=True)
def enable_test_logging(db: Session, monkeypatch: Any) -> None:
    # Alembic's fileConfig disables modules imported before session migrations.
    monkeypatch.setattr(hybrid.logger, "disabled", False)


def ready(db: Session, corpus: dict[str, Any]) -> Bot:
    bot = db.scalar(
        select(Bot).where(
            Bot.tenant_id == corpus["users_a"].tenant_id,
            Bot.id == UUID(corpus["bot_main"]),
        )
    )
    assert bot is not None
    bot.embedding_ready = True
    bot.active_embedding_model = "ollama:bge-m3"
    db.commit()
    return bot


def run(db: Session, corpus: dict[str, Any], **kwargs: Any) -> Any:
    return hybrid.retrieve_hybrid(
        db,
        tenant_id=corpus["users_a"].tenant_id,
        bot_id=UUID(corpus["bot_main"]),
        revision_id=UUID(
            helpers.published_revision_id(db, corpus["users_a"].tenant_id, corpus["bot_main"])
        ),
        question="opening hours",
        question_language="en",
        settings=corpus["settings"],
        **kwargs,
    )


def test_filtered_vector_isolation_full_k_and_explain(
    db: Session, corpus: dict[str, Any], tmp_path: Path, caplog: Any
) -> None:
    bot = ready(db, corpus)
    assert bot.published_revision_id is not None
    # Near-identical text and identical vectors across both tenants and bots.
    # The tiny target has only three eligible published chunks, the decoy 300+.
    chunks = list(db.scalars(select(Chunk)))
    for chunk in chunks:
        chunk.embedding = VECTOR
        chunk.embedding_model = "ollama:bge-m3"
        chunk.embedding_dim = 1024
    decoy = next(chunk for chunk in chunks if str(chunk.bot_id) == corpus["bot_b"])
    for ordinal in range(300):
        db.add(
            Chunk(
                tenant_id=decoy.tenant_id,
                bot_id=decoy.bot_id,
                revision_id=decoy.revision_id,
                source_id=decoy.source_id,
                document_id=decoy.document_id,
                title=decoy.title,
                text=decoy.text,
                text_norm=decoy.text_norm,
                language=decoy.language,
                content_hash=f"synthetic-{ordinal}",
                ordinal=ordinal + 1,
                embedding=VECTOR,
                embedding_model="ollama:bge-m3",
                embedding_dim=1024,
            )
        )
    db.commit()
    settings = helpers.retrieval_settings(retrieval_hnsw_max_scan_tuples=1)
    expected = {
        chunk.id
        for chunk in chunks
        if chunk.tenant_id == bot.tenant_id
        and chunk.bot_id == bot.id
        and chunk.revision_id == bot.published_revision_id
    }
    assert len(expected) == 3
    # Force the HNSW path even on this intentionally small test fixture.
    db.execute(text("SET LOCAL enable_seqscan=off"))
    db.execute(text("SET LOCAL enable_sort=off"))
    with caplog.at_level("INFO"):
        result = hybrid.vector_search(
            db,
            tenant_id=bot.tenant_id,
            bot_id=bot.id,
            revision_id=bot.published_revision_id,
            model="ollama:bge-m3",
            vector=VECTOR,
            k=8,
            settings=settings,
        )
    # Immediate-stop contract: any foreign hit here is a blocking isolation failure.
    assert {chunk.chunk_id for chunk in result} == expected
    assert all(chunk.vector_similarity == pytest.approx(1.0) for chunk in result)
    assert "rag.vector_exact_fallback" in caplog.text
    parameters = {
        "tenant_id": str(bot.tenant_id),
        "bot_id": str(bot.id),
        "revision_id": str(bot.published_revision_id),
        "model": "ollama:bge-m3",
        "vector": json.dumps(VECTOR),
        "k": 8,
    }
    plans = {}
    for name, query in (("ann", hybrid.VECTOR_SQL), ("repair", hybrid.EXACT_VECTOR_SQL)):
        plans[name] = db.execute(
            text("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + query), parameters
        ).scalar_one()
    plan_text = json.dumps(plans, indent=2)
    (tmp_path / "filtered-vector-explain.json").write_text(plan_text)
    assert "ix_chunks_embedding_hnsw" in plan_text
    assert "tenant_id" in plan_text and "bot_id" in plan_text
    wrong_model = hybrid.vector_search(
        db,
        tenant_id=bot.tenant_id,
        bot_id=bot.id,
        revision_id=bot.published_revision_id,
        model="ollama:other-model",
        vector=VECTOR,
        k=8,
        settings=settings,
    )
    assert wrong_model == []


def test_rrf_retains_both_scores_without_using_raw_scores_for_rank() -> None:
    item = RetrievedChunk(uuid4(), uuid4(), "Hours", None, "Open", "en", 0, 0, None, "1", 4, 0)
    other = replace(item, chunk_id=uuid4(), fts_match=99)
    fused = hybrid.fuse(
        [replace(item, fts_match=0.1), other],
        [replace(item, vector_similarity=0.8)],
        8,
        60,
    )
    assert fused[0].chunk_id == item.chunk_id
    assert fused[0].rrf_score == pytest.approx(2 / 61)
    assert fused[0].fts_match == 0.1 and fused[0].vector_similarity == 0.8
    assert fused[0].document_id == item.document_id and fused[0].page_ref == "1"


def test_rrf_tie_is_decided_by_cosine_then_fts_rank_then_ordinal_deterministically() -> None:
    low, high = UUID(int=1), UUID(int=2)  # the old tie-break (chunk id) would pick `low`
    base = RetrievedChunk(uuid4(), uuid4(), "T", None, "x", "en", 0, 0, None, "1", 4, 0)
    by_fts = replace(base, chunk_id=low, rank=0.9)
    by_vector = replace(base, chunk_id=high, vector_similarity=0.7)
    for _ in range(5):
        fused = hybrid.fuse([by_fts], [by_vector], 8, 60)
        assert fused[0].rrf_score == fused[1].rrf_score
        assert [c.chunk_id for c in fused] == [high, low]  # cosine beats the missing score
    # Same fused score and cosine: FTS rank decides first, then ordinal, then chunk id.
    first = replace(base, chunk_id=high, ordinal=0, vector_similarity=0.6)
    second = replace(base, chunk_id=low, ordinal=1, vector_similarity=0.6)
    both = hybrid.fuse([first], [second], 8, 60)
    assert [c.chunk_id for c in both] == [high, low]  # ordinal 0 before ordinal 1
    same = hybrid.fuse([replace(first, ordinal=0)], [replace(second, ordinal=0)], 8, 60)
    assert [c.chunk_id for c in same] == [low, high]  # chunk id is the last resort


@pytest.mark.parametrize("reason", ["forced", "backfill", "failure"])
def test_degradation_is_logged_and_does_not_call_unneeded_provider(
    db: Session, corpus: dict[str, Any], monkeypatch: Any, caplog: Any, reason: str
) -> None:
    bot = ready(db, corpus)
    calls = []

    def factory(*args: Any) -> Any:
        calls.append(True)
        raise EmbeddingError("safe synthetic failure")

    monkeypatch.setattr(hybrid, "from_settings", factory)
    if reason == "backfill":
        db.add(Job(tenant_id=bot.tenant_id, bot_id=bot.id, type="reembed_backfill"))
        db.commit()
    with caplog.at_level("INFO"):
        result = run(db, corpus, mode_override="fts_only" if reason == "forced" else None)
    assert result.mode == "fts_only" and result.evidence
    assert result.degradation_reason is not None
    assert result.degradation_reason in caplog.text
    assert len(calls) == (1 if reason == "failure" else 0)


def test_fts_and_embedding_run_in_parallel_on_separate_sessions(
    db: Session, corpus: dict[str, Any], monkeypatch: Any
) -> None:
    ready(db, corpus)
    fts_started, embed_started = Event(), Event()
    original = retrieve
    original_vector = hybrid.vector_search
    caller_thread = get_ident()

    class Fake:
        def embed(self, texts: list[str]) -> EmbeddingBatch:
            assert get_ident() != caller_thread
            embed_started.set()
            assert fts_started.wait(3), "FTS must run while embedding is waiting"
            return EmbeddingBatch([VECTOR])

    def keyword(*args: Any, **kwargs: Any) -> Any:
        assert get_ident() == caller_thread and args[0] is db
        fts_started.set()
        assert embed_started.wait(3)
        return original(*args, **kwargs)

    def vector(vector_db: Session, **kwargs: Any) -> Any:
        assert vector_db is not db and get_ident() != caller_thread
        return original_vector(vector_db, **kwargs)

    monkeypatch.setattr(hybrid, "from_settings", lambda *args: Fake())
    monkeypatch.setattr(hybrid, "retrieve", keyword)
    monkeypatch.setattr(hybrid, "vector_search", vector)
    result = run(db, corpus)
    assert result.mode == "hybrid" and result.evidence


def test_hybrid_keeps_always_include_and_whole_document_rules(
    db: Session, corpus: dict[str, Any], monkeypatch: Any
) -> None:
    ready(db, corpus)
    revision = helpers.published_revision_id(db, corpus["users_a"].tenant_id, corpus["bot_main"])
    reserved_id = db.execute(
        text(
            "SELECT id FROM documents WHERE revision_id = CAST(:r AS uuid) "
            "AND title = 'Return policy'"
        ),
        {"r": revision},
    ).scalar_one()
    reserved_chunks = set(
        db.execute(
            text("SELECT id FROM chunks WHERE document_id = :d"), {"d": reserved_id}
        ).scalars()
    )
    assert reserved_chunks

    class Fake:
        def embed(self, texts: list[str]) -> EmbeddingBatch:
            return EmbeddingBatch([VECTOR])

    monkeypatch.setattr(hybrid, "from_settings", lambda *args: Fake())
    reserved = {str(reserved_id)}
    keyword = run(db, corpus, mode_override="fts_only", always_include_document_ids=reserved)
    fused = run(db, corpus, always_include_document_ids=reserved)
    assert keyword.mode == "fts_only" and fused.mode == "hybrid"
    for result in (keyword, fused):
        evidence_ids = {chunk.chunk_id for chunk in result.evidence}
        assert reserved_chunks <= evidence_ids, result.mode  # reserved, whole document
        best = result.evidence[len(reserved_chunks)]  # first non-reserved evidence chunk
        best_doc = {
            row
            for row in db.execute(
                text("SELECT id FROM chunks WHERE document_id = :d"), {"d": best.document_id}
            ).scalars()
        }
        assert best_doc <= evidence_ids, result.mode  # best document whole
    assert keyword.evidence[: len(reserved_chunks)] == [
        c for c in keyword.evidence if c.chunk_id in reserved_chunks
    ]
    # Same rules, same reserved slots first, in both modes.
    assert [c.chunk_id for c in fused.evidence[: len(reserved_chunks)]] == [
        c.chunk_id for c in keyword.evidence[: len(reserved_chunks)]
    ]


def test_embedding_budget_exhaustion_degrades_to_keyword_search(
    db: Session, corpus: dict[str, Any], monkeypatch: Any
) -> None:
    bot = ready(db, corpus)
    bot.rag_limits = {"monthly_embedding_tokens": 0}
    db.commit()

    class Fake:
        def embed(self, texts: list[str]) -> EmbeddingBatch:
            raise AssertionError("the provider must not be called past the cap")

    monkeypatch.setattr(hybrid, "from_settings", lambda *args: Fake())
    result = run(db, corpus)
    assert result.mode == "fts_only" and result.evidence
    assert result.degradation_reason == "embedding_budget_exhausted"


def test_query_embedding_events_carry_the_real_channel(
    db: Session, corpus: dict[str, Any], monkeypatch: Any
) -> None:
    from app.db.models import UsageEvent

    ready(db, corpus)

    class Fake:
        def embed(self, texts: list[str]) -> EmbeddingBatch:
            return EmbeddingBatch([VECTOR], tokens=3)

    monkeypatch.setattr(hybrid, "from_settings", lambda *args: Fake())
    run(db, corpus, channel="playground")
    db.expire_all()
    channels = {
        row.payload["channel"]
        for row in db.scalars(
            select(UsageEvent).where(
                UsageEvent.tenant_id == corpus["users_a"].tenant_id,
                UsageEvent.kind == "ai_usage",
            )
        )
        if row.payload["event_type"] == "embed_query"
    }
    assert channels == {"playground"}
