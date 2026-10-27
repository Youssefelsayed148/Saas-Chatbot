"""P6-03 outbound contract, security, retry and website isolation checks."""

import json
import socket
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import app.channels.outbound as outbound
from app.channels.inbound import run_channel_inbound
from app.channels.outbound import enqueue_message
from app.channels.secrets import encrypt_secret
from app.chat.conversations import append_message
from app.core.config import Settings
from app.db.models import (
    ChannelConnection,
    ChannelEvent,
    Conversation,
    Job,
    Message,
)
from app.jobs.runner import execute_claimed_job
from app.knowledge.storage import LocalStorage
from tests.conftest import build_test_settings, run_migrations
from tests.fakes.fake_many import FakeMany
from tests.helpers import seeded_tenant
from tests.test_channel_events import (
    _connection,
    _patch_success_pipeline,
    _payload,
    _post,
    _run_event,
)


@pytest.fixture
def send_context(client: Any, app: Any, db: Session, monkeypatch: pytest.MonkeyPatch) -> Any:
    connection_id, secret = _connection(app, db)
    payload = _payload(connection_id)
    assert _post(client, connection_id, secret, json.dumps(payload).encode()).status_code == 202
    # Human mode avoids a provider call while keeping genuine inbound mapping.
    connection = db.get(ChannelConnection, connection_id)
    assert connection is not None
    connection.ai_enabled = False
    db.commit()
    _run_event(db, payload["event_id"])
    conversation = db.scalar(select(Conversation))
    assert conversation is not None
    conversation.mode = "human"
    message = append_message(
        db, conversation, sender_type="ai", text="Private reply: مرحباً", can_answer=True
    )
    settings = build_test_settings(
        channel_secret_encryption_keys=SecretStr(app.state.channel_test_key)
    )
    enqueue_message(db, conversation, message, settings)
    db.commit()
    job = db.scalar(select(Job).where(Job.type == "channel_send"))
    assert job is not None
    fake = FakeMany(str(connection_id), secret)
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_a, **_k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))],
    )
    monkeypatch.setattr(outbound, "_client", fake.client)
    return connection, conversation, message, job, settings, fake


def run(db: Session, job: Job, settings: Settings) -> None:
    job.status = "running"
    job.attempts += 1
    job.started_at = job.started_at or datetime.now(UTC)
    db.commit()
    execute_claimed_job(db, job, settings, LocalStorage(settings))
    db.refresh(job)


def callbacks(db: Session, settings: Settings) -> None:
    for event in db.scalars(select(ChannelEvent).where(ChannelEvent.status == "received")):
        job = Job(
            tenant_id=event.tenant_id,
            bot_id=db.scalar(
                select(ChannelConnection.bot_id).where(ChannelConnection.id == event.connection_id)
            ),
            type="channel_inbound",
            payload={"channel_event_id": str(event.id)},
            status="running",
            attempts=1,
        )
        db.add(job)
        db.flush()
        assert run_channel_inbound(db, job, settings) is None
    db.commit()


