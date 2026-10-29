"""P6-01 channel connection, signing, secret, isolation, and quota contracts."""

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.channels.secrets import decrypt_secret, encrypt_secret, signing_secrets
from app.channels.signing import sign, verify
from app.core.config import get_settings
from app.db.models import (
    AuditEvent,
    ChannelConnection,
    Contact,
    ContactIdentity,
    Conversation,
    Message,
)
from tests.conftest import build_test_settings, csrf_headers
from tests.helpers import make_bot, seeded_tenant


def _configure_channel_key(app: Any, key: str | None = None) -> str:
    generated = key or Fernet.generate_key().decode("ascii")
    app.dependency_overrides[get_settings] = lambda: build_test_settings(
        channel_secret_encryption_keys=SecretStr(generated),
        environment="test",
    )
    return generated


def _platform_call(client: Any, method: str, path: str, **kwargs: Any) -> Any:
    headers = kwargs.pop("headers", {})
    if method in {"POST", "PATCH", "DELETE"}:
        headers = {**csrf_headers(client), **headers}
    return client.request(method, f"/api/v1/platform{path}", headers=headers, **kwargs)


def _create_payload(
    tenant_id: UUID, bot_id: str, *, name: str = "Support WhatsApp"
) -> dict[str, object]:
    return {
        "tenant_id": str(tenant_id),
        "bot_id": bot_id,
        "channel": "whatsapp",
        "display_name": name,
        "many_base_url": "https://many.example.test",
        "many_channel_ref": "wa-001",
    }


def test_hmac_fixed_vector_and_timestamp_boundaries() -> None:
    secret = "channel-secret-test-vector"
    body = b'{"event_id":"evt-1","event_type":"message.received"}'
    timestamp = 1_700_000_000
    signature = sign(secret, timestamp, body)
    assert signature == "sha256=e02dda2eec948dd39b8d13e24c88a03b5c755bb56de1abaa393029e880262109"
    assert verify(secret, timestamp, body, signature, now=timestamp + 300)
    assert verify(secret, timestamp, body, signature, now=timestamp - 300)
    assert not verify(secret, timestamp, body + b" ", signature, now=timestamp)
    assert not verify("wrong-secret", timestamp, body, signature, now=timestamp)
    assert not verify(secret, timestamp, body, signature, now=timestamp + 301)
    assert not verify(secret, timestamp, body, signature, now=timestamp - 301)
    assert not verify(secret, "not-a-time", body, signature, now=timestamp)


def test_multi_fernet_decrypt_and_previous_secret_grace() -> None:
    old_key, new_key = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    old_secret, current_secret = "old-secret", "current-secret"
    now = datetime(2026, 10, 18, tzinfo=UTC)
    connection = ChannelConnection(
        secret_ciphertext=encrypt_secret(current_secret, new_key),
        prev_secret_ciphertext=encrypt_secret(old_secret, old_key),
        prev_secret_expires_at=now + timedelta(hours=1),
    )
    settings = build_test_settings(channel_secret_encryption_keys=SecretStr(f"{new_key},{old_key}"))
    assert decrypt_secret(connection.secret_ciphertext, settings.channel_secret_encryption_keys)
    assert signing_secrets(connection, settings, now=now) == (current_secret, old_secret)
    timestamp = int(now.timestamp())
    body = b'{"event_id":"rotation-check"}'
    old_signature = sign(old_secret, timestamp, body)
    current_signature = sign(current_secret, timestamp, body)
    active_secrets = signing_secrets(connection, settings, now=now)
    assert any(
        verify(candidate, timestamp, body, old_signature, now=timestamp)
        for candidate in active_secrets
    )
    assert any(
        verify(candidate, timestamp, body, current_signature, now=timestamp)
        for candidate in active_secrets
    )
    assert signing_secrets(connection, settings, now=now + timedelta(hours=1)) == (current_secret,)
    expired_secrets = signing_secrets(connection, settings, now=now + timedelta(hours=1))
    assert not any(
        verify(candidate, timestamp, body, old_signature, now=timestamp)
        for candidate in expired_secrets
    )
    assert any(
        verify(candidate, timestamp, body, current_signature, now=timestamp)
        for candidate in expired_secrets
    )


