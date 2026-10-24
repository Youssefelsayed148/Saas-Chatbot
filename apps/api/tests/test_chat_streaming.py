"""S.3 / S.6 / S.7: the SSE chat endpoint end to end (DB-backed, stub model).

Everything runs on the offline stub or a scripted fake model: no network, no
paid provider. Checks the same auth/session/availability/rate-limit gates as
the buffered route, release rules, every fallback, persistence at ``done``,
disconnect handling and the streamed trace fields.
"""

import asyncio
import json
import threading
import time
from collections.abc import Callable, Iterator
from typing import Any
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session as OrmSession

import tests.retrieval_helpers as _rh  # noqa: F401 - registers the corpus fixture
from app.chat.providers import ChatModel, ProviderError
from app.chat.streaming import evidence_ids
from app.db.models import Bot, Message, UsageEvent, VisitorSession
from tests.test_widget_public import (
    _override_widget_settings,
    _set_bot_status,
    app_client,
    client_session,
    make_active_bot_with_knowledge,
)

corpus = _rh.corpus

HOURS_Q = "What are your opening hours?"
OFF_TOPIC_Q = "Do you sell parachutes for elephants?"


def rag_trace(usage: UsageEvent) -> dict[str, Any]:
    trace = dict(usage.payload)["rag_trace"]
    assert isinstance(trace, dict)
    return trace


def parse_sse(body: str) -> list[tuple[str, Any]]:
    events: list[tuple[str, Any]] = []
    for block in body.split("\n\n"):
        name, data = None, None
        for line in block.split("\n"):
            if line.startswith("event: "):
                name = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
        if name is not None:
            events.append((name, data))
    return events


def stream(
    client: TestClient, session: dict[str, Any], text: str = HOURS_Q
) -> tuple[Any, list[tuple[str, Any]]]:
    response = client.post(
        f"/api/public/v1/sessions/{session['session_id']}/messages/stream",
        json={"text": text},
        headers={"X-Session-Token": session["token"]},
    )
    return response, parse_sse(response.text) if response.status_code == 200 else []


def deltas(events: list[tuple[str, Any]]) -> str:
    return "".join(data["text"] for name, data in events if name == "delta")


def names(events: list[tuple[str, Any]]) -> list[str]:
    return [name for name, _ in events]


def messages_of(db: OrmSession, session_id: str) -> list[Message]:
    db.expire_all()
    session = db.get(VisitorSession, UUID(session_id))
    assert session is not None
    return list(
        db.execute(
            select(Message)
            .where(Message.tenant_id == session.tenant_id)
            .order_by(Message.created_at.asc(), Message.id)
        ).scalars()
    )


class ScriptedModel(ChatModel):
    """Streams whatever ``script(chunk_ids)`` returns; ``complete`` answers the
    buffered path with the same JSON so both paths can be compared."""

    def __init__(
        self,
        script: Callable[[list[str]], list[str]] | None,
        *,
        buffered: Callable[[list[str]], str] | None = None,
        fail: bool = False,
    ) -> None:
        self.script, self.buffered, self.fail = script, buffered, fail
        self.stream_calls = 0
        self.complete_calls = 0

    def complete(self, messages: list[dict[str, str]], *, json_mode: bool, max_tokens: int) -> str:
        if not json_mode:
            return "query"
        self.complete_calls += 1
        ids = sorted(evidence_ids(messages[0]["content"]))
        if self.buffered is None:
            raise ProviderError("no buffered script")
        return self.buffered(ids)

    def stream_complete(self, messages: list[dict[str, str]], *, max_tokens: int) -> Iterator[str]:
        from app.chat.providers import StreamUnsupported

        if self.script is None:
            raise StreamUnsupported("scripted: cannot stream")
        self.stream_calls += 1
        if self.fail:
            raise ProviderError("scripted failure")
        yield from self.script(sorted(evidence_ids(messages[0]["content"])))


def reply_json(ids: list[str], answer: str, *, can_answer: bool = True, cite: bool = True) -> str:
    return json.dumps(
        {"can_answer": can_answer, "sources": ids[:1] if cite else [], "answer": answer},
        ensure_ascii=False,
    )


def chunks_of(raw: str, size: int = 4) -> list[str]:
    return [raw[i : i + size] for i in range(0, len(raw), size)]