def test_success_duplicate_current_secret_rotation_and_no_text_logs(
    send_context: Any,
    db: Session,
    app: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    connection, conversation, message, job, settings, fake = send_context
    caplog.set_level("INFO")
    run(db, job, settings)
    assert job.status == "succeeded"
    assert message.channel_message_id == "many-1" and message.delivery_status == "pending"
    run(db, job, settings)
    assert len(fake.requests) == 1
    assert fake.requests[0] == {
        "message_id": str(message.id),
        "connection_id": str(connection.id),
        "external_contact_id": "contact-1",
        "external_conversation_id": "conversation-1",
        "text": message.text,
        "kind": "reply",
    }
    rotated = "new-secret-after-rotation"
    connection.secret_ciphertext = encrypt_secret(rotated, app.state.channel_test_key)
    connection.secret_key_version += 1
    fake.secret = rotated
    second = append_message(db, conversation, sender_type="agent", text="Second private reply")
    enqueue_message(db, conversation, second, settings)
    db.commit()
    second_job = db.scalar(select(Job).where(Job.payload["message_id"].astext == str(second.id)))
    assert second_job is not None
    run(db, second_job, settings)
    assert len(fake.requests) == 2 and fake.requests[-1]["kind"] == "agent"
    assert message.text not in caplog.text and second.text not in caplog.text
    assert rotated not in caplog.text and fake.secret not in caplog.text
    assert all(
        set(j.payload) <= {"message_id", "previous_message_id"}
        for j in db.scalars(select(Job).where(Job.type == "channel_send"))
    )


@pytest.mark.parametrize(
    "outcome",
    [
        500,
        httpx.ReadTimeout("private exception text"),
        httpx.ConnectError("secret exception text"),
        (429, "120"),
    ],
)
def test_retry_then_success_with_same_id(send_context: Any, db: Session, outcome: Any) -> None:
    _connection, _conversation, message, job, settings, fake = send_context
    fake.responses.extend([outcome, 202])
    before = datetime.now(UTC)
    run(db, job, settings)
    assert job.status == "pending" and message.delivery_status == "pending"
    assert job.error == "Many is temporarily unavailable."
    if isinstance(outcome, tuple):
        assert (job.run_at - before).total_seconds() >= 120
    else:
        assert 14 <= (job.run_at - before).total_seconds() <= 24
    run(db, job, settings)
    assert job.status == "succeeded" and message.channel_message_id == "many-1"
    assert {r["message_id"] for r in fake.requests} == {str(message.id)}
    assert len(fake.deliveries) == 1


def test_permanent_4xx_and_callback_reason_not_retried(
    send_context: Any, db: Session, client: Any
) -> None:
    _connection, _conversation, message, job, settings, fake = send_context
    fake.responses.append(400)
    run(db, job, settings)
    assert message.delivery_status == "failed" and message.error_code == "window_closed"
    assert fake.post_status(client, str(message.id), "failed", "window_closed").status_code == 202
    callbacks(db, settings)
    run(db, job, settings)
    assert len(fake.requests) == 1


def test_retry_exhaustion(send_context: Any, db: Session) -> None:
    connection, _conversation, message, job, settings, fake = send_context
    fake.responses.extend([500] * 6)
    for _ in range(6):
        run(db, job, settings)
    assert job.status == "failed" and job.attempts == 6 and len(fake.requests) == 6
    assert message.delivery_status == "failed" and message.error_code == "many_unreachable"
    assert connection.health_status == "degraded" and connection.health_reason == "many_unreachable"


@pytest.mark.parametrize("status", ["paused", "revoked"])
def test_paused_at_job_time(send_context: Any, db: Session, status: str) -> None:
    connection, _conversation, message, job, settings, fake = send_context
    connection.status = status
    db.commit()
    run(db, job, settings)
    assert not fake.requests
    assert message.delivery_status == "failed" and message.error_code == "connection_paused"


def test_resume_does_not_resend_messages_failed_with_connection_paused(
    send_context: Any, db: Session
) -> None:
    """Auto-resume never re-sends: `connection_paused` failures stay terminal."""
    connection, _conversation, message, job, settings, fake = send_context
    connection.status = "paused"
    db.commit()
    run(db, job, settings)
    assert message.delivery_status == "failed" and message.error_code == "connection_paused"
    assert job.status == "succeeded" and not fake.requests
    connection.status = "active"
    db.commit()
    run(db, job, settings)
    # Nothing is re-enqueued and the stored failure is not retried into a send.
    assert not fake.requests
    assert message.delivery_status == "failed" and message.error_code == "connection_paused"
    assert (
        db.scalar(
            select(func.count())
            .select_from(Job)
            .where(Job.type == "channel_send", Job.status == "pending")
        )
        == 0
    )


@pytest.mark.parametrize(
    "target",
    [
        "http://127.0.0.1",
        "ftp://many.example.test",
        "http://localhost",
        "https://many.example.test",
    ],
)
def test_send_time_target_rejection(
    send_context: Any, db: Session, monkeypatch: pytest.MonkeyPatch, target: str
) -> None:
    connection, _conversation, message, job, settings, fake = send_context
    connection.many_base_url = target
    db.commit()
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_a, **_k: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.2", 443)),
        ],
    )
    run(db, job, settings)
    assert not fake.requests and message.error_code == "invalid_many_target"


def test_long_reply_order_and_enqueue_idempotency(send_context: Any, db: Session) -> None:
    _connection, conversation, first, first_job, settings, fake = send_context
    # Complete the fixture message, then deliver a three-part reply out of scheduling order.
    run(db, first_job, settings)
    full = ("مرحبا بالعالم. " * 175) + "Goodbye."
    message = append_message(db, conversation, sender_type="ai", text=full, needs_human=True)
    enqueue_message(db, conversation, message, settings)
    enqueue_message(db, conversation, message, settings)
    db.commit()
    messages = list(
        db.scalars(
            select(Message)
            .where(Message.sender_type == "ai", Message.id != first.id)
            .order_by(Message.created_at, Message.id)
        )
    )
    assert len(messages) >= 3 and "".join(m.text for m in messages) == full
    assert all(len(m.text) <= 1000 for m in messages)
    jobs: list[Job] = []
    for part in messages:
        part_job = db.scalar(select(Job).where(Job.payload["message_id"].astext == str(part.id)))
        assert part_job is not None
        jobs.append(part_job)
    run(db, jobs[-1], settings)
    assert jobs[-1].attempts == 0 and len(fake.requests) == 1
    for job in jobs:
        run(db, job, settings)
    assert [r["text"] for r in fake.requests[1:]] == [m.text for m in messages]
    assert all(r["kind"] == "handoff" for r in fake.requests[1:])


