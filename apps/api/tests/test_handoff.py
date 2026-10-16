"""P5-01 state machine, handoff and widget agent-message visibility."""

import threading
from typing import Any
from uuid import UUID

from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession
from starlette.testclient import TestClient

import tests.retrieval_helpers as _rh  # noqa: F401
from app.db.models import AuditEvent, Bot, Conversation, Message
from tests.conftest import csrf_headers
from tests.test_conversations_view import seed_setup

corpus = _rh.corpus


def test_handoff_reply_copy_is_business_generic() -> None:
    from app.chat.prompts import canned

    for language in ("en", "ar"):
        message = canned("handoff", language, support_contact="help@example.com")
        assert "help@example.com" in message
        assert not any(word in message.casefold() for word in ("orders", "accounts", "payments"))


def _actions_path(tenant_id: UUID, conversation_id: str) -> str:
    return f"/api/v1/tenants/{tenant_id}/conversations/{conversation_id}"


def test_handoff_state_cycle_viewer_tenant_and_widget_scope(
    app: FastAPI, db: OrmSession, corpus: dict[str, Any]
) -> None:
    users = corpus["users_a"]
    setup = seed_setup(app, users, db, name="Handoff cycle")
    client = setup["client"]
    session = setup["session"]
    path = _actions_path(users.tenant_id, setup["turn"]["conversation_id"])

    viewer = users.as_user("viewer")
    foreign = corpus["users_b"].as_user("admin")
    foreign_path = _actions_path(corpus["users_b"].tenant_id, setup["turn"]["conversation_id"])
    route_actions = [
        ("GET", "", None),
        ("POST", "/takeover", None),
        ("POST", "/return-to-ai", None),
        ("POST", "/resolve", None),
        ("POST", "/assign", {"assigned_user_id": None}),
        ("POST", "/messages", {"text": "viewer must not reply"}),
        ("POST", "/notes", {"text": "viewer must not add note"}),
    ]
    for method, suffix, body in route_actions:
        kwargs: dict[str, Any] = {"headers": csrf_headers(viewer)} if method == "POST" else {}
        if body is not None:
            kwargs["json"] = body
        denied = viewer.request(method, path + suffix, **kwargs)
        assert denied.status_code == (200 if method == "GET" else 403), denied.text

        foreign_kwargs: dict[str, Any] = (
            {"headers": csrf_headers(foreign)} if method == "POST" else {}
        )
        if body is not None:
            foreign_kwargs["json"] = body
        hidden = foreign.request(method, foreign_path + suffix, **foreign_kwargs)
        assert hidden.status_code == 404, hidden.text

    owner = users.as_user("admin")
    takeover = owner.post(path + "/takeover", headers=csrf_headers(owner))
    assert takeover.status_code == 200, takeover.text
    assert takeover.json()["conversation"]["mode"] == "human"
    assert takeover.json()["conversation"]["assigned_user_id"] == users.users["admin"]["id"]

    # While in human mode the widget accepts visitor text, but returns no AI answer.
    visitor_turn = client.post(
        f"/api/public/v1/sessions/{session['session_id']}/messages",
        json={"text": "I have one more question"},
        headers={"X-Session-Token": session["token"]},
    )
    assert visitor_turn.status_code == 201, visitor_turn.text
    assert visitor_turn.json()["ai_message"] is None
    visitor_cursor = visitor_turn.json()["visitor_message"]["created_at"]

    editor = users.as_user("editor")
    reply = editor.post(
        path + "/messages",
        json={"text": "A colleague will follow up shortly."},
        headers=csrf_headers(editor),
    )
    assert reply.status_code == 201, reply.text
    reply_message = reply.json()["message"]
    assert reply_message["sender_type"] == "agent"
    assert reply_message["citations"] == []

    note = editor.post(
        path + "/notes",
        json={"text": "Check the order details before follow-up."},
        headers=csrf_headers(editor),
    )
    assert note.status_code == 201, note.text
    note_messages = owner.get(path).json()["messages"]
    assert any(
        message["sender_type"] == "system"
        and message["text"] == "Internal note: Check the order details before follow-up."
        for message in note_messages
    )
    ai_message_id = setup["turn"]["ai_message"]["id"]
    feedback = client.post(
        f"/api/public/v1/sessions/{session['session_id']}/messages/{ai_message_id}/feedback",
        json={"rating": "up"},
        headers={"X-Session-Token": session["token"]},
    )
    assert feedback.status_code == 200, feedback.text
    detail_messages = owner.get(path).json()["messages"]
    ai_detail = next(message for message in detail_messages if message["id"] == ai_message_id)
    assert ai_detail["feedback"] == ["up"]

    # The capability token sees only its session, and agent text has no citations.
    polled = client.get(
        f"/api/public/v1/sessions/{session['session_id']}/messages",
        headers={"X-Session-Token": session["token"]},
        params={"since": visitor_cursor},
    )
    assert polled.status_code == 200
    assert not any("Internal note:" in row["text"] for row in polled.json())
    assert any(
        row["id"] == reply_message["id"] and row["text"] == reply_message["text"]
        for row in polled.json()
    )
    foreign_session = client.post(
        f"/api/public/v1/widgets/{setup['bot']['widget_locator']}/sessions", json={}
    ).json()
    guessed = client.get(
        f"/api/public/v1/sessions/{foreign_session['session_id']}/messages",
        headers={"X-Session-Token": session["token"]},
    )
    assert guessed.status_code == 401

    returned = owner.post(path + "/return-to-ai", headers=csrf_headers(owner))
    assert returned.status_code == 200
    assert returned.json()["conversation"]["mode"] == "ai"
    resolved = owner.post(path + "/resolve", headers=csrf_headers(owner))
    assert resolved.status_code == 200
    assert resolved.json()["conversation"]["status"] == "resolved"

    reopened = client.post(
        f"/api/public/v1/sessions/{session['session_id']}/messages",
        json={"text": "What are your opening hours?"},
        headers={"X-Session-Token": session["token"]},
    )
    assert reopened.status_code == 201, reopened.text
    assert reopened.json()["ai_message"] is not None
    state = owner.get(path)
    assert state.json()["conversation"]["status"] == "open"
    assert state.json()["conversation"]["mode"] == "ai"

    actions = (
        db.execute(
            select(AuditEvent.action).where(
                AuditEvent.tenant_id == users.tenant_id,
                AuditEvent.target_id == setup["turn"]["conversation_id"],
            )
        )
        .scalars()
        .all()
    )
    assert {
        "conversation.taken_over",
        "conversation.returned_to_ai",
        "conversation.resolved",
        "conversation.note_added",
    } <= set(actions)


