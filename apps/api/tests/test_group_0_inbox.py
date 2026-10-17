"""Group 0: realistic multi-conversation read state and client sidebar GETs."""

import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from itertools import islice
from uuid import UUID

import pytest
from fastapi import FastAPI
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.db.models import (
    ChangeRequest,
    Contact,
    Conversation,
    ConversationRead,
    ConversationTag,
    InboxEvent,
    Membership,
    Message,
)
from app.inbox import listing
from tests.conftest import csrf_headers
from tests.helpers import TenantUsers, make_bot, make_invitation, seeded_tenant

ROLES = ("admin", "editor", "viewer", "staff")


@dataclass
class InboxData:
    users: TenantUsers
    foreign: TenantUsers
    bot_id: UUID
    contact_id: UUID
    conversations: list[Conversation]
    foreign_conversation_id: UUID

    @property
    def base(self) -> str:
        return f"/api/v1/tenants/{self.users.tenant_id}"


@pytest.fixture
def inbox_data(app: FastAPI, db: Session) -> Iterator[InboxData]:
    users = seeded_tenant(app, db, "group-0")
    foreign = seeded_tenant(app, db, "group-0-foreign")
    try:
        bot_id = UUID(make_bot(users)["id"])
        foreign_bot_id = UUID(make_bot(foreign)["id"])
        contact = Contact(tenant_id=users.tenant_id, email="visitor@example.com")
        db.add(contact)
        db.flush()
        now = datetime.now(UTC) - timedelta(minutes=1)
        conversations = []
        for index, status in enumerate(("open", "waiting_human", "resolved")):
            for assigned in (False, True):
                conversation = Conversation(
                    tenant_id=users.tenant_id,
                    bot_id=bot_id,
                    contact_id=contact.id,
                    source="website",
                    status=status,
                    mode="human" if assigned or status == "waiting_human" else "ai",
                    assigned_user_id=(
                        UUID(users.users["admin" if index == 0 else "editor"]["id"])
                        if assigned
                        else None
                    ),
                    handoff_reason="visitor_request" if status == "waiting_human" else None,
                    last_message_at=now + timedelta(seconds=1),
                )
                db.add(conversation)
                db.flush()
                conversations.append(conversation)
                # Ordered UUIDs exercise equal-timestamp read cursor boundaries.
                messages = [
                    Message(
                        id=UUID(int=(len(conversations) * 100 + position)),
                        tenant_id=users.tenant_id,
                        bot_id=bot_id,
                        conversation_id=conversation.id,
                        sender_type=sender,
                        sender_user_id=UUID(users.users[role]["id"]) if role else None,
                        text=f"Inbox fixture {sender}",
                        created_at=now + timedelta(seconds=int(position == 5)),
                    )
                    for position, (sender, role) in enumerate(
                        (
                            ("visitor", None),
                            ("ai", None),
                            ("agent", "editor"),
                            ("agent", "admin"),
                            ("system", None),
                            ("visitor", None),
                        )
                    )
                ]
                db.add_all(messages)
                db.flush()
                for role, position in (("admin", 0), ("editor", 2)):
                    marker = messages[5] if len(conversations) == 1 else messages[position]
                    db.add(
                        ConversationRead(
                            tenant_id=users.tenant_id,
                            conversation_id=conversation.id,
                            user_id=UUID(users.users[role]["id"]),
                            last_read_at=marker.created_at,
                            last_read_message_id=marker.id,
                        )
                    )
                db.add_all(
                    [
                        ConversationTag(
                            tenant_id=users.tenant_id,
                            conversation_id=conversation.id,
                            tag="fixture",
                        ),
                        InboxEvent(
                            tenant_id=users.tenant_id,
                            conversation_id=conversation.id,
                            message_id=messages[-1].id,
                            event_type="message.created",
                        ),
                    ]
                )
        # The same member has read state in another tenant too.
        admin_id = UUID(users.users["admin"]["id"])
        db.add(Membership(tenant_id=foreign.tenant_id, user_id=admin_id, role="viewer"))
        other = Conversation(tenant_id=foreign.tenant_id, bot_id=foreign_bot_id, source="website")
        db.add(other)
        db.flush()
        db.add(
            ConversationRead(
                tenant_id=foreign.tenant_id,
                conversation_id=other.id,
                user_id=admin_id,
                last_read_at=now,
                last_read_message_id=UUID(int=0),
            )
        )
        db.add(
            ChangeRequest(
                tenant_id=users.tenant_id,
                requester_id=admin_id,
                type="other",
                text="Fixture change request",
                attachments=[],
            )
        )
        db.commit()
        make_invitation(users, "pending-group-0@example.com")
        yield InboxData(users, foreign, bot_id, contact.id, conversations, other.id)
    finally:
        users.cleanup()
        foreign.cleanup()