@pytest.fixture(autouse=False)
def use_model(monkeypatch: pytest.MonkeyPatch) -> Callable[[ChatModel], None]:
    def install(model: ChatModel) -> None:
        monkeypatch.setattr("app.chat.models.model_from_settings", lambda settings, bot=None: model)

    return install


def setup_session(
    db: OrmSession, app: FastAPI, corpus: dict[str, Any], name: str = "Streamy"
) -> tuple[dict[str, Any], dict[str, Any], TestClient]:
    users = corpus["users_a"]
    bot = make_active_bot_with_knowledge(app, users, db, name=name)
    _override_widget_settings(app)
    session = client_session(app, bot["widget_locator"])
    return bot, session, app_client(app)


# --- stub model: the real pipeline, streamed ---------------------------------


def test_stream_with_stub_model_matches_buffered_answer_and_persists_at_done(
    db: OrmSession, app: FastAPI, corpus: dict[str, Any]
) -> None:
    _, session, client = setup_session(db, app, corpus)
    response, events = stream(client, session)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache, no-transform"
    assert response.headers["x-accel-buffering"] == "no"
    kinds = names(events)
    assert kinds[0] == "verdict" and kinds[-1] == "done"
    assert kinds.count("done") == 1 and "error" not in kinds
    done = events[-1][1]
    final = done["ai_message"]["text"]
    assert deltas(events) == final and final.strip()
    assert done["ai_message"]["can_answer"] is True
    assert done["ai_message"]["citations"] == []  # private on the public channel
    assert done["kind"] == "answer"
    rows = messages_of(db, session["session_id"])
    assert [row.sender_type for row in rows] == ["visitor", "ai"]
    assert rows[1].text == final and str(rows[1].id) == done["ai_message"]["id"]
    assert rows[1].citations  # stored citations exist server-side

    # The buffered route gives the identical grounded answer (parity).
    buffered = client.post(
        f"/api/public/v1/sessions/{session['session_id']}/messages",
        json={"text": HOURS_Q},
        headers={"X-Session-Token": session["token"]},
    )
    assert buffered.status_code == 201
    assert buffered.json()["ai_message"]["text"] == final


def test_stream_off_topic_sends_single_canned_event_and_no_model_text(
    db: OrmSession, app: FastAPI, corpus: dict[str, Any]
) -> None:
    _, session, client = setup_session(db, app, corpus)
    _, events = stream(client, session, OFF_TOPIC_Q)
    assert "delta" not in names(events)
    done = events[-1][1]
    assert done["ai_message"]["can_answer"] is False
    assert done["ai_message"]["needs_human"] is True
    canned = [data for name, data in events if name == "cannot_confirm"]
    # Either the gate refused before the model (no streamed event: done only)
    # or the verdict was negative (exactly one canned event, same text).
    assert len(canned) <= 1
    if canned:
        assert canned[0]["text"] == done["ai_message"]["text"]


def test_stream_trace_records_streamed_flag_and_time_to_first_token(
    db: OrmSession, app: FastAPI, corpus: dict[str, Any]
) -> None:
    _, session, client = setup_session(db, app, corpus)
    _, events = stream(client, session)
    message_id = events[-1][1]["ai_message"]["id"]
    db.expire_all()
    usage = db.execute(
        select(UsageEvent).where(UsageEvent.external_key == f"message:{message_id}")
    ).scalar_one()
    trace = rag_trace(usage)
    assert trace["streamed"] is True
    assert trace["stream_mode"] == "streamed"
    assert isinstance(trace["time_to_first_token_ms"], int)
    assert trace["time_to_first_token_ms"] >= 0
    assert trace["gate"] == "passed"  # the ordinary trace is intact


def test_buffered_turn_trace_has_no_stream_fields(
    db: OrmSession, app: FastAPI, corpus: dict[str, Any]
) -> None:
    _, session, client = setup_session(db, app, corpus)
    response = client.post(
        f"/api/public/v1/sessions/{session['session_id']}/messages",
        json={"text": HOURS_Q},
        headers={"X-Session-Token": session["token"]},
    )
    message_id = response.json()["ai_message"]["id"]
    db.expire_all()
    usage = db.execute(
        select(UsageEvent).where(UsageEvent.external_key == f"message:{message_id}")
    ).scalar_one()
    assert "streamed" not in rag_trace(usage)


