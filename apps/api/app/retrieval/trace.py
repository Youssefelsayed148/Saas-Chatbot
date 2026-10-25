"""Read-only staff trace rows for retrieval candidates (B.3, issue #28).

One row per candidate chunk: the query terms, which of them the chunk matched,
cosine, FTS score, RRF rank score and the gate verdict with the rule that
decided it. Pure data; no behaviour change, no database access.
"""

import re
from typing import Any

from app.retrieval.gate import ChunkVerdict, GateDecision
from app.retrieval.service import RetrievalResult, RetrievedChunk


def candidate_trace(
    retrieval: RetrievalResult,
    decision: GateDecision,
    accepted: list[RetrievedChunk],
) -> list[dict[str, Any]]:
    """Trace rows for ``retrieval.evidence``; ``accepted`` is what reached the model."""
    verdicts: dict[str, ChunkVerdict] = {row.chunk_id: row for row in decision.verdicts}
    accepted_ids = {chunk.chunk_id for chunk in accepted}
    passed_documents = {chunk.document_id for chunk in decision.passed}
    rows: list[dict[str, Any]] = []
    for chunk in retrieval.evidence:
        verdict = verdicts.get(str(chunk.chunk_id))
        row: dict[str, Any] = {
            "chunk_id": str(chunk.chunk_id),
            "document_id": str(chunk.document_id),
            "title": chunk.title,
            "locator": chunk.page_ref,
            "vector_similarity": chunk.vector_similarity,
            "fts_match": chunk.fts_match,
            "rrf_score": chunk.rrf_score,
            "accepted": chunk.chunk_id in accepted_ids,
            "document_passed": chunk.document_id in passed_documents,
            "query_terms": list(chunk.query_term_labels),
            "matched_terms": list(chunk.matched_term_labels),
            "matched_term_count": chunk.matched_terms,
            "query_term_count": chunk.query_terms,
        }
        if verdict is not None:
            row["gate"] = {
                "passed": verdict.accepted,
                "accepted_by": verdict.accepted_by,
                "reason": verdict.reason,
                "cosine": {
                    "value": verdict.cosine,
                    "floor": verdict.cosine_floor,
                    "passed": verdict.cosine_pass,
                },
                "terms": {
                    "matched": verdict.matched_terms,
                    "required": verdict.required_terms,
                    "passed": verdict.terms_pass,
                },
                "fts": {
                    "value": verdict.fts_match,
                    "minimum": verdict.fts_minimum,
                    "passed": verdict.fts_pass,
                },
                "top_result": verdict.top_result_pass,
            }
        rows.append(row)
    return rows


def _ranked(retrieval: RetrievalResult) -> list[RetrievedChunk]:
    return sorted(
        retrieval.evidence,
        key=lambda chunk: (
            -chunk.rrf_score,
            -(chunk.vector_similarity if chunk.vector_similarity is not None else -2.0),
            -chunk.fts_match,
        ),
    )


_FILE_EXTENSION = re.compile(r"\.(pdf|docx?|txt|md|csv)$", re.IGNORECASE)
MAX_TOPIC_CHARS = 80


def _topic_label(chunk: RetrievedChunk) -> str:
    """A visitor-readable topic: the chunk heading, else the document title."""
    for raw in (chunk.heading, chunk.title):
        label = _FILE_EXTENSION.sub("", " ".join((raw or "").lstrip("# ").split())).strip()
        if label:
            return label[:MAX_TOPIC_CHARS].strip()
    return ""


def near_miss_topics(retrieval: RetrievalResult, limit: int = 3) -> list[str]:
    """Up to ``limit`` topics for a refused turn, from the stored headings or
    titles of near-miss candidates (never model text).

    Near miss: the gate refused the chunk but the query shared at least one
    content term with it, or its keyword score is positive. A purely semantic
    neighbour with no shared term is not offered, so an unrelated question
    gets no suggestions."""
    topics: list[str] = []
    seen: set[str] = set()
    for chunk in _ranked(retrieval):
        if chunk.matched_terms < 1 and chunk.fts_match <= 0:
            continue
        label = _topic_label(chunk)
        key = label.casefold()
        if not label or key in seen:
            continue
        seen.add(key)
        topics.append(label)
        if len(topics) == limit:
            break
    return topics


def rejected_candidates(
    retrieval: RetrievalResult,
    decision: GateDecision,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """The strongest candidates the gate turned away, for a turn with no evidence.

    Document title, chunk id, scores and the gate's reason; no chunk text."""
    verdicts = {row.chunk_id: row for row in decision.verdicts}
    ranked = _ranked(retrieval)
    rows: list[dict[str, Any]] = []
    for chunk in ranked:
        verdict = verdicts.get(str(chunk.chunk_id))
        if verdict is not None and verdict.accepted:
            continue
        rows.append(
            {
                "document_title": chunk.title,
                "chunk_id": str(chunk.chunk_id),
                "locator": chunk.page_ref,
                "vector_similarity": chunk.vector_similarity,
                "fts_match": chunk.fts_match,
                "rrf_score": chunk.rrf_score,
                "reason": verdict.reason if verdict is not None else "not judged",
            }
        )
        if len(rows) == limit:
            break
    return rows


def document_trace(
    decision: GateDecision,
    accepted: list[RetrievedChunk],
) -> list[dict[str, Any]]:
    """One row per evidence document: verdict, reason and what reached the model."""
    kept: dict[str, int] = {}
    for chunk in accepted:
        kept[str(chunk.document_id)] = kept.get(str(chunk.document_id), 0) + 1
    return [
        {
            "document_id": verdict.document_id,
            "passed": verdict.accepted,
            "reason": verdict.reason,
            "chunk_count": verdict.chunk_count,
            "passed_chunks": len(verdict.passed_chunk_ids),
            "chunks_sent": kept.get(verdict.document_id, 0),
            "best_rrf_score": verdict.best_rrf_score,
            "max_cosine": verdict.max_cosine,
            "best_fts_match": verdict.best_fts_match,
        }
        for verdict in decision.document_verdicts
    ]
