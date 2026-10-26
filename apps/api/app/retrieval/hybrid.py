"""Tenant/bot/model-scoped parallel FTS + vector retrieval with rank fusion.

The caller's session is used only on its own thread. Vector work uses an
independent session. Filtered ANN underfill is repaired with an exact search
over a materialized, already-filtered relation, never Python post-filtering.
"""

import json
import logging
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from uuid import UUID

from sqlalchemy import Engine, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session as OrmSession

from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.db.models import Bot, KnowledgeRevision
from app.embeddings.providers import EmbeddingBatch, EmbeddingError, from_settings, validate_vector
from app.quotas.ai import metered_embed
from app.retrieval.service import (
    RetrievalResult,
    RetrievedChunk,
    TranslateQuery,
    assemble_evidence,
    retrieve,
    score_lexical,
)

logger = logging.getLogger(__name__)

# Query-embedding circuit breaker (#84): after this many failures (errors or
# timeouts) inside the window, the vector leg is skipped for one window.
# In-process, keyed by embedding identity; a success clears the count.
EMBED_BREAKER_FAILURES = 3
EMBED_BREAKER_WINDOW_SECONDS = 60.0
_clock = time.monotonic
_breaker_lock = threading.Lock()
_embed_failures: dict[str, list[float]] = {}
_embed_suspended_until: dict[str, float] = {}


def reset_embed_breaker() -> None:
    with _breaker_lock:
        _embed_failures.clear()
        _embed_suspended_until.clear()


def _vector_leg_suspended(identity: str) -> bool:
    with _breaker_lock:
        return _embed_suspended_until.get(identity, 0.0) > _clock()


def _record_embed_failure(identity: str) -> None:
    now = _clock()
    with _breaker_lock:
        recent = [
            at
            for at in _embed_failures.get(identity, [])
            if now - at < EMBED_BREAKER_WINDOW_SECONDS
        ]
        recent.append(now)
        if len(recent) >= EMBED_BREAKER_FAILURES:
            _embed_suspended_until[identity] = now + EMBED_BREAKER_WINDOW_SECONDS
            recent = []
        _embed_failures[identity] = recent


def _record_embed_success(identity: str) -> None:
    with _breaker_lock:
        _embed_failures.pop(identity, None)


VECTOR_COLUMNS = """
    c.id AS chunk_id, c.document_id, c.title, c.heading, c.text AS chunk_text,
    c.language, c.priority, c.ordinal, d.source_url, d.page_ref,
    d.total_chars AS document_total_chars, c.embedding
"""
VECTOR_SCOPE = """
    FROM chunks c JOIN documents d ON d.id=c.document_id
      AND d.tenant_id=c.tenant_id AND d.bot_id=c.bot_id
    WHERE c.tenant_id=CAST(:tenant_id AS uuid) AND c.bot_id=CAST(:bot_id AS uuid)
      AND c.revision_id=CAST(:revision_id AS uuid)
      AND c.embedding_model=:model AND c.embedding_dim=1024 AND c.embedding IS NOT NULL
"""
VECTOR_SQL = f"""
    SELECT {VECTOR_COLUMNS},
        1 - (c.embedding <=> CAST(:vector AS vector(1024))) AS similarity
    {VECTOR_SCOPE}
    ORDER BY c.embedding <=> CAST(:vector AS vector(1024)) LIMIT :k
"""
EXACT_VECTOR_SQL = f"""
    WITH eligible AS MATERIALIZED (SELECT {VECTOR_COLUMNS} {VECTOR_SCOPE})
    SELECT eligible.*, 1 - (embedding <=> CAST(:vector AS vector(1024))) AS similarity
    FROM eligible ORDER BY embedding <=> CAST(:vector AS vector(1024)) LIMIT :k
"""


def vector_search(
    db: OrmSession,
    *,
    tenant_id: UUID,
    bot_id: UUID,
    revision_id: UUID,
    model: str,
    vector: list[float],
    k: int,
    settings: Settings,
) -> list[RetrievedChunk]:
    parameters = {
        "tenant_id": str(tenant_id),
        "bot_id": str(bot_id),
        "revision_id": str(revision_id),
        "model": model,
        "vector": json.dumps(validate_vector(vector)),
        "k": k,
    }
    db.execute(text("SELECT set_config('hnsw.iterative_scan','strict_order',true)"))
    db.execute(
        text("SELECT set_config('hnsw.max_scan_tuples',:limit,true)"),
        {"limit": str(settings.retrieval_hnsw_max_scan_tuples)},
    )
    rows = db.execute(text(VECTOR_SQL), parameters).mappings().all()
    if len(rows) < k:
        # Iterative scans have a bounded scan budget. Repair underfill exactly,
        # including highly selective tiny tenants, using the same SQL filters.
        rows = db.execute(text(EXACT_VECTOR_SQL), parameters).mappings().all()
        logger.info("rag.vector_exact_fallback tenant=%s bot=%s", tenant_id, bot_id)
    return [
        RetrievedChunk(
            chunk_id=row["chunk_id"],
            document_id=row["document_id"],
            title=row["title"],
            heading=row["heading"],
            text=row["chunk_text"],
            language=row["language"],
            priority=row["priority"],
            ordinal=row["ordinal"],
            source_url=row["source_url"],
            page_ref=row["page_ref"],
            document_total_chars=row["document_total_chars"],
            rank=0.0,
            vector_similarity=max(-1.0, min(1.0, float(row["similarity"]))),
        )
        for row in rows
    ]


