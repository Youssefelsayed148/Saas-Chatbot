"""R-02 channel turn: one shared reply brain plus channel gating, throttle,
plain-text output, localized texts and per-conversation serialization."""

import threading
import time
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import app.channels.config as channel_config
import app.chat.conversations as chat_conversations
from app.channels.guard import conversation_turn_lock
from app.channels.inbound import run_channel_inbound
from app.channels.sanitize import to_plain_text
from app.chat.providers import ProviderError
from app.chat.service import ChatReply
from app.core.errors import ApiError
from app.db.models import Bot, ChannelConnection, ChannelEvent, Conversation, Job, Message
from tests.conftest import build_test_settings
from tests.test_channel_events import (
    _connection,
    _patch_success_pipeline,
    _post_received,
    _run_event,
    _UnusedModel,
)

STUB = build_test_settings(chat_stub_model=True)


def _count(db: Session, sender: str) -> int:
    return int(db.scalar(select(func.count(Message.id)).where(Message.sender_type == sender)) or 0)


def _send(client: Any, db: Session, connection_id: UUID, secret: str, name: str, **kw: Any) -> None:
    _post_received(
        client,
        connection_id,
        secret,
        event_id=f"evt-{name}",
        external_message_id=f"msg-{name}",
        **kw,
    )
    _run_event(db, f"evt-{name}", settings=STUB)


def test_plain_text_sanitizer() -> None:
    raw = "## Hours\n**Open** 9-5 [1] and *daily*.\n* Item one\n- Item two\n`code` [site](https://a.example/x)"
    plain = to_plain_text(raw)
    assert plain == "Hours\nOpen 9-5 and daily.\n- Item one\n- Item two\ncode site"
    assert "https://" not in plain and "[1]" not in plain and "**" not in plain
    assert "site: https://a.example/x" in to_plain_text(raw, allow_links=True)
    assert to_plain_text("See https://a.example/y now") == "See now"


