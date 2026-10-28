"""P6-05 health pull, poll job, scheduling, staleness and transition audit."""

import json
import socket
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

import app.channels.health as health
from app.channels.health import run_channel_health_poll, schedule_health_polls
from app.channels.outbound import SendRetry
from app.channels.secrets import encrypt_secret
from app.db.models import AuditEvent, ChannelConnection, Job
from tests.conftest import build_test_settings
from tests.fakes.fake_many import FakeMany
from tests.helpers import make_bot, seeded_tenant
from tests.test_channels import _configure_channel_key, _create_payload, _platform_call


def _staff_connection(
    app: Any, db: Session, *, status: str = "active"
) -> tuple[Any, ChannelConnection, str]:
    """A seeded tenant plus one connection created through the platform API."""
    key = _configure_channel_key(app, Fernet.generate_key().decode("ascii"))
    app.state.channel_test_key = key
    users = seeded_tenant(
        app, db, prefix=f"channel-health-{uuid4().hex[:8]}", plan_label="business"
    )
    bot = make_bot(users)
    staff = users.as_user("staff")
    payload = _create_payload(users.tenant_id, bot["id"])
    created = _platform_call(staff, "POST", "/channel-connections", json=payload)
    assert created.status_code == 201, created.text
    body = created.json()
    connection = db.get(ChannelConnection, UUID(body["id"]))
    assert connection is not None
    if status != "active":
        connection.status = status
        db.commit()
        db.refresh(connection)
    return users, connection, body["secret"]


def _direct_connection(db: Session, app: Any, *, status: str = "active") -> ChannelConnection:
    key = _configure_channel_key(app, Fernet.generate_key().decode("ascii"))
    app.state.channel_test_key = key
    users = seeded_tenant(
        app, db, prefix=f"channel-direct-{uuid4().hex[:8]}", plan_label="business"
    )
    bot = make_bot(users)
    connection = ChannelConnection(
        tenant_id=users.tenant_id,
        bot_id=UUID(bot["id"]),
        channel="whatsapp",
        display_name="Direct",
        many_base_url="https://many.example.test",
        status=status,
        ai_enabled=True,
        secret_ciphertext=encrypt_secret("direct-poll-secret", key),
        secret_key_version=1,
        health_status="unknown",
    )
    db.add(connection)
    db.commit()
    db.refresh(connection)
    return connection


def _wire_fake(monkeypatch: pytest.MonkeyPatch, fake: FakeMany) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_a, **_k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))],
    )
    monkeypatch.setattr(health, "_client", fake.client)


def _check_now(client: Any, connection_id: UUID) -> Any:
    return _platform_call(client, "POST", f"/channel-connections/{connection_id}/check-health")


def _health_audit_rows(db: Session) -> list[AuditEvent]:
    return list(
        db.scalars(
            select(AuditEvent).where(AuditEvent.action == "channel_connection.health_changed")
        )
    )


def _settings(app: Any, key: str | None = None) -> Any:
    return build_test_settings(
        channel_secret_encryption_keys=SecretStr(key or app.state.channel_test_key),
        chat_stub_model=True,
        environment="test",
    )


def _poll_job(
    db: Session,
    connection: ChannelConnection,
    *,
    attempts: int = 0,
    max_attempts: int = 3,
    tenant_id: UUID | None = None,
    bot_id: UUID | None = None,
) -> Job:
    job = Job(
        tenant_id=tenant_id or connection.tenant_id,
        bot_id=bot_id or connection.bot_id,
        type="channel_health_poll",
        payload={"connection_id": str(connection.id)},
        status="running",
        attempts=attempts,
        max_attempts=max_attempts,
    )
    db.add(job)
    db.flush()
    return job


