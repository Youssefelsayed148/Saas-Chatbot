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


def estimate_calibration(texts: list[str]) -> dict[str, Any]:
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
    if tokens > MAX_CALIBRATION_TOKENS:
        raise ValueError(
            f"Calibration estimate {tokens} tokens / ${estimate['estimated_cost_usd_upper_bound']} "
            "exceeds the 2M-token cap; no embedding requests allowed."
        )
    if any(length > 8192 for length in lengths):
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


class CappedChatTransport(httpx.BaseTransport):
    """Persist a request reservation BEFORE transport; crashes cannot reset cap40."""

    def __init__(
        self, journal: Path, limit: int = 40, inner: httpx.BaseTransport | None = None
    ) -> None:
        if not 1 <= limit <= 40:
            raise ValueError("Chat request limit must be between 1 and 40.")
        self.journal, self.limit = journal, limit
        self.used = len(journal.read_text().splitlines()) if journal.exists() else 0
        self.inner = inner or httpx.HTTPTransport(retries=0)

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        if self.used >= self.limit:
            raise StopBaseline("run_request_cap_reached")
        self.used += 1
        append_record(self.journal, {"id": str(self.used), "event": "request_reserved"})
        return self.inner.handle_request(request)

    def close(self) -> None:
        self.inner.close()