def test_connection_lifecycle_secrets_audit_export_and_tenant_sanitization(
    app: Any, db: Session, caplog: pytest.LogCaptureFixture
) -> None:
    encryption_key = _configure_channel_key(app)
    users_a = seeded_tenant(app, db, prefix="channel-a", plan_label="business")
    users_b = seeded_tenant(app, db, prefix="channel-b", plan_label="business")
    bot_a = make_bot(users_a)
    bot_b = make_bot(users_b)
    staff = users_a.as_user("staff")
    payload_a = _create_payload(users_a.tenant_id, bot_a["id"])
    created = _platform_call(staff, "POST", "/channel-connections", json=payload_a)
    assert created.status_code == 201, created.text
    body = created.json()
    connection_id = UUID(body["id"])
    secret = body["secret"]
    assert len(secret) >= 40
    assert body["secret_key_version"] == 1

    connection = db.get(ChannelConnection, connection_id)
    assert connection is not None
    assert connection.secret_ciphertext != secret
    assert decrypt_secret(connection.secret_ciphertext, encryption_key) == secret

    detail = _platform_call(staff, "GET", f"/channel-connections/{connection_id}")
    listing = _platform_call(staff, "GET", "/channel-connections")
    assert detail.status_code == listing.status_code == 200
    for response in (detail, listing):
        output = json.dumps(response.json())
        assert secret not in output
        assert connection.secret_ciphertext not in output
        assert "secret_ciphertext" not in output
        assert "prev_secret_ciphertext" not in output

    client_channels = users_a.call("viewer", "GET", f"/api/v1/tenants/{users_a.tenant_id}/channels")
    assert client_channels.status_code == 200
    client_output = client_channels.json()["items"]
    assert len(client_output) == 1
    assert set(client_output[0]) == {
        "channel",
        "display_name",
        "status",
        "health_status",
        "last_event_at",
    }
    assert client_output[0]["display_name"] == "Support WhatsApp"

    # A staff action for tenant B cannot leak into tenant A's read model.
    payload_b = _create_payload(users_b.tenant_id, bot_b["id"], name="B Messenger")
    payload_b["channel"] = "messenger"
    created_b = _platform_call(staff, "POST", "/channel-connections", json=payload_b)
    assert created_b.status_code == 201, created_b.text
    client_channels_a_again = users_a.call(
        "admin", "GET", f"/api/v1/tenants/{users_a.tenant_id}/channels"
    )
    assert [item["display_name"] for item in client_channels_a_again.json()["items"]] == [
        "Support WhatsApp"
    ]
    hidden = users_a.call("viewer", "GET", f"/api/v1/tenants/{users_b.tenant_id}/channels")
    assert hidden.status_code == 404

    export = users_a.call("admin", "GET", f"/api/v1/tenants/{users_a.tenant_id}/data/export")
    assert export.status_code == 200
    export_text = export.text
    assert secret not in export_text
    assert connection.secret_ciphertext not in export_text
    assert "secret_ciphertext" not in export_text
    assert "prev_secret_ciphertext" not in export_text
    assert len(export.json()["channel_connections"]) == 1

    updated = _platform_call(
        staff,
        "PATCH",
        f"/channel-connections/{connection_id}",
        json={"display_name": "Support number", "ai_enabled": False},
    )
    assert updated.status_code == 200
    assert updated.json()["display_name"] == "Support number"
    assert updated.json()["ai_enabled"] is False
    assert secret not in updated.text
    paused = _platform_call(staff, "POST", f"/channel-connections/{connection_id}/pause")
    assert paused.status_code == 200 and paused.json()["status"] == "paused"
    assert secret not in paused.text
    resumed = _platform_call(staff, "POST", f"/channel-connections/{connection_id}/resume")
    assert resumed.status_code == 200 and resumed.json()["status"] == "active"
    assert secret not in resumed.text

    rotated = _platform_call(staff, "POST", f"/channel-connections/{connection_id}/rotate-secret")
    assert rotated.status_code == 200
    new_secret = rotated.json()["secret"]
    assert new_secret != secret
    db.refresh(connection)
    settings = build_test_settings(channel_secret_encryption_keys=SecretStr(encryption_key))
    assert signing_secrets(connection, settings) == (new_secret, secret)
    assert connection.secret_key_version == 2
    assert secret not in json.dumps(rotated.json())
    assert new_secret in json.dumps(rotated.json())

    rotated_detail = _platform_call(staff, "GET", f"/channel-connections/{connection_id}")
    rotated_list = _platform_call(staff, "GET", "/channel-connections")
    for response in (rotated_detail, rotated_list):
        output = json.dumps(response.json())
        assert secret not in output and new_secret not in output
        assert "secret_ciphertext" not in output
        assert "prev_secret_ciphertext" not in output
    rotated_export = users_a.call(
        "admin", "GET", f"/api/v1/tenants/{users_a.tenant_id}/data/export"
    )
    assert rotated_export.status_code == 200
    assert secret not in rotated_export.text and new_secret not in rotated_export.text

    audit_rows = list(
        db.scalars(select(AuditEvent).where(AuditEvent.target_type == "channel_connection"))
    )
    audit_json = json.dumps([row.metadata_json for row in audit_rows])
    assert secret not in audit_json and new_secret not in audit_json
    assert connection.secret_ciphertext not in audit_json
    assert connection.prev_secret_ciphertext is not None
    assert connection.prev_secret_ciphertext not in audit_json
    assert secret not in caplog.text and new_secret not in caplog.text

    revoked = _platform_call(staff, "POST", f"/channel-connections/{connection_id}/revoke")
    assert revoked.status_code == 200 and revoked.json()["status"] == "revoked"
    assert secret not in revoked.text and new_secret not in revoked.text
    resume_revoked = _platform_call(staff, "POST", f"/channel-connections/{connection_id}/resume")
    assert resume_revoked.status_code == 409


