"""Retrieval service (docs/14 §1, §2, §5): language-aware keyword search.

One pass = query the GIN-indexed tsvector columns for the question's
language (``fts_en`` for English, ``fts_simple`` for Arabic-normalised
chunks) — always filtered by ``tenant_id``, ``bot_id``,
``revision_id = bots.published_revision_id`` and chunk ``language``.
If the language pass is empty, a second pass runs against the bot's
primary content language (results are still cited in the visitor's
language later — docs/14 §2, ADR-014).

Ranking uses ``ts_rank_cd`` with ``priority DESC`` and ``ordinal`` as
tie-breaks; one best chunk per document is kept per pass, then evidence
is assembled: the best document is included whole, lower-ranked small
documents (total text ≤ 1500 chars) are included **whole only if they
fit** the evidence budget, larger ones contribute their best chunk.
Optional always-include documents occupy reserved slots ahead of the
ranked hits. Defaults: ``top_k=8`` candidates, ``final_k=4`` chunks,
``max_evidence_chunks=8`` (tune only via a dated note in docs/14).
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session as OrmSession

from app.core.config import Settings
from app.retrieval.query import build_tsquery

SUPPORTED_LANGUAGES = ("en", "ar")

# Cross-script hook (P4-00): when the question-language pass is empty and the
# question language differs from the bot's primary language, the caller may
# translate the query into the primary language with ONE ChatModel call
# (docs/14 §2, ADR-014). Returns the translated query, or None to keep the
# raw question (provider failure must degrade cleanly).
TranslateQuery = Callable[[str, str], str | None]


@dataclass
class RetrievedChunk:
    """One evidence item handed to the answer step."""

    chunk_id: UUID
    document_id: UUID
    title: str
    heading: str | None
    text: str
    language: str
    priority: int
    ordinal: int
    source_url: str | None
    page_ref: str
    # Total text length of the document (small-document rule).
    document_total_chars: int
    rank: float


@dataclass
class RetrievalResult:
    query_language: str
    # The language the hits were actually found in (after cross-language fallback).
    applied_language: str
    # Did the pass fall back to the bot's primary content language?
    used_fallback: bool
    # The query actually used by the fallback pass, when it differs from the
    # raw question (cross-script translation, P4-00).
    fallback_query: str | None = None
    candidates: list[RetrievedChunk] = field(default_factory=list)
    evidence: list[RetrievedChunk] = field(default_factory=list)


def _fts_column(language: str) -> str:
    if language == "ar":
        return "fts_simple"
    return "fts_en"


def _tsquery_config(language: str) -> str:
    return "simple" if language == "ar" else "english"


def _best_chunk_per_document(
    db: OrmSession,
    *,
    tenant_id: UUID,
    bot_id: UUID,
    revision_id: UUID,
    language: str,
    tsquery_text: str,
    top_k: int,
) -> list[RetrievedChunk]:
    """One best chunk per document by ``ts_rank_cd`` (priority DESC, then ordinal)."""
    column = _fts_column(language)
    # ``q.query`` is NULL only if the builder produced no terms (both inputs
    # checked before this call, so a valid tsquery string is guaranteed).
    sql = text(
        f"""
        WITH q AS (SELECT to_tsquery(:ts_config, :query) AS query)
        SELECT * FROM (
            SELECT DISTINCT ON (c.document_id)
                c.id AS chunk_id,
                c.document_id,
                c.title,
                c.heading,
                c."text" AS chunk_text,
                c.language,
                c.priority,
                c.ordinal,
                d.source_url,
                d.page_ref,
                d.total_chars AS document_total_chars,
                ts_rank_cd(c.{column}, q.query) AS rank
            FROM chunks c
            CROSS JOIN q
            JOIN documents d ON d.id = c.document_id
            WHERE c.tenant_id = CAST(:tenant_id AS uuid)
              AND c.bot_id = CAST(:bot_id AS uuid)
              AND c.revision_id = CAST(:revision_id AS uuid)
              AND c.language = :language
              AND q.query @@ c.{column}
            ORDER BY c.document_id, rank DESC, c.priority DESC, c.ordinal, c.id
        ) best
        ORDER BY rank DESC, priority DESC, document_id
        LIMIT :top_k
        """
    )
    rows = db.execute(
        sql,
        {
            "ts_config": _tsquery_config(language),
            "query": tsquery_text,
            "tenant_id": str(tenant_id),
            "bot_id": str(bot_id),
            "revision_id": str(revision_id),
            "language": language,
            "top_k": top_k,
        },
    ).mappings()
    chunks: list[RetrievedChunk] = []
    for row in rows:
        chunks.append(
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
                rank=float(row["rank"]),
            )
        )
    return chunks


def _whole_document_chunks(
    db: OrmSession,
    *,
    tenant_id: UUID,
    revision_id: UUID,
    language: str,
    document_id: UUID,
) -> list[RetrievedChunk]:
    """All chunks of one document (retrieved whole), in ordinal order.

    The language filter stays active: a document's chunks in other languages
    are not dropped from the document, but evidence is kept per-pass
    consistent (small-document rule, docs/14 §5).
    """
    rows = db.execute(
        text(
            """
            SELECT
                c.id AS chunk_id,
                c.document_id,
                c.title,
                c.heading,
                c."text" AS chunk_text,
                c.language,
                c.priority,
                c.ordinal,
                d.source_url,
                d.page_ref,
                d.total_chars AS document_total_chars,
                NULL::real AS rank
            FROM chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE c.tenant_id = CAST(:tenant_id AS uuid)
              AND c.revision_id = CAST(:revision_id AS uuid)
              AND c.language = :language
              AND c.document_id = CAST(:document_id AS uuid)
            ORDER BY c.ordinal, c.id
            """
        ),
        {
            "tenant_id": str(tenant_id),
            "revision_id": str(revision_id),
            "language": language,
            "document_id": str(document_id),
        },
    ).mappings()
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
        )
        for row in rows
    ]


def _retrieve_one_pass(
    db: OrmSession,
    *,
    tenant_id: UUID,
    bot_id: UUID,
    revision_id: UUID,
    language: str,
    question: str,
    settings: Settings,
    always_include_document_ids: set[str] | None,
) -> list[RetrievedChunk]:
    """Ranked evidence list for one language pass (expansion + reserved slots)."""
    tsquery_text = build_tsquery(question, language)
    if tsquery_text is None:
        ranked: list[RetrievedChunk] = []
    else:
        ranked = _best_chunk_per_document(
            db,
            tenant_id=tenant_id,
            bot_id=bot_id,
            revision_id=revision_id,
            language=language,
            tsquery_text=tsquery_text,
            top_k=settings.retrieval_top_k,
        )

    evidence: list[RetrievedChunk] = []
    seen_chunk_ids: set[UUID] = set()

    def add(chunks: list[RetrievedChunk]) -> None:
        for chunk in chunks:
            if chunk.chunk_id in seen_chunk_ids:
                continue
            seen_chunk_ids.add(chunk.chunk_id)
            evidence.append(chunk)

    # 1) Reserved slots: always-include documents first (whole documents).
    for value in always_include_document_ids or set():
        document_id = value if isinstance(value, UUID) else UUID(str(value))
        add(
            _whole_document_chunks(
                db,
                tenant_id=tenant_id,
                revision_id=revision_id,
                language=language,
                document_id=document_id,
            )
        )
    while len(evidence) > settings.retrieval_max_evidence_chunks:
        evidence.pop()

    # 2) The best document is included whole; it may exceed the soft budget
    #    (final_k) but never the hard cap (max_evidence_chunks).
    if ranked:
        add(
            _whole_document_chunks(
                db,
                tenant_id=tenant_id,
                revision_id=revision_id,
                language=language,
                document_id=ranked[0].document_id,
            )
        )
        del evidence[settings.retrieval_max_evidence_chunks :]

    # 3) Lower-ranked documents must fit whole (small docs) or contribute
    #    their single best chunk to the remaining soft budget.
    remaining = settings.retrieval_final_k - len(evidence)
    for candidate in ranked[1:]:
        if remaining <= 0:
            break
        if candidate.document_total_chars <= settings.chunk_size:
            whole = _whole_document_chunks(
                db,
                tenant_id=tenant_id,
                revision_id=revision_id,
                language=language,
                document_id=candidate.document_id,
            )
            if len(whole) <= remaining:
                add(whole)
                remaining -= len(whole)
        else:
            remaining -= 1
            add([candidate])
    del evidence[settings.retrieval_max_evidence_chunks :]
    return evidence


def retrieve(
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
) -> RetrievalResult:
    """Top-level retrieval: question-language pass + cross-language fallback.

    When the caller supplies ``translate_query`` (P4-00) and the question
    language differs from the bot's primary language, the fallback pass runs
    on the translated query (one ChatModel call); a failed translation keeps
    the raw question."""
    settings = settings or Settings()
    if question_language not in SUPPORTED_LANGUAGES:
        question_language = "en"

    evidence = _retrieve_one_pass(
        db,
        tenant_id=tenant_id,
        bot_id=bot_id,
        revision_id=revision_id,
        language=question_language,
        question=question,
        settings=settings,
        always_include_document_ids=always_include_document_ids,
    )
    if evidence:
        return RetrievalResult(
            query_language=question_language,
            applied_language=question_language,
            used_fallback=False,
            evidence=evidence,
        )

    fallback_language = (
        bot_primary_language if bot_primary_language in SUPPORTED_LANGUAGES else "en"
    )
    if fallback_language == question_language:
        # Nothing anywhere in the primary language either.
        return RetrievalResult(
            query_language=question_language,
            applied_language=question_language,
            used_fallback=False,
            evidence=[],
        )
    fallback_query: str | None = None
    if translate_query is not None:
        fallback_query = translate_query(question, fallback_language)
        if not (fallback_query and fallback_query.strip()):
            fallback_query = None
    evidence = _retrieve_one_pass(
        db,
        tenant_id=tenant_id,
        bot_id=bot_id,
        revision_id=revision_id,
        language=fallback_language,
        question=fallback_query or question,
        settings=settings,
        always_include_document_ids=always_include_document_ids,
    )
    return RetrievalResult(
        query_language=question_language,
        applied_language=fallback_language if evidence else question_language,
        used_fallback=True,
        fallback_query=fallback_query,
        evidence=evidence,
    )