def test_channel_answer_is_plain_text_with_style_hint_from_the_shared_core(
    client: Any, app: Any, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    connection_id, secret = _connection(app, db)
    monkeypatch.setattr(chat_conversations, "default_model", lambda _bot: _UnusedModel())
    seen: dict[str, Any] = {}

    def answer(*_a: Any, **kwargs: Any) -> ChatReply:
        seen.update(kwargs)
        return ChatReply(
            answer="**We open at 9** [1]\n- Mon to Fri",
            can_answer=True,
            needs_human=False,
            language="en",
            kind="answer",
            citations=[{"chunk_id": "c1", "title": "Hours", "url": "https://x.example"}],
        )

    monkeypatch.setattr(chat_conversations, "chat_answer", answer)
    _send(client, db, connection_id, secret, "plain")
    reply = db.scalar(select(Message).where(Message.sender_type == "ai"))
    assert reply is not None
    assert reply.text == "We open at 9\n- Mon to Fri"
    assert reply.citations  # staff still see sources; only the DM text is cleaned
    assert seen["channel_style"] == channel_config.DEFAULT_STYLE_HINT
    assert seen["history"] == []

    bot = db.scalar(select(Bot))
    assert bot is not None
    bot.config = {**bot.config, "channel_style_hint": "Answer in one sentence."}
    db.commit()
    _send(client, db, connection_id, secret, "plain2")
    assert seen["channel_style"] == "Answer in one sentence."


def test_human_mode_beats_ai_off_and_paused_status_flips(
    client: Any, app: Any, db: Session
) -> None:
    connection_id, secret = _connection(app, db)
    _send(client, db, connection_id, secret, "h-seed")
    ai_after_seed = _count(db, "ai")
    conversation = db.scalar(select(Conversation))
    connection = db.get(ChannelConnection, connection_id)
    assert conversation is not None and connection is not None
    conversation.mode = "human"
    conversation.status = "open"
    for ai_enabled, status in ((False, "active"), (True, "paused")):
        connection.ai_enabled = ai_enabled
        connection.status = status
        db.commit()
        _send(client, db, connection_id, secret, f"h-{ai_enabled}-{status}")
        db.refresh(conversation)
        assert conversation.mode == "human" and conversation.status == "open"
    # Human mode: none of the later messages got an AI reply.
    assert _count(db, "ai") == ai_after_seed
    assert _count(db, "visitor") == 3


def test_unsupported_message_fires_handoff_and_is_localized(
    client: Any, app: Any, db: Session
) -> None:
    connection_id, secret = _connection(app, db)
    _send(client, db, connection_id, secret, "u1", text="", message_type="unsupported")
    conversation = db.scalar(select(Conversation))
    assert conversation is not None
    assert conversation.status == "waiting_human"
    assert conversation.handoff_reason == "unsupported_message"
    visitor = db.scalar(select(Message).where(Message.sender_type == "visitor"))
    assert visitor is not None and visitor.text == "Unsupported message type."
    notice = db.scalar(select(Message).where(Message.sender_type == "ai"))
    assert notice is not None and notice.delivery_status == "pending"

    connection_b, secret_b = _connection(app, db)
    bot = db.scalar(
        select(Bot).where(
            Bot.id
            == db.scalar(
                select(ChannelConnection.bot_id).where(ChannelConnection.id == connection_b)
            )
        )
    )
    assert bot is not None
    bot.config = {**bot.config, "default_language": "ar"}
    db.commit()
    _send(client, db, connection_b, secret_b, "u2", text="", message_type="unsupported")
    arabic = db.scalar(
        select(Message).where(Message.sender_type == "visitor", Message.bot_id == bot.id)
    )
    assert arabic is not None and arabic.text == "تعذر عرض هذه الرسالة."


def test_flood_throttle_stores_but_stops_the_ai(
    client: Any, app: Any, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    connection_id, secret = _connection(app, db)
    monkeypatch.setattr(channel_config, "INBOUND_PER_MINUTE", 2)
    _patch_success_pipeline(monkeypatch)
    for index in range(4):
        _send(client, db, connection_id, secret, f"flood{index}", text=f"question {index}")
    assert _count(db, "visitor") == 4
    assert _count(db, "ai") == 2
    conversation = db.scalar(select(Conversation))
    assert conversation is not None and conversation.status == "waiting_human"


def test_busy_reply_is_sent_at_most_once_per_window(
    client: Any, app: Any, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    connection_id, secret = _connection(app, db)
    monkeypatch.setattr(chat_conversations, "default_model", lambda _bot: _UnusedModel())
    monkeypatch.setattr(
        chat_conversations,
        "reserve",
        lambda *_a, **_k: (_ for _ in ()).throw(ApiError(429, "QUOTA_EXCEEDED", "limit")),
    )
    for index in range(3):
        _send(client, db, connection_id, secret, f"busy{index}")
    assert _count(db, "visitor") == 3
    assert _count(db, "ai") == 1
    assert db.scalar(select(func.count(Job.id)).where(Job.type == "channel_send")) == 1


def test_provider_failure_without_a_model_still_degrades(
    client: Any, app: Any, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    connection_id, secret = _connection(app, db)
    monkeypatch.setattr(chat_conversations, "default_model", lambda _bot: None)
    _send(client, db, connection_id, secret, "nomodel")
    reply = db.scalar(select(Message).where(Message.sender_type == "ai"))
    assert reply is not None and reply.can_answer is False


def test_rerun_after_an_ai_reply_is_idempotent(
    client: Any, app: Any, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    connection_id, secret = _connection(app, db)
    _patch_success_pipeline(monkeypatch)
    _send(client, db, connection_id, secret, "rerun")
    before = (_count(db, "visitor"), _count(db, "ai"))
    event_id = "evt-rerun"
    _run_event(db, event_id, settings=STUB)
    assert (_count(db, "visitor"), _count(db, "ai")) == before == (1, 1)


def test_turn_lock_blocks_a_second_worker_until_released(db: Session) -> None:
    connection_id = UUID(int=1)
    order: list[str] = []
    entered = threading.Event()

    def second() -> None:
        with Session(bind=db.get_bind()) as other:
            with conversation_turn_lock(other, connection_id, "same-conversation"):
                order.append("second")

    with conversation_turn_lock(db, connection_id, "same-conversation"):
        thread = threading.Thread(target=second)
        thread.start()
        entered.wait(0.5)
        time.sleep(0.5)
        order.append("first-done")
    thread.join(5)
    assert order == ["first-done", "second"]
    # A different conversation is not blocked.
    with conversation_turn_lock(db, connection_id, "same-conversation"):
        with Session(bind=db.get_bind()) as other:
            with conversation_turn_lock(other, connection_id, "another-conversation"):
                pass


def test_two_quick_messages_in_one_conversation_run_one_after_the_other(
    client: Any, app: Any, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    connection_id, secret = _connection(app, db)
    monkeypatch.setattr(chat_conversations, "default_model", lambda _bot: _UnusedModel())
    spans: list[tuple[float, float]] = []
    gate = threading.Lock()

    def answer(*_a: Any, **_k: Any) -> ChatReply:
        started = time.monotonic()
        time.sleep(0.4)  # long enough for a non-serialized second turn to overlap
        with gate:
            spans.append((started, time.monotonic()))
        return ChatReply(
            answer="ok", can_answer=True, needs_human=False, language="en", kind="answer"
        )

    monkeypatch.setattr(chat_conversations, "chat_answer", answer)
    for name in ("q1", "q2"):
        _post_received(
            client, connection_id, secret, event_id=f"evt-{name}", external_message_id=name
        )
    errors: list[BaseException] = []

    def work(name: str) -> None:
        try:
            with Session(bind=db.get_bind()) as session:
                event = session.scalar(
                    select(ChannelEvent).where(ChannelEvent.event_id == f"evt-{name}")
                )
                assert event is not None
                job = Job(
                    tenant_id=event.tenant_id,
                    bot_id=session.scalar(
                        select(ChannelConnection.bot_id).where(
                            ChannelConnection.id == event.connection_id
                        )
                    ),
                    type="channel_inbound",
                    status="running",
                    payload={"channel_event_id": str(event.id)},
                    attempts=1,
                    max_attempts=3,
                )
                session.add(job)
                session.commit()  # like claim_job: nothing is held open before the turn
                assert run_channel_inbound(session, job, STUB) is None
                session.commit()
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=work, args=(name,)) for name in ("q1", "q2")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(60)
    assert not errors, errors
    db.expire_all()
    assert _count(db, "visitor") == 2 and _count(db, "ai") == 2
    assert db.scalar(select(func.count(Conversation.id))) == 1
    first, second = sorted(spans)
    assert first[1] <= second[0]  # the two turns never overlapped


def test_provider_error_keeps_visitor_message_and_releases_reservation(
    client: Any, app: Any, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    connection_id, secret = _connection(app, db)
    monkeypatch.setattr(chat_conversations, "default_model", lambda _bot: _UnusedModel())
    monkeypatch.setattr(
        chat_conversations,
        "chat_answer",
        lambda *_a, **_k: (_ for _ in ()).throw(ProviderError("down")),
    )
    _send(client, db, connection_id, secret, "perr")
    assert _count(db, "visitor") == 1 and _count(db, "ai") == 1
