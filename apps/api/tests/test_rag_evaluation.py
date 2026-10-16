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
    threshold_sweep,
)
from scripts.rag_phase2_eval import (
    DEFAULT_CASES,
    bind_cases,
    cache_embeddings,
    corpus,
    embed_demo,
    evaluate,
    load_cases,
    planned_embedding_texts,
    retrieval_main,
)
from scripts.rag_stage0_baseline import BudgetModel, StopBaseline
from scripts.seed_demo import demo_id
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
    assert len(chunks) == 44 and sum(c.language == "ar" for c in chunks) == 8
    assert sorted(texts) == sorted(planned_embedding_texts(settings))
    assert len(cases) == 76
    assert all(
        any("\u0600" <= ch <= "\u06ff" for ch in c["question"])
        for c in cases
        if c["language"] == "ar"
    )
    assert all(c["unanswerable"] or c["expected_chunk_ids"] for c in cases)
    assert {c.source_id for c in chunks} == {
        demo_id(f"source/{c['expected_source']}") for c in cases if c["expected_source"]
    }
    texts += [case["question"] for case in cases]
    cached = cache_embeddings(
        HashEmbedder("openai:text-embedding-3-large"), texts, tmp_path / "cache.jsonl"
    )

    def no_http(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("Offline eval must never call an HTTP embedder")

    monkeypatch.setattr(HTTPEmbedder, "embed", no_http)
    embed_demo(db, bot, settings, cached)
    metrics = evaluate(db, bot, cases, settings, cached, tmp_path / "retrieval-results.jsonl")
    assert (
        metrics["modes"]["fts_only"]["cases"] == metrics["modes"]["hybrid"]["cases"] == len(cases)
    )
    rows = [
        json.loads(line) for line in (tmp_path / "retrieval-results.jsonl").read_text().splitlines()
    ]
    assert len(rows) == 2 * len(cases) and all(
        row["actual_mode"] == row["requested_mode"] for row in rows
    )
    assert all(not row["generation_measured"] for row in rows)
    metrics["synthetic_vectors"] = True
    metrics["embedding_model_label"] = "synthetic lexical vectors; OpenAI semantics UNVERIFIED"
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


def test_calibration_preflight_prints_cost_before_database_or_provider(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    import sys

    from scripts import rag_phase2_eval as runner

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "calibrate",
            "--database-url",
            "postgresql://postgres@localhost/preflight_test",
            "--output",
            str(tmp_path),
        ],
    )
    monkeypatch.setattr(runner, "planned_embedding_texts", lambda settings: ["x" * 2_000_001])

    def forbidden(*args: Any, **kwargs: Any) -> None:
        pytest.fail("No DB/provider activity allowed above the token budget")

    monkeypatch.setattr(runner, "prepare_database", forbidden)
    monkeypatch.setattr(runner, "from_settings", forbidden)
    with pytest.raises(ValueError, match="2M-token cap"):
        retrieval_main(openai_calibration=True)
    first = json.loads(capsys.readouterr().out.splitlines()[0])
    assert not first["within_budget"] and first["estimated_cost_usd_upper_bound"]
    assert not list(tmp_path.iterdir())


def test_ranking_metrics_use_top_three_and_reciprocal_rank() -> None:
    rows = [
        dict(
            type="paraphrase",
            unanswerable=False,
            gate_passed=True,
            hit_at_k=True,
            hit_at_3=False,
            reciprocal_rank=0.25,
        ),
        dict(
            type="arabic",
            unanswerable=False,
            gate_passed=False,
            hit_at_k=True,
            hit_at_3=True,
            reciprocal_rank=0.5,
        ),
        dict(
            type="unanswerable",
            unanswerable=True,
            gate_passed=True,
            hit_at_k=False,
            hit_at_3=False,
            reciprocal_rank=0.0,
        ),
    ]
    summary = summarize(rows)
    assert summary["hit_at_3"] == 0.5 and summary["mrr"] == 0.375


