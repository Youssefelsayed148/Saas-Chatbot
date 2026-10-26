"""R3c-1: every provider attempt is recorded — model, attempt number, HTTP status, a
sanitized provider error code, finish reason and content state — in the client's
attempt log, in ``rag_trace.provider_error`` and in the ``chat.provider_failure``
log line. Mocked HTTP only; nothing here reads a key or calls a real model."""

import json
import logging
import re
from typing import Any

import httpx
import pytest
from sqlalchemy.orm import Session as OrmSession

import tests.retrieval_helpers as _rh  # noqa: F401 — registers the corpus fixture
from app.chat import providers
from app.chat.providers import OpenAICompatibleModel, ProviderError
from tests.test_chat import answer

corpus = _rh.corpus
MESSAGES = [{"role": "user", "content": "hi"}]


def client(
    handler: Any, *, model: str = "vendor/m", fallbacks: list[str] | None = None, free: bool = False
) -> OpenAICompatibleModel:
    return OpenAICompatibleModel(
        base_url="https://llm.test/v1",
        api_key="sk-secret-key",
        model=model,
        fallback_models=fallbacks,
        free_only=free,
        transport=httpx.MockTransport(handler),
    )


def reply_200(content: object, finish: str = "stop") -> httpx.Response:
    return httpx.Response(
        200, json={"choices": [{"message": {"content": content}, "finish_reason": finish}]}
    )


@pytest.mark.parametrize(
    ("status", "body", "code", "blocked"),
    [
        (
            404,
            {"error": {"message": "The model `gpt-x` does not exist", "code": "model_not_found"}},
            "model_not_found",
            False,
        ),
        (
            401,
            {
                "error": {
                    "message": "Incorrect API key provided: sk-secret-key",
                    "code": "invalid_api_key",
                }
            },
            "invalid_api_key",
            True,
        ),
        (
            429,
            {"error": {"message": "You exceeded your quota", "type": "insufficient_quota"}},
            "insufficient_quota",
            True,  # one model: nothing to move on to
        ),
        (
            402,
            {"error": {"message": "Insufficient credits", "code": 402}},
            "insufficient_quota",
            True,
        ),
        (500, {"error": {"message": "boom"}}, None, False),
        (400, {"error": {"message": "Some other bad request"}}, None, False),
    ],
)
def test_error_responses_are_classified_without_keeping_the_body(
    status: int, body: dict[str, Any], code: str | None, blocked: bool
) -> None:
    model = client(lambda request: httpx.Response(status, json=body))
    with pytest.raises(ProviderError):
        model.complete(MESSAGES, json_mode=True, max_tokens=50)
    (attempt,) = model.attempt_log
    assert attempt["attempt"] == 1 and attempt["model"] == "vendor/m"
    assert attempt["http_status"] == status and attempt["error_code"] == code
    assert attempt["outcome"] == ("blocked" if blocked else "failed")
    assert model.blocked is blocked
    dumped = json.dumps(model.attempt_log)
    for secret in ("sk-secret-key", "Incorrect API key", "exceeded your quota", "Bearer"):
        assert secret not in dumped


def test_rate_limited_without_a_code_is_named_from_the_status() -> None:
    model = client(lambda request: httpx.Response(429, text="slow down"), fallbacks=["vendor/b"])
    with pytest.raises(ProviderError):
        model.complete(MESSAGES, json_mode=False, max_tokens=50)
    assert [item["error_code"] for item in model.attempt_log] == ["rate_limited", "rate_limited"]


def test_a_200_with_empty_content_records_finish_reason_and_content_state() -> None:
    model = client(lambda request: reply_200(None, "length"))
    with pytest.raises(ProviderError):
        model.complete(MESSAGES, json_mode=True, max_tokens=50)
    (attempt,) = model.attempt_log
    assert attempt["outcome"] == "unusable" and attempt["http_status"] == 200
    assert attempt["finish_reason"] == "length" and attempt["content"] == "empty"


