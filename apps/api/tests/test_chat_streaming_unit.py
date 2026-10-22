# ruff: noqa: UP031
"""S.1 / S.3 / S.6 (DB-free): provider streaming and the streaming model
wrapper, against scripted fake streams. No network, no paid provider."""

import json
from collections.abc import Iterator

import httpx
import pytest

from app.chat import prompts
from app.chat.providers import (
    ChatModel,
    ExtractiveStubModel,
    FakeChatModel,
    OpenAICompatibleModel,
    ProviderError,
)
from app.chat.streaming import (
    StreamCancelled,
    StreamingReplyModel,
    evidence_ids,
    wrap_for_streaming,
)

ID_A = "11111111-1111-1111-1111-111111111111"
CANNED = "I don't have that information."


@pytest.fixture(autouse=True)
def clean_tables() -> Iterator[None]:
    """Override the DB-backed autouse fixture: these tests are DB-free."""
    yield


def messages() -> list[dict[str, str]]:
    system = prompts.system_prompt(
        assistant_name="Aida",
        business_name="Acme",
        business_description="",
        support_contact="help@acme.test",
        language="en",
        evidence_block=prompts.evidence_block([(ID_A, "Hours", "We open 9 to 5.")]),
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": "hours?"}]


def reply(answer: str, *, can_answer: bool = True, sources: list[str] | None = None) -> str:
    return json.dumps(
        {
            "can_answer": can_answer,
            "sources": [ID_A] if sources is None else sources,
            "answer": answer,
        },
        ensure_ascii=False,
    )


def pieces(raw: str, size: int = 5) -> list[str]:
    return [raw[i : i + size] for i in range(0, len(raw), size)]


class Harness:
    def __init__(self, model: ChatModel, cancelled: bool = False) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []
        self.cancel_flag = cancelled
        self.model: StreamingReplyModel = wrap_for_streaming(
            model,
            emit=lambda kind, data: self.events.append((kind, data)),
            cannot_confirm_text=CANNED,
            cancelled=lambda: self.cancel_flag,
        )

    def run(self) -> str:
        return self.model.complete(messages(), json_mode=True, max_tokens=300)

    def kinds(self) -> list[str]:
        return [kind for kind, _ in self.events]

    def text(self) -> str:
        return "".join(str(data["text"]) for kind, data in self.events if kind == "delta")


def test_evidence_ids_come_from_the_evidence_block() -> None:
    assert evidence_ids(messages()[0]["content"]) == frozenset({ID_A})
    assert evidence_ids("no evidence block here") == frozenset()


def test_streams_released_text_then_returns_the_full_json() -> None:
    raw = reply("We open 9 to 5.")
    harness = Harness(FakeChatModel(stream_chunks=[pieces(raw)]))
    assert harness.run() == raw
    assert harness.kinds()[0] == "verdict"
    assert harness.kinds().count("verdict") == 1
    assert set(harness.kinds()) == {"verdict", "delta"}
    assert harness.text() == "We open 9 to 5."
    stats = harness.model.stats
    assert stats.streamed and stats.mode == "streamed"
    assert stats.ttft_ms is not None and stats.ttft_ms >= 0


def test_arabic_answer_streams_intact() -> None:
    answer = "نفتح من التاسعة حتى الخامسة"
    harness = Harness(FakeChatModel(stream_chunks=[pieces(reply(answer), 3)]))
    harness.run()
    assert harness.text() == answer


@pytest.mark.parametrize(
    "raw",
    [
        reply("Model text", can_answer=False, sources=[]),
        reply("Model text", can_answer=True, sources=[]),
        reply("Model text", can_answer=True, sources=["99999999-9999-9999-9999-999999999999"]),
        reply(
            "Model text", can_answer=True, sources=[ID_A, "99999999-9999-9999-9999-999999999999"]
        ),
    ],
)
def test_unreleased_verdicts_send_only_the_canned_event(raw: str) -> None:
    model = FakeChatModel(stream_chunks=[pieces(raw)])
    harness = Harness(model)
    result = json.loads(harness.run())
    assert harness.kinds() == ["cannot_confirm"]
    assert harness.events[0][1] == {"text": CANNED}
    assert "Model text" not in json.dumps(harness.events)
    # chat_answer will validate this exact JSON: canned, not model text.
    assert result == {"can_answer": False, "sources": [], "answer": CANNED}
    assert model.stream_closed  # provider call stopped early
    assert harness.model.stats.mode == "canned"


@pytest.mark.parametrize(
    "raw",
    [
        '{"answer": "secret", "can_answer": true, "sources": ["%s"]}' % ID_A,
        '{"sources": ["%s"], "can_answer": true, "answer": "secret"}' % ID_A,
        '{"can_answer": true, "can_answer": true, "sources": ["%s"], "answer": "secret"}' % ID_A,
        "this is not json at all but contains secret",
        '```json\n{"can_answer": true, "sources": ["%s"], "answer": "secret"}\n```' % ID_A,
    ],
)
def test_invalid_structure_falls_back_to_buffered_with_no_events(raw: str) -> None:
    harness = Harness(FakeChatModel(stream_chunks=[pieces(raw)]))
    assert harness.run() == raw  # untouched: chat_answer's strict parse decides
    assert harness.events == []
    assert harness.model.stats.mode == "buffered"
    assert harness.model.stats.invalid_reason is not None


def test_truncated_before_verdict_sends_nothing() -> None:
    raw = reply("Model text")
    harness = Harness(FakeChatModel(stream_chunks=[pieces(raw[: raw.index("sources") + 12])]))
    harness.run()
    assert harness.events == []


def test_truncated_after_release_returns_incomplete_json_for_strict_rejection() -> None:
    raw = reply("a long answer that never finishes")
    cut = raw[: raw.index("never")]
    harness = Harness(FakeChatModel(stream_chunks=[pieces(cut)]))
    returned = harness.run()
    assert returned == cut
    with pytest.raises(ValueError):
        json.loads(returned)  # chat_answer treats this as a busy turn; done replaces the text


def test_provider_that_cannot_stream_uses_buffered_complete() -> None:
    raw = reply("We open 9 to 5.")
    model = FakeChatModel([raw])  # no stream script -> StreamUnsupported
    harness = Harness(model)
    assert harness.run() == raw
    assert harness.events == []
    assert harness.model.stats.mode == "unsupported"
    assert harness.model.stats.streamed is False


def test_non_json_calls_pass_straight_through() -> None:
    model = FakeChatModel(["condensed question"])
    harness = Harness(model)
    out = harness.model.complete(messages(), json_mode=False, max_tokens=50)
    assert out == "condensed question" and harness.events == []


def test_provider_error_before_any_text_propagates() -> None:
    harness = Harness(FakeChatModel(stream_chunks=[["!error"]]))
    with pytest.raises(ProviderError):
        harness.run()
    assert harness.events == []


def test_provider_error_after_text_propagates_after_partial_release() -> None:
    raw = reply("We open 9 to 5.")
    harness = Harness(FakeChatModel(stream_chunks=[[*pieces(raw)[:20], "!error"]]))
    with pytest.raises(ProviderError):
        harness.run()
    assert "verdict" in harness.kinds()  # text was released; done/error replaces it


def test_cancel_stops_the_provider_stream_and_raises() -> None:
    model = FakeChatModel(stream_chunks=[pieces(reply("We open 9 to 5."))])
    harness = Harness(model, cancelled=True)
    with pytest.raises(StreamCancelled):
        harness.run()
    assert model.stream_closed
    assert harness.events == []


def test_cancel_midway_closes_the_provider_stream() -> None:
    raw = reply("We open 9 to 5, every day of the week.")
    model = FakeChatModel(stream_chunks=[pieces(raw, 4)])
    harness = Harness(model)
    seen = {"count": 0}

    def cancelled() -> bool:
        seen["count"] += 1
        return seen["count"] > 6

    harness.model._cancelled = cancelled
    with pytest.raises(StreamCancelled):
        harness.run()
    assert model.stream_closed


def test_stub_wrapper_keeps_stub_identity_for_metering() -> None:
    harness = Harness(ExtractiveStubModel())
    assert isinstance(harness.model, ExtractiveStubModel)
    assert harness.model.usage_totals is None


def test_stub_streams_end_to_end_in_the_new_key_order() -> None:
    stub = ExtractiveStubModel()
    system = prompts.system_prompt(
        assistant_name="Aida",
        business_name="Acme",
        business_description="",
        support_contact="x",
        language="en",
        evidence_block=prompts.evidence_block([(ID_A, "Hours", "We open 9 to 5 every day.")]),
    )
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": "open hours"}]
    raw = "".join(stub.stream_complete(msgs, max_tokens=100))
    assert list(json.loads(raw)) == ["can_answer", "sources", "answer"]
    events: list[tuple[str, dict[str, object]]] = []
    wrapped = wrap_for_streaming(
        ExtractiveStubModel(),
        emit=lambda kind, data: events.append((kind, data)),
        cannot_confirm_text=CANNED,
        cancelled=lambda: False,
    )
    assert wrapped.complete(msgs, json_mode=True, max_tokens=100) == raw
    assert (
        "".join(str(d["text"]) for k, d in events if k == "delta")
        == "Hours We open 9 to 5 every day."
    )


# --- OpenAI-compatible SSE client ------------------------------------------


def sse_body(raw: str, *, usage: bool = True, size: int = 6) -> bytes:
    lines = []
    for i in range(0, len(raw), size):
        chunk = {"choices": [{"delta": {"content": raw[i : i + size]}}]}
        lines.append(f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n")
    lines.append(": keep-alive\n\n")
    if usage:
        final = {
            "choices": [],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15, "cost": 0},
        }
        lines.append(f"data: {json.dumps(final)}\n\n")
    lines.append("data: [DONE]\n\n")
    return "".join(lines).encode()


def client(
    handler: httpx.MockTransport, fallbacks: list[str] | None = None
) -> OpenAICompatibleModel:
    return OpenAICompatibleModel(
        base_url="https://provider.test/v1",
        api_key="k-test",
        model="a:free",
        fallback_models=fallbacks if fallbacks is not None else ["b:free"],
        free_only=True,
        transport=handler,
    )


def test_openai_stream_yields_fragments_and_records_usage() -> None:
    raw = reply("مرحباً — we open 9 to 5.")
    bodies: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, content=sse_body(raw))

    model = client(httpx.MockTransport(handler))
    assert "".join(model.stream_complete(messages(), max_tokens=100)) == raw
    assert bodies[0]["stream"] is True
    assert bodies[0]["response_format"] == {"type": "json_object"}
    assert bodies[0]["model"] == "a:free"
    assert model.usage_totals == {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
    assert model.model_used == "a:free"


def test_openai_stream_falls_back_to_the_next_model_before_any_text() -> None:
    raw = reply("ok")
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        model_id = json.loads(request.content)["model"]
        seen.append(model_id)
        if model_id == "a:free":
            return httpx.Response(500, content=b"boom")
        return httpx.Response(200, content=sse_body(raw))

    model = client(httpx.MockTransport(handler))
    assert "".join(model.stream_complete(messages(), max_tokens=100)) == raw
    assert seen == ["a:free", "b:free"]
    assert model.model_used == "b:free"
    assert model.requests_used == 2


def test_openai_stream_auth_or_quota_blocks_the_instance() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, content=b"slow down")

    model = client(httpx.MockTransport(handler))
    with pytest.raises(ProviderError):
        list(model.stream_complete(messages(), max_tokens=100))
    assert model.blocked is True
    with pytest.raises(ProviderError):
        list(model.stream_complete(messages(), max_tokens=100))
    assert model.requests_used == 1  # the second call never left the process