def test_two_concurrent_takeovers_only_one_wins(
    app: FastAPI, db: OrmSession, corpus: dict[str, Any]
) -> None:
    users = corpus["users_a"]
    setup = seed_setup(app, users, db, name="Takeover race")
    path = _actions_path(users.tenant_id, setup["turn"]["conversation_id"])
    barrier = threading.Barrier(2)
    results: list[tuple[int, dict[str, Any]]] = []

    def take(role: str) -> None:
        client: TestClient = users.as_user(role)
        barrier.wait()
        response = client.post(path + "/takeover", headers=csrf_headers(client))
        results.append((response.status_code, response.json()))

    threads = [threading.Thread(target=take, args=(role,)) for role in ("admin", "editor")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert all(not thread.is_alive() for thread in threads)
    assert sorted(status for status, _ in results) == [200, 409]
    conflict = next(body for status, body in results if status == 409)
    assert conflict["error"]["code"] == "TAKEOVER_CONFLICT"
    assert conflict["error"]["details"]["assigned_user_id"] in {
        users.users["admin"]["id"],
        users.users["editor"]["id"],
    }
    conversation = db.execute(
        select(Conversation).where(Conversation.id == setup["turn"]["conversation_id"])
    ).scalar_one()
    assert conversation.mode == "human"
    assert conversation.assigned_user_id in {
        UUID(users.users["admin"]["id"]),
        UUID(users.users["editor"]["id"]),
    }


def test_handoff_rules_and_reopen_after_resolution(
    app: FastAPI, db: OrmSession, corpus: dict[str, Any]
) -> None:
    from tests.test_widget_public import (
        _override_widget_settings,
        app_client,
        client_session,
        make_active_bot_with_knowledge,
    )

    users = corpus["users_a"]
    _override_widget_settings(app)
    bot = make_active_bot_with_knowledge(app, users, db, name="Handoff rules")
    session = client_session(app, bot["widget_locator"])
    client = app_client(app)
    base = f"/api/public/v1/sessions/{session['session_id']}/messages"
    headers = {"X-Session-Token": session["token"]}

    person = client.post(base, json={"text": "Please let me speak to an agent"}, headers=headers)
    assert person.status_code == 201
    conversation_id = person.json()["conversation_id"]
    conversation = db.get(Conversation, conversation_id)
    assert conversation is not None and conversation.status == "waiting_human"
    assert conversation.handoff_reason == "visitor_requested"

    owner = users.as_user("admin")
    path = _actions_path(users.tenant_id, conversation_id)
    owner.post(path + "/resolve", headers=csrf_headers(owner))
    # Account/order routes hand off immediately; a new visitor turn reopens first.
    order = client.post(base, json={"text": "Can you track my order?"}, headers=headers)
    assert order.status_code == 201
    assert order.json()["ai_message"] is not None
    db.expire_all()
    conversation = db.get(Conversation, conversation_id)
    assert conversation is not None
    assert conversation.status == "waiting_human"
    assert conversation.mode == "ai"
    assert conversation.handoff_reason == "order_account"

    rows = (
        db.execute(
            select(Message).where(
                Message.conversation_id == conversation_id,
                Message.sender_type == "system",
            )
        )
        .scalars()
        .all()
    )
    assert any("support team" in row.text for row in rows)


def test_unanswered_threshold_and_provider_failure_rule(
    app: FastAPI, db: OrmSession, corpus: dict[str, Any]
) -> None:
    from app.inbox.handoff import decide_handoff
    from tests.test_widget_public import (
        _override_widget_settings,
        app_client,
        client_session,
        make_active_bot_with_knowledge,
    )

    users = corpus["users_a"]
    _override_widget_settings(app)
    bot_payload = make_active_bot_with_knowledge(app, users, db, name="Unanswered threshold")
    bot = db.get(Bot, UUID(bot_payload["id"]))
    assert bot is not None
    session = client_session(app, bot_payload["widget_locator"])
    client = app_client(app)
    base = f"/api/public/v1/sessions/{session['session_id']}/messages"
    headers = {"X-Session-Token": session["token"]}
    first = client.post(base, json={"text": "wireless charging pads?"}, headers=headers)
    assert first.status_code == 201
    assert first.json()["ai_message"]["can_answer"] is False
    conversation_id = UUID(first.json()["conversation_id"])
    db.expire_all()
    conversation = db.get(Conversation, conversation_id)
    assert conversation is not None and conversation.status == "open"

    second = client.post(base, json={"text": "wireless charging pads?"}, headers=headers)
    assert second.status_code == 201
    db.expire_all()
    conversation = db.get(Conversation, conversation_id)
    assert conversation is not None
    assert conversation.status == "waiting_human"
    assert conversation.handoff_reason == "unanswered_threshold"
    conversation.status = "open"
    db.flush()
    decision = decide_handoff(
        db,
        bot=bot,
        conversation=conversation,
        question="please try again",
        language="en",
        reply_kind="busy",
        can_answer=False,
    )
    assert decision is not None and decision.reason == "provider_failure"
