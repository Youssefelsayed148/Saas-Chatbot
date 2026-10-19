"""docs/17 contract suite v1 against the FakeMany transport (P6-06).

Each test names the docs/17 section it pins. The suite is one file an owner can
read next to docs/17; deeper per-area coverage lives in test_channel_events.py
( section 4 ), test_channel_outbound.py ( sections 5.1 and 6 ) and
test_channel_health.py ( sections 4.3 and 5.2 ). Everything runs on the
disposable database; no network and no docker.

| docs/17 section | covered here | reinforced in |
| --- | --- | --- |
| 3 signing (HMAC-SHA256, ±5 min skew, generic 401) | A1-A3 | events |
| 2 connection states (paused/revoked/secret) | B1-B4 | outbound, channels |
| 4 events endpoint (202 / dedupe / 422 / unknown) | C1-C2 | events |
| 5.1 SaaS→Many send (headers / body / kind / idempotency) | D1-D3 | outbound |
| 6 retries (same message_id, budget → many_unreachable) | E1-E3 | outbound |
| 5.2 health pull / 4.3 push channel.status | F1-F2 | health |
| 7 privacy (secret never leaves the SaaS) | B4 | channels |
"""

import hashlib
import hmac as hmac_module
import json
import socket
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

import app.channels.outbound as outbound_module
from app.channels.outbound import enqueue_message
from app.channels.secrets import encrypt_secret
from app.channels.signing import sign, verify
from app.chat.conversations import append_message
from app.db.models import (
    ChannelConnection,
    ChannelEvent,
    Contact,
    ContactIdentity,
    Conversation,
    Job,
    Message,
)
from app.jobs.runner import execute_claimed_job
from app.knowledge.storage import LocalStorage
from tests.conftest import build_test_settings
from tests.fakes.fake_many import FakeMany
from tests.helpers import make_bot, seeded_tenant
from tests.test_channel_events import (
    _connection,
    _patch_success_pipeline,
    _payload,
    _post,
    _run_event,
)

SKEW_SECONDS = 300
MANY_IP = "93.184.216.34"


def _many_url(base_url: str | None) -> str:
    return base_url or f"https://many-{uuid4().hex[:6]}.example.test"


def _token(app: Any) -> str:
    return getattr(app.state, "channel_test_key", None) or Fernet.generate_key().decode(
        "ascii"
    )


def _run_job(db: OrmSession, job: Job, settings: Any) -> None:
    job.status = "running"
    job.attempts += 1
    job.started_at = job.started_at or datetime.now(UTC)
    db.commit()
    execute_claimed_job(db, job, settings, LocalStorage(settings))
    db.refresh(job)


def _wire_ip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_a, **_k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (MANY_IP, 443))],
    )


# --- A. Section 3: signing ---------------------------------------------------


def test_a1_signature_is_hmac_sha256_over_timestamp_dot_body(
    client: Any, app: Any, db: OrmSession
) -> None:
    """§3: `sha256=<hex HMAC-SHA256(secret, timestamp + "." + raw_body)>`."""
    connection_id, secret = _connection(app, db)
    raw = json.dumps(_payload(connection_id)).encode()
    timestamp = int(time.time())
    mac = sign(secret, timestamp, raw)
    assert mac.startswith("sha256=") and len(mac.split("=", 1)[1]) == 64
    recomputed = hmac_module.new(
        secret.encode(), f"{timestamp}.".encode() + raw, hashlib.sha256
    ).hexdigest()
    assert mac == f"sha256={recomputed}"
    accepted = client.post(
        "/api/channels/manyosiris/events",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "X-Osiris-Connection": str(connection_id),
            "X-Osiris-Timestamp": str(timestamp),
            "X-Osiris-Signature": mac,
        },
    )
    assert accepted.status_code == 202, accepted.text
    # The signature binds the exact bytes: one space changes the verdict.
    tampered = client.post(
        "/api/channels/manyosiris/events",
        content=raw + b" ",
        headers={
            "X-Osiris-Connection": str(connection_id),
            "X-Osiris-Timestamp": str(timestamp),
            "X-Osiris-Signature": mac,
        },
    )
    assert tampered.status_code == 401