def test_openai_stream_empty_body_counts_as_failure_and_tries_next() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if json.loads(request.content)["model"] == "a:free":
            return httpx.Response(200, content=b"data: [DONE]\n\n")
        return httpx.Response(200, content=sse_body(reply("ok")))

    model = client(httpx.MockTransport(handler))
    assert "".join(model.stream_complete(messages(), max_tokens=100)) == reply("ok")
    assert model.ambiguous_attempts == 1


def test_openai_stream_all_models_failing_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, content=b"down")

    model = client(httpx.MockTransport(handler))
    with pytest.raises(ProviderError):
        list(model.stream_complete(messages(), max_tokens=100))


def test_openai_stream_closing_the_iterator_is_clean() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=sse_body(reply("a long answer " * 20)))

    model = client(httpx.MockTransport(handler))
    iterator = model.stream_complete(messages(), max_tokens=100)
    assert next(iterator)
    iterator.close()  # type: ignore[attr-defined]


def test_base_model_stream_complete_is_unsupported() -> None:
    class Plain(ChatModel):
        def complete(
            self, messages: list[dict[str, str]], *, json_mode: bool, max_tokens: int
        ) -> str:
            return "x"

    from app.chat.providers import StreamUnsupported

    with pytest.raises(StreamUnsupported):
        Plain().stream_complete([], max_tokens=1)