def test_a_200_with_cut_off_json_is_truncated_and_plain_text_is_not_json() -> None:
    cut = client(lambda request: reply_200('{"can_answer": tr', "length"))
    assert cut.complete(MESSAGES, json_mode=True, max_tokens=50) == '{"can_answer": tr'
    assert cut.attempt_log[0]["content"] == "truncated"
    plain = client(lambda request: reply_200("Sure, 14 days."))
    assert plain.complete(MESSAGES, json_mode=True, max_tokens=50) == "Sure, 14 days."
    assert plain.attempt_log[0]["content"] == "not_json"
    assert plain.attempt_log[0]["outcome"] == "unusable"


def test_timeouts_and_network_errors_are_attempts_without_a_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if json.loads(request.content)["model"] == "vendor/m":
            raise httpx.ReadTimeout("slow", request=request)
        raise httpx.ConnectError("down", request=request)

    model = client(handler, fallbacks=["vendor/b"])
    with pytest.raises(ProviderError):
        model.complete(MESSAGES, json_mode=False, max_tokens=50)
    assert [(a["outcome"], a["http_status"]) for a in model.attempt_log] == [
        ("timeout", None),
        ("network", None),
    ]


def test_the_compat_retry_is_marked_on_the_attempt() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "temperature" in json.loads(request.content):
            return httpx.Response(
                400, json={"error": {"message": "Unsupported value: temperature"}}
            )
        return reply_200('{"a": 1}')

    providers._COMPAT_PROFILE.clear()
    try:
        model = client(handler, model="vendor/reasoner")
        model.complete(MESSAGES, json_mode=True, max_tokens=50)
        assert model.attempt_log[0]["outcome"] == "ok"
        assert model.attempt_log[0]["compat_retry"] is True
    finally:
        providers._COMPAT_PROFILE.clear()


def test_streaming_records_the_same_fields() -> None:
    def not_found(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404, json={"error": {"message": "no such model", "code": "model_not_found"}}
        )

    model = client(not_found)
    with pytest.raises(ProviderError):
        list(model.stream_complete(MESSAGES, max_tokens=50))
    (attempt,) = model.attempt_log
    assert attempt["http_status"] == 404 and attempt["error_code"] == "model_not_found"

    cut_off = b'data: {"choices":[{"delta":{},"finish_reason":"length"}]}\n\ndata: [DONE]\n\n'
    empty = client(lambda request: httpx.Response(200, content=cut_off))
    with pytest.raises(ProviderError):
        list(empty.stream_complete(MESSAGES, max_tokens=50))
    (attempt,) = empty.attempt_log
    assert attempt["content"] == "empty" and attempt["finish_reason"] == "length"
    assert attempt["outcome"] == "unusable"


def test_a_failed_turn_carries_the_attempts_in_the_trace_and_the_log(
    app: Any, db: OrmSession, corpus: dict[str, Any], caplog: Any
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404, json={"error": {"message": "The model does not exist", "code": "model_not_found"}}
        )

    model = client(handler, model="gpt-gone")
    with caplog.at_level(logging.WARNING):
        reply = answer(db, corpus, model, "What are your opening hours?", tier="premium")
    assert reply.kind == "busy"
    detail = reply.trace["provider_error"]
    assert detail["status"] == "failed" and detail["http_status"] == 404
    assert detail["model"] == "gpt-gone" and detail["error_code"] == "model_not_found"
    assert detail["attempts"][0]["attempt"] == 1
    line = next(
        r.getMessage() for r in caplog.records if r.getMessage().startswith("chat.provider_failure")
    )
    assert "http_status=404" in line and "error_code=model_not_found" in line
    assert re.search(r"attempts=gpt-gone:failed:404:model_not_found", line)
    for secret in ("sk-secret-key", "Bearer", "Authorization", "opening hours"):
        assert secret not in caplog.text