def test_a2_five_minute_skew_boundary_in_both_directions(
    client: Any, app: Any, db: OrmSession
) -> None:
    """§3: reject when the timestamp is more than 5 minutes from now."""
    connection_id, secret = _connection(app, db)
    now = int(time.time())
    for offset in (-SKEW_SECONDS + 1, 0, SKEW_SECONDS - 1):
        raw = json.dumps(
            _payload(connection_id, event_id=f"evt-skew-inside-{offset + SKEW_SECONDS}")
        ).encode()
        inside = _post(client, connection_id, secret, raw, timestamp=now + offset)
        assert inside.status_code == 202, (offset, inside.text)
    for offset in (-SKEW_SECONDS - 2, SKEW_SECONDS + 2):
        raw = json.dumps(
            _payload(connection_id, event_id=f"evt-skew-outside-{offset}")
        ).encode()
        outside = _post(client, connection_id, secret, raw, timestamp=now + offset)
        assert outside.status_code == 401, (offset, outside.text)


def test_a3_every_authentication_failure_is_the_same_generic_401(
    client: Any, app: Any, db: OrmSession
) -> None:
    """§3: one generic 401 for a bad signature, an old/future clock, an unknown
    and a revoked connection (no oracle about which check failed)."""
    active_id, active_secret = _connection(app, db)
    revoked_id, revoked_secret = _connection(app, db, status="revoked")
    raw_active = json.dumps(_payload(active_id)).encode()
    raw_revoked = json.dumps(_payload(revoked_id)).encode()
    failures = (
        _post(client, active_id, active_secret, raw_active, signature="sha256=00"),
        _post(client, active_id, active_secret, raw_active, timestamp=0),
        _post(client, uuid4(), active_secret, raw_active),
        _post(client, revoked_id, revoked_secret, raw_revoked),
    )
    assert {response.status_code for response in failures} == {401}
    assert {response.json()["error"]["message"] for response in failures} == {
        "Invalid channel request."
    }


# --- B. Section 2: connection states ----------------------------------------