# --- the async relay (worker thread -> SSE text), run_turn stubbed ----------------


def _turn() -> object:
    from uuid import uuid4

    from app.chat.streaming import StreamTurn

    return StreamTurn(
        tenant_id=uuid4(),
        bot_id=uuid4(),
        visitor_session_id=uuid4(),
        conversation_id=uuid4(),
        text="hi",
        language_hint=None,
        settings=None,  # type: ignore[arg-type]
        model=FakeChatModel(),
    )


async def _collect(agen: object) -> list[str]:
    return [chunk async for chunk in agen]  # type: ignore[attr-defined]


def test_relay_orders_events_and_ends_with_done(monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio

    from app.chat import streaming

    def fake_run_turn(turn: object, emit: object, cancelled: object) -> dict[str, object]:
        emit("verdict", {"can_answer": True, "released": True})  # type: ignore[operator]
        emit("delta", {"text": "مرحباً"})  # type: ignore[operator]
        return {"ai_message": {"text": "مرحباً"}}

    monkeypatch.setattr(streaming, "run_turn", fake_run_turn)
    chunks = asyncio.run(_collect(streaming.stream_events(_turn(), lambda p: p)))  # type: ignore[arg-type]
    assert chunks[0] == ": stream\n\n"
    assert [c.split("\n")[0] for c in chunks[1:]] == [
        "event: verdict",
        "event: delta",
        "event: done",
    ]
    assert "مرحباً" in chunks[2]  # non-ASCII is sent as UTF-8, not \u escapes


def test_relay_maps_errors_without_leaking_internals(monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio

    from app.chat import streaming
    from app.core.errors import ApiError

    def quota(turn: object, emit: object, cancelled: object) -> dict[str, object]:
        raise ApiError(429, "QUOTA_EXCEEDED", "limit reached")

    def boom(turn: object, emit: object, cancelled: object) -> dict[str, object]:
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(streaming, "run_turn", quota)
    out = "".join(asyncio.run(_collect(streaming.stream_events(_turn(), lambda p: p))))  # type: ignore[arg-type]
    assert "event: error" in out and "QUOTA_EXCEEDED" in out
    monkeypatch.setattr(streaming, "run_turn", boom)
    out = "".join(asyncio.run(_collect(streaming.stream_events(_turn(), lambda p: p))))  # type: ignore[arg-type]
    assert "INTERNAL_ERROR" in out and "secret internal detail" not in out


def test_relay_closing_the_generator_flags_the_worker_to_cancel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio
    import threading
    import time

    from app.chat import streaming

    seen_cancel = threading.Event()

    def slow(turn: object, emit: object, cancelled: object) -> dict[str, object]:
        emit("delta", {"text": "a"})  # type: ignore[operator]
        deadline = time.time() + 5
        while time.time() < deadline:
            if cancelled():  # type: ignore[operator]
                seen_cancel.set()
                raise StreamCancelled()
            time.sleep(0.01)
        return {}

    monkeypatch.setattr(streaming, "run_turn", slow)

    async def go() -> None:
        agen = streaming.stream_events(_turn(), lambda p: p)  # type: ignore[arg-type]
        async for chunk in agen:
            if chunk.startswith("event: delta"):
                break
        await agen.aclose()

    asyncio.run(go())
    assert seen_cancel.wait(timeout=5)
