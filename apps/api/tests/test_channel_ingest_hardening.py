"""R-03 inbound hardening: channel match, bytes-safe signature, clock clamp,
receipt ordering, contact refresh and one live connection per Many channel."""

import json
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.channels.signing import sign, verify
from app.db.models import ChannelConnection, ChannelEvent, Contact, Job, Message
from tests.conftest import build_test_settings
from tests.helpers import make_bot, seeded_tenant
from tests.test_channel_events import _connection, _payload, _post, _post_received, _run_event
from tests.test_channels import _configure_channel_key, _create_payload, _platform_call

STUB = build_test_settings(chat_stub_model=True)


def test_channel_must_match_the_connection_with_signed_422(
    client: Any, app: Any, db: Session
) -> None:
    connection_id, secret = _connection(app, db)  # a WhatsApp connection
    raw = json.dumps(_payload(connection_id, event_id="evt-wrong", channel="instagram")).encode()
    response = _post(client, connection_id, secret, raw)
    assert response.status_code == 422
    assert db.scalar(select(ChannelEvent).where(ChannelEvent.event_id == "evt-wrong")) is None
    ok = json.dumps(_payload(connection_id, event_id="evt-right")).encode()
    assert _post(client, connection_id, secret, ok).status_code == 202


def test_non_ascii_signature_is_a_generic_401_never_a_500(
    client: Any, app: Any, db: Session
) -> None:
    connection_id, secret = _connection(app, db)
    raw = json.dumps(_payload(connection_id)).encode()
    now = int(time.time())
    assert verify(secret, now, raw, "sha256=é中", now=now) is False
    response = client.post(
        "/api/channels/manyosiris/events",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "X-Osiris-Connection": str(connection_id),
            "X-Osiris-Timestamp": str(now),
            "X-Osiris-Signature": "sha256=\u00e9".encode("latin-1"),
        },
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"
    assert verify(secret, now, raw, sign(secret, now, raw), now=now) is True


def test_received_at_is_clamped_to_a_sane_window(client: Any, app: Any, db: Session) -> None:
    connection_id, secret = _connection(app, db)
    now = datetime.now(UTC)
    cases = {
        "old": (now - timedelta(days=3)).isoformat(),
        "future": (now + timedelta(hours=2)).isoformat(),
        "fine": (now - timedelta(hours=1)).isoformat(),
    }
    for name, stamp in cases.items():
        body = _payload(
            connection_id,
            event_id=f"evt-{name}",
            external_message_id=f"msg-{name}",
            received_at=stamp,
        )
        assert _post(client, connection_id, secret, json.dumps(body).encode()).status_code == 202
        _run_event(db, f"evt-{name}", settings=STUB)
    created = {
        message.channel_message_id: message.created_at
        for message in db.scalars(select(Message).where(Message.sender_type == "visitor"))
    }
    assert abs((created["msg-old"] - now).total_seconds()) < 120
    assert abs((created["msg-future"] - now).total_seconds()) < 120
    assert abs((created["msg-fine"] - (now - timedelta(hours=1))).total_seconds()) < 5


def test_an_earlier_unprocessed_event_runs_before_a_later_one(
    client: Any, app: Any, db: Session
) -> None:
    connection_id, secret = _connection(app, db)
    for name in ("first", "second"):
        _post_received(
            client, connection_id, secret, event_id=f"evt-{name}", external_message_id=name
        )
    _run_event(db, "evt-second", settings=STUB)  # the later job wins the race
    first = db.scalar(select(ChannelEvent).where(ChannelEvent.event_id == "evt-first"))
    second = db.scalar(select(ChannelEvent).where(ChannelEvent.event_id == "evt-second"))
    assert first is not None and second is not None
    assert first.status == second.status == "processed"
    assert first.processed_at is not None and second.processed_at is not None
    assert first.processed_at <= second.processed_at
    answers = list(
        db.scalars(select(Message).where(Message.sender_type == "ai").order_by(Message.created_at))
    )
    # No model is configured in this test, so both turns degrade to the busy reply,
    # which is capped at one per conversation per window (A8).
    assert len(answers) == 1
    visitors = list(
        db.scalars(
            select(Message.channel_message_id)
            .where(Message.sender_type == "visitor")
            .order_by(Message.created_at, Message.id)
        )
    )
    assert visitors == ["first", "second"]
    before = db.scalar(select(Message.id).where(Message.sender_type == "visitor"))
    # The first event's own job later finds it processed: no duplicates.
    _run_event(db, "evt-first", settings=STUB)
    assert db.scalar(select(Message.id).where(Message.sender_type == "visitor")) == before
    assert len(list(db.scalars(select(Message).where(Message.sender_type == "ai")))) == 1
    assert db.scalar(select(Job.id).where(Job.status == "failed")) is None


def test_contact_details_refresh_but_staff_edits_are_kept(
    client: Any, app: Any, db: Session
) -> None:
    connection_id, secret = _connection(app, db)

    def send(name: str, contact: dict[str, str]) -> None:
        body = _payload(
            connection_id, event_id=f"evt-{name}", external_message_id=name, contact=contact
        )
        assert _post(client, connection_id, secret, json.dumps(body).encode()).status_code == 202
        _run_event(db, f"evt-{name}", settings=STUB)

    send("c1", {"name": "Old Name", "phone": "+100"})
    contact = db.scalar(select(Contact))
    assert contact is not None and contact.display_name == "Old Name"
    send("c2", {"name": "New Name", "phone": "+200", "handle": "@new"})
    db.refresh(contact)
    assert contact.display_name == "New Name" and contact.phone == "+200"
    assert contact.custom_fields["channel_handle"] == "@new"
    contact.display_name = "Typed by staff"
    db.commit()
    send("c3", {"name": "Third Name"})
    db.refresh(contact)
    assert contact.display_name == "Typed by staff"


def test_one_live_connection_per_many_channel_ref(app: Any, db: Session) -> None:
    _configure_channel_key(app)
    one = seeded_tenant(app, db, prefix="ref-a", plan_label="business")
    two = seeded_tenant(app, db, prefix="ref-b", plan_label="business")
    staff = one.as_user("staff")
    first = _platform_call(
        staff,
        "POST",
        "/channel-connections",
        json=_create_payload(one.tenant_id, make_bot(one)["id"]),
    )
    assert first.status_code == 201, first.text
    clash = _platform_call(
        staff,
        "POST",
        "/channel-connections",
        json=_create_payload(two.tenant_id, make_bot(two)["id"]),
    )
    assert clash.status_code == 409 and clash.json()["error"]["code"] == "CHANNEL_REF_IN_USE"
    other_channel = {**_create_payload(two.tenant_id, make_bot(two)["id"]), "channel": "messenger"}
    assert (
        _platform_call(staff, "POST", "/channel-connections", json=other_channel).status_code == 201
    )
    revoked = _platform_call(staff, "POST", f"/channel-connections/{first.json()['id']}/revoke")
    assert revoked.status_code == 200
    again = _platform_call(
        staff,
        "POST",
        "/channel-connections",
        json=_create_payload(two.tenant_id, make_bot(two)["id"]),
    )
    assert again.status_code == 201, again.text
    live = db.scalars(
        select(ChannelConnection).where(
            ChannelConnection.channel == "whatsapp",
            ChannelConnection.many_channel_ref == "wa-001",
            ChannelConnection.status != "revoked",
        )
    ).all()
    assert len(live) == 1
