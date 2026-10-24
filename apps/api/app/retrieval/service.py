"""Retrieval service (docs/14 §1, §2, §5): language-aware keyword search.

One pass = query the GIN-indexed tsvector columns for the question's
language (``fts_en`` for English, ``fts_ar`` with the PostgreSQL ``arabic``
configuration over Arabic-normalised chunks) — always filtered by ``tenant_id``, ``bot_id``,
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

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session as OrmSession

from app.core.config import Settings, get_settings
from app.knowledge.language import normalise_text
from app.retrieval.query import (
    build_tsquery,
    normalise_ignore_terms,
    term_labels,
    term_queries,
)

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
    vector_similarity: float | None = None
    fts_match: float = 0.0
    rrf_score: float = 0.0
    matched_terms: int = 0
    # Distinct content terms in the query that produced matched_terms.
    query_terms: int = 0
    # Readable labels behind the two counts (staff trace, read-only).
    query_term_labels: list[str] = field(default_factory=list)
    matched_term_labels: list[str] = field(default_factory=list)


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
    mode: str = "fts_only"
    degradation_reason: str | None = None
    embedding_model: str | None = None
    embedding_tokens: int | None = None
    embedding_cost_usd: Decimal | None = None


def _fts_column(language: str) -> str:
    if language == "ar":
        return "fts_ar"
    return "fts_en"


def _tsquery_config(language: str) -> str:
    return "arabic" if language == "ar" else "english"


def score_lexical(
    db: OrmSession,
    chunks: list[RetrievedChunk],
    *,
    tenant_id: UUID,
    bot_id: UUID,
    revision_id: UUID,
    question: str,
    language: str,
    ignore_terms: Iterable[str] = (),
) -> None:
    """Score each selected chunk's stored index, with the same scoped SQL.

    Collapse English stems and Arabic article/prefix variants into distinct
    content-term groups before counting matches. Never copy a document's score
    to another chunk that may contain no matching terms. ``ignore_terms`` (the
    store-name/filler list) leaves the term count only; ranking is unchanged.
    """
    ignore = normalise_ignore_terms(ignore_terms)
    query = build_tsquery(question, language)
    if not chunks or not query:
        return
    column = _fts_column(language)
    # Terms are counted on heading + text only: the title (a filename such as
    # "returns_1.pdf") is searchable for ranking but never satisfies a term.
    bodies: dict[str, str] = {}
    for chunk in chunks:
        body = f"{chunk.heading or ''} {chunk.text}"
        bodies[str(chunk.chunk_id)] = normalise_text(body) if language == "ar" else body
    rows = db.execute(
        text(f"""
            WITH terms AS (
                SELECT to_tsquery(:config, t.term) AS query, min(t.label) AS label
                FROM unnest(CAST(:terms AS text[]), CAST(:labels AS text[])) AS t(term, label)
                WHERE numnode(to_tsquery(:config, t.term)) > 0
                GROUP BY to_tsquery(:config, t.term)
            ), bodies AS (
                SELECT CAST(b.id AS uuid) AS id, to_tsvector(:config, b.body) AS tsv
                FROM unnest(CAST(:body_ids AS text[]), CAST(:bodies AS text[])) AS b(id, body)
            )
            SELECT c.id, ts_rank_cd(c.{column}, to_tsquery(:config, :query)) AS score,
                (SELECT count(*) FROM terms WHERE terms.query @@ bodies.tsv) AS matched,
                (SELECT array_agg(terms.label ORDER BY terms.label)
                   FROM terms WHERE terms.query @@ bodies.tsv) AS matched_labels,
                (SELECT count(*) FROM terms) AS term_total,
                (SELECT array_agg(terms.label) FROM terms) AS term_group_labels
            FROM chunks c JOIN bodies ON bodies.id = c.id
            WHERE c.tenant_id=CAST(:tenant AS uuid) AND c.bot_id=CAST(:bot AS uuid)
              AND c.revision_id=CAST(:revision AS uuid)
        """),
        {
            "config": _tsquery_config(language),
            "terms": term_queries(question, language, ignore),
            "labels": term_labels(question, language, ignore),
            "query": query,
            "tenant": str(tenant_id),
            "bot": str(bot_id),
            "revision": str(revision_id),
            "body_ids": list(bodies),
            "bodies": list(bodies.values()),
        },
    ).mappings()
    rows_seen = list(rows)
    scores = {
        row["id"]: (float(row["score"]), int(row["matched"]), list(row["matched_labels"] or []))
        for row in rows_seen
    }
    # The distinct term groups PostgreSQL itself keeps (stems collapsed, stop-words
    # gone): the count the gate requires against can always be reached.
    labels = term_labels(question, language, ignore)
    total = len(labels)
    for row in rows_seen:
        total = int(row["term_total"])
        kept = set(row["term_group_labels"] or [])
        labels = [label for label in labels if label in kept]
        break
    for chunk in chunks:
        chunk.fts_match, chunk.matched_terms, chunk.matched_term_labels = scores.get(
            chunk.chunk_id, (0.0, 0, [])
        )
        chunk.query_terms = total
        chunk.query_term_labels = list(labels)


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
    bot_id: UUID,
    revision_id: UUID,
    language: str | None,
    document_id: UUID,
) -> list[RetrievedChunk]:
    """All chunks of one document (retrieved whole), in ordinal order.

    ``language`` is the document's own language (the matched chunk's), never
    the pass language: a cross-language hit must still come back whole. None
    (reserved always-include documents, whose language is unknown) fetches
    every chunk of the document.
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
              AND c.bot_id = CAST(:bot_id AS uuid)
              AND c.revision_id = CAST(:revision_id AS uuid)
              AND (CAST(:language AS text) IS NULL OR c.language = CAST(:language AS text))
              AND c.document_id = CAST(:document_id AS uuid)
            ORDER BY c.ordinal, c.id
            """
        ),
        {
            "tenant_id": str(tenant_id),
            "bot_id": str(bot_id),
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
) -> tuple[list[RetrievedChunk], list[RetrievedChunk]]:
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

    evidence = assemble_evidence(
        db,
        tenant_id=tenant_id,
        bot_id=bot_id,
        revision_id=revision_id,
        language=language,
        ranked=ranked,
        settings=settings,
        always_include_document_ids=always_include_document_ids,
    )
    score_lexical(
        db,
        [*ranked, *evidence],
        tenant_id=tenant_id,
        bot_id=bot_id,
        revision_id=revision_id,
        question=question,
        language=language,
        ignore_terms=settings.retrieval_gate_ignore_terms,
    )
    return ranked, evidence


def assemble_evidence(
    db: OrmSession,
    *,
    tenant_id: UUID,
    bot_id: UUID,
    revision_id: UUID,
    language: str,
    ranked: list[RetrievedChunk],
    settings: Settings,
    always_include_document_ids: set[str] | None,
) -> list[RetrievedChunk]:
    """Evidence rules shared by keyword and hybrid retrieval.

    ``ranked`` holds one entry per document, best first. Reserved always-include
    documents come first (whole), the best document is included whole, lower
    ranked documents fit whole when small or contribute their best chunk.
    """
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
                bot_id=bot_id,
                revision_id=revision_id,
                language=None,
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
                bot_id=bot_id,
                revision_id=revision_id,
                language=ranked[0].language,
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
                bot_id=bot_id,
                revision_id=revision_id,
                language=candidate.language,
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
    settings = settings or get_settings()
    if question_language not in SUPPORTED_LANGUAGES:
        question_language = "en"

    candidates, evidence = _retrieve_one_pass(
        db,
        tenant_id=tenant_id,
        bot_id=bot_id,
        revision_id=revision_id,
        language=question_language,
        question=question,
        settings=settings,
        always_include_document_ids=always_include_document_ids,
    )
    if candidates:
        return RetrievalResult(
            query_language=question_language,
            applied_language=question_language,
            used_fallback=False,
            evidence=evidence,
            candidates=candidates,
        )
    # No ranked hit in the question language. ``evidence`` may still hold the
    # reserved always-include documents; that must not suppress the fallback.
    first_pass_evidence = evidence

    fallback_language = (
        bot_primary_language if bot_primary_language in SUPPORTED_LANGUAGES else "en"
    )
    if fallback_language == question_language:
        # Nothing anywhere in the primary language either.
        return RetrievalResult(
            query_language=question_language,
            applied_language=question_language,
            used_fallback=False,
            evidence=first_pass_evidence,
        )
    fallback_query: str | None = None
    if translate_query is not None:
        fallback_query = translate_query(question, fallback_language)
        if not (fallback_query and fallback_query.strip()):
            fallback_query = None
    candidates, evidence = _retrieve_one_pass(
        db,
        tenant_id=tenant_id,
        bot_id=bot_id,
        revision_id=revision_id,
        language=fallback_language,
        question=fallback_query or question,
        settings=settings,
        always_include_document_ids=always_include_document_ids,
    )
    if not candidates and first_pass_evidence:
        # The fallback found nothing either: keep the always-include evidence.
        return RetrievalResult(
            query_language=question_language,
            applied_language=question_language,
            used_fallback=False,
            evidence=first_pass_evidence,
        )
    return RetrievalResult(
        query_language=question_language,
        applied_language=fallback_language if evidence else question_language,
        used_fallback=True,
        fallback_query=fallback_query,
        evidence=evidence,
        candidates=candidates,
    )