def test_sweep_counts_leaks_refusals_and_enforces_matched_terms() -> None:
    def evidence(key: str, fts: float, terms: int) -> list[dict[str, Any]]:
        return [
            dict(
                chunk_id=key,
                document_id=key,
                vector_similarity=0.3,
                fts_match=fts,
                matched_terms=terms,
            )
        ]

    rows = [
        dict(
            unanswerable=False,
            expected_chunk_ids=["a"],
            expected_document_ids=["a"],
            evidence=evidence("a", 0.1, 2),
        ),
        dict(
            unanswerable=True,
            expected_chunk_ids=[],
            expected_document_ids=[],
            evidence=evidence("b", 0.01, 1),
        ),
    ]
    sweep = threshold_sweep(rows, "hybrid")
    weak = next(
        s
        for s in sweep["settings"]
        if s["cosine_floor"] is None and s["fts_floor"] == 0.01 and s["min_matched_terms"] == 1
    )
    strict = next(
        s
        for s in sweep["settings"]
        if s["cosine_floor"] is None and s["fts_floor"] == 0.01 and s["min_matched_terms"] == 2
    )
    assert weak["unanswerable_leaks"] == 1 and weak["wrong_refusals"] == 0
    assert strict["unanswerable_leaks"] == strict["wrong_refusals"] == 0
    assert sweep["recommended"]["unanswerable_leaks"] == 0
    assert not sweep["automatically_applied"]


def test_owner_calibration_runner_writes_one_complete_report_without_live_http(
    engine: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import sys

    from scripts import rag_phase2_eval as runner

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "calibrate",
            "--test-vectors",
            "--database-url",
            engine.url.render_as_string(hide_password=False),
            "--output",
            str(tmp_path),
        ],
    )
    monkeypatch.setattr(runner, "prepare_database", lambda url: None)
    monkeypatch.setattr(runner, "create_db_engine", lambda settings: engine)
    monkeypatch.setattr(engine, "dispose", lambda: None)

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("No live HTTP is allowed in calibration tests")

    monkeypatch.setattr(HTTPEmbedder, "embed", forbidden)
    assert retrieval_main() == 0
    first = json.loads(capsys.readouterr().out.splitlines()[0])
    report = json.loads((tmp_path / "calibration-results.json").read_text(encoding="utf-8"))
    assert (
        first["estimated_tokens_upper_bound"] == report["estimate"]["estimated_tokens_upper_bound"]
    )
    assert report["corpus_chunks"] == 44 and report["eval_cases"] == 76
    assert report["synthetic_vectors"] and report["chat_requests_used"] == 0
    assert len(report["retrieval_results"]) == 152
    assert len(report["threshold_sweeps"]["hybrid"]["settings"]) == 75
    assert len(report["threshold_sweeps"]["fts_only"]["settings"]) == 15
    assert report["embedding_usage"]
    assert set(report["recommended_threshold_set"]) == {
        "RETRIEVAL_VECTOR_FLOORS",
        "RETRIEVAL_MIN_FTS_MATCH",
        "RETRIEVAL_MIN_MATCHED_TERMS",
        "status",
    }
    assert all(
        "hit_at_3" in report["modes"][mode] and "mrr" in report["modes"][mode]
        for mode in ("fts_only", "hybrid")
    )
    assert all(
        row["fts_config"] == "simple"
        for row in report["retrieval_results"]
        if row["applied_language"] == "ar"
    )


def test_generation_check_loads_recommendation_before_any_connection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import sys

    from scripts import rag_phase2_eval as runner

    baseline = tmp_path / "baseline.jsonl"
    baseline.write_text("", encoding="utf-8")
    calibration = tmp_path / "calibration.json"
    calibration.write_text(
        json.dumps(
            {
                "synthetic_vectors": False,
                "recommended_threshold_set": {
                    "RETRIEVAL_VECTOR_FLOORS": {},
                    "RETRIEVAL_MIN_FTS_MATCH": 0.05,
                    "RETRIEVAL_MIN_MATCHED_TERMS": 2,
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "generation",
            "--database-url",
            "postgresql://postgres@localhost/unused_test",
            "--output",
            str(tmp_path),
            "--baseline-results",
            str(baseline),
            "--calibration-results",
            str(calibration),
        ],
    )
    monkeypatch.setattr(runner, "load_credentials", lambda: ("synthetic-key", ["fixture:free"]))
    captured: dict[str, Any] = {}

    def settings(**options: Any) -> Any:
        captured.update(options)
        return build_test_settings(**options)

    def forbidden_connection(url: str) -> None:
        raise ValueError("test stops before connecting")

    monkeypatch.setattr(runner, "Settings", settings)
    monkeypatch.setattr(runner, "prepare_database", forbidden_connection)
    with pytest.raises(ValueError, match="test stops before connecting"):
        runner.generation_main()
    assert captured["retrieval_vector_floors"] == {}
    assert captured["retrieval_min_fts_match"] == 0.05
    assert captured["retrieval_min_matched_terms"] == 2
