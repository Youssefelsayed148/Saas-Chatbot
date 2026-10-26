# ruff: noqa: F811  (pytest fixture imported from test_channel_outbound)
"""R-04 outbound + delivery: byte-aware splitting, closed error enum, unconfirmed
sweep and owner-triggered resend, against the fake Many (contract v1.1 A2-A4)."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.channels.outbound import split_reply, sweep_unconfirmed
from app.db.models import Job, Membership, Message, User
from tests.helpers import PASSWORD, csrf_headers
from tests.test_channel_outbound import callbacks, run, send_context  # noqa: F401


def test_instagram_splits_by_utf8_bytes_while_other_channels_use_characters() -> None:
    arabic = ("مرحبا بكم في متجرنا. نسعد بخدمتكم دائما. " * 60).strip()
    assert len(arabic) > 1000
    parts = split_reply(arabic, "instagram")
    assert "".join(parts) == arabic
    assert all(len(part.encode("utf-8")) <= 900 for part in parts)
    assert len(parts) >= 3
    # The same text is character-limited (not byte-limited) on WhatsApp.
    wa_parts = split_reply(arabic, "whatsapp")
    assert "".join(wa_parts) == arabic and all(len(part) <= 1000 for part in wa_parts)
    assert len(wa_parts) < len(parts)
    # A multi-byte character is never cut in half and ASCII fills 900 bytes.
    ascii_parts = split_reply("x" * 2000, "instagram")
    assert [len(part) for part in ascii_parts] == [900, 900, 200]


def test_fake_many_never_truncates_and_the_failure_is_permanent(
    send_context: Any,
    db: Session,
) -> None:
    _connection, _conversation, message, job, settings, fake = send_context
    fake.limit_chars = 5
    run(db, job, settings)
    assert message.delivery_status == "failed" and message.error_code == "message_too_long"
    assert len(fake.requests) == 1  # permanent: not retried
    run(db, job, settings)
    assert len(fake.requests) == 1


@pytest.mark.parametrize(
    ("reported", "stored"),
    [
        ("window_closed", "window_closed"),
        ("template_required", "template_required"),
        ("message_too_long", "message_too_long"),
        ("rate_limited", "rate_limited"),
        ("Meta says: (#10) outside window for jane@example.com", "unknown"),
        ("totally_new_code", "unknown"),
    ],
)
def test_status_callback_error_codes_use_the_closed_enum(
    send_context: Any,
    db: Session,
    client: Any,
    reported: str,
    stored: str,
) -> None:
    _connection, _conversation, message, job, settings, fake = send_context
    run(db, job, settings)
    assert fake.post_status(client, str(message.id), "failed", reported).status_code == 202
    callbacks(db, settings)
    db.refresh(message)
    assert message.delivery_status == "failed" and message.error_code == stored


def test_accepted_without_a_status_becomes_unconfirmed_and_a_real_status_overrides(
    send_context: Any,
    db: Session,
    client: Any,
) -> None:
    _connection, _conversation, message, job, settings, fake = send_context
    run(db, job, settings)
    db.refresh(message)
    assert message.delivery_status == "pending" and message.accepted_at is not None
    now = datetime.now(UTC)
    assert sweep_unconfirmed(db, now=now + timedelta(minutes=5)) == 0
    assert sweep_unconfirmed(db, now=now + timedelta(minutes=16)) == 1
    db.commit()
    db.refresh(message)
    assert message.delivery_status == "unconfirmed"
    assert sweep_unconfirmed(db, now=now + timedelta(minutes=30)) == 0  # not swept twice
    assert fake.post_status(client, str(message.id), "sent").status_code == 202
    callbacks(db, settings)
    db.refresh(message)
    assert message.delivery_status == "sent"
    assert fake.post_status(client, str(message.id), "delivered").status_code == 202
    callbacks(db, settings)
    db.refresh(message)
    assert message.delivery_status == "delivered"
    assert sweep_unconfirmed(db, now=now + timedelta(hours=2)) == 0


def test_a_failed_status_after_unconfirmed_is_kept(
    send_context: Any,
    db: Session,
    client: Any,
) -> None:
    _connection, _conversation, message, job, settings, fake = send_context
    run(db, job, settings)
    sweep_unconfirmed(db, now=datetime.now(UTC) + timedelta(minutes=20))
    db.commit()
    assert fake.post_status(client, str(message.id), "failed", "window_closed").status_code == 202
    callbacks(db, settings)
    db.refresh(message)
    assert message.delivery_status == "failed" and message.error_code == "window_closed"


def test_resend_after_connection_paused_failure_is_owner_triggered_and_scoped(
    send_context: Any,
    app: Any,
    db: Session,
) -> None:
    connection, conversation, message, job, settings, fake = send_context
    connection.status = "paused"
    db.commit()
    run(db, job, settings)
    assert message.delivery_status == "failed" and message.error_code == "connection_paused"

    user = db.scalar(
        select(User)
        .join(Membership, Membership.user_id == User.id)
        .where(Membership.tenant_id == connection.tenant_id, Membership.role == "editor")
    )
    assert user is not None
    editor = TestClient(app)
    assert (
        editor.post(
            "/api/v1/auth/login", json={"email": user.email, "password": PASSWORD}
        ).status_code
        == 200
    )
    path = f"/api/v1/tenants/{connection.tenant_id}/conversations/{conversation.id}"
    resend = f"{path}/messages/{message.id}/resend"
    headers = csrf_headers(editor)

    paused = editor.post(resend, headers=headers)
    assert paused.status_code == 409 and paused.json()["error"]["code"] == "CONNECTION_PAUSED"

    connection.status = "active"
    db.commit()
    ok = editor.post(resend, headers=headers)
    assert ok.status_code == 200, ok.text
    assert ok.json()["message"]["delivery_status"] == "pending"
    db.refresh(message)
    assert message.error_code is None
    pending = db.scalars(
        select(Job).where(Job.type == "channel_send", Job.status == "pending")
    ).all()
    assert len(pending) == 1
    run(db, pending[0], settings)
    db.refresh(message)
    assert message.channel_message_id == "many-1" and len(fake.requests) == 1

    # Not resendable again (no longer failed), nor other failures, nor foreign ids.
    again = editor.post(resend, headers=headers)
    assert again.status_code == 409 and again.json()["error"]["code"] == "NOT_RESENDABLE"
    message.delivery_status = "failed"
    message.error_code = "window_closed"
    db.commit()
    other_failure = editor.post(resend, headers=headers)
    assert other_failure.status_code == 409
    missing = editor.post(f"{path}/messages/{conversation.id}/resend", headers=headers)
    assert missing.status_code == 404
    assert (
        db.scalar(select(func.count(Message.id)).where(Message.text == "A message was sent again."))
        == 1
    )
    editor.close()


def test_resend_denies_viewers_and_other_tenants(
    send_context: Any,
    app: Any,
    db: Session,
) -> None:
    from tests.helpers import seeded_tenant

    connection, conversation, message, job, settings, _fake = send_context
    connection.status = "paused"
    db.commit()
    run(db, job, settings)
    other = seeded_tenant(app, db, prefix="resend-other")
    foreign = f"/api/v1/tenants/{other.tenant_id}/conversations/{conversation.id}"
    response = other.call("editor", "POST", f"{foreign}/messages/{message.id}/resend")
    assert response.status_code == 404