def test_channel_connection_quota_counts_non_revoked_rows(app: Any, db: Session) -> None:
    _configure_channel_key(app)
    users = seeded_tenant(app, db, prefix="channel-quota", plan_label="free")
    bot = make_bot(users)
    staff = users.as_user("staff")
    first = _platform_call(
        staff,
        "POST",
        "/channel-connections",
        json=_create_payload(users.tenant_id, bot["id"], name="First"),
    )
    assert first.status_code == 201, first.text
    connection_id = first.json()["id"]
    quota = users.call("admin", "GET", f"/api/v1/tenants/{users.tenant_id}/quota")
    assert quota.status_code == 200
    assert quota.json()["usage"]["channel_connections"] == 1

    second = _platform_call(
        staff,
        "POST",
        "/channel-connections",
        json=_create_payload(users.tenant_id, bot["id"], name="Second"),
    )
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "QUOTA_EXCEEDED"

    revoked = _platform_call(staff, "POST", f"/channel-connections/{connection_id}/revoke")
    assert revoked.status_code == 200
    quota_after = users.call("admin", "GET", f"/api/v1/tenants/{users.tenant_id}/quota")
    assert quota_after.json()["usage"]["channel_connections"] == 0
    retry = _platform_call(
        staff,
        "POST",
        "/channel-connections",
        json=_create_payload(users.tenant_id, bot["id"], name="Second"),
    )
    assert retry.status_code == 201, retry.text