# --- gates: identical to the buffered route -----------------------------------


def test_stream_requires_the_session_token(
    db: OrmSession, app: FastAPI, corpus: dict[str, Any]
) -> None:
    _, session, client = setup_session(db, app, corpus)
    missing = client.post(
        f"/api/public/v1/sessions/{session['session_id']}/messages/stream",
        json={"text": HOURS_Q},
    )
    assert missing.status_code == 401
    wrong = client.post(
        f"/api/public/v1/sessions/{session['session_id']}/messages/stream",
        json={"text": HOURS_Q},
        headers={"X-Session-Token": "not-the-token"},
    )
    assert wrong.status_code == 401
    assert wrong.json()["error"]["code"] == "SESSION_INVALID"
    assert messages_of(db, session["session_id"]) == []


def test_stream_cross_session_token_is_rejected(
    db: OrmSession, app: FastAPI, corpus: dict[str, Any]
) -> None:
    users = corpus["users_a"]
    bot_a = make_active_bot_with_knowledge(app, users, db, name="Bot A")
    bot_b = make_active_bot_with_knowledge(app, users, db, name="Bot B")
    _override_widget_settings(app)
    session_a = client_session(app, bot_a["widget_locator"])
    session_b = client_session(app, bot_b["widget_locator"])
    client = app_client(app)
    response = client.post(
        f"/api/public/v1/sessions/{session_b['session_id']}/messages/stream",
        json={"text": HOURS_Q},
        headers={"X-Session-Token": session_a["token"]},
    )
    assert response.status_code == 401
    assert messages_of(db, session_b["session_id"]) == []


def test_stream_paused_bot_is_a_controlled_409_before_the_stream_opens(
    db: OrmSession, app: FastAPI, corpus: dict[str, Any]
) -> None:
    bot, session, client = setup_session(db, app, corpus)
    _set_bot_status(db, corpus["users_a"], bot_id=str(bot["id"]), status="paused")
    response, _ = stream(client, session)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "BOT_PAUSED"


def test_stream_shares_the_message_rate_limit_with_the_buffered_route(
    db: OrmSession, app: FastAPI, corpus: dict[str, Any]
) -> None:
    _, session, client = setup_session(db, app, corpus)  # limit: 3 per minute
    for _ in range(2):
        response, _ = stream(client, session)
        assert response.status_code == 200
    buffered = client.post(
        f"/api/public/v1/sessions/{session['session_id']}/messages",
        json={"text": HOURS_Q},
        headers={"X-Session-Token": session["token"]},
    )
    assert buffered.status_code == 201
    capped, _ = stream(client, session)
    assert capped.status_code == 429
    assert capped.json()["error"]["code"] == "RATE_LIMITED"


def test_stream_empty_or_oversized_text_is_422(
    db: OrmSession, app: FastAPI, corpus: dict[str, Any]
) -> None:
    _, session, client = setup_session(db, app, corpus)
    for body in ("", "x" * 1001):
        response, _ = stream(client, session, body)
        assert response.status_code == 422


# --- release rules and fallbacks (scripted models) ----------------------------


def test_released_text_arrives_in_deltas_then_done(
    db: OrmSession,
    app: FastAPI,
    corpus: dict[str, Any],
    use_model: Callable[[ChatModel], None],
) -> None:
    _, session, client = setup_session(db, app, corpus)
    answer = "We are open Monday to Friday, 9:00 to 17:00. مرحباً"
    use_model(ScriptedModel(lambda ids: chunks_of(reply_json(ids, answer))))
    _, events = stream(client, session)
    assert names(events)[0] == "verdict"
    assert len([n for n in names(events) if n == "delta"]) > 1  # progressive
    assert deltas(events) == answer
    assert events[-1][1]["ai_message"]["text"] == answer


