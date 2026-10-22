"""Model-specific relevance signals; rank-fusion scores are never a gate."""

import math
from dataclasses import dataclass, field

from app.core.config import Settings
from app.retrieval.service import RetrievalResult, RetrievedChunk


@dataclass(frozen=True)
class ChunkVerdict:
    """Why one candidate passed or failed the gate (read-only explanation)."""

    chunk_id: str
    accepted: bool
    # "cosine" | "keyword" | "top_result" | None (rejected)
    accepted_by: str | None
    reason: str
    cosine: float | None
    cosine_floor: float | None
    # None when the model has no usable floor (vector acceptance disabled).
    cosine_pass: bool | None
    matched_terms: int
    required_terms: int
    terms_pass: bool
    fts_match: float
    fts_minimum: float
    fts_pass: bool
    top_result_pass: bool | None = None


@dataclass(frozen=True)
class GateDecision:
    passed: list[RetrievedChunk]
    rejected_ids: list[str]
    vector_floor: float | None
    fts_minimum: float
    verdicts: list[ChunkVerdict] = field(default_factory=list)


def _finite(value: float | None) -> bool:
    return value is not None and math.isfinite(value)


def _top_result_id(result: RetrievalResult, settings: Settings) -> str | None:
    """Chunk the optional top-result rule lets through (None while the rule is off)."""
    top_floor = settings.retrieval_top_result_cosine_floor
    if top_floor is None:
        return None
    sims = sorted(
        (
            (chunk.vector_similarity, str(chunk.chunk_id))
            for chunk in result.evidence
            if chunk.vector_similarity is not None and math.isfinite(chunk.vector_similarity)
        ),
        reverse=True,
    )
    if not sims:
        return None
    runner_up = sims[1][0] if len(sims) > 1 else -1.0
    if sims[0][0] >= top_floor and sims[0][0] - runner_up >= settings.retrieval_top_result_margin:
        return sims[0][1]
    return None


def relevance_gate(result: RetrievalResult, settings: Settings) -> GateDecision:
    floor = settings.retrieval_vector_floors.get(result.embedding_model or "")
    # Malformed or uncalibrated model configuration fails closed on the vector
    # signal. Keyword evidence can still pass independently.
    if floor is not None and (not math.isfinite(floor) or not -1 <= floor <= 1):
        floor = None
    passed: list[RetrievedChunk] = []
    rejected: list[str] = []
    verdicts: list[ChunkVerdict] = []
    keyword_gate = settings.retrieval_keyword_gates.get(result.embedding_model or "")
    min_fts = keyword_gate.min_fts_match if keyword_gate else settings.retrieval_min_fts_match
    min_terms = (
        keyword_gate.min_matched_terms if keyword_gate else settings.retrieval_min_matched_terms
    )
    top_id = _top_result_id(result, settings)
    top_rule_on = settings.retrieval_top_result_cosine_floor is not None
    for chunk in result.evidence:
        sim = chunk.vector_similarity
        cosine_pass: bool | None = None
        if floor is not None:
            cosine_pass = sim is not None and math.isfinite(sim) and sim >= floor
        # A one-word question can only ever match one term.
        required = min(min_terms, chunk.query_terms) if chunk.query_terms else min_terms
        required = max(1, required)
        terms_pass = chunk.matched_terms >= required
        fts_pass = (
            math.isfinite(chunk.fts_match) and chunk.fts_match > 0 and chunk.fts_match >= min_fts
        )
        top_ok = top_id is not None and str(chunk.chunk_id) == top_id
        accepted_by: str | None = None
        if cosine_pass:
            accepted_by = "cosine"
        elif terms_pass and fts_pass:
            accepted_by = "keyword"
        elif top_ok:
            accepted_by = "top_result"
        if accepted_by:
            passed.append(chunk)
        else:
            rejected.append(str(chunk.chunk_id))
        verdicts.append(
            ChunkVerdict(
                chunk_id=str(chunk.chunk_id),
                accepted=accepted_by is not None,
                accepted_by=accepted_by,
                reason=_reason(accepted_by, chunk, floor, required, min_fts, terms_pass, fts_pass),
                cosine=sim if sim is not None and math.isfinite(sim) else None,
                cosine_floor=floor,
                cosine_pass=cosine_pass,
                matched_terms=chunk.matched_terms,
                required_terms=required,
                terms_pass=terms_pass,
                fts_match=chunk.fts_match if math.isfinite(chunk.fts_match) else 0.0,
                fts_minimum=min_fts,
                fts_pass=fts_pass,
                top_result_pass=top_ok if top_rule_on else None,
            )
        )
    return GateDecision(passed, rejected, floor, min_fts, verdicts)


def _reason(
    accepted_by: str | None,
    chunk: RetrievedChunk,
    floor: float | None,
    required: int,
    min_fts: float,
    terms_pass: bool,
    fts_pass: bool,
) -> str:
    sim = chunk.vector_similarity
    has_sim = sim is not None and math.isfinite(sim)
    if accepted_by == "cosine":
        return f"passed: cosine {sim:.3f} >= floor {floor:.2f}"
    if accepted_by == "keyword":
        return (
            f"passed: matched terms {chunk.matched_terms} >= {required} "
            f"and fts {chunk.fts_match:.3f} >= {min_fts:g}"
        )
    if accepted_by == "top_result":
        return f"passed: top-result rule (cosine {sim:.3f}, clear lead over the runner-up)"
    parts = []
    if floor is None:
        parts.append("cosine floor disabled for this model")
    elif not has_sim:
        parts.append("no cosine score")
    else:
        parts.append(f"cosine {sim:.3f} < floor {floor:.2f}")
    if not terms_pass:
        parts.append(f"matched terms {chunk.matched_terms} < required {required}")
    if not fts_pass:
        parts.append(f"fts {chunk.fts_match:.3f} < minimum {min_fts:g}")
    return "rejected: " + "; ".join(parts)