def test_channel_create_rejects_private_hosts_non_http_and_production_http(
    app: Any, db: Session
) -> None:
    key = _configure_channel_key(app)
    users = seeded_tenant(app, db, prefix="channel-url-validation", plan_label="business")
    bot = make_bot(users)
    staff = users.as_user("staff")
    for base_url in (
        "http://127.0.0.1:8080",
        "http://0x7f000001:8080",
        "http://192.168.1.20",
        "http://[::1]:8080",
        "http://localhost:8080",
        "http://service.internal",
        "ftp://many.example.test",
    ):
        payload = _create_payload(users.tenant_id, bot["id"])
        payload["many_base_url"] = base_url
        response = _platform_call(staff, "POST", "/channel-connections", json=payload)
        assert response.status_code == 422, (base_url, response.text)
        assert response.json()["error"]["code"] == "INVALID_MANY_URL"

    app.dependency_overrides[get_settings] = lambda: build_test_settings(
        channel_secret_encryption_keys=SecretStr(key),
        environment="production",
    )
    payload = _create_payload(users.tenant_id, bot["id"])
    payload["many_base_url"] = "http://many.example.test"
    response = _platform_call(staff, "POST", "/channel-connections", json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_MANY_URL"


def test_contact_identity_indexes_preserve_website_and_scope_channels(
    app: Any, db: Session
) -> None:
    _configure_channel_key(app)
    users = seeded_tenant(app, db, prefix="identity-scope", plan_label="business")
    bot = make_bot(users)
    key = Fernet.generate_key().decode("ascii")
    connection_ids = [uuid4(), uuid4()]
    connections = [
        ChannelConnection(
            id=connection_id,
            tenant_id=users.tenant_id,
            bot_id=UUID(bot["id"]),
            channel="whatsapp",
            display_name=f"WA {index}",
            many_base_url="https://many.example.test",
            secret_ciphertext=encrypt_secret(f"test-secret-{index}", key),
            health_status="unknown",
        )
        for index, connection_id in enumerate(connection_ids)
    ]
    contacts = [
        Contact(
            id=uuid4(),
            tenant_id=users.tenant_id,
            display_name=f"Contact {index}",
            email=f"contact-{index}-{users.tenant_id.hex[:8]}@example.test",
        )
        for index in range(4)
    ]
    db.add_all([*connections, *contacts])
    db.flush()

    first_website = ContactIdentity(
        id=uuid4(),
        tenant_id=users.tenant_id,
        contact_id=contacts[0].id,
        channel="website",
        external_id="website-visitor-one",
    )
    second_website = ContactIdentity(
        id=uuid4(),
        tenant_id=users.tenant_id,
        contact_id=contacts[1].id,
        channel="website",
        external_id="website-visitor-two",
    )
    db.add_all([first_website, second_website])
    db.flush()
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.add(
                ContactIdentity(
                    id=uuid4(),
                    tenant_id=users.tenant_id,
                    contact_id=contacts[2].id,
                    channel="website",
                    external_id="website-visitor-one",
                )
            )
            db.flush()

    same_external_ids = [
        ContactIdentity(
            id=uuid4(),
            tenant_id=users.tenant_id,
            contact_id=contacts[index + 2].id,
            channel="whatsapp",
            external_id="same-external-contact",
            connection_id=connection_ids[index],
        )
        for index in range(2)
    ]
    db.add_all(same_external_ids)
    db.flush()
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.add(
                ContactIdentity(
                    id=uuid4(),
                    tenant_id=users.tenant_id,
                    contact_id=contacts[2].id,
                    channel="whatsapp",
                    external_id="same-external-contact",
                    connection_id=connection_ids[0],
                )
            )
            db.flush()
    assert (
        db.scalar(
            select(ContactIdentity).where(
                ContactIdentity.channel == "website",
                ContactIdentity.external_id == "website-visitor-two",
            )
        )
        is not None
    )
    assert (
        db.scalar(
            select(ContactIdentity.id).where(
                ContactIdentity.external_id == "same-external-contact",
                ContactIdentity.connection_id == connection_ids[1],
            )
        )
        is not None
    )


def test_inbound_channel_message_dedupe_is_unique_per_conversation(app: Any, db: Session) -> None:
    users = seeded_tenant(app, db, prefix="channel-message-dedupe", plan_label="business")
    bot = make_bot(users)
    conversation = Conversation(
        tenant_id=users.tenant_id,
        bot_id=UUID(bot["id"]),
        channel="whatsapp",
        mode="ai",
        status="open",
        source="website",
    )
    db.add(conversation)
    db.flush()

    db.add(
        Message(
            tenant_id=users.tenant_id,
            bot_id=UUID(bot["id"]),
            conversation_id=conversation.id,
            sender_type="visitor",
            text="hello",
            channel_message_id="external-message-1",
        )
    )
    db.flush()
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.add(
                Message(
                    tenant_id=users.tenant_id,
                    bot_id=UUID(bot["id"]),
                    conversation_id=conversation.id,
                    sender_type="visitor",
                    text="duplicate inbound",
                    channel_message_id="external-message-1",
                )
            )
            db.flush()

    # The partial index applies only to inbound visitor messages.
    db.add(
        Message(
            tenant_id=users.tenant_id,
            bot_id=UUID(bot["id"]),
            conversation_id=conversation.id,
            sender_type="ai",
            text="reply",
            channel_message_id="external-message-1",
        )
    )
    db.flush()
