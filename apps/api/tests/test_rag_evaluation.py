"""Eval budgets/provider contracts mocked; full two-mode fixture comparison offline."""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy.orm import Session

from app.embeddings.providers import HTTPEmbedder
from app.embeddings.providers import TestHashEmbedder as HashEmbedder
from app.retrieval.evaluation import (
    CappedChatTransport,
    estimate_calibration,
    read_cache,
    summarize,
    threshold_proposal,
)
from scripts.rag_phase2_eval import (
    DEFAULT_CASES,
    bind_cases,
    cache_embeddings,
    corpus,
    embed_demo,
    evaluate,
    load_cases,
)
from scripts.rag_stage0_baseline import BudgetModel, StopBaseline
from tests.conftest import build_test_settings


def test_calibration_preflight_is_conservative_and_aborts_before_spending() -> None:
    texts = ["hours", "hours", "Arabic العربية"]
    estimate = estimate_calibration(texts)
    assert estimate["estimated_tokens_upper_bound"] == sum(
        len(value.encode()) for value in set(texts)
    )
    assert estimate["within_budget"]
    with pytest.raises(ValueError, match="2M-token cap"):
        estimate_calibration(["x" * 2_000_001])
    with pytest.raises(ValueError, match="per-input"):
        estimate_calibration(["x" * 8193])


def test_openai_calibration_cache_http_is_mocked_and_not_replayed(tmp_path: Path) -> None:
    calls = []
    vector = [1.0] + [0.0] * 1023

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        body = json.loads(request.content)
        assert body["model"] == "text-embedding-3-large" and body["dimensions"] == 1024
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": index, "embedding": vector} for index in range(len(body["input"]))
                ],
                "usage": {"total_tokens": 12},
            },
        )

    embedder = HTTPEmbedder(
        identity="openai:text-embedding-3-large",
        base_url="https://fixture.invalid/v1",
        api_key="synthetic-key",
        transport=httpx.MockTransport(respond),
    )
    output = tmp_path / "cache.jsonl"
    cached = cache_embeddings(embedder, ["one", "two", "one"], output)
    assert cached.embed(["one"]).vectors == [vector] and len(calls) == 1
    assert read_cache(output, embedder.identity).embed(["two"]).vectors == [vector]
    batches = [
        json.loads(line) for line in (tmp_path / "embedding-usage.jsonl").read_text().splitlines()
    ]
    assert len(batches) == 1 and batches[0]["tokens"] == 12
    with pytest.raises(ValueError, match="already started"):
        cache_embeddings(embedder, ["one"], output)
    assert len(calls) == 1


def test_chat_cap_survives_restart_and_counts_all_fallback_attempts(tmp_path: Path) -> None:
    calls = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(503, json={})

    journal = tmp_path / "requests.jsonl"
    transport = CappedChatTransport(journal, inner=httpx.MockTransport(respond))
    with httpx.Client(transport=transport) as client:
        for _ in range(40):
            client.get("https://fixture.invalid")
        with pytest.raises(StopBaseline, match="run_request_cap_reached"):
            client.get("https://fixture.invalid")
    assert len(calls) == 40
    restarted = CappedChatTransport(journal, inner=httpx.MockTransport(respond))
    with httpx.Client(transport=restarted) as client:
        with pytest.raises(StopBaseline):
            client.get("https://fixture.invalid")
    assert len(calls) == 40


def test_quota_stops_before_fallback_with_durable_request_count(tmp_path: Path) -> None:
    transport = CappedChatTransport(
        tmp_path / "requests.jsonl", inner=httpx.MockTransport(lambda req: httpx.Response(429))
    )
    with httpx.Client(transport=transport) as client:
        model = BudgetModel(client, ["first:free", "second:free"])
        with pytest.raises(StopBaseline, match="quota_or_rate_limit"):
            model.complete([], json_mode=True, max_tokens=120)
    assert transport.used == model.requests_used == 1


def test_budget_model_only_exposes_integer_usage_counters() -> None:
    response = httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": "fixture"}}],
            "usage": {"total_tokens": 12, "cost": 0, "prompt_tokens_details": {"cached": 1}},
        },
    )
    with httpx.Client(transport=httpx.MockTransport(lambda request: response)) as client:
        model = BudgetModel(client, ["fixture:free"])
        assert model.complete([], json_mode=True, max_tokens=120) == "fixture"
        assert model.usage_totals == {"total_tokens": 12}


def test_two_mode_retrieval_eval_is_entirely_offline(
    db: Session, tmp_path: Path, monkeypatch: Any
) -> None:
    settings = build_test_settings(storage_root=str(tmp_path / "storage"))
    bot, chunks = corpus(db, settings)
    cases = bind_cases(load_cases(DEFAULT_CASES), chunks)
    texts = [" ".join(part for part in (c.title, c.heading, c.text) if part) for c in chunks]
    texts += [case["question"] for case in cases]
    cached = cache_embeddings(HashEmbedder("ollama:bge-m3"), texts, tmp_path / "cache.jsonl")

    def no_http(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("Offline eval must never call an HTTP embedder")

    monkeypatch.setattr(HTTPEmbedder, "embed", no_http)
    embed_demo(db, bot, settings, cached)
    metrics = evaluate(db, bot, cases, settings, cached, tmp_path / "retrieval-results.jsonl")
    assert metrics["modes"]["fts_only"]["cases"] == metrics["modes"]["hybrid"]["cases"] == 32
    rows = [
        json.loads(line) for line in (tmp_path / "retrieval-results.jsonl").read_text().splitlines()
    ]
    assert len(rows) == 64 and all(row["actual_mode"] == row["requested_mode"] for row in rows)
    assert all(not row["generation_measured"] for row in rows)
    metrics["synthetic_vectors"] = True
    metrics["embedding_model_label"] = "synthetic lexical vectors; bge-m3 semantics UNVERIFIED"
    (tmp_path / "summary.json").write_text(json.dumps(metrics, indent=2))
    with pytest.raises(ValueError, match="already exist"):
        evaluate(db, bot, cases, settings, cached, tmp_path / "retrieval-results.jsonl")


def test_refusal_metrics_and_threshold_overlap_do_not_claim_generation_quality() -> None:
    rows = [
        {
            "type": "unanswerable",
            "unanswerable": True,
            "gate_passed": False,
            "hit_at_k": False,
            "expected_chunk_ids": [],
            "candidates": [{"chunk_id": "a", "vector_similarity": 0.9}],
        },
        {
            "type": "paraphrase",
            "unanswerable": False,
            "gate_passed": True,
            "hit_at_k": True,
            "expected_chunk_ids": ["b"],
            "candidates": [{"chunk_id": "b", "vector_similarity": 0.8}],
        },
    ]
    result = summarize(rows)
    assert result["gate_refusal_correctness"] == [1, 1]
    assert result["generation_metrics"].startswith("PENDING")
    proposal = threshold_proposal(rows)
    assert proposal["proposed_cosine_floor"] is None and not proposal["automatically_applied"]