@pytest.mark.parametrize("code", ["window_closed", "template_required", "recipient_unreachable"])
def test_status_callbacks_and_out_of_order(
    send_context: Any, db: Session, client: Any, code: str
) -> None:
    _connection, _conversation, message, job, settings, fake = send_context
    run(db, job, settings)
    assert fake.post_status(client, str(message.id), "failed", code).status_code == 202
    callbacks(db, settings)
    db.refresh(message)
    assert message.error_code == code and message.delivery_status == "failed"
    run(db, job, settings)
    assert len(fake.requests) == 1
    # A separate message demonstrates positive monotonicity and failure below delivered only.
    message.delivery_status = "pending"
    message.error_code = None
    db.commit()
    for status in ["delivered", "sent", "failed", "read", "sent"]:
        assert fake.post_status(client, str(message.id), status, code).status_code == 202
        callbacks(db, settings)
    db.refresh(message)
    assert message.delivery_status == "read" and message.error_code is None


def test_agent_reply_pause_atomic_enqueue_notes_and_tenant_isolation(
    send_context: Any,
    app: Any,
    db: Session,
) -> None:
    connection, conversation, _message, _job, _settings, _fake = send_context
    from fastapi.testclient import TestClient

    from tests.helpers import PASSWORD, csrf_headers

    user_client = TestClient(app)
    # Existing fixture's editor is an authorized tenant member.
    from app.db.models import Membership, User

    user = db.scalar(
        select(User)
        .join(Membership, Membership.user_id == User.id)
        .where(Membership.tenant_id == connection.tenant_id, Membership.role == "editor")
    )
    assert user is not None
    assert (
        user_client.post(
            "/api/v1/auth/login", json={"email": user.email, "password": PASSWORD}
        ).status_code
        == 200
    )
    path = f"/api/v1/tenants/{connection.tenant_id}/conversations/{conversation.id}"
    headers = csrf_headers(user_client)
    before = db.scalar(select(func.count(Message.id)))
    for status in ["paused", "revoked"]:
        connection.status = status
        db.commit()
        response = user_client.post(
            path + "/messages", json={"text": "Agent reply"}, headers=headers
        )
        assert (
            response.status_code == 409 and response.json()["error"]["code"] == "CONNECTION_PAUSED"
        )
        assert db.scalar(select(func.count(Message.id))) == before
        detail = user_client.get(path).json()
        assert detail["conversation"]["connection_status"] == status
    connection.status = "active"
    db.commit()
    response = user_client.post(path + "/messages", json={"text": "Agent reply"}, headers=headers)
    assert response.status_code == 201
    mid = response.json()["message"]["id"]
    assert db.scalar(select(Job).where(Job.payload["message_id"].astext == mid)) is not None
    count = db.scalar(select(func.count(Job.id)).where(Job.type == "channel_send"))
    assert (
        user_client.post(
            path + "/notes", json={"text": "Secret internal note"}, headers=headers
        ).status_code
        == 201
    )
    assert db.scalar(select(func.count(Job.id)).where(Job.type == "channel_send")) == count
    other = seeded_tenant(app, db, prefix="outbound-other")
    foreign = f"/api/v1/tenants/{other.tenant_id}/conversations/{conversation.id}"
    assert (
        other.call("editor", "POST", foreign + "/messages", json={"text": "Foreign"}).status_code
        == 404
    )
    assert other.as_user("viewer").get(foreign).status_code == 404
    assert user_client.get(path).json()["messages"][-2]["delivery_status"] == "pending"
    user_client.close()


