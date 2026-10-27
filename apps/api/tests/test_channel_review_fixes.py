"""Review fixes S2, S3 and S9 (batch 3) and later small items."""

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

import app.chat.conversations as chat_conversations
from app.channels.health import apply_health
from app.channels.sanitize import to_plain_text
from app.core.errors import ApiError
from app.db.models import Bot, ChannelConnection, Message
from tests.conftest import build_test_settings
from tests.test_channel_events import (
    _connection,
    _post,
    _post_received,
    _run_event,
    _UnusedModel,
)

STUB = build_test_settings(chat_stub_model=True)


def test_pushed_channel_status_in_the_future_does_not_shadow_a_later_pull(
    client: Any, app: Any, db: Session
) -> None:
    connection_id, secret = _connection(app, db)
    body = {
        "version": 1,
        "event_id": "evt-future",
        "event_type": "channel.status",
        "connection_id": str(connection_id),
        "occurred_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
        "status": "disconnected",
    }
    assert _post(client, connection_id, secret, json.dumps(body).encode()).status_code == 202
    _run_event(db, "evt-future")
    connection = db.get(ChannelConnection, connection_id)
    assert connection is not None
    assert connection.health_updated_at is not None
    assert connection.health_updated_at <= datetime.now(UTC)

    changed = apply_health(
        db,
        connection,
        status="connected",
        detail=None,
        occurred_at=datetime.now(UTC),
        source="pull",
    )
    db.commit()
    db.refresh(connection)
    assert changed is True and connection.health_reason == "connected"


def test_busy_reply_keeps_a_url_support_contact_and_is_capped(
    client: Any, app: Any, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    connection_id, secret = _connection(app, db)
    bot = db.scalar(
        select(Bot).where(
            Bot.id
            == db.scalar(
                select(ChannelConnection.bot_id).where(ChannelConnection.id == connection_id)
            )
        )
    )
    assert bot is not None
    bot.config = {**bot.config, "support_email": "https://help.example.com/contact"}
    db.commit()
    monkeypatch.setattr(chat_conversations, "default_model", lambda _bot: _UnusedModel())
    monkeypatch.setattr(
        chat_conversations,
        "reserve",
        lambda *_a, **_k: (_ for _ in ()).throw(ApiError(429, "QUOTA_EXCEEDED", "limit")),
    )
    for index in range(3):
        _post_received(
            client,
            connection_id,
            secret,
            event_id=f"evt-u{index}",
            external_message_id=f"m-u{index}",
        )
        _run_event(db, f"evt-u{index}", settings=STUB)
    replies = db.scalars(select(Message).where(Message.sender_type == "ai")).all()
    assert len(replies) == 1
    assert "https://help.example.com/contact" in replies[0].text


def test_sanitizer_keeps_listed_strings_and_still_strips_other_urls() -> None:
    text = to_plain_text(
        "Write to https://help.example.com/x or see https://other.example/y **now**",
        keep=("https://help.example.com/x",),
    )
    assert text == "Write to https://help.example.com/x or see now"
