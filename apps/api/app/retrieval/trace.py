"""Read-only staff trace rows for retrieval candidates (B.3, issue #28).

One row per candidate chunk: the query terms, which of them the chunk matched,
cosine, FTS score, RRF rank score and the gate verdict with the rule that
decided it. Pure data; no behaviour change, no database access.
"""

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