@pytest.mark.parametrize("role", ROLES)
def test_inbox_multiple_read_cursors(inbox_data: InboxData, role: str) -> None:
    """Two or more markers used to cause PostgreSQL CardinalityViolation."""
    data = inbox_data
    client = data.users.as_user(role)
    response = client.get(data.base + "/inbox")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total"] == 6
    counts = {row["id"]: row["unread_count"] for row in payload["conversations"]}
    expected = {
        str(conversation.id): (0 if index == 0 else 2) if role in ("admin", "editor") else 4
        for index, conversation in enumerate(data.conversations)
    }
    assert counts == expected
    response = client.get(data.base + "/inbox/counts")
    assert response.status_code == 200, response.text
    assert response.json() == {
        "waiting_human": 2,
        "assigned_to_me": int(role in ("admin", "editor")),
        "unread_messages": sum(expected.values()),
        "unread_conversations": sum(value > 0 for value in expected.values()),
    }

    uid = data.users.users[role]["id"]
    filters: list[dict[str, str]] = [
        {"assignee": "me"},
        {"assignee": "unassigned"},
        {"assignee": uid},
        {"unread": "true"},
        {"unread": "false"},
        {"status": "open"},
        {"status": "waiting_human"},
        {"status": "resolved"},
        {"mode": "human"},
        {"q": "fixture", "tag": "fixture", "channel": "website"},
    ]
    for params in filters:
        filtered = client.get(data.base + "/inbox", params=params)
        assert filtered.status_code == 200, (role, params, filtered.text)
        rows = filtered.json()["conversations"]
        assert filtered.json()["total"] == len(rows)
        for row in rows:
            assert row["unread_count"] == expected[row["id"]]
        if "assignee" in params:
            wanted = None if params["assignee"] == "unassigned" else uid
            ids = {
                str(c.id)
                for c in data.conversations
                if (str(c.assigned_user_id) if c.assigned_user_id else None) == wanted
            }
            assert {row["id"] for row in rows} == ids
        elif "unread" in params:
            assert {row["id"] for row in rows} == {
                cid
                for cid, count in expected.items()
                if (count > 0) == (params["unread"] == "true")
            }
        elif "status" in params:
            assert len(rows) == 2
            assert all(row["status"] == params["status"] for row in rows)
        elif "mode" in params:
            assert len(rows) == 4
        else:
            assert len(rows) == 6


@pytest.fixture
def bounded_events(monkeypatch: pytest.MonkeyPatch) -> None:
    original = listing.event_stream

    def first_event(tenant_id: UUID, user_id: UUID, cursor: int | None) -> Iterator[str]:
        # TestClient buffers streams. Bound transport, retain real SQL/serialization.
        stream = original(tenant_id, user_id, cursor)
        try:
            yield from islice(stream, 1)
        finally:
            stream.close()

    monkeypatch.setattr(listing, "event_stream", first_event)


