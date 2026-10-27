"""Operator eval primitives: durable cases, retrieval metrics, conservative budgets."""

import hashlib
import json
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx

from app.embeddings.providers import EmbeddingBatch, EmbeddingError, validate_vector
from scripts.rag_stage0_baseline import StopBaseline, append_record

MAX_CALIBRATION_TOKENS = 2_000_000


def text_key(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def estimate_calibration(texts: list[str], *, enforce: bool = True) -> dict[str, Any]:
    # UTF-8 bytes form a conservative token upper bound, without another model
    # or tokenizer dependency. Report the deliberately conservative assumption.
    lengths = [len(value.encode("utf-8")) for value in dict.fromkeys(texts)]
    tokens = sum(lengths)
    estimate = {
        "estimated_tokens_upper_bound": tokens,
        "estimated_cost_usd_upper_bound": str(Decimal(tokens) * Decimal("0.13") / 1_000_000),
        "estimate_method": "UTF-8 byte upper bound, $0.13 per million input tokens",
        "within_budget": tokens <= MAX_CALIBRATION_TOKENS,
    }
    if enforce and tokens > MAX_CALIBRATION_TOKENS:
        raise ValueError(
            f"Calibration estimate {tokens} tokens / ${estimate['estimated_cost_usd_upper_bound']} "
            "exceeds the 2M-token cap; no embedding requests allowed."
        )
    if enforce and any(length > 8192 for length in lengths):
        raise ValueError("An input may exceed the embedding per-input token cap; split it first.")
    return estimate


class CachedEmbedder:
    def __init__(self, identity: str, vectors: dict[str, list[float]]) -> None:
        self.identity, self.vectors = identity, vectors

    def embed(self, texts: list[str]) -> EmbeddingBatch:
        try:
            return EmbeddingBatch(
                [validate_vector(self.vectors[text_key(value)]) for value in texts],
                cost_usd=Decimal(0),
            )
        except KeyError:
            raise EmbeddingError(
                "Query embedding is not cached; no implicit provider call."
            ) from None


def read_cache(path: Path, identity: str) -> CachedEmbedder:
    vectors = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row["embedding_model"] != identity:
            raise ValueError("Embedding cache model does not match the active index.")
        vectors[row["text_key"]] = validate_vector(row["vector"])
    return CachedEmbedder(identity, vectors)


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[row["type"]].append(row)
    answerable = [row for row in rows if not row["unanswerable"]]
    gaps = [row for row in rows if row["unanswerable"]]
    return {
        "cases": len(rows),
        "hit_at_3": sum(row.get("hit_at_3", False) for row in answerable) / len(answerable)
        if answerable
        else None,
        "mrr": sum(row.get("reciprocal_rank", 0.0) for row in answerable) / len(answerable)
        if answerable
        else None,
        "mrr_cutoff": "all retrieved candidates (top_k), answerable cases only",
        "answerable_hit_at_k": [sum(row["hit_at_k"] for row in answerable), len(answerable)],
        "gate_refusal_correctness": [sum(not row["gate_passed"] for row in gaps), len(gaps)],
        "gate_wrong_refusals": [sum(not row["gate_passed"] for row in answerable), len(answerable)],
        "generation_metrics": "PENDING (retrieval-only)",
        "by_type": {
            kind: {
                "cases": len(items),
                "hits": sum(item["hit_at_k"] for item in items),
                "gate_passes": sum(item["gate_passed"] for item in items),
            }
            for kind, items in groups.items()
        },
    }


def threshold_proposal(rows: list[dict[str, Any]]) -> dict[str, Any]:
    positives, negatives = [], []
    for row in rows:
        for chunk in row["candidates"]:
            score = chunk["vector_similarity"]
            if score is None:
                continue
            if chunk["chunk_id"] in row["expected_chunk_ids"]:
                positives.append(score)
            elif row["unanswerable"]:
                negatives.append(score)
    if not positives or not negatives:
        return {"proposed_cosine_floor": None, "status": "insufficient labelled scores"}
    positive_floor, negative_ceiling = min(positives), max(negatives)
    return {
        "minimum_positive": positive_floor,
        "maximum_negative": negative_ceiling,
        "proposed_cosine_floor": (
            (positive_floor + negative_ceiling) / 2 if positive_floor > negative_ceiling else None
        ),
        "status": "separable sample only; owner validation required"
        if positive_floor > negative_ceiling
        else "overlap: owner must choose the refusal/recall tradeoff",
        "automatically_applied": False,
    }


def threshold_sweep(rows: list[dict[str, Any]], mode: str) -> dict[str, Any]:
    """Choose a conservative labelled-sample tradeoff, never apply it implicitly."""
    settings = []
    positives = sum(not row["unanswerable"] for row in rows)
    negatives = len(rows) - positives
    for cosine in [None] if mode == "fts_only" else [None, 0.4, 0.5, 0.6, 0.7]:
        for fts in (0.005, 0.01, 0.05, 0.1, 0.2):
            for terms in (1, 2, 3):
                leaks = refusals = wrong_accepts = 0
                for row in rows:
                    accepted = [
                        c
                        for c in row["evidence"]
                        if (
                            cosine is not None
                            and c["vector_similarity"] is not None
                            and c["vector_similarity"] >= cosine
                        )
                        or (c["fts_match"] >= fts and c["matched_terms"] >= terms)
                    ]
                    correct = any(
                        c["chunk_id"] in row["expected_chunk_ids"]
                        or c["document_id"] in row["expected_document_ids"]
                        for c in accepted
                    )
                    if row["unanswerable"]:
                        leaks += bool(accepted)
                    else:
                        refusals += not accepted
                        wrong_accepts += bool(accepted) and not correct
                settings.append(
                    {
                        "cosine_floor": cosine,
                        "fts_floor": fts,
                        "min_matched_terms": terms,
                        "unanswerable_leaks": leaks,
                        "unanswerable_cases": negatives,
                        "wrong_refusals": refusals,
                        "answerable_cases": positives,
                        "wrong_evidence_accepts": wrong_accepts,
                    }
                )
    recommended = min(
        settings,
        key=lambda s: (
            s["unanswerable_leaks"],
            s["wrong_refusals"],
            s["wrong_evidence_accepts"],
            s["min_matched_terms"],
            s["fts_floor"],
            s["cosine_floor"] or 2,
        ),
    )
    return {
        "settings": settings,
        "recommended": recommended,
        "selection_rule": "fewest leaks, then wrong refusals, then wrong-evidence accepts",
        "status": "sample recommendation only; pending owner calibration review",
        "automatically_applied": False,
    }


SWEEP_COSINES: tuple[float | None, ...] = (None, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60)
SWEEP_FTS: tuple[float, ...] = (0.005, 0.01, 0.02, 0.05, 0.1, 0.2)
SWEEP_TERMS: tuple[int, ...] = (1, 2, 3)


def _page_accepts(chunk: dict[str, Any], cosine: float | None, fts: float, terms: int) -> bool:
    """The gate's chunk rule, replayed on recorded numbers (cosine OR terms+FTS)."""
    sim = chunk.get("cosine")
    if cosine is not None and sim is not None and sim >= cosine:
        return True
    needed = max(1, min(terms, chunk["query_terms"]) if chunk["query_terms"] else terms)
    return bool(
        chunk["matched_terms"] >= needed and chunk["fts_match"] > 0 and chunk["fts_match"] >= fts
    )


def page_sweep(
    records: list[dict[str, Any]],
    *,
    cosines: tuple[float | None, ...] = SWEEP_COSINES,
    fts_floors: tuple[float, ...] = SWEEP_FTS,
    min_terms: tuple[int, ...] = SWEEP_TERMS,
    current: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Replay the gate over recorded candidates for every threshold combination.

    ``records``: one per case with ``behavior`` (grounded|abstain), ``language``,
    ``expected`` (list of [file stem, page]) and ``candidates`` (each: ``page`` as
    [stem, page] or None, ``cosine``, ``fts_match``, ``matched_terms``,
    ``query_terms``). Nothing is applied: this only counts, per combination, how
    many answerable cases would be wrongly refused, how many would keep only the
    wrong page, and how many unanswerable cases would leak evidence.
    """
    answerable = [r for r in records if r["behavior"] == "grounded"]
    unanswerable = [r for r in records if r["behavior"] != "grounded"]
    rows: list[dict[str, Any]] = []
    for cosine in cosines:
        for fts in fts_floors:
            for terms in min_terms:
                refusals = wrong_only = leaks = 0
                by_language: dict[str, int] = {}
                for record in answerable:
                    passed = {
                        tuple(c["page"])
                        for c in record["candidates"]
                        if c["page"] is not None and _page_accepts(c, cosine, fts, terms)
                    }
                    expected = {tuple(page) for page in record["expected"]}
                    if not passed:
                        refusals += 1
                        by_language[record["language"]] = by_language.get(record["language"], 0) + 1
                    elif not passed & expected:
                        wrong_only += 1
                for record in unanswerable:
                    leaks += any(_page_accepts(c, cosine, fts, terms) for c in record["candidates"])
                rows.append(
                    {
                        "cosine_floor": cosine,
                        "fts_floor": fts,
                        "min_matched_terms": terms,
                        "wrong_refusals": refusals,
                        "wrong_refusals_by_language": dict(sorted(by_language.items())),
                        "wrong_evidence_only": wrong_only,
                        "unanswerable_leaks": leaks,
                    }
                )
    ordered = sorted(
        rows,
        key=lambda r: (
            r["unanswerable_leaks"],
            r["wrong_refusals"],
            r["wrong_evidence_only"],
            -r["min_matched_terms"],
            -r["fts_floor"],
            r["cosine_floor"] if r["cosine_floor"] is not None else 2,
        ),
    )
    return {
        "answerable_cases": len(answerable),
        "unanswerable_cases": len(unanswerable),
        "rows": rows,
        "ranked": ordered[:5],
        "current": next((r for r in rows if _matches_current(r, current)), None),
        "selection_rule": "fewest leaks, then wrong refusals, then wrong-evidence-only; "
        "ties prefer the stricter setting",
        "status": "recommendation only; pending owner calibration review",
        "automatically_applied": False,
    }


def _matches_current(row: dict[str, Any], current: dict[str, Any] | None) -> bool:
    if current is None:
        return False
    return bool(
        row["cosine_floor"] == current.get("cosine_floor")
        and row["fts_floor"] == current.get("fts_floor")
        and row["min_matched_terms"] == current.get("min_matched_terms")
    )


class CappedChatTransport(httpx.BaseTransport):
    """Persist a request reservation BEFORE transport; crashes cannot reset cap40."""

    def __init__(
        self, journal: Path, limit: int = 40, inner: httpx.BaseTransport | None = None
    ) -> None:
        if not 1 <= limit <= 40:
            raise ValueError("Chat request limit must be between 1 and 40.")
        self.journal, self.limit = journal, limit
        self.used = len(journal.read_text(encoding="utf-8").splitlines()) if journal.exists() else 0
        self.inner = inner or httpx.HTTPTransport(retries=0)

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        if self.used >= self.limit:
            raise StopBaseline("run_request_cap_reached")
        self.used += 1
        append_record(self.journal, {"id": str(self.used), "event": "request_reserved"})
        return self.inner.handle_request(request)

    def close(self) -> None:
        self.inner.close()