def fuse(
    fts: list[RetrievedChunk], vectors: list[RetrievedChunk], k: int, constant: int
) -> list[RetrievedChunk]:
    by_id: dict[UUID, RetrievedChunk] = {}
    for ranking, is_vector in ((fts, False), (vectors, True)):
        for position, chunk in enumerate(ranking, 1):
            item = by_id.setdefault(chunk.chunk_id, replace(chunk, rrf_score=0.0))
            item.rrf_score += 1 / (constant + position)
            if is_vector:
                item.vector_similarity = chunk.vector_similarity
            else:
                item.fts_match = chunk.fts_match
    # Equal fused scores are common (rank 1 in one list vs rank 1 in the other):
    # decide by the stronger signals, then by what the content is called (document
    # title, page, ordinal), so a re-seeded corpus ranks the same. The chunk id
    # only separates chunks that are identical in all of those.
    return sorted(by_id.values(), key=_fusion_order)[:k]


def _fusion_order(
    chunk: RetrievedChunk,
) -> tuple[float, float, float, str, str, int, str]:
    sim = chunk.vector_similarity
    cosine = sim if sim is not None and math.isfinite(sim) else -2.0
    return (
        -chunk.rrf_score,
        -cosine,
        -chunk.rank,
        chunk.title,
        chunk.page_ref,
        chunk.ordinal,
        str(chunk.chunk_id),
    )


def _revision_embedding_model(
    db: OrmSession, tenant_id: UUID, bot_id: UUID, revision_id: UUID
) -> str | None:
    """The identity every chunk of this revision carries, or None (keyword-only)."""
    return db.scalar(
        select(KnowledgeRevision.embedding_model)
        .where(
            KnowledgeRevision.tenant_id == tenant_id,
            KnowledgeRevision.bot_id == bot_id,
            KnowledgeRevision.id == revision_id,
        )
        .execution_options(populate_existing=True)
    )


def _is_draft_revision(db: OrmSession, tenant_id: UUID, bot_id: UUID, revision_id: UUID) -> bool:
    return (
        db.scalar(
            select(KnowledgeRevision.id).where(
                KnowledgeRevision.tenant_id == tenant_id,
                KnowledgeRevision.bot_id == bot_id,
                KnowledgeRevision.id == revision_id,
                KnowledgeRevision.status == "draft",
            )
        )
        is not None
    )


