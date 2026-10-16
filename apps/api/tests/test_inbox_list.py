"""P5-02 filtering, unread state, tenant scope, and shared SSE cursor."""

from collections.abc import Iterator
from typing import Any
from uuid import UUID, uuid4

import pytest
from _pytest.fixtures import FixtureRequest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session as OrmSession

from app.db.models import Conversation, ConversationTag, InboxEvent
from tests.conftest import csrf_headers
from tests.helpers import seeded_tenant
from tests.test_conversations_view import seed_setup


def _base(tenant_id: UUID, conversation_id: str) -> str:
    return f"/api/v1/tenants/{tenant_id}/inbox/{conversation_id}"


def _tenant(app: FastAPI, db: OrmSession, label: str, request: FixtureRequest) -> Any:
    users = seeded_tenant(app, db, prefix=f"{label}-{uuid4().hex[:10]}")
    request.addfinalizer(users.cleanup)
    return users


def _next_sse_event(lines: Iterator[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in lines:
        if line == "":
            if values:
                return values
            continue
        if line.startswith(":"):
            continue
        key, _, value = line.partition(":")
        values[key] = value.lstrip()
    raise AssertionError("SSE stream ended before the next event")


def _next_generator_event(stream: Iterator[str]) -> dict[str, str]:
    for _ in range(20):
        event = _next_sse_event(iter(next(stream).splitlines()))
        if "event" in event:
            return event
    raise AssertionError("SSE stream did not emit an event within the polling window")


def test_inbox_filters_search_tags_and_per_user_unread(
    app: FastAPI, db: OrmSession, request: FixtureRequest
) -> None:
    users = _tenant(app, db, "inbox-filter", request)
    foreign_users = _tenant(app, db, "inbox-filter-b", request)
    setup = seed_setup(app, users, db, name="Inbox filters")
    request.addfinalizer(setup["client"].close)
    conversation_id = setup["turn"]["conversation_id"]
    base = _base(users.tenant_id, conversation_id)
    admin = users.as_user("admin")
    editor = users.as_user("editor")
    viewer = users.as_user("viewer")
    list_url = f"/api/v1/tenants/{users.tenant_id}/inbox"

    initial = admin.get(list_url)
    assert initial.status_code == 200, initial.text
    assert initial.json()["total"] == 1
    item = initial.json()["conversations"][0]
    assert item["id"] == conversation_id
    assert item["unread_count"] == 1
    assert item["last_message"]

    for params in (
        {"status": "open"},
        {"mode": "ai"},
        {"channel": "website"},
        {"assignee": "unassigned"},
        {"unread": "true"},
        {"q": "opening hours"},
    ):
        result = admin.get(list_url, params=params)
        assert result.status_code == 200, result.text
        assert result.json()["total"] == 1, params
    assert admin.get(list_url, params={"status": "resolved"}).json()["total"] == 0

    added = editor.post(base + "/tags", json={"tag": "  Urgent "}, headers=csrf_headers(editor))
    assert added.status_code == 201, added.text
    assert added.json()["tags"] == ["urgent"]
    tagged = admin.get(list_url, params={"tag": "URGENT"})
    assert tagged.status_code == 200
    assert tagged.json()["conversations"][0]["tags"] == ["urgent"]

    # Read markers are per-member: marking as read for the admin leaves the
    # same visitor message unread for the editor.
    assert admin.post(base + "/read", headers=csrf_headers(admin)).json() == {"unread_count": 0}
    assert admin.get(list_url).json()["conversations"][0]["unread_count"] == 0
    assert editor.get(list_url).json()["conversations"][0]["unread_count"] == 1

    later = setup["client"].post(
        f"/api/public/v1/sessions/{setup['session']['session_id']}/messages",
        json={"text": "Is weekend parking available?"},
        headers={"X-Session-Token": setup["session"]["token"]},
    )
    assert later.status_code == 201, later.text
    assert admin.get(list_url).json()["conversations"][0]["unread_count"] == 1
    assert editor.get(list_url).json()["conversations"][0]["unread_count"] == 2

    assert viewer.get(list_url).status_code == 200
    denied = viewer.post(base + "/tags", json={"tag": "blocked"}, headers=csrf_headers(viewer))
    assert denied.status_code == 403
    hidden = users.as_user("admin").get(f"/api/v1/tenants/{foreign_users.tenant_id}/inbox")
    assert hidden.status_code == 404

    counts = admin.get(list_url + "/counts")
    assert counts.status_code == 200
    assert counts.json()["unread_messages"] >= 1
    assert counts.json()["unread_conversations"] == 1


def test_tag_endpoint_hides_cross_tenant_conversation(
    app: FastAPI, db: OrmSession, request: FixtureRequest
) -> None:
    users = _tenant(app, db, "inbox-isolation", request)
    foreign_users = _tenant(app, db, "inbox-isolation-b", request)
    setup = seed_setup(app, users, db, name="Inbox isolation")
    request.addfinalizer(setup["client"].close)
    foreign = foreign_users.as_user("admin")
    path = _base(foreign_users.tenant_id, setup["turn"]["conversation_id"])
    response = foreign.post(path + "/tags", json={"tag": "secret"}, headers=csrf_headers(foreign))
    assert response.status_code == 404
    assert (
        db.query(ConversationTag)
        .filter(ConversationTag.tenant_id == foreign_users.tenant_id)
        .count()
        == 0
    )


def test_notification_counts_follow_waiting_and_assignment(
    app: FastAPI, db: OrmSession, request: FixtureRequest
) -> None:
    users = _tenant(app, db, "inbox-counts", request)
    setup = seed_setup(app, users, db, name="Inbox notifications")
    request.addfinalizer(setup["client"].close)
    conversation_id = UUID(setup["turn"]["conversation_id"])
    conversation = db.get(Conversation, conversation_id)
    assert conversation is not None
    conversation.status = "waiting_human"
    db.commit()

    admin = users.as_user("admin")
    editor = users.as_user("editor")
    counts_url = f"/api/v1/tenants/{users.tenant_id}/inbox/counts"
    waiting = admin.get(counts_url).json()
    assert waiting["waiting_human"] == 1
    assert waiting["assigned_to_me"] == 0

    takeover = admin.post(
        f"/api/v1/tenants/{users.tenant_id}/conversations/{conversation_id}/takeover",
        headers=csrf_headers(admin),
    )
    assert takeover.status_code == 200, takeover.text
    assigned = admin.get(counts_url).json()
    assert assigned["waiting_human"] == 0
    assert assigned["assigned_to_me"] == 1
    assert editor.get(counts_url).json()["assigned_to_me"] == 0


def test_sse_reconnects_across_two_app_instances(
    app: FastAPI, db: OrmSession, monkeypatch: pytest.MonkeyPatch, request: FixtureRequest
) -> None:
    from app.inbox import listing
    from app.inbox.listing import event_stream
    from tests.test_widget_public import _override_widget_settings

    monkeypatch.setattr(listing, "INBOX_POLL_SECONDS", 0.01)
    users = _tenant(app, db, "inbox-events", request)
    setup = seed_setup(app, users, db, name="Inbox two instances")
    request.addfinalizer(setup["client"].close)

    from app.main import create_app

    second_app = create_app()
    _override_widget_settings(second_app)
    admin_id = UUID(users.users["admin"]["id"])
    with TestClient(second_app) as process_two:
        first = event_stream(users.tenant_id, admin_id, None)
        try:
            initial = _next_generator_event(first)
            assert initial["event"] == "inbox.ready"
            cursor = int(initial["id"])
            assert '"waiting_human"' in initial["data"]

            visitor_response = process_two.post(
                f"/api/public/v1/sessions/{setup['session']['session_id']}/messages",
                json={"text": "A new question from API process two"},
                headers={"X-Session-Token": setup["session"]["token"]},
            )
            assert visitor_response.status_code == 201, visitor_response.text
            event = _next_generator_event(first)
            assert event["event"] == "inbox.update"
            assert int(event["id"]) > cursor
            cursor = int(event["id"])
            assert visitor_response.json()["conversation_id"] in event["data"]
        finally:
            first.close()

        resumed = event_stream(users.tenant_id, admin_id, cursor)
        try:
            ready = _next_generator_event(resumed)
            assert ready["event"] == "inbox.ready"
            assert int(ready["id"]) == cursor
            next_turn = setup["client"].post(
                f"/api/public/v1/sessions/{setup['session']['session_id']}/messages",
                json={"text": "A follow-up after reconnect"},
                headers={"X-Session-Token": setup["session"]["token"]},
            )
            assert next_turn.status_code == 201, next_turn.text
            update = _next_generator_event(resumed)
            assert update["event"] == "inbox.update"
            assert int(update["id"]) > cursor
        finally:
            resumed.close()


def test_invalid_sse_cursor_and_inbox_rows_are_tenant_scoped(
    app: FastAPI, db: OrmSession, request: FixtureRequest
) -> None:
    users = _tenant(app, db, "inbox-cursor", request)
    setup = seed_setup(app, users, db, name="Inbox cursor")
    request.addfinalizer(setup["client"].close)
    admin = users.as_user("admin")
    stream_url = f"/api/v1/tenants/{users.tenant_id}/inbox/events"
    invalid = admin.get(stream_url, headers={"Last-Event-ID": "not-a-cursor"})
    assert invalid.status_code == 400
    rows = db.query(InboxEvent).filter(InboxEvent.tenant_id == users.tenant_id).all()
    assert rows
    assert all(row.conversation_id == UUID(setup["turn"]["conversation_id"]) for row in rows)
    from app.inbox.listing import event_stream

    latest = max(row.id for row in rows)
    stream = event_stream(users.tenant_id, UUID(users.users["admin"]["id"]), latest + 10_000)
    ready = _next_generator_event(stream)
    assert int(ready["id"]) == latest
    stream.close()