@pytest.mark.parametrize("role", ROLES)
def test_sidebar_get_sweep(inbox_data: InboxData, bounded_events: None, role: str) -> None:
    data = inbox_data
    client = data.users.as_user(role)
    bot = f"/bots/{data.bot_id}"
    conversation = data.conversations[0].id
    # Explicit statuses from docs/06; include denied GETs to detect role regressions.
    admin_status = 200 if role in ("admin", "staff") else 403
    endpoints = [
        ("", 200),
        ("/quota", 200),
        ("/bots", 200),
        (bot, 200),
        (bot + "/quota", 200),
        ("/inbox", 200),
        ("/inbox/counts", 200),
        ("/inbox/assignees", 403 if role == "viewer" else 200),
        ("/inbox/events", 200),
        # Thread GET lives at /conversations/{id}; /inbox/{id} is a web page only.
        (f"/inbox/{conversation}", 404),
        (f"/conversations/{conversation}", 200),
        (bot + "/conversations", 200),
        (bot + f"/conversations/{conversation}", 200),
        ("/contacts", 200),
        (f"/contacts/{data.contact_id}", 200),
        ("/contacts/stages", 200),
        ("/contacts/export.csv", admin_status),
        ("/analytics", 200),
        ("/follow-ups", 200),
        ("/members", admin_status),
        ("/invitations", admin_status),
        ("/data/audit", admin_status),
        ("/data/export", admin_status),
        ("/change-requests", admin_status),
        *(
            (bot + "/analytics/" + view, 200)
            for view in ("summary", "volume", "top-questions", "unanswered", "leads")
        ),
        *(
            (bot + "/analytics/" + view, admin_status)
            for view in ("conversations.csv", "leads.csv")
        ),
    ]
    errors = []
    for suffix, status in endpoints:
        try:
            response = client.get(data.base + suffix)
            assert response.status_code < 500, response.text
            assert response.status_code == status, response.text
            if suffix == "/inbox/events":
                assert response.headers["content-type"].startswith("text/event-stream")
                assert "event: inbox.ready" in response.text
                event_data = next(
                    line[6:] for line in response.text.splitlines() if line.startswith("data: ")
                )
                assert (
                    json.loads(event_data)["counts"]
                    == client.get(data.base + "/inbox/counts").json()
                )
        except Exception as exc:
            # Aggregate diagnostics so one failure cannot conceal another GET crash.
            errors.append(f"{role} GET {suffix}: {type(exc).__name__}: {exc}")
    assert not errors, "\n".join(errors)


@pytest.mark.parametrize("role", ("admin", "editor", "viewer"))
def test_inbox_tenant_isolation(inbox_data: InboxData, bounded_events: None, role: str) -> None:
    data = inbox_data
    foreign_reader = data.foreign.as_user(role)
    for suffix in (
        "/inbox",
        "/inbox/counts",
        "/inbox/assignees",
        "/inbox/events",
        f"/conversations/{data.conversations[0].id}",
    ):
        assert foreign_reader.get(data.base + suffix).status_code == 404
    client = data.users.as_user(role)
    assert (
        client.get(data.base + f"/conversations/{data.foreign_conversation_id}").status_code == 404
    )


@pytest.mark.parametrize("role", ("admin", "editor"))
def test_mark_read_with_other_conversation_cursors(inbox_data: InboxData, role: str) -> None:
    data = inbox_data
    client = data.users.as_user(role)
    response = client.post(
        data.base + f"/inbox/{data.conversations[1].id}/read", headers=csrf_headers(client)
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"unread_count": 0}
    assert client.get(data.base + "/inbox/counts").json()["unread_messages"] == 8


@pytest.mark.parametrize("marker_count", (0, 1, 2))
def test_unread_zero_one_and_multiple_markers(
    inbox_data: InboxData, db: Session, marker_count: int
) -> None:
    data = inbox_data
    db.execute(
        delete(ConversationRead).where(
            ConversationRead.tenant_id == data.users.tenant_id,
            ConversationRead.user_id == UUID(data.users.users["admin"]["id"]),
            ConversationRead.conversation_id.in_(
                [row.id for row in data.conversations[marker_count:]]
            ),
        )
    )
    db.commit()
    response = data.users.as_user("admin").get(data.base + "/inbox")
    assert response.status_code == 200, response.text
    actual = {row["id"]: row["unread_count"] for row in response.json()["conversations"]}
    assert actual == {
        str(row.id): (0 if index == 0 else 2) if index < marker_count else 3
        for index, row in enumerate(data.conversations)
    }