@pytest.mark.parametrize("variant", ["no_verdict_yes", "no_citation", "bad_citation"])
def test_unreleased_verdicts_never_leak_model_text(
    db: OrmSession,
    app: FastAPI,
    corpus: dict[str, Any],
    use_model: Callable[[ChatModel], None],
    variant: str,
) -> None:
    _, session, client = setup_session(db, app, corpus)

    def script(ids: list[str]) -> list[str]:
        if variant == "no_verdict_yes":
            return chunks_of(reply_json(ids, "SECRET MODEL TEXT", can_answer=False))
        if variant == "no_citation":
            return chunks_of(reply_json(ids, "SECRET MODEL TEXT", cite=False))
        bad = json.dumps(
            {
                "can_answer": True,
                "sources": ["00000000-0000-0000-0000-000000000000"],
                "answer": "SECRET MODEL TEXT",
            }
        )
        return chunks_of(bad)

    use_model(ScriptedModel(script))
    _, events = stream(client, session)
    assert "SECRET MODEL TEXT" not in json.dumps(events)
    assert "delta" not in names(events)
    assert names(events).count("cannot_confirm") == 1
    done = events[-1][1]
    assert done["ai_message"]["text"] == [d for n, d in events if n == "cannot_confirm"][0]["text"]
    assert done["ai_message"]["can_answer"] is False
    stored = [r for r in messages_of(db, session["session_id"]) if r.sender_type == "ai"]
    assert "SECRET MODEL TEXT" not in stored[0].text
    assert stored[0].text == done["ai_message"]["text"]


def test_out_of_order_keys_fall_back_to_the_buffered_path(
    db: OrmSession,
    app: FastAPI,
    corpus: dict[str, Any],
    use_model: Callable[[ChatModel], None],
) -> None:
    _, session, client = setup_session(db, app, corpus)

    def script(ids: list[str]) -> list[str]:
        raw = json.dumps({"answer": "Open 9 to 5.", "can_answer": True, "sources": ids[:1]})
        return chunks_of(raw)

    use_model(ScriptedModel(script))
    _, events = stream(client, session)
    assert names(events) == ["done"]  # nothing streamed early
    assert events[-1][1]["ai_message"]["text"] == "Open 9 to 5."
    assert events[-1][1]["ai_message"]["can_answer"] is True


def test_malformed_json_before_release_is_invalid_output_with_no_stream(
    db: OrmSession,
    app: FastAPI,
    corpus: dict[str, Any],
    use_model: Callable[[ChatModel], None],
) -> None:
    _, session, client = setup_session(db, app, corpus)
    use_model(ScriptedModel(lambda ids: chunks_of("Sure! Here is my answer in prose.")))
    _, events = stream(client, session)
    assert names(events) == ["done"]
    assert events[-1][1]["kind"] == "invalid_output"
    assert events[-1][1]["ai_message"]["text"].strip()  # the canned reply, never model text
    assert "Sure!" not in events[-1][1]["ai_message"]["text"]


def test_truncated_stream_after_release_is_replaced_by_the_validated_result(
    db: OrmSession,
    app: FastAPI,
    corpus: dict[str, Any],
    use_model: Callable[[ChatModel], None],
) -> None:
    _, session, client = setup_session(db, app, corpus)

    def script(ids: list[str]) -> list[str]:
        raw = reply_json(ids, "A long answer that never finishes properly")
        return chunks_of(raw[: raw.index("never")])

    use_model(ScriptedModel(script))
    _, events = stream(client, session)
    assert deltas(events)  # some text was released
    done = events[-1][1]
    assert done["kind"] == "invalid_output"  # strict parse failed: the partial is NOT kept
    stored = [r for r in messages_of(db, session["session_id"]) if r.sender_type == "ai"]
    assert stored[0].text == done["ai_message"]["text"]
    assert "never" not in stored[0].text and "long answer" not in stored[0].text


def test_provider_error_midstream_persists_only_the_busy_reply(
    db: OrmSession,
    app: FastAPI,
    corpus: dict[str, Any],
    use_model: Callable[[ChatModel], None],
) -> None:
    _, session, client = setup_session(db, app, corpus)

    class Breaking(ScriptedModel):
        def stream_complete(
            self, messages: list[dict[str, str]], *, max_tokens: int
        ) -> Iterator[str]:
            ids = sorted(evidence_ids(messages[0]["content"]))
            yield from chunks_of(reply_json(ids, "partial text then boom"))[:30]
            raise ProviderError("connection reset")

    use_model(Breaking(None))
    _, events = stream(client, session)
    done = events[-1]
    assert done[0] == "done" and done[1]["kind"] == "busy"
    stored = [r for r in messages_of(db, session["session_id"]) if r.sender_type == "ai"]
    assert len(stored) == 1 and "partial" not in stored[0].text


