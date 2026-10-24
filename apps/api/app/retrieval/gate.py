"""Model-specific relevance signals; rank-fusion scores are never a gate."""

import math
from dataclasses import dataclass, field
from uuid import UUID

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
class DocumentVerdict:
    """A document passes when ANY of its evidence chunks passes the chunk rules."""

    document_id: str
    accepted: bool
    reason: str
    chunk_count: int
    passed_chunk_ids: list[str]
    best_rrf_score: float
    max_cosine: float | None
    best_fts_match: float


@dataclass(frozen=True)
class GateDecision:
    # Evidence chunks of every passed document: documents in relevance order,
    # chunks in reading (ordinal) order inside each document.
    passed: list[RetrievedChunk]
    rejected_ids: list[str]
    vector_floor: float | None
    fts_minimum: float
    verdicts: list[ChunkVerdict] = field(default_factory=list)
    document_verdicts: list[DocumentVerdict] = field(default_factory=list)


def _finite(value: float | None) -> bool:
    return value is not None and math.isfinite(value)


def _top_result_id(result: RetrievalResult, settings: Settings) -> str | None:
    """Chunk the optional top-result rule lets through (None while the rule is off)."""
    top_floor = settings.retrieval_top_result_cosine_floor
    if top_floor is None:
        return None
    # Equal cosines are ordered by what the content is called, not by chunk id.
    sims = sorted(
        (
            (chunk.vector_similarity, chunk)
            for chunk in result.evidence
            if chunk.vector_similarity is not None and math.isfinite(chunk.vector_similarity)
        ),
        key=lambda item: (-item[0], item[1].title, item[1].page_ref, item[1].ordinal),
    )
    if not sims:
        return None
    runner_up = sims[1][0] if len(sims) > 1 else -1.0
    if sims[0][0] >= top_floor and sims[0][0] - runner_up >= settings.retrieval_top_result_margin:
        return str(sims[0][1].chunk_id)
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
    return _document_level(result, passed, verdicts, floor, min_fts)


def _sim(chunk: RetrievedChunk) -> float | None:
    sim = chunk.vector_similarity
    return sim if sim is not None and math.isfinite(sim) else None


def _document_level(
    result: RetrievalResult,
    chunk_passed: list[RetrievedChunk],
    verdicts: list[ChunkVerdict],
    floor: float | None,
    min_fts: float,
) -> GateDecision:
    """Judge per document: one passing chunk keeps the whole document's evidence.

    Documents are ordered by relevance (best RRF score, then max cosine, then
    FTS rank; ties keep retrieval order) and chunks inside a document by
    ordinal. Sibling chunks need no cosine of their own."""
    by_chunk = {v.chunk_id: v for v in verdicts}
    passing_ids = {str(c.chunk_id) for c in chunk_passed}
    groups: dict[UUID, list[RetrievedChunk]] = {}
    for chunk in result.evidence:
        groups.setdefault(chunk.document_id, []).append(chunk)
    scored: list[tuple[tuple[float, float, float, int], UUID]] = []
    document_verdicts: list[DocumentVerdict] = []
    accepted_documents: set[UUID] = set()
    for index, (document_id, chunks) in enumerate(groups.items()):
        winners = [c for c in chunks if str(c.chunk_id) in passing_ids]
        sims = [s for s in (_sim(c) for c in chunks) if s is not None]
        cosine = max(sims) if sims else None
        best_rrf = max(c.rrf_score for c in chunks)
        best_fts = max((c.fts_match for c in chunks if math.isfinite(c.fts_match)), default=0.0)
        if winners:
            lead = max(winners, key=lambda c: -2.0 if (sim := _sim(c)) is None else sim)
            detail = by_chunk[str(lead.chunk_id)].reason.removeprefix("passed: ")
            reason = f"passed: {len(winners)} of {len(chunks)} chunks passed; {detail}"
            accepted_documents.add(document_id)
            rank = (-best_rrf, -(cosine if cosine is not None else -2.0), -best_fts, index)
            scored.append((rank, document_id))
        else:
            reason = f"rejected: none of {len(chunks)} chunks passed"
        document_verdicts.append(
            DocumentVerdict(
                document_id=str(document_id),
                accepted=bool(winners),
                reason=reason,
                chunk_count=len(chunks),
                passed_chunk_ids=[str(c.chunk_id) for c in winners],
                best_rrf_score=best_rrf,
                max_cosine=cosine,
                best_fts_match=best_fts,
            )
        )
    scored.sort(key=lambda item: item[0])
    passed: list[RetrievedChunk] = []
    for _, document_id in scored:
        passed.extend(sorted(groups[document_id], key=lambda c: c.ordinal))
    rejected = [
        str(c.chunk_id)
        for document_id, chunks in groups.items()
        if document_id not in accepted_documents
        for c in chunks
    ]
    return GateDecision(passed, rejected, floor, min_fts, verdicts, document_verdicts)


def select_evidence(decision: GateDecision, settings: Settings) -> list[RetrievedChunk]:
    """Slice the passed documents for the prompt without cutting one mid-way.

    The most relevant passed document is kept whole (up to the hard
    ``retrieval_max_evidence_chunks`` cap). Further documents are added whole,
    in relevance order, while the soft ``retrieval_final_k`` chunk budget has
    room; the first one that does not fit ends the selection, so a lower
    document never displaces part of a higher one."""
    documents: dict[UUID, list[RetrievedChunk]] = {}
    for chunk in decision.passed:
        documents.setdefault(chunk.document_id, []).append(chunk)
    selected: list[RetrievedChunk] = []
    for document_chunks in documents.values():
        if not selected:
            selected.extend(document_chunks[: settings.retrieval_max_evidence_chunks])
            continue
        if len(selected) + len(document_chunks) > settings.retrieval_final_k:
            break
        selected.extend(document_chunks)
    return selected


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
