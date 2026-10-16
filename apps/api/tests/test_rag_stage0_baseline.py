"""Stage 0 request-budget checks use mock HTTP only, never owner credentials."""

import argparse
import json
import os
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import Engine

from app.chat.providers import ExtractiveStubModel, ProviderError
from scripts import rag_stage0_baseline as baseline
from scripts.rag_stage0_baseline import (
    BudgetModel,
    StopBaseline,
    append_record,
    load_credentials,
    prepare_database,
    started_ids,
)


@pytest.mark.parametrize("status", [402, 429])
def test_quota_stops_before_fallback(status: int) -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(status, json={"error": {"message": "quota"}})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        model = BudgetModel(client, ["first:free", "second:free", "third:free"])
        with pytest.raises(StopBaseline, match="quota_or_rate_limit"):
            model.complete([], json_mode=True, max_tokens=64)
        assert len(calls) == model.requests_used == 1


def test_fallback_once_and_preprocessing_never_calls_provider() -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(503, json={"error": {"message": "unavailable"}})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        model = BudgetModel(client, ["first:free", "second:free", "third:free"])
        with pytest.raises(ProviderError):
            model.complete([], json_mode=False, max_tokens=64)
        assert not calls
        with pytest.raises(ProviderError):
            model.complete([], json_mode=True, max_tokens=64)
        assert len(calls) == model.requests_used == 2
        with pytest.raises(StopBaseline, match="question_budget_exhausted"):
            model.complete([], json_mode=True, max_tokens=64)
        assert len(calls) == 2


def test_successful_generation_makes_one_request() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content)["model"] == "first:free"
        return httpx.Response(200, json={"choices": [{"message": {"content": "answer"}}]})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        model = BudgetModel(client, ["first:free", "second:free"])
        assert model.complete([], json_mode=True, max_tokens=64) == "answer"
        assert model.requests_used == 1


def test_checkpoint_survives_interrupt_and_redacts_key(tmp_path: Path) -> None:
    journal = tmp_path / "journal.jsonl"
    append_record(journal, {"id": "first", "event": "started"})
    assert started_ids(journal) == {"first"}
    results = tmp_path / "results.jsonl"
    append_record(results, {"answer": "fictional-secret"}, secret="fictional-secret")
    assert "fictional-secret" not in results.read_text()


def test_credentials_are_process_environment_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CHAT_OPENROUTER_API_KEY", "fake")
    monkeypatch.setenv("CHAT_FREE_MODEL_CHAIN", '["fixture:free"]')
    assert load_credentials() == ("fake", ["fixture:free"])
    assert os.environ["ENVIRONMENT"] == "test"


@pytest.mark.parametrize("status", [401, 403])
def test_bad_authorization_stops_without_spending_on_fallback(status: int) -> None:
    with httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(status))
    ) as client:
        model = BudgetModel(client, ["first:free", "second:free"])
        with pytest.raises(StopBaseline, match="provider_authorization_failed"):
            model.complete([], json_mode=True, max_tokens=64)
        assert model.requests_used == 1


def test_quota_in_success_status_body_still_stops() -> None:
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"error": {"code": 429}})
        )
    ) as client:
        model = BudgetModel(client, ["first:free", "second:free"])
        with pytest.raises(StopBaseline, match="quota_or_rate_limit"):
            model.complete([], json_mode=True, max_tokens=64)
        assert model.requests_used == 1


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://postgres@localhost/customer_dev",
        "postgresql://postgres@external.example.com/clinic_test",
        "postgresql://postgres@localhost/production_test",
    ],
)
def test_baseline_refuses_non_disposable_targets(url: str) -> None:
    with pytest.raises(ValueError, match="disposable"):
        prepare_database(url)


def test_real_fts_pipeline_checkpoints_and_never_replays(
    engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cases = tmp_path / "cases.jsonl"
    cases.write_text(
        json.dumps(
            {
                "id": "arabic",
                "question": "كم تكلفة الكشف؟",
                "history": [],
                "expected_source": "pricing-ar",
            }
        )
        + "\n"
        + json.dumps(
            {
                "id": "hours",
                "question": "What are your opening hours?",
                "history": [],
                "expected_source": "hours",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        body = json.loads(request.content)
        content = ExtractiveStubModel().complete(
            body["messages"], json_mode=True, max_tokens=body["max_tokens"]
        )
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    real_client = httpx.Client

    def offline_client(**kwargs: Any) -> httpx.Client:
        return real_client(transport=httpx.MockTransport(respond), **kwargs)

    monkeypatch.setattr(httpx, "Client", offline_client)
    monkeypatch.setattr(baseline, "load_credentials", lambda: ("fake", ["fixture:free"]))
    # The shared fixture has already migrated this guarded disposable database.
    monkeypatch.setattr(baseline, "prepare_database", lambda url: None)
    monkeypatch.delenv("CHAT_STUB_MODEL", raising=False)
    args = argparse.Namespace(
        database_url=engine.url.render_as_string(hide_password=False),
        cases=cases,
        output=tmp_path / "results",
        scoped_dotenv=None,
        resume=False,
    )
    assert baseline.run(args) == 0
    rows = [json.loads(line) for line in (args.output / "results.jsonl").read_text().splitlines()]
    assert len(rows) == 2
    assert rows[0]["kind"] == "answer"
    assert rows[0]["hit_at_8"] is True
    assert rows[0]["citations_valid"] is True
    assert rows[0]["requests_used"] == 1
    assert rows[0]["preprocessing_skipped"] == 0
    assert rows[1]["hit_at_8"] is True
    assert rows[1]["citations_valid"] is True
    assert rows[1]["requests_used"] == 1
    assert len(calls) == 2
    with pytest.raises(ValueError, match="replay"):
        baseline.run(args)
    args.resume = True
    assert baseline.run(args) == 0
    assert len(calls) == 2
    args.retrieval_only = True
    assert baseline.run(args) == 0
    assert len((args.output / "retrieval-results.jsonl").read_text().splitlines()) == 2
    assert len(calls) == 2


def test_follow_up_history_goes_to_generation_without_rewrite() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        messages = json.loads(request.content)["messages"]
        assert [item["content"] for item in messages] == ["rules", "Earlier question", "And now?"]
        return httpx.Response(200, json={"choices": [{"message": {"content": "answer"}}]})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        model = BudgetModel(client, ["fixture:free"], ["Earlier question"])
        assert (
            model.complete(
                [{"role": "system", "content": "rules"}, {"role": "user", "content": "And now?"}],
                json_mode=True,
                max_tokens=64,
            )
            == "answer"
        )
        assert model.requests_used == 1
