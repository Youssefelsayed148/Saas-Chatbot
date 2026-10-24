"""R3-3 (#93): a 400 that blames temperature / max_tokens is retried once with the
compat profile (no temperature, max_completion_tokens); a working profile is
remembered per model name. Mocked HTTP only."""

import json
from collections.abc import Iterator

import httpx
import pytest

from app.chat import providers
from app.chat.providers import OpenAICompatibleModel, ProviderError

MESSAGES = [{"role": "user", "content": "hi"}]
OK = {"choices": [{"message": {"content": '{"answer": "x"}'}}]}


@pytest.fixture(autouse=True)
def fresh_profiles() -> Iterator[None]:
    providers._COMPAT_PROFILE.clear()
    yield
    providers._COMPAT_PROFILE.clear()


def client(
    handler: httpx.MockTransport,
    *,
    model: str = "vendor/reasoner",
    fallbacks: list[str] | None = None,
) -> OpenAICompatibleModel:
    return OpenAICompatibleModel(
        base_url="https://llm.test/v1",
        api_key="k",
        model=model,
        fallback_models=fallbacks,
        free_only=False,
        transport=handler,
    )


def picky(seen: list[dict[str, object]]) -> httpx.MockTransport:
    """Rejects temperature/max_tokens like a reasoning model; accepts the compat body."""

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body)
        if "temperature" in body or "max_tokens" in body:
            return httpx.Response(
                400,
                json={
                    "error": {
                        "message": "Unsupported parameter: 'max_tokens'. Use max_completion_tokens."
                    }
                },
            )
        return httpx.Response(200, json=OK)

    return httpx.MockTransport(handler)


def test_400_on_temperature_retries_once_with_the_compat_profile() -> None:
    seen: list[dict[str, object]] = []
    model = client(picky(seen))
    assert model.complete(MESSAGES, json_mode=True, max_tokens=300) == '{"answer": "x"}'
    assert len(seen) == 2
    assert seen[0]["temperature"] == 0.2 and seen[0]["max_tokens"] == 300
    assert "temperature" not in seen[1] and "max_tokens" not in seen[1]
    assert seen[1]["max_completion_tokens"] == 300
    assert seen[1]["response_format"] == {"type": "json_object"}
    assert model.last_http_status == 200 and not model.blocked


def test_working_profile_is_remembered_per_model_name() -> None:
    seen: list[dict[str, object]] = []
    handler = picky(seen)
    client(handler).complete(MESSAGES, json_mode=True, max_tokens=300)
    seen.clear()
    # A new client object (a new request) skips the failed attempt for that model...
    client(handler).complete(MESSAGES, json_mode=True, max_tokens=300)
    assert len(seen) == 1 and "max_completion_tokens" in seen[0]
    # ...but another model name still starts with the classic parameters.
    seen.clear()
    client(handler, model="vendor/other").complete(MESSAGES, json_mode=True, max_tokens=300)
    assert len(seen) == 2 and "max_tokens" in seen[0]


def test_other_400_is_not_retried() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(400, json={"error": {"message": "Invalid JSON in messages."}})

    model = client(httpx.MockTransport(handler))
    with pytest.raises(ProviderError):
        model.complete(MESSAGES, json_mode=True, max_tokens=300)
    assert len(calls) == 1 and model.last_http_status == 400
    assert not model.blocked and providers._COMPAT_PROFILE == set()


def test_second_400_is_not_retried_again_and_not_remembered() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(400, json={"error": {"message": "bad temperature"}})

    model = client(httpx.MockTransport(handler))
    with pytest.raises(ProviderError):
        model.complete(MESSAGES, json_mode=True, max_tokens=300)
    assert len(calls) == 2 and providers._COMPAT_PROFILE == set()


@pytest.mark.parametrize("status", [401, 402])
def test_auth_and_payment_still_block(status: int) -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(status, json={"error": {"message": "temperature"}})

    model = client(httpx.MockTransport(handler), fallbacks=["vendor/next"])
    with pytest.raises(ProviderError):
        model.complete(MESSAGES, json_mode=True, max_tokens=300)
    assert len(calls) == 1 and model.blocked and model.last_http_status == status


def test_stream_400_on_max_tokens_retries_once_and_remembers() -> None:
    seen: list[dict[str, object]] = []
    sse = 'data: {"choices": [{"delta": {"content": "hello"}}]}\n\ndata: [DONE]\n\n'

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body)
        if "max_tokens" in body:
            return httpx.Response(400, json={"error": {"message": "max_tokens is not supported"}})
        return httpx.Response(200, text=sse, headers={"content-type": "text/event-stream"})

    transport = httpx.MockTransport(handler)
    first = client(transport)
    assert "".join(first.stream_complete(MESSAGES, max_tokens=300)) == "hello"
    assert len(seen) == 2 and seen[1]["stream"] is True and "max_completion_tokens" in seen[1]
    seen.clear()
    assert "".join(client(transport).stream_complete(MESSAGES, max_tokens=300)) == "hello"
    assert len(seen) == 1 and "max_completion_tokens" in seen[0]
