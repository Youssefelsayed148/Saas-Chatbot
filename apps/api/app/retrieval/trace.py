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
                "failed_rules": list(verdict.failed_rules),
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


def _shortfall(verdict: ChunkVerdict) -> dict[str, float | int | None]:
    """How far the candidate was from each rule (positive = missed by that much)."""
    cosine = (
        round(verdict.cosine_floor - verdict.cosine, 4)
        if verdict.cosine is not None and verdict.cosine_floor is not None
        else None
    )
    return {
        "cosine": cosine,
        "terms": max(0, verdict.required_terms - verdict.matched_terms),
        "fts": round(max(0.0, verdict.fts_minimum - verdict.fts_match), 4),
    }


def refusal_diagnosis(retrieval: RetrievalResult, decision: GateDecision) -> dict[str, Any]:
    """Which gate rule failed for a refused turn and how near the best candidate came.

    ``nearest`` is the top-ranked candidate (same order as ``rejected_candidates``);
    ``best`` holds the maximum of each signal over ALL candidates, so a staff member
    can see whether any single chunk came close even when the ranking leader did not.
    Numbers only; no chunk text."""
    ranked = _ranked(retrieval)
    verdicts = {row.chunk_id: row for row in decision.verdicts}
    counts = {"cosine": 0, "cosine_disabled": 0, "terms": 0, "fts": 0}
    for verdict in decision.verdicts:
        for rule in verdict.failed_rules:
            counts[rule] = counts.get(rule, 0) + 1
    if not ranked:
        return {
            "outcome": "no_candidates",
            "candidates": 0,
            "failed_rules": [],
            "rule_counts": counts,
            "nearest": None,
            "best": None,
        }
    lead = ranked[0]
    lead_verdict = verdicts.get(str(lead.chunk_id))
    nearest: dict[str, Any] = {
        "document_title": lead.title,
        "chunk_id": str(lead.chunk_id),
        "locator": lead.page_ref,
        "cosine": lead.vector_similarity,
        "fts_match": lead.fts_match,
        "matched_terms": lead.matched_terms,
        "query_terms": lead.query_terms,
        "rrf_score": lead.rrf_score,
    }
    if lead_verdict is not None:
        nearest.update(
            cosine_floor=lead_verdict.cosine_floor,
            required_terms=lead_verdict.required_terms,
            fts_minimum=lead_verdict.fts_minimum,
            failed_rules=list(lead_verdict.failed_rules),
            shortfall=_shortfall(lead_verdict),
        )
    sims = [c.vector_similarity for c in ranked if c.vector_similarity is not None]
    return {
        "outcome": "gate_rejected_all",
        "candidates": len(ranked),
        "failed_rules": list(lead_verdict.failed_rules) if lead_verdict is not None else [],
        "rule_counts": counts,
        "nearest": nearest,
        "best": {
            "cosine": max(sims) if sims else None,
            "fts_match": max(c.fts_match for c in ranked),
            "matched_terms": max(c.matched_terms for c in ranked),
        },
    }


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