def test_website_agent_reply_keeps_response_and_has_no_outbox(
    send_context: Any, db: Session, app: Any
) -> None:
    _connection, _conversation, _message, _job, _settings, _fake = send_context
    users = seeded_tenant(app, db, prefix="website-regression")
    from tests.helpers import make_bot

    bot = make_bot(users)
    conversation = Conversation(
        tenant_id=users.tenant_id,
        bot_id=UUID(bot["id"]),
        source="website",
        channel="website",
        mode="human",
        status="open",
    )
    db.add(conversation)
    db.commit()
    count = db.scalar(select(func.count(Job.id)))
    path = f"/api/v1/tenants/{users.tenant_id}/conversations/{conversation.id}"
    response = users.call("editor", "POST", path + "/messages", json={"text": " Website reply "})
    assert response.status_code == 201
    assert set(response.json()["message"]) == {
        "id",
        "sender_type",
        "sender_user_id",
        "text",
        "citations",
        "created_at",
    }
    assert response.json()["message"]["text"] == "Website reply"
    stored = db.get(Message, UUID(response.json()["message"]["id"]))
    assert stored is not None and stored.delivery_status is None
    assert db.scalar(select(func.count(Job.id))) == count
    detail = users.as_user("viewer").get(path).json()
    assert "connection_status" not in detail["conversation"]
    assert "delivery_status" not in detail["messages"][0]


def test_channel_pipeline_enqueues_final_replies(
    client: Any,
    app: Any,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_success_pipeline(monkeypatch)
    connection_id, secret = _connection(app, db)
    payload = _payload(connection_id)
    assert _post(client, connection_id, secret, json.dumps(payload).encode()).status_code == 202
    _run_event(db, payload["event_id"], settings=build_test_settings(chat_stub_model=True))
    messages = list(db.scalars(select(Message).where(Message.sender_type == "ai")))
    assert len(messages) == 1
    job = db.scalar(select(Job).where(Job.type == "channel_send"))
    assert job is not None and job.payload == {"message_id": str(messages[0].id)}


@pytest.mark.parametrize(
    "status,raw,expected",
    [
        (302, b"", "many_invalid_response"),
        (401, b"oops", "many_http_401"),
        (202, b"{}", None),
        (202, b"x" * 70000, None),
    ],
    ids=["redirect", "permanent_4xx", "invalid_ack", "oversized_response"],
)
def test_redirect_response_cap_and_invalid_ack(
    send_context: Any,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
    status: int,
    raw: bytes,
    expected: str | None,
) -> None:
    _connection, _conversation, message, job, settings, fake = send_context
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            status, stream=httpx.ByteStream(raw), headers={"Location": "http://127.0.0.1/"}
        )

    monkeypatch.setattr(
        outbound,
        "_client",
        lambda: httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False),
    )
    run(db, job, settings)
    assert len(requests) == 1
    assert message.error_code == expected
    assert job.status == ("succeeded" if expected else "pending")


def test_send_migration_round_trip_and_unique_message_key(db: Session, engine: Engine) -> None:
    url = engine.url.render_as_string(hide_password=False)
    db.close()
    run_migrations(url, upgrade_to="", downgrade_to="0024_channel_inbound")
    run_migrations(url)
    with engine.connect() as conn:
        version = conn.scalar(text("SELECT version_num FROM alembic_version"))
        assert version == "0029_channel_event_payload_purge"
        assert (
            conn.scalar(
                text("SELECT count(*) FROM pg_indexes WHERE indexname = 'uq_channel_send_message'")
            )
            == 1
        )


def test_job_unique_key_and_foreign_job_cannot_send(
    send_context: Any, db: Session, app: Any
) -> None:
    _connection, _conversation, message, job, settings, fake = send_context
    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(
            Job(
                tenant_id=job.tenant_id,
                bot_id=job.bot_id,
                type="channel_send",
                payload={"message_id": str(message.id)},
            )
        )
        db.flush()
    other = seeded_tenant(app, db, prefix="foreign-job")
    from tests.helpers import make_bot

    bot = make_bot(other)
    foreign = Job(
        tenant_id=other.tenant_id,
        bot_id=UUID(bot["id"]),
        type="channel_send",
        payload={"message_id": str(message.id)},
        attempts=0,
    )
    db.add(foreign)
    db.commit()
    run(db, foreign, settings)
    assert not fake.requests and message.delivery_status == "pending"


def test_job_queued_before_rotation_signs_with_new_secret(
    send_context: Any, db: Session, app: Any
) -> None:
    connection, _conversation, message, job, settings, fake = send_context
    connection.prev_secret_ciphertext = connection.secret_ciphertext
    connection.prev_secret_expires_at = datetime.now(UTC) + timedelta(hours=24)
    connection.secret_ciphertext = encrypt_secret("rotated-before-send", app.state.channel_test_key)
    db.commit()
    fake.secret = "rotated-before-send"
    run(db, job, settings)
    assert job.status == "succeeded" and message.channel_message_id == "many-1"
    assert len(fake.requests) == 1
