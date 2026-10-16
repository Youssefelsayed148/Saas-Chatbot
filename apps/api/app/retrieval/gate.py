"""Model-specific relevance signals; rank-fusion scores are never a gate."""

import math
from dataclasses import dataclass

from app.core.config import Settings
from app.retrieval.service import RetrievalResult, RetrievedChunk


@dataclass(frozen=True)
class GateDecision:
    passed: list[RetrievedChunk]
    rejected_ids: list[str]
    vector_floor: float | None
    fts_minimum: float


def relevance_gate(result: RetrievalResult, settings: Settings) -> GateDecision:
    floor = settings.retrieval_vector_floors.get(result.embedding_model or "")
    # Malformed or uncalibrated model configuration fails closed on the vector
    # signal. Keyword evidence can still pass independently.
    if floor is not None and (not math.isfinite(floor) or not -1 <= floor <= 1):
        floor = None
    passed, rejected = [], []
    keyword_gate = settings.retrieval_keyword_gates.get(result.embedding_model or "")
    min_fts = keyword_gate.min_fts_match if keyword_gate else settings.retrieval_min_fts_match
    min_terms = (
        keyword_gate.min_matched_terms if keyword_gate else settings.retrieval_min_matched_terms
    )
    for chunk in result.evidence:
        vector_ok = (
            floor is not None
            and chunk.vector_similarity is not None
            and math.isfinite(chunk.vector_similarity)
            and chunk.vector_similarity >= floor
        )
        # A one-word question can only ever match one term.
        required = min(min_terms, chunk.query_terms) if chunk.query_terms else min_terms
        keyword_ok = chunk.matched_terms >= max(1, required) and (
            math.isfinite(chunk.fts_match) and chunk.fts_match > 0 and chunk.fts_match >= min_fts
        )
        if vector_ok or keyword_ok:
            passed.append(chunk)
        else:
            rejected.append(str(chunk.chunk_id))
    return GateDecision(passed, rejected, floor, min_fts)
