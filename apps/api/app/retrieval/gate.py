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
    for chunk in result.evidence:
        vector_ok = (
            floor is not None
            and chunk.vector_similarity is not None
            and math.isfinite(chunk.vector_similarity)
            and chunk.vector_similarity >= floor
        )
        keyword_ok = math.isfinite(chunk.fts_match) and (
            chunk.fts_match >= settings.retrieval_min_fts_match
        )
        if vector_ok or keyword_ok:
            passed.append(chunk)
        else:
            rejected.append(str(chunk.chunk_id))
    return GateDecision(passed, rejected, floor, settings.retrieval_min_fts_match)