def test_check_now_signed_pull_applies_health_and_audits(
    app: Any, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    users, connection, secret = _staff_connection(app, db)
    fake = FakeMany(str(connection.id), secret)
    fake.health_responses.append("token_expiring")
    _wire_fake(monkeypatch, fake)
    response = _check_now(users.as_user("staff"), connection.id)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["health_status"] == "degraded"
    assert body["health_reason"] == "token_expiring"
    assert secret not in response.text
    assert "secret_ciphertext" not in response.text
    assert "prev_secret_ciphertext" not in response.text
    assert len(fake.health_requests) == 1
    rows = _health_audit_rows(db)
    assert len(rows) == 1
    assert rows[0].metadata_json.get("source") == "pull"
    assert rows[0].metadata_json.get("from") == "unknown"
    assert rows[0].actor_user_id is not None
    db.refresh(connection)
    assert connection.health_status == "degraded"
    assert connection.health_reason == "token_expiring"


def test_check_now_failures_then_revoked_is_rejected(
    app: Any, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    users, connection, secret = _staff_connection(app, db)
    fake = FakeMany(str(connection.id), secret)
    fake.health_responses.append(httpx.ConnectError("refused"))
    _wire_fake(monkeypatch, fake)
    staff = users.as_user("staff")
    response = _check_now(staff, connection.id)
    assert response.status_code == 200
    assert response.json()["health_status"] == "degraded"
    assert response.json()["health_reason"] == "many_unreachable"
    assert len(fake.health_requests) == 1

    fake.health_responses.append(503)
    response = _check_now(staff, connection.id)
    assert response.status_code == 200
    assert response.json()["health_reason"] == "many_invalid_response"

    connection.status = "revoked"
    db.commit()
    revoked = _check_now(staff, connection.id)
    assert revoked.status_code == 409
    assert revoked.json()["error"]["code"] == "CONNECTION_REVOKED"
    # The two failed pulls each audited a transition from the previous state.
    rows = _health_audit_rows(db)
    assert len(rows) == 2


def test_check_now_allows_paused_connection(
    app: Any, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    users, connection, secret = _staff_connection(app, db, status="paused")
    fake = FakeMany(str(connection.id), secret)
    fake.health_responses.append("connected")
    _wire_fake(monkeypatch, fake)
    response = _check_now(users.as_user("staff"), connection.id)
    assert response.status_code == 200
    assert response.json()["health_status"] == "healthy"
    assert response.json()["health_reason"] == "connected"


def test_poll_job_applies_health_ignores_older_and_audits(
    app: Any, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    connection = _direct_connection(db, app)
    key = app.state.channel_test_key
    settings = _settings(app, key)
    fake = FakeMany(str(connection.id), "direct-poll-secret")
    fake.health_responses.append("token_expiring")
    _wire_fake(monkeypatch, fake)
    job = _poll_job(db, connection)
    assert run_channel_health_poll(db, job, settings) is None
    db.commit()
    db.refresh(connection)
    assert connection.health_status == "degraded"
    assert connection.health_reason == "token_expiring"
    rows = _health_audit_rows(db)
    assert len(rows) == 1
    assert rows[0].metadata_json.get("source") == "poll"
    assert rows[0].actor_user_id is None
    assert len(fake.health_requests) == 1

    # An older signal than the stored health is ignored, no new audit row.
    connection.health_updated_at = datetime.now(UTC) + timedelta(minutes=10)
    job.status = "succeeded"
    db.commit()
    fake.health_responses.append("connected")
    job2 = _poll_job(db, connection)
    assert run_channel_health_poll(db, job2, settings) is None
    db.commit()
    db.refresh(connection)
    assert connection.health_reason == "token_expiring"
    assert len(_health_audit_rows(db)) == 1


def test_poll_job_skips_non_active_and_foreign_connections(
    app: Any, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    connection = _direct_connection(db, app, status="paused")
    settings = _settings(app, app.state.channel_test_key)
    fake = FakeMany(str(connection.id), "direct-poll-secret")
    _wire_fake(monkeypatch, fake)
    job = _poll_job(db, connection)
    assert run_channel_health_poll(db, job, settings) is None
    db.commit()
    assert fake.health_requests == []
    assert connection.health_status == "unknown"
    assert _health_audit_rows(db) == []

    # A job whose tenant/bot differ can never load the connection.
    other = seeded_tenant(
        app, db, prefix=f"channel-foreign-{uuid4().hex[:8]}", plan_label="business"
    )
    other_bot = make_bot(other)
    foreign_job = _poll_job(db, connection, tenant_id=other.tenant_id, bot_id=UUID(other_bot["id"]))
    assert run_channel_health_poll(db, foreign_job, settings) is None
    db.commit()
    assert fake.health_requests == []
    assert connection.health_status == "unknown"


def test_poll_job_retries_transient_then_degrades_on_exhaustion(
    app: Any, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    connection = _direct_connection(db, app)
    settings = _settings(app, app.state.channel_test_key)
    fake = FakeMany(str(connection.id), "direct-poll-secret")
    fake.health_responses.extend([httpx.ConnectError("refused")] * 4)
    _wire_fake(monkeypatch, fake)
    job = _poll_job(db, connection, attempts=0, max_attempts=3)
    with pytest.raises(SendRetry):
        run_channel_health_poll(db, job, settings)
    db.commit()

    job.status = "succeeded"
    exhausted = _poll_job(db, connection, attempts=3, max_attempts=3)
    assert run_channel_health_poll(db, exhausted, settings) is None
    db.commit()
    db.refresh(connection)
    assert connection.health_status == "degraded"
    assert connection.health_reason == "many_unreachable"
    rows = _health_audit_rows(db)
    assert len(rows) == 1
    assert rows[0].metadata_json.get("source") == "poll"


def test_schedule_health_polls_jitter_batch_and_single_live_job(app: Any, db: Session) -> None:
    connection_a = _direct_connection(db, app)
    connection_b = _direct_connection(db, app)
    _direct_connection(db, app, status="paused")
    settings = build_test_settings(
        channel_secret_encryption_keys=SecretStr(app.state.channel_test_key),
        chat_stub_model=True,
        environment="test",
        channel_health_poll_batch=2,
        channel_health_poll_jitter_seconds=60,
    )
    before = datetime.now(UTC)
    scheduled = schedule_health_polls(db, settings)
    db.commit()
    jobs = list(db.scalars(select(Job).where(Job.type == "channel_health_poll")))
    assert scheduled == 2
    assert {job.tenant_id for job in jobs} >= {connection_a.tenant_id, connection_b.tenant_id}
    for job in jobs:
        delta = job.run_at - before
        assert timedelta(0) <= delta <= timedelta(seconds=61)
        assert job.status == "pending"

    # Only one live job per connection: the second cycle schedules nothing.
    assert schedule_health_polls(db, settings) == 0
    db.commit()
    assert len(list(db.scalars(select(Job).where(Job.type == "channel_health_poll")))) == 2

    # Once the jobs finish, the next cycle schedules them again (paused skipped).
    for job in db.scalars(select(Job).where(Job.type == "channel_health_poll")):
        job.status = "succeeded"
    db.commit()
    assert schedule_health_polls(db, settings) == 2
    db.commit()


def test_schedule_health_polls_orders_never_polled_then_least_recent(app: Any, db: Session) -> None:
    never = _direct_connection(db, app)
    old = _direct_connection(db, app)
    recent = _direct_connection(db, app)
    settings = build_test_settings(
        channel_secret_encryption_keys=SecretStr(app.state.channel_test_key),
        chat_stub_model=True,
        environment="test",
        channel_health_poll_batch=1,
        channel_health_poll_jitter_seconds=1,
    )
    now = datetime.now(UTC)
    for connection, age in ((old, timedelta(hours=5)), (recent, timedelta(hours=1))):
        job = Job(
            tenant_id=connection.tenant_id,
            bot_id=connection.bot_id,
            type="channel_health_poll",
            payload={"connection_id": str(connection.id)},
            status="succeeded",
            created_at=now - age,
        )
        db.add(job)
    db.commit()
    order: list[str] = []
    for _cycle in range(3):
        assert schedule_health_polls(db, settings, now=now) == 1
        db.commit()
        live = db.scalar(
            select(Job).where(Job.type == "channel_health_poll", Job.status == "pending")
        )
        assert live is not None
        order.append(live.payload["connection_id"])
        live.status = "succeeded"
        db.commit()
    assert order == [str(never.id), str(old.id), str(recent.id)]


def test_poll_migration_round_trip_and_unique_live_job(db: Any, engine: Any) -> None:
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from sqlalchemy import text

    from tests.conftest import API_DIR, run_migrations

    url = engine.url.render_as_string(hide_password=False)
    db.close()
    run_migrations(url, upgrade_to="", downgrade_to="0025_channel_send")
    run_migrations(url)
    with engine.connect() as conn:
        version = conn.scalar(text("SELECT version_num FROM alembic_version"))
        heads = ScriptDirectory.from_config(Config(API_DIR / "alembic.ini")).get_heads()
        assert len(heads) == 1
        assert version == heads[0]
        assert (
            conn.scalar(
                text(
                    "SELECT count(*) FROM pg_indexes "
                    "WHERE indexname = 'ix_jobs_channel_health_poll_last'"
                )
            )
            == 1
        )
        assert (
            conn.scalar(
                text(
                    "SELECT count(*) FROM pg_constraint "
                    "WHERE conname = 'ck_jobs_type' AND pg_get_constraintdef(oid) "
                    "LIKE '%channel_health_poll%'"
                )
            )
            == 1
        )
        assert (
            conn.scalar(
                text(
                    "SELECT count(*) FROM pg_indexes "
                    "WHERE indexname = 'uq_channel_health_poll_connection'"
                )
            )
            == 1
        )


def test_staleness_shows_unknown_stale_in_both_read_models(
    app: Any, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    users, connection, secret = _staff_connection(app, db)
    connection.health_status = "healthy"
    connection.health_reason = "connected"
    connection.health_updated_at = datetime.now(UTC) - timedelta(minutes=30)
    db.commit()

    staff_detail = _platform_call(
        users.as_user("staff"), "GET", f"/channel-connections/{connection.id}"
    )
    staff_list = _platform_call(users.as_user("staff"), "GET", "/channel-connections")
    assert staff_detail.status_code == staff_list.status_code == 200
    assert staff_detail.json()["health_status"] == "unknown"
    assert staff_detail.json()["health_reason"] == "stale"
    assert staff_list.json()["items"][0]["health_status"] == "unknown"
    assert staff_list.json()["items"][0]["health_reason"] == "stale"
    client_list = users.call("viewer", "GET", f"/api/v1/tenants/{users.tenant_id}/channels")
    assert client_list.status_code == 200
    item = client_list.json()["items"][0]
    assert set(item) == {
        "channel",
        "display_name",
        "status",
        "health_status",
        "last_event_at",
    }
    assert item["health_status"] == "unknown"

    # A fresh signal keeps the stored state.
    connection.health_updated_at = datetime.now(UTC) - timedelta(minutes=5)
    db.commit()
    fresh = _platform_call(users.as_user("staff"), "GET", f"/channel-connections/{connection.id}")
    assert fresh.json()["health_status"] == "healthy"
    assert fresh.json()["health_reason"] == "connected"
    client_fresh = users.call("viewer", "GET", f"/api/v1/tenants/{users.tenant_id}/channels")
    assert client_fresh.json()["items"][0]["health_status"] == "healthy"


def test_schedule_skips_while_another_worker_holds_the_scheduler_lock(
    app: Any, db: Session, engine: Any
) -> None:
    """Multi-worker safety: a second scheduler skips instead of racing."""
    connection = _direct_connection(db, app)
    settings = build_test_settings(
        channel_secret_encryption_keys=SecretStr(app.state.channel_test_key),
        chat_stub_model=True,
        environment="test",
    )
    other = Session(bind=engine)
    try:
        assert schedule_health_polls(other, settings) >= 1  # holds the xact lock
        assert schedule_health_polls(db, settings) == 0  # skipped, not an error
        other.commit()
        # The lock is gone after commit and the live job already exists.
        assert schedule_health_polls(db, settings) == 0
        db.commit()
    finally:
        other.close()
    live = list(
        db.scalars(
            select(Job).where(
                Job.type == "channel_health_poll",
                Job.status == "pending",
                Job.tenant_id == connection.tenant_id,
            )
        )
    )
    assert len(live) == 1


def test_future_checked_at_counts_as_now_so_freshness_is_not_frozen() -> None:
    now = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)
    future = (now + timedelta(hours=2)).isoformat().replace("+00:00", "Z")
    body = json.dumps({"status": "connected", "checked_at": future}).encode()
    status, _detail, occurred = health.parse_health_body(body, now=now)
    assert status == "connected"
    assert occurred == now


def test_a9_successful_poll_clears_stale(
    app: Any, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    connection = _direct_connection(db, app)
    connection.health_status = "healthy"
    connection.health_reason = "connected"
    connection.health_updated_at = datetime.now(UTC) - timedelta(minutes=40)
    db.commit()
    assert health.effective_health(connection) == ("unknown", "stale")

    fake = FakeMany(str(connection.id), "direct-poll-secret")
    fake.health_responses.append("connected")
    _wire_fake(monkeypatch, fake)
    job = _poll_job(db, connection)
    assert run_channel_health_poll(db, job, _settings(app, app.state.channel_test_key)) is None
    db.commit()
    db.refresh(connection)
    assert health.effective_health(connection) == ("healthy", "connected")