def retrieve_hybrid(
    db: OrmSession,
    *,
    tenant_id: UUID,
    bot_id: UUID,
    revision_id: UUID,
    question: str,
    question_language: str,
    bot_primary_language: str = "en",
    settings: Settings | None = None,
    always_include_document_ids: set[str] | None = None,
    translate_query: TranslateQuery | None = None,
    mode_override: str | None = None,
    channel: str = "website",
    embed_timeout: float | None = None,
    preview: bool = False,
) -> RetrievalResult:
    """``preview=True`` (staff playground) reads an explicit DRAFT revision of this
    tenant + bot instead of the published pointer. Anything that is not such a
    draft returns an empty result, so a preview id can never expose another
    bot's, tenant's or the live revision through this switch."""
    settings = settings or get_settings()
    bot = db.scalar(
        select(Bot)
        .where(
            Bot.tenant_id == tenant_id,
            Bot.id == bot_id,
            *(() if preview else (Bot.published_revision_id == revision_id,)),
            Bot.status != "archived",
        )
        .execution_options(populate_existing=True)
    )
    if bot is None:
        return RetrievalResult(question_language, question_language, False)
    if preview and not _is_draft_revision(db, tenant_id, bot_id, revision_id):
        return RetrievalResult(question_language, question_language, False)

    def keyword() -> RetrievalResult:
        return retrieve(
            db,
            tenant_id=tenant_id,
            bot_id=bot_id,
            revision_id=revision_id,
            question=question,
            question_language=question_language,
            bot_primary_language=bot_primary_language,
            settings=settings,
            always_include_document_ids=always_include_document_ids,
            translate_query=translate_query,
        )

    reason = None
    identity: str | None = None
    if (mode_override or bot.retrieval_mode) == "fts_only":
        reason = "operator_fts_only"
    else:
        # Only the PUBLISHED revision's completeness matters; draft backfill
        # progress and ingest never degrade the live bot.
        identity = _revision_embedding_model(db, tenant_id, bot_id, revision_id)
        if not identity:
            reason = "embedding_index_unavailable"
    if reason:
        result = keyword()
        result.degradation_reason = reason
        logger.info("rag.fts_only reason=%s tenant=%s bot=%s", reason, tenant_id, bot_id)
        return result

    assert identity is not None
    if _vector_leg_suspended(identity):
        result = keyword()
        result.degradation_reason = "embedding_suspended_after_failures"
        logger.warning(
            "rag.fts_only reason=embedding_suspended tenant=%s bot=%s", tenant_id, bot_id
        )
        return result
    bind = db.get_bind()
    engine = bind if isinstance(bind, Engine) else bind.engine

    def semantic() -> tuple[list[RetrievedChunk], EmbeddingBatch]:
        with OrmSession(engine) as vector_db:
            batch = metered_embed(
                vector_db,
                tenant_id,
                bot_id,
                settings,
                identity=identity,
                texts=[question],
                embed=from_settings(settings, identity).embed,
                event_type="embed_query",
                channel=channel,
            )
            found = vector_search(
                vector_db,
                tenant_id=tenant_id,
                bot_id=bot_id,
                revision_id=revision_id,
                model=identity,
                vector=batch.vectors[0],
                k=settings.retrieval_top_k,
                settings=settings,
            )
        return found, batch

    # No ``with``: leaving the block must never wait for a stalled embed thread.
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="rag-vector")
    submitted = _clock()
    try:
        future = executor.submit(semantic)
        result = keyword()
        wait = None if embed_timeout is None else max(0.0, embed_timeout - (_clock() - submitted))
        try:
            vectors, batch = future.result(timeout=wait)
        except TimeoutError:
            _record_embed_failure(identity)
            result.degradation_reason = "embedding_timeout"
            logger.warning(
                "rag.fts_only reason=embedding_timeout tenant=%s bot=%s", tenant_id, bot_id
            )
            return result
        except ApiError as error:
            if error.code != "QUOTA_EXCEEDED":
                raise
            result.degradation_reason = "embedding_budget_exhausted"
            logger.warning(
                "rag.fts_only reason=embedding_budget_exhausted tenant=%s bot=%s",
                tenant_id,
                bot_id,
            )
            return result
        except (EmbeddingError, SQLAlchemyError) as error:
            if isinstance(error, EmbeddingError):
                _record_embed_failure(identity)
            result.degradation_reason = "embedding_or_vector_failure"
            logger.warning(
                "rag.fts_only reason=embedding_or_vector_failure tenant=%s bot=%s",
                tenant_id,
                bot_id,
            )
            return result
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
    _record_embed_success(identity)
    # A model-change backfill may rewrite this revision after the first check;
    # never mix the previously captured query identity with a new index.
    bot = db.scalar(
        select(Bot)
        .where(Bot.tenant_id == tenant_id, Bot.id == bot_id)
        .execution_options(populate_existing=True)
    )
    if (
        bot is None
        or (not preview and bot.published_revision_id != revision_id)
        or _revision_embedding_model(db, tenant_id, bot_id, revision_id) != identity
    ):
        result.degradation_reason = "backfill_changed_during_query"
        logger.info(
            "rag.fts_only reason=backfill_changed_during_query tenant=%s bot=%s",
            tenant_id,
            bot_id,
        )
        return result
    ranked = fuse(result.candidates, vectors, settings.retrieval_top_k, settings.retrieval_rrf_k)
    score_lexical(
        db,
        ranked,
        tenant_id=tenant_id,
        bot_id=bot_id,
        revision_id=revision_id,
        question=result.fallback_query or question,
        language=result.applied_language,
        ignore_terms=settings.retrieval_gate_ignore_terms,
    )
    # Same evidence rules as keyword mode (reserved always-include documents,
    # best document whole, small documents whole), applied to the fused ranking.
    by_document: dict[UUID, RetrievedChunk] = {}
    for chunk in ranked:
        by_document.setdefault(chunk.document_id, chunk)
    evidence = assemble_evidence(
        db,
        tenant_id=tenant_id,
        bot_id=bot_id,
        revision_id=revision_id,
        language=result.applied_language,
        ranked=list(by_document.values()),
        settings=settings,
        always_include_document_ids=always_include_document_ids,
    )
    fused = {chunk.chunk_id: chunk for chunk in ranked}
    for chunk in evidence:
        hit = fused.get(chunk.chunk_id)
        if hit is not None:
            chunk.vector_similarity = hit.vector_similarity
            chunk.rrf_score = hit.rrf_score
    score_lexical(
        db,
        [chunk for chunk in evidence if chunk.chunk_id not in fused],
        tenant_id=tenant_id,
        bot_id=bot_id,
        revision_id=revision_id,
        question=result.fallback_query or question,
        language=result.applied_language,
        ignore_terms=settings.retrieval_gate_ignore_terms,
    )
    for chunk in evidence:
        hit = fused.get(chunk.chunk_id)
        if hit is not None:
            chunk.fts_match, chunk.matched_terms = hit.fts_match, hit.matched_terms
            chunk.query_terms = hit.query_terms
            chunk.query_term_labels = hit.query_term_labels
            chunk.matched_term_labels = hit.matched_term_labels
    result.mode = "hybrid"
    result.candidates = ranked
    result.evidence = evidence
    result.embedding_model = identity
    result.embedding_tokens = batch.tokens
    result.embedding_cost_usd = batch.cost_usd
    return result
