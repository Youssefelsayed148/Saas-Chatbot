"""P6-02 authenticated Many event transport and idempotent storage handlers."""

import json
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

import app.channels.events as event_module
import app.chat.conversations as chat_conversations
from app.channels.inbound import run_channel_inbound
from app.channels.secrets import encrypt_secret
from app.channels.signing import sign
from app.chat.providers import ChatModel, ProviderError
from app.chat.service import ChatReply
from app.core.config import get_settings
from app.core.errors import ApiError
from app.db.models import (
    ChannelConnection,
    ChannelEvent,
    Contact,
    ContactIdentity,
    Conversation,
    Job,
    Message,
    UsageEvent,
)
from tests.conftest import build_test_settings
from tests.helpers import make_bot, seeded_tenant


def _connection(app: Any, db: Session, *, status: str = "active") -> tuple[UUID, str]:
    key = getattr(app.state, "channel_test_key", None) or Fernet.generate_key().decode("ascii")
    app.state.channel_test_key = key
    secret = f"phase6-event-secret-{uuid4().hex}"
    app.dependency_overrides[get_settings] = lambda: build_test_settings(
        channel_secret_encryption_keys=SecretStr(key), environment="test"
    )
    tenant = seeded_tenant(
        app, db, prefix=f"channel-event-{uuid4().hex[:8]}", plan_label="business"
    )
    bot = make_bot(tenant)
    connection = ChannelConnection(
        tenant_id=tenant.tenant_id,
        bot_id=UUID(bot["id"]),
        channel="whatsapp",
        display_name="Events",
        many_base_url="https://many.example.test",
        status=status,
        ai_enabled=True,
        secret_ciphertext=encrypt_secret(secret, key),
        secret_key_version=1,
        health_status="unknown",
    )
    db.add(connection)
    db.commit()
    return connection.id, secret


def _payload(
    connection_id: UUID, *, event_id: str | None = None, **overrides: object
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "version": 1,
        "event_id": event_id or str(uuid4()),
        "event_type": "message.received",
        "connection_id": str(connection_id),
        "occurred_at": datetime.now(UTC).isoformat(),
        "channel": "whatsapp",
        "external_contact_id": "contact-1",
        "contact": {"name": " Visitor\u0000 Name ", "handle": "@person\u0007"},
        "external_conversation_id": "conversation-1",
        "external_message_id": "message-1",
        "type": "text",
        "text": "Hello",
        "received_at": datetime.now(UTC).isoformat(),
        "origin": {"type": "campaign", "campaign_name": "Spring"},
    }
    payload.update(overrides)
    return payload


def _post(
    client: Any,
    connection_id: UUID,
    secret: str,
    raw: bytes,
    *,
    timestamp: int | None = None,
    connection_header: str | None = None,
    signature: str | None = None,
) -> Any:
    current = int(time.time()) if timestamp is None else timestamp
    return client.post(
        "/api/channels/manyosiris/events",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "X-Osiris-Connection": connection_header or str(connection_id),
            "X-Osiris-Timestamp": str(current),
            "X-Osiris-Signature": signature or sign(secret, current, raw),
        },
    )


def _run_event(db: Session, event_id: str, *, settings: Any | None = None) -> ChannelEvent:
    event = db.scalar(select(ChannelEvent).where(ChannelEvent.event_id == event_id))
    assert event is not None
    job = Job(
        tenant_id=event.tenant_id,
        bot_id=db.scalar(
            select(ChannelConnection.bot_id).where(ChannelConnection.id == event.connection_id)
        ),
        type="channel_inbound",
        status="running",
        payload={"channel_event_id": str(event.id)},
        attempts=1,
        max_attempts=3,
    )
    db.add(job)
    db.flush()
    assert run_channel_inbound(db, job, settings) is None
    db.commit()
    db.refresh(event)
    return event


