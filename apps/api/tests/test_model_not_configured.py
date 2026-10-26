"""R3-5 (#91, visitor part): no model configured is a canned busy reply on the
buffered and streamed widget paths (never a 503), recorded as an
``unavailable`` event (not a billable ``message``), with no handoff; staff see
it in the trace and in the readiness checklist. Keys are never echoed."""

from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

import tests.retrieval_helpers as _rh  # noqa: F401 — registers the corpus fixture
from app.bots.service import readiness_items
from app.chat.models import model_configured
from app.core.config import Settings
from app.db.models import Bot, Conversation, UsageEvent
from tests.test_chat_streaming import HOURS_Q, names, setup_session, stream

corpus = _rh.corpus


@pytest.fixture
def no_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.widget.service.model_from_settings", lambda settings, bot=None: None)
    monkeypatch.setattr("app.chat.models.model_from_settings", lambda settings, bot=None: None)


def usage(db: OrmSession) -> dict[str, list[UsageEvent]]:
    db.expire_all()
    rows = list(db.scalars(select(UsageEvent)))
    return {kind: [row for row in rows if row.kind == kind] for kind in {r.kind for r in rows}}


def assert_unavailable_recorded(db: OrmSession, text: str) -> None:
    events = usage(db)
    assert "message" not in events, "an unavailable turn is not a billable message"
    assert "handoff" not in events
    (event,) = events["unavailable"]
    trace = event.payload["rag_trace"]
    assert trace["provider_error"] == {
        "status": "not_configured",
        "http_status": None,
        "model": None,
    }
    assert event.message_id is not None
    conversation = db.scalars(select(Conversation)).one()
    assert conversation.status != "waiting_human" and conversation.mode == "ai"
    assert "briefly unavailable" in text


def test_buffered_widget_turn_gets_the_busy_reply_not_a_503(
    db: OrmSession, app: FastAPI, corpus: dict[str, Any], no_model: None
) -> None:
    _, session, client = setup_session(db, app, corpus)
    response = client.post(
        f"/api/public/v1/sessions/{session['session_id']}/messages",
        json={"text": HOURS_Q},
        headers={"X-Session-Token": session["token"]},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["kind"] == "busy" and body["ai_message"]["citations"] == []
    assert body["ai_message"]["needs_human"] is True and body["ai_message"]["can_answer"] is False
    assert_unavailable_recorded(db, body["ai_message"]["text"])


def test_streamed_widget_turn_gets_the_busy_reply_not_a_503(
    db: OrmSession, app: FastAPI, corpus: dict[str, Any], no_model: None
) -> None:
    _, session, client = setup_session(db, app, corpus)
    response, events = stream(client, session)
    assert response.status_code == 200, response.text
    assert names(events) == ["done"]
    done = events[-1][1]
    assert done["kind"] == "busy"
    assert_unavailable_recorded(db, done["ai_message"]["text"])


def test_staff_trace_lists_the_unavailable_turn(
    db: OrmSession, app: FastAPI, corpus: dict[str, Any], no_model: None
) -> None:
    bot, session, client = setup_session(db, app, corpus)
    client.post(
        f"/api/public/v1/sessions/{session['session_id']}/messages",
        json={"text": HOURS_Q},
        headers={"X-Session-Token": session["token"]},
    )
    users = corpus["users_a"]
    traces = users.call(
        "staff", "GET", f"/api/v1/tenants/{users.tenant_id}/bots/{bot['id']}/rag/traces"
    )
    assert traces.status_code == 200
    (row,) = traces.json()["traces"]
    assert row["trace"]["provider_error"]["status"] == "not_configured"


def test_readiness_item_reflects_the_provider_without_leaking_keys() -> None:
    bot = Bot(name="B", config={}, tier="standard")
    empty = Settings.model_construct(chat_stub_model=False, chat_openrouter_api_key=None)
    items = {item.id: item for item in readiness_items(bot, empty)}
    assert items["model_provider"].status == "todo"
    assert items["model_provider"].label == "Model provider configured"
    stub = Settings.model_construct(chat_stub_model=True)
    assert {i.id: i.status for i in readiness_items(bot, stub)}["model_provider"] == "ok"
    assert model_configured(stub) and not model_configured(empty)
    for item in items.values():
        assert "sk-" not in item.detail and "key" not in item.detail.lower()
