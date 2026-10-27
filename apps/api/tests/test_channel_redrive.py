"""B2: a turn that aborts after reserve() committed the visitor message is re-driven
by the queue retry; a genuine duplicate event never produces a second reply."""

from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import app.chat.conversations as chat_conversations
from app.chat.conversations import visitor_chat_turn
from app.db.models import Conversation, Message
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


def test_aborted_turn_is_redriven_on_retry_with_exactly_one_reply(
    client: Any, app: Any, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    connection_id, secret = _connection(app, db)
    _post_received(client, connection_id, secret, event_id="evt-crash", external_message_id="m-1")
    monkeypatch.setattr(chat_conversations, "default_model", lambda _bot: _UnusedModel())

    def crash(*_a: Any, **_k: Any) -> Any:
        raise RuntimeError("worker killed mid-turn")

    monkeypatch.setattr(chat_conversations, "chat_answer", crash)
    with pytest.raises(RuntimeError):
        _run_event(db, "evt-crash", settings=STUB)
    db.rollback()
    # The state the owner reproduced: message stored, nothing answered, still open.
    assert (_count(db, "visitor"), _count(db, "ai")) == (1, 0)
    conversation = db.scalar(select(Conversation))
    assert conversation is not None and conversation.status == "open"

    monkeypatch.undo()
    _patch_success_pipeline(monkeypatch)
    event = _run_event(db, "evt-crash", settings=STUB)
    assert event.status == "processed"
    assert (_count(db, "visitor"), _count(db, "ai")) == (1, 1)

    # Retrying a processed event, or a second event for the same message, adds nothing.
    _run_event(db, "evt-crash", settings=STUB)
    _post_received(client, connection_id, secret, event_id="evt-dup", external_message_id="m-1")
    _run_event(db, "evt-dup", settings=STUB)
    assert (_count(db, "visitor"), _count(db, "ai")) == (1, 1)


def test_aborted_website_turn_discards_the_unanswered_visitor_message(
    app: Any, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    connection_id, _secret = _connection(app, db)
    from app.db.models import Bot, Tenant

    bot = db.scalar(select(Bot))
    tenant = db.scalar(select(Tenant))
    assert bot is not None and tenant is not None
    conversation = Conversation(tenant_id=tenant.id, bot_id=bot.id, source="website")
    db.add(conversation)
    db.commit()

    def crash(*_a: Any, **_k: Any) -> Any:
        raise RuntimeError("killed")

    monkeypatch.setattr(chat_conversations, "chat_answer", crash)
    with pytest.raises(RuntimeError):
        visitor_chat_turn(
            db,
            tenant_id=tenant.id,
            bot=bot,
            conversation=conversation,
            question="Hello there",
            language_hint="en",
            model=_UnusedModel(),
            settings=STUB,
        )
    db.rollback()
    assert _count(db, "visitor") == 0 and _count(db, "ai") == 0
