"""R3c-2/3: the free chain tries every configured model in order, a reasoning model
gets a larger completion cap, and a cut-off reply moves on to the next model.
Mocked HTTP only."""

from typing import Any

import httpx
import pytest
from sqlalchemy.orm import Session as OrmSession

import tests.retrieval_helpers as _rh  # noqa: F401 — registers the corpus fixture
from app.chat.providers import OpenAICompatibleModel, ProviderError
from tests.test_chat import EchoFirstEvidenceId, answer

corpus = _rh.corpus
MESSAGES = [{"role": "user", "content": "hi"}]
CHAIN = ["a:free", "b:free", "c:free"]
GOOD = '{"answer": "ok", "can_answer": true, "sources": []}'


def chain_model(statuses: dict[str, httpx.Response]) -> tuple[OpenAICompatibleModel, list[str]]:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        model = json.loads(request.content)["model"]
        seen.append(model)
        return statuses[model]

    return (
        OpenAICompatibleModel(
            base_url="https://llm.test/v1",
            api_key="k",
            model=CHAIN[0],
            fallback_models=CHAIN[1:],
            free_only=True,
            transport=httpx.MockTransport(handler),
        ),
        seen,
    )


def ok(content: str = GOOD, finish: str = "stop") -> httpx.Response:
    return httpx.Response(
        200, json={"choices": [{"message": {"content": content}, "finish_reason": finish}]}
    )


def limited() -> httpx.Response:
    return httpx.Response(429, json={"error": {"message": "temporarily rate-limited upstream"}})


def test_two_rate_limits_then_the_third_model_answers() -> None:
    model, seen = chain_model({"a:free": limited(), "b:free": limited(), "c:free": ok()})
    assert model.complete(MESSAGES, json_mode=True, max_tokens=50) == GOOD
    assert seen == CHAIN and model.model_used == "c:free"
    assert [a["outcome"] for a in model.attempt_log] == ["failed", "failed", "ok"]
    assert [a["error_code"] for a in model.attempt_log[:2]] == ["rate_limited"] * 2


def test_every_model_failing_records_every_attempt() -> None:
    model, seen = chain_model({name: limited() for name in CHAIN})
    with pytest.raises(ProviderError):
        model.complete(MESSAGES, json_mode=True, max_tokens=50)
    assert seen == CHAIN and len(model.attempt_log) == 3


def test_a_payment_error_stops_the_chain() -> None:
    denied = httpx.Response(402, json={"error": {"message": "Insufficient credits"}})
    model, seen = chain_model({"a:free": denied, "b:free": ok(), "c:free": ok()})
    with pytest.raises(ProviderError):
        model.complete(MESSAGES, json_mode=True, max_tokens=50)
    assert seen == ["a:free"] and model.blocked


@pytest.mark.parametrize("head", [ok("", "length"), ok('{"answer": "cut', "length")])
def test_a_cut_off_reply_moves_on_to_the_next_model(head: httpx.Response) -> None:
    model, seen = chain_model({"a:free": head, "b:free": ok(), "c:free": ok()})
    assert model.complete(MESSAGES, json_mode=True, max_tokens=50) == GOOD
    assert seen == ["a:free", "b:free"]
    first = model.attempt_log[0]
    assert first["outcome"] == "unusable" and first["finish_reason"] == "length"
    assert first["content"] in ("empty", "truncated")


def test_the_free_chain_gets_the_larger_cap_and_premium_keeps_its_own(
    app: Any, db: OrmSession, corpus: dict[str, Any]
) -> None:
    settings = corpus["settings"]
    assert settings.chat_max_tokens_free == 1500 and settings.chat_max_tokens == 700

    free = EchoFirstEvidenceId("Open 9 to 5.", True)
    free.free_only = True  # type: ignore[attr-defined]
    answer(db, corpus, free, "What are your opening hours?")
    premium = EchoFirstEvidenceId("Open 9 to 5.", True)
    answer(db, corpus, premium, "What are your opening hours?", tier="premium")
    assert free.calls[-1][2] == settings.chat_max_tokens_free
    assert premium.calls[-1][2] == settings.chat_max_tokens