def test_event_hmac_auth_matrix_and_signed_malformed_body(
    client: Any, app: Any, db: Session
) -> None:
    connection_id, secret = _connection(app, db)
    raw = json.dumps(_payload(connection_id)).encode()
    valid_time = int(time.time())
    bad_signature = _post(client, connection_id, secret, raw, signature="sha256=bad")
    stale = _post(client, connection_id, secret, raw, timestamp=valid_time - 600)
    future = _post(client, connection_id, secret, raw, timestamp=valid_time + 600)
    wrong_connection = _post(client, connection_id, secret, raw, connection_header=str(uuid4()))
    missing = _post(client, uuid4(), secret, raw)
    assert all(
        response.status_code == 401
        for response in (bad_signature, stale, future, wrong_connection, missing)
    )
    assert {
        (r.json()["error"]["code"], r.json()["error"]["message"])
        for r in (bad_signature, stale, future, wrong_connection, missing)
    } == {("UNAUTHORIZED", "Invalid channel request.")}
    malformed = _post(client, connection_id, secret, b"{not-json")
    assert malformed.status_code == 422


def test_revoked_and_wrong_valid_connection_have_same_generic_401(
    client: Any, app: Any, db: Session
) -> None:
    first_id, first_secret = _connection(app, db)
    second_id, _second_secret = _connection(app, db)
    raw = json.dumps(_payload(first_id)).encode()
    wrong_connection = _post(client, first_id, first_secret, raw, connection_header=str(second_id))
    revoked_id, revoked_secret = _connection(app, db, status="revoked")
    revoked = _post(client, revoked_id, revoked_secret, json.dumps(_payload(revoked_id)).encode())
    assert wrong_connection.status_code == revoked.status_code == 401
    assert wrong_connection.json()["error"]["message"] == revoked.json()["error"]["message"]


def test_event_duplicate_replay_paused_acceptance_and_atomic_enqueue(
    client: Any, app: Any, db: Session
) -> None:
    connection_id, secret = _connection(app, db, status="paused")
    payload = _payload(connection_id, event_id="evt-duplicate")
    raw = json.dumps(payload).encode()
    accepted = _post(client, connection_id, secret, raw)
    duplicate = _post(
        client, connection_id, secret, raw, timestamp=int(time.time()) + 1
    )  # fresh timestamp/signature, same event id
    assert accepted.status_code == duplicate.status_code == 202
    assert accepted.json() == {"status": "accepted"}
    assert duplicate.json() == {"status": "duplicate"}
    event = db.scalar(select(ChannelEvent).where(ChannelEvent.event_id == "evt-duplicate"))
    jobs = list(db.scalars(select(Job).where(Job.type == "channel_inbound")))
    assert event is not None and event.status == "received"
    assert len(jobs) == 1 and jobs[0].payload == {"channel_event_id": str(event.id)}
    _run_event(db, "evt-duplicate")
    paused_conversation = db.scalar(select(Conversation))
    assert paused_conversation is not None and paused_conversation.status == "waiting_human"
    visitor_message = db.scalar(select(Message).where(Message.sender_type == "visitor"))
    assert visitor_message is not None and visitor_message.text == "Hello"
    assert db.scalar(select(func_count(Message.id)).where(Message.sender_type == "ai")) == 0


def test_unknown_type_is_stored_ignored_and_oversized_is_generic_401(
    client: Any, app: Any, db: Session
) -> None:
    connection_id, secret = _connection(app, db)
    unknown = _payload(connection_id, event_id="evt-unknown", event_type="future.event")
    response = _post(client, connection_id, secret, json.dumps(unknown).encode())
    assert response.status_code == 202
    event = _run_event(db, "evt-unknown")
    assert event.status == "ignored"
    oversized = _post(client, connection_id, secret, b"x" * (64 * 1024 + 1))
    assert oversized.status_code == 401
    assert oversized.json()["error"]["message"] == "Invalid channel request."