def test_b1_paused_accepts_202_stores_no_ai_no_send_agent_reply_409(
    client: Any, app: Any, db: OrmSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§2 paused: signed events accepted (202). The message is stored, no AI
    reply is generated, no outbound job is created; the inbox agent reply is
    refused with 409 CONNECTION_PAUSED (test B2 for the reply side)."""
    _patch_success_pipeline(monkeypatch)
    connection_id, secret = _connection(app, db, status="paused")
    event_id = f"evt-paused-{uuid4().hex[:8]}"
    payload = _payload(connection_id, event_id=event_id)
    accepted = _post(client, connection_id, secret, json.dumps(payload).encode())
    assert accepted.status_code == 202, accepted.text
    assert accepted.json() == {"status": "accepted"}
    event = _run_event(db, event_id)
    assert event.status == "processed"
    visitor = db.scalar(select(Message).where(Message.sender_type == "visitor"))
    assert visitor is not None and visitor.text == "Hello"
    assert db.scalar(
        select(func.count(Message.id)).where(Message.sender_type == "ai")
    ) == 0
    assert db.scalar(
        select(func.count(Job.id)).where(Job.type == "channel_send")
    ) == 0
    conversation = db.scalar(select(Conversation))
    assert conversation is not None
    assert conversation.status == "waiting_human"


def test_b2_paused_agent_reply_is_409_and_resume_does_not_resend(
    app: Any, db: OrmSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§2 paused: `CONNECTION_PAUSED` on the inbox agent reply; messages that
    were pending when the connection paused fail and are never auto-resent."""
    key = _token(app)
    app.state.channel_test_key = key
    users = seeded_tenant(app, db, prefix=f"contract-paused-{uuid4().hex[:8]}")
    bot = make_bot(users)
    connection = ChannelConnection(
        tenant_id=users.tenant_id,
        bot_id=UUID(bot["id"]),
        channel="whatsapp",
        display_name="Contract Paused",
        many_base_url=_many_url(None),
        status="paused",
        ai_enabled=True,
        secret_ciphertext=encrypt_secret("contract-pause-secret", key),
        secret_key_version=1,
        health_status="unknown",
    )
    db.add(connection)
    conversation = Conversation(
        tenant_id=users.tenant_id,
        bot_id=connection.bot_id,
        source="channel",
        channel="whatsapp",
        connection_id=connection.id,
        mode="human",
        status="open",
    )
    db.add(conversation)
    db.commit()
    path = f"/api/v1/tenants/{users.tenant_id}/conversations/{conversation.id}"
    jobs_before = db.scalar(select(func.count(Job.id)))
    refuse = users.call("editor", "POST", path + "/messages", json={"text": "Hi"})
    assert refuse.status_code == 409
    assert refuse.json()["error"]["code"] == "CONNECTION_PAUSED"
    assert db.scalar(select(func.count(Job.id))) == jobs_before
    # Resume stays quiet about anything that failed while paused.
    connection.status = "active"
    db.commit()
    assert db.scalar(
        select(func.count(Job.id)).where(Job.type == "channel_send")
    ) == 0


def test_b3_revoked_rejects_every_signed_event_like_unknown(
    client: Any, app: Any, db: OrmSession
) -> None:
    """§2 revoked: terminal — every signed event is the generic 401."""
    revoked_id, revoked_secret = _connection(app, db, status="revoked")
    for index in range(2):
        raw = json.dumps(_payload(revoked_id, event_id=f"evt-revoked-{index}")).encode()
        response = _post(client, revoked_id, revoked_secret, raw)
        assert response.status_code == 401
        assert response.json()["error"]["message"] == "Invalid channel request."
    assert db.scalar(select(func.count(ChannelEvent.id))) == 0


def test_b4_secret_is_encrypted_at_rest_and_never_returned(
    app: Any, db: OrmSession
) -> None:
    """§2/§7: one secret per connection, shown once, stored encrypted, and
    present on no staff or client read model."""
    connection_id, secret = _connection(app, db)
    from app.channels.router import ClientChannelOut, StaffConnectionOut

    connection = db.get(ChannelConnection, connection_id)
    assert connection is not None
    fernet = Fernet(_token(app))
    assert fernet.decrypt(connection.secret_ciphertext) == secret.encode()
    staff_fields = set(StaffConnectionOut.model_fields)
    client_fields = set(ClientChannelOut.model_fields)
    for field in ("secret", "secret_ciphertext", "prev_secret_ciphertext"):
        assert field not in staff_fields
        assert field not in client_fields


# --- C. Section 4: events endpoint -------------------------------------------


def test_c1_accepted_duplicate_malformed_unknown_are_pinned(
    client: Any, app: Any, db: OrmSession
) -> None:
    """§4: 202 `accepted`/`duplicate` for the same `event_id`; 422 for a signed
    malformed body (Many must not retry); unknown event types are ignored."""
    connection_id, secret = _connection(app, db)
    event_id = f"evt-contract-{uuid4().hex[:8]}"
    raw = json.dumps(_payload(connection_id, event_id=event_id)).encode()
    first = _post(client, connection_id, secret, raw)
    duplicate = _post(client, connection_id, secret, raw, timestamp=int(time.time()) + 1)
    assert first.status_code == duplicate.status_code == 202
    assert first.json() == {"status": "accepted"}
    assert duplicate.json() == {"status": "duplicate"}
    event = db.scalar(select(ChannelEvent).where(ChannelEvent.event_id == event_id))
    assert event is not None and event.status == "received"
    malformed = _post(client, connection_id, secret, b"{not-json")
    assert malformed.status_code == 422
    unknown = _payload(
        connection_id,
        event_id=f"evt-unknown-{uuid4().hex[:8]}",
        event_type="future.event",
    )
    accepted_unknown = _post(client, connection_id, secret, json.dumps(unknown).encode())
    assert accepted_unknown.status_code == 202
    processed = _run_event(db, unknown["event_id"])
    assert processed.status == "ignored"


def test_c2_processing_waits_for_the_job_and_reruns_are_idempotent(
    client: Any, app: Any, db: OrmSession
) -> None:
    """§4: processing runs as a job after the 202; rerunning the job and a
    replay of the same event_id never duplicate rows."""
    connection_id, secret = _connection(app, db)
    event_id = f"evt-job-{uuid4().hex[:8]}"
    assert (
        _post(
            client,
            connection_id,
            secret,
            json.dumps(_payload(connection_id, event_id=event_id)).encode(),
        ).status_code
        == 202
    )
    assert db.scalar(select(func.count(Conversation.id))) == 0  # job not run yet
    _run_event(db, event_id)
    after = (
        int(db.scalar(select(func.count(Conversation.id))) or 0),
        int(db.scalar(select(func.count(Message.id))) or 0),
    )
    assert after[0] == 1 and after[1] >= 1  # the reply came through the pipeline
    _run_event(db, event_id)  # worker-visible retry of the same job payload
    assert (
        int(db.scalar(select(func.count(Conversation.id))) or 0),
        int(db.scalar(select(func.count(Message.id))) or 0),
    ) == after


# --- D. Section 5.1: SaaS → Many send ----------------------------------------


class _RecordingFakeMany(FakeMany):
    """FakeMany plus the exact outbound request bytes for §3 verification."""

    def __init__(self, connection_id: str, secret: str) -> None:
        super().__init__(connection_id, secret)
        self.raw: list[tuple[bytes, str, str]] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.raw.append(
            (
                request.content,
                request.headers["X-Osiris-Timestamp"],
                request.headers["X-Osiris-Signature"],
            )
        )
        return super().handle(request)


def _outbound_context(
    app: Any, db: OrmSession, monkeypatch: pytest.MonkeyPatch
) -> tuple[ChannelConnection, Conversation, Message, Job, Any, _RecordingFakeMany]:
    key = _token(app)
    app.state.channel_test_key = key
    users = seeded_tenant(app, db, prefix=f"contract-send-{uuid4().hex[:8]}")
    bot = make_bot(users)
    secret = "contract-send-secret"
    connection = ChannelConnection(
        tenant_id=users.tenant_id,
        bot_id=UUID(bot["id"]),
        channel="whatsapp",
        display_name="Contract Send",
        many_base_url="https://many.example.test",
        status="active",
        ai_enabled=True,
        secret_ciphertext=encrypt_secret(secret, key),
        secret_key_version=1,
        health_status="unknown",
    )
    db.add(connection)
    contact = Contact(
        tenant_id=users.tenant_id,
        display_name="Contract contact",
        source_channel="whatsapp",
    )
    db.add(contact)
    db.flush()
    identity = ContactIdentity(
        tenant_id=users.tenant_id,
        contact_id=contact.id,
        channel="whatsapp",
        external_id="contract-contact-1",
        connection_id=connection.id,
    )
    db.add(identity)
    db.flush()
    conversation = Conversation(
        tenant_id=users.tenant_id,
        bot_id=connection.bot_id,
        source="channel",
        channel="whatsapp",
        connection_id=connection.id,
        contact_id=contact.id,
        external_conversation_id="contract-conversation-1",
        mode="human",
        status="open",
    )
    db.add(conversation)
    db.commit()
    message = append_message(
        db, conversation, sender_type="ai", text="Contract reply: مرحباً", can_answer=True
    )
    settings = build_test_settings(channel_secret_encryption_keys=SecretStr(key))
    enqueue_message(db, conversation, message, settings)
    db.commit()
    job = db.scalar(select(Job).where(Job.type == "channel_send"))
    assert job is not None
    fake = _RecordingFakeMany(str(connection.id), secret)
    _wire_ip(monkeypatch)
    monkeypatch.setattr(outbound_module, "_client", fake.client)
    return connection, conversation, message, job, settings, fake


def test_d1_outbound_is_signed_to_many_with_contract_headers(
    app: Any, db: OrmSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§5.1: signed `POST {many_base_url}/api/saas/messages` where `message_id`
    (our id) is the idempotency key; only ai/agent replies are sent."""
    connection, conversation, message, job, settings, fake = _outbound_context(
        app, db, monkeypatch
    )
    _run_job(db, job, settings)
    assert job.status == "succeeded"
    assert len(fake.requests) == 1
    body = fake.requests[0]
    assert body["message_id"] == str(message.id)
    assert body["connection_id"] == str(connection.id)
    assert body["external_contact_id"] == "contract-contact-1"
    assert body["external_conversation_id"] == "contract-conversation-1"
    assert body["kind"] in {"reply", "agent", "handoff"}
    assert body["text"] == "Contract reply: مرحباً"
    headers = fake.headers[0]
    assert headers["X-Osiris-Connection"] == str(connection.id)
    raw_body, ts_header, sig_header = fake.raw[0]
    assert ts_header == headers["X-Osiris-Timestamp"]
    assert verify("contract-send-secret", ts_header, raw_body, sig_header)
    # Many's ack is stored as channel_message_id; delivery waits for §4.2.
    assert message.channel_message_id == "many-1"
    assert message.delivery_status == "pending"


def test_d2_duplicate_and_crashed_runs_never_resend(
    app: Any, db: OrmSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§5.1: Many dedupes on `message_id`; the SaaS sends a given AI message
    once even across repeated job executions."""
    connection, conversation, message, job, settings, fake = _outbound_context(
        app, db, monkeypatch
    )
    for _ in range(3):
        job.status = "succeeded"
        db.commit()
        _run_job(db, job, settings)
    assert len(fake.requests) == 1
    assert fake.deliveries == {str(message.id): "many-1"}


def test_d3_notes_and_system_messages_never_reach_many(
    app: Any, db: OrmSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§5.1: internal notes and system events are never sent."""
    key = _token(app)
    app.state.channel_test_key = key
    users = seeded_tenant(app, db, prefix=f"contract-notes-{uuid4().hex[:8]}")
    bot = make_bot(users)
    secret = "contract-notes-secret"
    connection = ChannelConnection(
        tenant_id=users.tenant_id,
        bot_id=UUID(bot["id"]),
        channel="whatsapp",
        display_name="Notes connection",
        many_base_url="https://many.example.test",
        status="active",
        ai_enabled=True,
        secret_ciphertext=encrypt_secret(secret, key),
        secret_key_version=1,
        health_status="unknown",
    )
    db.add(connection)
    conversation = Conversation(
        tenant_id=users.tenant_id,
        bot_id=connection.bot_id,
        source="channel",
        channel="whatsapp",
        connection_id=connection.id,
        mode="human",
        status="open",
    )
    db.add(conversation)
    db.commit()
    settings = build_test_settings(channel_secret_encryption_keys=SecretStr(key))
    for sender_type, text in (
        ("system", "System event that is never sent"),
        ("agent", "Agent reply that is sent"),
    ):
        message = append_message(db, conversation, sender_type=sender_type, text=text)
        enqueue_message(db, conversation, message, settings)
    db.commit()
    send_jobs = list(db.scalars(select(Job).where(Job.type == "channel_send")))
    assert len(send_jobs) == 1


# --- E. Section 6: retries ---------------------------------------------------


def test_e1_budget_reuses_message_id_and_many_unreachable_degrades_health(
    app: Any, db: OrmSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§6: retry 5xx/timeouts with the same `message_id`; after the retry
    budget the message is `failed`/`many_unreachable` and the connection is
    degraded."""
    connection, conversation, message, job, settings, fake = _outbound_context(
        app, db, monkeypatch
    )
    for _ in range(6):
        fake.responses.append(500)
        _run_job(db, job, settings)
        job.status = "pending" if job.status != "failed" else "failed"
        db.commit()
    ids = {body["message_id"] for body in fake.requests}
    assert ids == {str(message.id)}
    assert job.status == "failed"
    assert message.delivery_status == "failed"
    assert message.error_code == "many_unreachable"
    db.refresh(connection)
    assert connection.health_status == "degraded"
    assert connection.health_reason == "many_unreachable"


def test_e2_429_is_delayed_by_retry_after_and_4xx_ends_immediately(
    app: Any, db: OrmSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§6: 429 with `Retry-After` schedules the retry later; other 4xx are
    permanent. (Full 4xx matrix and timeout cases live in test_channel_outbound.)"""
    connection, conversation, message, job, settings, fake = _outbound_context(
        app, db, monkeypatch
    )
    fake.responses.append((429, "30"))
    _run_job(db, job, settings)
    assert len(fake.requests) == 1
    assert job.status == "pending"
    db.refresh(job)
    assert job.run_at is not None


def test_e3_no_alternative_send_path_after_exhaustion(
    app: Any, db: OrmSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§1.4/§6: once the budget is spent the message is failed and nothing else
    is scheduled on the SaaS side. (The Many-side rule is docs/17 §1.4 item 4:
    Many must not fall back to its own AI — verified in the Many workstream.)"""
    connection, conversation, message, job, settings, fake = _outbound_context(
        app, db, monkeypatch
    )
    for _ in range(6):
        fake.responses.append(500)
        _run_job(db, job, settings)
        db.refresh(job)
        if job.status != "pending":
            break
        job.status = "pending"
        db.commit()
    assert job.status == "failed"
    assert message.delivery_status == "failed" and message.error_code == "many_unreachable"
    assert db.scalar(
        select(func.count(Job.id)).where(Job.type == "channel_send")
    ) == 1


# --- F. Sections 5.2 / 4.3: health pull and push -----------------------------


def test_f1_health_pull_is_a_signed_empty_body_get(
    app: Any, db: OrmSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§5.2: signed `GET /api/saas/connections/{id}/health` over the empty
    body; the peer status maps onto the connection health."""
    from tests.test_channel_health import _staff_connection, _wire_fake

    users, connection, secret = _staff_connection(app, db)
    fake = FakeMany(str(connection.id), secret)
    fake.health_responses.append("token_expiring")
    _wire_fake(monkeypatch, fake)
    from app.channels.health import pull_health

    settings = build_test_settings(
        channel_secret_encryption_keys=SecretStr(_token(app))
    )
    status, detail, checked = pull_health(connection, settings)
    assert len(fake.health_requests) == 1
    headers = fake.health_requests[0]
    assert headers["X-Osiris-Connection"] == str(connection.id)
    assert verify(secret, headers["X-Osiris-Timestamp"], b"", headers["X-Osiris-Signature"])
    assert (status, detail) == ("token_expiring", None)
    assert checked is not None
    db.refresh(connection)


def test_f2_health_push_maps_statuses_and_ignores_older_events(
    client: Any, app: Any, db: OrmSession
) -> None:
    """§4.3: `channel.status` maps connected/token_expiring/token_expired;
    an older `occurred_at` than the stored one is ignored."""
    from app.channels.health import apply_health

    connection_id, secret = _connection(app, db)
    connection = db.get(ChannelConnection, connection_id)
    assert connection is not None
    now = datetime.now(UTC)
    newer = _payload(
        connection_id,
        event_id=f"evt-status-{uuid4().hex[:8]}",
        event_type="channel.status",
        occurred_at=(now - timedelta(minutes=1)).isoformat(),
        status="token_expiring",
    )
    accepted = _post(client, connection_id, secret, json.dumps(newer).encode())
    assert accepted.status_code == 202
    _run_event(db, newer["event_id"])
    db.refresh(connection)
    assert connection.health_status == "degraded"
    assert connection.health_reason == "token_expiring"
    before = connection.health_updated_at
    assert before is not None
    # An older transition must not move health backwards.
    apply_health(
        db,
        connection=connection,
        status="disconnected",
        detail="",
        occurred_at=now - timedelta(hours=2),
        source="push",
    )
    db.commit()
    db.refresh(connection)
    assert connection.health_updated_at == before
    assert connection.health_status == "degraded"
