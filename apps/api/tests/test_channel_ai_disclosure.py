"""The first AI answer on a channel tells the customer they are talking to AI."""

from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

import app.chat.conversations as chat_conversations
from app.bots.schemas import BotConfig
from app.chat.service import DEFAULT_AI_DISCLOSURE, ai_disclosure_for
from app.core.errors import ApiError
from app.db.models import Bot, Message
from tests.conftest import build_test_settings
from tests.test_channel_events import _connection, _patch_success_pipeline, _post_received, _run_event

STUB = build_test_settings(chat_stub_model=True)


def _send(client: Any, db: Session, connection_id: Any, secret: str, name: str) -> None:
    _post_received(client, connection_id, secret, event_id=f"evt-{name}", external_message_id=f"msg-{name}")
    _run_event(db, f"evt-{name}", settings=STUB)


def _ai_texts(db: Session) -> list[str]:
    rows = db.scalars(select(Message).where(Message.sender_type == "ai").order_by(Message.created_at)).all()
    return [row.text for row in rows]


def test_default_text_is_localized() -> None:
    bot = SimpleNamespace(config={})
    assert ai_disclosure_for(bot, "en") == DEFAULT_AI_DISCLOSURE["en"]
    assert ai_disclosure_for(bot, "ar") == DEFAULT_AI_DISCLOSURE["ar"]
    assert ai_disclosure_for(bot, "fr") == DEFAULT_AI_DISCLOSURE["en"]


def test_business_can_edit_the_line_per_language_and_switch_it_off() -> None:
    edited = SimpleNamespace(config={"ai_disclosure": {"en": "  Hi, I'm a bot.  "}})
    assert ai_disclosure_for(edited, "en") == "Hi, I'm a bot."
    assert ai_disclosure_for(edited, "ar") == "Hi, I'm a bot."  # falls back to the language that is set
    off = SimpleNamespace(config={"ai_disclosure": {"en": "", "ar": " "}})
    assert ai_disclosure_for(off, "en") == ""
    assert ai_disclosure_for(off, "ar") == ""


def test_config_schema_accepts_the_line_and_still_rejects_unknown_keys() -> None:
    assert BotConfig.model_validate({"ai_disclosure": {"en": "I'm an AI."}}).ai_disclosure is not None
    with pytest.raises(ValidationError):
        BotConfig.model_validate({"ai_disclosure": {"fr": "x"}})
    with pytest.raises(ValidationError):
        BotConfig.model_validate({"not_a_setting": True})


def test_first_answer_is_disclosed_and_later_answers_are_not(
    client: Any, app: Any, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    connection_id, secret = _connection(app, db)
    _patch_success_pipeline(monkeypatch)
    _send(client, db, connection_id, secret, "d1")
    _send(client, db, connection_id, secret, "d2")
    first, second = _ai_texts(db)
    assert first == f"{DEFAULT_AI_DISCLOSURE['en']}\n\nStored answer"
    assert second == "Stored answer"


def test_switched_off_line_is_not_added(
    client: Any, app: Any, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    connection_id, secret = _connection(app, db)
    _patch_success_pipeline(monkeypatch)
    bot = db.scalar(select(Bot))
    assert bot is not None
    bot.config = {**bot.config, "ai_disclosure": {"en": "", "ar": ""}}
    db.commit()
    _send(client, db, connection_id, secret, "o1")
    assert _ai_texts(db) == ["Stored answer"]


def test_a_busy_notice_does_not_use_up_the_disclosure(
    client: Any, app: Any, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    connection_id, secret = _connection(app, db)
    _patch_success_pipeline(monkeypatch)
    real_reserve = chat_conversations.reserve
    state = {"busy": True}

    def reserve(*args: Any, **kwargs: Any) -> Any:
        if state["busy"]:
            raise ApiError(429, "QUOTA_EXCEEDED", "limit")
        return real_reserve(*args, **kwargs)

    monkeypatch.setattr(chat_conversations, "reserve", reserve)
    _send(client, db, connection_id, secret, "b1")
    busy_text = _ai_texts(db)[0]
    assert DEFAULT_AI_DISCLOSURE["en"] not in busy_text  # canned notice stays exact for de-duplication

    state["busy"] = False
    _send(client, db, connection_id, secret, "b2")
    assert _ai_texts(db)[-1] == f"{DEFAULT_AI_DISCLOSURE['en']}\n\nStored answer"