def test_provider_failure_before_any_text_is_busy(
    db: OrmSession,
    app: FastAPI,
    corpus: dict[str, Any],
    use_model: Callable[[ChatModel], None],
) -> None:
    _, session, client = setup_session(db, app, corpus)
    use_model(ScriptedModel(lambda ids: [], fail=True))
    _, events = stream(client, session)
    assert names(events) == ["done"] and events[0][1]["kind"] == "busy"


def test_provider_that_cannot_stream_uses_the_buffered_call(
    db: OrmSession,
    app: FastAPI,
    corpus: dict[str, Any],
    use_model: Callable[[ChatModel], None],
) -> None:
    _, session, client = setup_session(db, app, corpus)
    model = ScriptedModel(None, buffered=lambda ids: reply_json(ids, "Buffered hours answer."))
    use_model(model)
    _, events = stream(client, session)
    assert names(events) == ["done"]
    assert events[-1][1]["ai_message"]["text"] == "Buffered hours answer."
    assert model.complete_calls == 1
    message_id = events[-1][1]["ai_message"]["id"]
    db.expire_all()
    usage = db.execute(
        select(UsageEvent).where(UsageEvent.external_key == f"message:{message_id}")
    ).scalar_one()
    assert rag_trace(usage)["streamed"] is False
    assert rag_trace(usage)["stream_mode"] == "unsupported"


def test_human_mode_conversation_streams_only_done(
    db: OrmSession, app: FastAPI, corpus: dict[str, Any]
) -> None:
    _, session, client = setup_session(db, app, corpus)
    first, _ = stream(client, session)
    assert first.status_code == 200
    db.execute(text("UPDATE conversations SET mode = 'human'"))
    db.commit()
    _, events = stream(client, session)
    assert names(events) == ["done"]
    assert events[0][1]["ai_message"] is None and events[0][1]["kind"] == "waiting_human"


# --- disconnect ------------------------------------------------------------------


def test_client_disconnect_stops_the_provider_and_persists_nothing(
    db: OrmSession,
    app: FastAPI,
    corpus: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.chat.streaming import prepare_widget_stream, stream_events
    from app.core.config import get_settings

    bot, session, _ = setup_session(db, app, corpus)
    closed = threading.Event()

    class Slow(ScriptedModel):
        def stream_complete(
            self, messages: list[dict[str, str]], *, max_tokens: int
        ) -> Iterator[str]:
            ids = sorted(evidence_ids(messages[0]["content"]))
            try:
                for fragment in chunks_of(reply_json(ids, "word " * 200), 6):
                    time.sleep(0.02)
                    yield fragment
            finally:
                closed.set()

    slow = Slow(None)
    monkeypatch.setattr("app.chat.models.model_from_settings", lambda settings, bot=None: slow)
    settings = app.dependency_overrides[get_settings]()
    visitor_session = db.get(VisitorSession, UUID(session["session_id"]))
    bot_row = db.get(Bot, UUID(bot["id"]))
    assert visitor_session is not None and bot_row is not None
    turn = prepare_widget_stream(
        db,
        visitor_session=visitor_session,
        bot=bot_row,
        text=HOURS_Q,
        ip="127.0.0.1",
        settings=settings,
        language_hint=None,
    )

    async def consume_one_delta_then_disconnect() -> None:
        events = stream_events(turn, lambda payload: payload)
        seen_delta = False
        async for chunk in events:
            if chunk.startswith("event: delta"):
                seen_delta = True
                break
        assert seen_delta
        await events.aclose()  # what a client disconnect does to the body generator

    asyncio.run(consume_one_delta_then_disconnect())
    assert closed.wait(timeout=10), "the provider stream was not closed after disconnect"
    time.sleep(0.5)  # let the worker finish its rollback
    db.expire_all()
    rows = messages_of(db, session["session_id"])
    assert [row for row in rows if row.sender_type == "ai"] == []
    assert [row for row in rows if row.sender_type == "visitor"] == []  # rolled back too
    assert db.execute(select(UsageEvent).where(UsageEvent.kind == "message")).first() is None