def test_connection_rate_limit_returns_retry_after(
    client: Any, app: Any, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    connection_id, secret = _connection(app, db)
    monkeypatch.setattr(event_module, "EVENTS_PER_MINUTE", 1)
    first = _payload(connection_id, event_id="evt-rate-1")
    second = _payload(connection_id, event_id="evt-rate-2")
    assert _post(client, connection_id, secret, json.dumps(first).encode()).status_code == 202
    limited = _post(client, connection_id, secret, json.dumps(second).encode())
    assert limited.status_code == 429
    assert 1 <= int(limited.headers["Retry-After"]) <= 60


def test_tenant_scoping_and_processed_job_rerun_are_idempotent(
    client: Any, app: Any, db: Session
) -> None:
    connection_a, secret_a = _connection(app, db)
    connection_b, secret_b = _connection(app, db)
    payload_a = _payload(connection_a, event_id="tenant-a-event")
    payload_b = _payload(connection_b, event_id="tenant-b-event")
    assert _post(client, connection_a, secret_a, json.dumps(payload_a).encode()).status_code == 202
    assert _post(client, connection_b, secret_b, json.dumps(payload_b).encode()).status_code == 202
    event = _run_event(db, "tenant-a-event")
    _run_event(db, "tenant-b-event")
    a_conversation = db.scalar(
        select(Conversation).where(Conversation.connection_id == connection_a)
    )
    b_conversation = db.scalar(
        select(Conversation).where(Conversation.connection_id == connection_b)
    )
    assert a_conversation is not None and b_conversation is not None
    assert a_conversation.id != b_conversation.id
    assert a_conversation.tenant_id != b_conversation.tenant_id
    replay = Job(
        tenant_id=event.tenant_id,
        bot_id=a_conversation.bot_id,
        type="channel_inbound",
        status="running",
        payload={"channel_event_id": str(event.id)},
        attempts=2,
        max_attempts=3,
    )
    db.add(replay)
    db.flush()
    message_count_before = db.scalar(select(func_count(Message.id)))
    assert run_channel_inbound(db, replay) is None
    db.commit()
    assert db.scalar(select(func_count(Message.id))) == message_count_before
    assert db.scalar(select(func_count(Message.id)).where(Message.sender_type == "visitor")) == 2


def test_inbound_dedupe_sanitization_and_origin_is_written_once(
    client: Any, app: Any, db: Session
) -> None:
    connection_id, secret = _connection(app, db)
    first = _payload(connection_id, event_id="evt-first")
    first["contact"] = {
        "name": " Visitor\u0000 Name " + "x" * 150,
        "handle": "@person\u0007" + "h" * 150,
    }
    assert _post(client, connection_id, secret, json.dumps(first).encode()).status_code == 202
    _run_event(db, "evt-first")
    second = _payload(
        connection_id,
        event_id="evt-second",
        external_message_id="message-2",
        origin={"type": "campaign", "campaign_name": "Overwrite"},
        contact=first["contact"],  # R-03: later events refresh details, so repeat them
    )
    assert _post(client, connection_id, secret, json.dumps(second).encode()).status_code == 202
    _run_event(db, "evt-second")
    duplicate_message = _payload(connection_id, event_id="evt-third", contact=first["contact"])
    assert (
        _post(client, connection_id, secret, json.dumps(duplicate_message).encode()).status_code
        == 202
    )
    _run_event(db, "evt-third")
    assert db.scalar(select(func_count(Message.id)).where(Message.sender_type == "visitor")) == 2
    contact = db.scalar(select(Contact))
    assert contact is not None and contact.display_name.startswith("Visitor Name")
    assert len(contact.display_name) == 120
    handle = contact.custom_fields["channel_handle"]
    assert isinstance(handle, str) and handle.startswith("@person") and len(handle) == 120
    assert "\u0007" not in handle
    identity = db.scalar(select(ContactIdentity))
    conversation = db.scalar(select(Conversation))
    assert identity is not None and identity.connection_id == connection_id
    assert conversation is not None and conversation.origin == first["origin"]


def func_count(column: Any) -> Any:
    from sqlalchemy import func

    return func.count(column)


class _UnusedModel(ChatModel):
    usage_totals: dict[str, int] | None = {}

    def complete(self, messages: list[dict[str, str]], *, json_mode: bool, max_tokens: int) -> str:
        del messages, json_mode, max_tokens
        raise ProviderError("test provider unavailable")


def _patch_success_pipeline(
    monkeypatch: pytest.MonkeyPatch, captured_questions: list[str] | None = None
) -> None:
    monkeypatch.setattr(chat_conversations, "default_model", lambda _bot: _UnusedModel())

    def successful_answer(*_args: Any, question: str, **_kwargs: Any) -> ChatReply:
        if captured_questions is not None:
            captured_questions.append(question)
        return ChatReply(
            answer="Stored answer",
            can_answer=True,
            needs_human=False,
            language="en",
            kind="answer",
            trace={"fake_pipeline": True},
        )

    monkeypatch.setattr(chat_conversations, "chat_answer", successful_answer)


def _post_received(
    client: Any,
    connection_id: UUID,
    secret: str,
    *,
    event_id: str,
    external_message_id: str,
    text: str = "Hello",
    message_type: str = "text",
) -> None:
    body = _payload(
        connection_id,
        event_id=event_id,
        external_message_id=external_message_id,
        text=text,
        type=message_type,
    )
    response = _post(client, connection_id, secret, json.dumps(body).encode())
    assert response.status_code == 202, response.text


def test_message_status_is_monotonic_and_health_ignores_old_events(
    client: Any, app: Any, db: Session
) -> None:
    connection_id, secret = _connection(app, db)
    received = _payload(connection_id, event_id="evt-inbound")
    assert _post(client, connection_id, secret, json.dumps(received).encode()).status_code == 202
    _run_event(db, "evt-inbound")
    message = db.scalar(select(Message))
    assert message is not None
    message.sender_type = "ai"
    message.delivery_status = "delivered"
    db.commit()
    for index, status in enumerate(("sent", "failed", "read")):
        event_payload = {
            "version": 1,
            "event_id": f"evt-status-{index}",
            "event_type": "message.status",
            "connection_id": str(connection_id),
            "occurred_at": datetime.now(UTC).isoformat(),
            "message_id": str(message.id),
            "status": status,
        }
        assert (
            _post(client, connection_id, secret, json.dumps(event_payload).encode()).status_code
            == 202
        )
        _run_event(db, f"evt-status-{index}")
    db.refresh(message)
    assert message.delivery_status == "read"
    health_time = datetime.now(UTC)
    newer = {
        "version": 1,
        "event_id": "evt-health-new",
        "event_type": "channel.status",
        "connection_id": str(connection_id),
        "occurred_at": health_time.isoformat(),
        "status": "connected",
    }
    older = {
        **newer,
        "event_id": "evt-health-old",
        "occurred_at": (health_time - timedelta(minutes=1)).isoformat(),
        "status": "disconnected",
    }
    for body in (newer, older):
        assert _post(client, connection_id, secret, json.dumps(body).encode()).status_code == 202
        _run_event(db, str(body["event_id"]))
    connection = db.get(ChannelConnection, connection_id)
    assert connection is not None and connection.health_status == "healthy"


def test_channel_pipeline_truncates_only_model_input_and_stores_pending_reply(
    client: Any,
    app: Any,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection_id, secret = _connection(app, db)
    captured: list[str] = []
    _patch_success_pipeline(monkeypatch, captured)
    long_text = "x" * 1500
    _post_received(
        client,
        connection_id,
        secret,
        event_id="evt-long-text",
        external_message_id="msg-long-text",
        text=long_text,
    )
    _run_event(db, "evt-long-text", settings=build_test_settings(chat_stub_model=True))
    visitor = db.scalar(select(Message).where(Message.sender_type == "visitor"))
    ai_message = db.scalar(select(Message).where(Message.sender_type == "ai"))
    assert visitor is not None and visitor.text == long_text
    assert captured == ["x" * 1000]
    assert ai_message is not None and ai_message.text == "Stored answer"
    assert ai_message.delivery_status == "pending"
    message_usage = db.scalar(
        select(UsageEvent).where(
            UsageEvent.kind == "message", UsageEvent.message_id == ai_message.id
        )
    )
    assert message_usage is not None
    trace = message_usage.payload["rag_trace"]
    assert isinstance(trace, dict)
    assert trace["channel"] == "whatsapp"
    assert trace["connection_id"] == str(connection_id)
    metering = db.scalar(
        select(UsageEvent).where(
            UsageEvent.kind == "ai_usage",
            UsageEvent.payload["event_type"].as_string() == "message",
        )
    )
    assert metering is not None and metering.payload["channel"] == "whatsapp"
    assert db.scalar(select(func_count(Job.id)).where(Job.type == "channel_send")) == 1


def test_human_mode_is_silent_and_resolved_conversation_reopens_in_ai_mode(
    client: Any,
    app: Any,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection_id, secret = _connection(app, db)
    connection = db.get(ChannelConnection, connection_id)
    assert connection is not None
    connection.ai_enabled = False
    db.commit()
    _post_received(
        client,
        connection_id,
        secret,
        event_id="evt-human-seed",
        external_message_id="msg-human-seed",
    )
    _run_event(db, "evt-human-seed")
    conversation = db.scalar(select(Conversation))
    assert conversation is not None
    conversation.mode = "human"
    conversation.status = "open"
    connection.ai_enabled = True
    db.commit()
    _post_received(
        client,
        connection_id,
        secret,
        event_id="evt-human-silent",
        external_message_id="msg-human-silent",
    )
    _run_event(db, "evt-human-silent")
    assert db.scalar(select(func_count(Message.id)).where(Message.sender_type == "ai")) == 0
    assert conversation.mode == "human"

    conversation.status = "resolved"
    db.commit()
    _patch_success_pipeline(monkeypatch)
    _post_received(
        client,
        connection_id,
        secret,
        event_id="evt-reopen",
        external_message_id="msg-reopen",
    )
    _run_event(db, "evt-reopen", settings=build_test_settings(chat_stub_model=True))
    db.refresh(conversation)
    assert conversation.mode == "ai"
    assert conversation.status == "open"
    assert db.scalar(select(func_count(Message.id)).where(Message.sender_type == "ai")) == 1


def test_ai_disabled_and_unsupported_hourly_reply_rules(client: Any, app: Any, db: Session) -> None:
    connection_id, secret = _connection(app, db)
    connection = db.get(ChannelConnection, connection_id)
    assert connection is not None
    connection.ai_enabled = False
    db.commit()
    _post_received(
        client,
        connection_id,
        secret,
        event_id="evt-disabled",
        external_message_id="msg-disabled",
    )
    _run_event(db, "evt-disabled")
    conversation = db.scalar(select(Conversation))
    assert conversation is not None and conversation.status == "waiting_human"
    assert db.scalar(select(func_count(Message.id)).where(Message.sender_type == "ai")) == 0

    connection.ai_enabled = True
    db.commit()
    for event_id, message_id in (
        ("evt-unsupported-1", "msg-unsupported-1"),
        ("evt-unsupported-2", "msg-unsupported-2"),
    ):
        _post_received(
            client,
            connection_id,
            secret,
            event_id=event_id,
            external_message_id=message_id,
            text="",
            message_type="unsupported",
        )
        _run_event(db, event_id)
    notices = list(
        db.scalars(
            select(Message).where(Message.sender_type == "ai", Message.needs_human.is_(True))
        )
    )
    assert len(notices) == 1
    assert notices[0].delivery_status == "pending"
    assert notices[0].citations is None
    assert conversation.status == "waiting_human"


def test_quota_and_provider_failures_store_handoff_replies_without_logging_text(
    client: Any,
    app: Any,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    connection_id, secret = _connection(app, db)
    monkeypatch.setattr(chat_conversations, "default_model", lambda _bot: _UnusedModel())
    monkeypatch.setattr(
        chat_conversations,
        "reserve",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ApiError(429, "QUOTA_EXCEEDED", "usage limit")
        ),
    )
    private_text = "private inbound message not for logs"
    _post_received(
        client,
        connection_id,
        secret,
        event_id="evt-quota",
        external_message_id="msg-quota",
        text=private_text,
    )
    _run_event(db, "evt-quota", settings=build_test_settings(chat_stub_model=True))
    quota_reply = db.scalar(select(Message).where(Message.sender_type == "ai"))
    conversation = db.scalar(select(Conversation))
    assert quota_reply is not None and "support" in quota_reply.text.lower()
    assert conversation is not None and conversation.status == "waiting_human"
    assert private_text not in caplog.text

    connection_id, secret = _connection(app, db)
    monkeypatch.undo()
    monkeypatch.setattr(chat_conversations, "default_model", lambda _bot: _UnusedModel())
    monkeypatch.setattr(
        chat_conversations,
        "chat_answer",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ProviderError("test provider failure")),
    )
    _post_received(
        client,
        connection_id,
        secret,
        event_id="evt-provider-failure",
        external_message_id="msg-provider-failure",
        text=private_text,
    )
    _run_event(db, "evt-provider-failure", settings=build_test_settings(chat_stub_model=True))
    failure_reply = db.scalar(
        select(Message).where(Message.sender_type == "ai").order_by(Message.created_at.desc())
    )
    assert failure_reply is not None and "support" in failure_reply.text.lower()
    assert private_text not in caplog.text
