"""Connection health: signed pull to Many, staleness and the poll job.

PLAN D10 / docs/17 §4.3 and §5.2: the SaaS learns health from pushed
``channel.status`` events, from a signed staff "Check now" pull and from a
periodic ``channel_health_poll`` job (active connections only, jittered,
concurrency capped). With no signal (event or poll) for 15 minutes the
effective health is ``unknown`` with reason ``stale``. Every transition
writes an audit row. No response content or secret is ever logged.
"""

import json
import random
import time
import unicodedata
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID

import httpx
from sqlalchemy import Text, cast, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import aliased

from app.channels.signing import sign
from app.core.audit import record_audit
from app.core.config import Settings

if TYPE_CHECKING:
    from app.db.models import ChannelConnection, Job, User

HEALTH_STATUS_MAP: dict[str, str] = {
    "connected": "healthy",
    "token_expiring": "degraded",
    "webhook_unhealthy": "degraded",
    "token_expired": "unhealthy",
    "disconnected": "unhealthy",
}
STALE_AFTER_MINUTES = 15
STALE_AFTER = timedelta(minutes=STALE_AFTER_MINUTES)
HEALTH_RESPONSE_BYTES = 64 * 1024
HEALTH_TIMEOUT = httpx.Timeout(15.0, connect=5.0)
HEALTH_PATH = "/api/saas/connections/{connection_id}/health"
# Held (transaction scoped) while one worker schedules polls, so several
# workers never race on the same connections. Arbitrary fixed 63-bit key.
SCHEDULER_LOCK_KEY = 0x5E7C0A11_1EA17001


class HealthPullFailure(Exception):
    """A sanitized pull outcome; never carries request or response content."""

    def __init__(self, code: str) -> None:
        super().__init__("Many could not be reached for a health check.")
        self.code = code


def clean_text(value: object, limit: int) -> str | None:
    """Collapse whitespace and strip control characters within ``limit``."""
    if not isinstance(value, str):
        return None
    cleaned = "".join(char for char in value if not unicodedata.category(char).startswith("C"))
    cleaned = " ".join(cleaned.split()).strip()[:limit]
    return cleaned or None


def newest_signal_at(connection: "ChannelConnection") -> datetime | None:
    """The freshest health signal: the newest of last event and last update."""
    if connection.last_event_at is not None and (
        connection.health_updated_at is None
        or connection.last_event_at > connection.health_updated_at
    ):
        return connection.last_event_at
    return connection.health_updated_at


def effective_health(
    connection: "ChannelConnection", *, now: datetime | None = None
) -> tuple[str, str | None]:
    """The health a UI must show: the stored state, or ``unknown/stale``.

    When the newest signal is older than 15 minutes — the poll job failing,
    Many going silent, or this worker being down — the stored state is no
    longer trustworthy and is shown as ``unknown`` with reason ``stale``.
    """
    stored_status = connection.health_status or "unknown"
    stored_reason = connection.health_reason
    newest = newest_signal_at(connection)
    if newest is not None and ((now or datetime.now(UTC)) - newest) > STALE_AFTER:
        return "unknown", "stale"
    return stored_status, stored_reason


def _record_transition(
    db: OrmSession,
    connection: "ChannelConnection",
    *,
    previous: tuple[str, str | None],
    source: str,
    actor: "User | None" = None,
) -> None:
    """One audit row per health transition (D10); ids only, never content."""
    current = (connection.health_status or "unknown", connection.health_reason)
    if previous == current:
        return
    record_audit(
        db,
        action="channel_connection.health_changed",
        tenant_id=connection.tenant_id,
        actor_user_id=actor.id if actor is not None else None,
        target_type="channel_connection",
        target_id=str(connection.id),
        metadata={"channel": connection.channel, "source": source, "from": previous[0]},
    )


def apply_health(
    db: OrmSession,
    connection: "ChannelConnection",
    *,
    status: str,
    detail: str | None,
    occurred_at: datetime,
    source: str,
    actor: "User | None" = None,
) -> bool:
    """Store one health signal if it is newer than the stored one.

    Older signals are ignored (identical to the pushed-event rule). Every
    transition writes an audit row (D10). Returns True when it changed.
    """
    previous = (connection.health_status or "unknown", connection.health_reason)
    if connection.health_updated_at is not None and occurred_at < connection.health_updated_at:
        return False
    connection.health_status = HEALTH_STATUS_MAP[status]
    connection.health_reason = status
    connection.health_detail = detail
    connection.health_updated_at = occurred_at
    connection.updated_at = datetime.now(UTC)
    _record_transition(db, connection, previous=previous, source=source, actor=actor)
    return True


def degrade_health(
    db: OrmSession,
    connection: "ChannelConnection",
    *,
    reason: str,
    source: str = "pull",
    actor: "User | None" = None,
) -> None:
    """Record a health-pull failure as degraded health (own audit row)."""
    now = datetime.now(UTC)
    previous = (connection.health_status or "unknown", connection.health_reason)
    connection.health_status = "degraded"
    connection.health_reason = reason
    connection.health_detail = None
    connection.health_updated_at = now
    connection.updated_at = now
    _record_transition(db, connection, previous=previous, source=source, actor=actor)


def parse_health_body(
    raw: bytes, *, now: datetime | None = None
) -> tuple[str, str | None, datetime]:
    """Validate a §5.2 health response: status, optional detail, checked_at."""
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HealthPullFailure("many_invalid_response") from exc
    if not isinstance(data, dict):
        raise HealthPullFailure("many_invalid_response")
    status = data.get("status")
    if not isinstance(status, str) or status not in HEALTH_STATUS_MAP:
        raise HealthPullFailure("many_invalid_response")
    detail = clean_text(data.get("detail"), 200)
    checked_at = data.get("checked_at")
    if isinstance(checked_at, str):
        try:
            occurred = datetime.fromisoformat(checked_at.replace("Z", "+00:00")).astimezone(UTC)
        except ValueError as exc:
            raise HealthPullFailure("many_invalid_response") from exc
    else:
        occurred = now or datetime.now(UTC)
    # A9: the pull is the freshness source. A Many clock ahead of ours must
    # not store a future time (it would freeze freshness and make every later
    # signal look older), so a future ``checked_at`` counts as "now".
    return status, detail, min(occurred, now or datetime.now(UTC))


def _client() -> httpx.Client:
    return httpx.Client(
        follow_redirects=False,
        trust_env=False,
        timeout=HEALTH_TIMEOUT,
    )


def signed_health_headers(connection: "ChannelConnection", settings: Settings) -> dict[str, str]:
    """§5.2 headers: the signature covers ``timestamp + "."`` (empty body)."""
    try:
        from app.channels.secrets import decrypt_secret

        secret = decrypt_secret(
            connection.secret_ciphertext, settings.channel_secret_encryption_keys
        )
    except ValueError as exc:
        raise HealthPullFailure("secret_unavailable") from exc
    timestamp = int(time.time())
    return {
        "X-Osiris-Connection": str(connection.id),
        "X-Osiris-Timestamp": str(timestamp),
        "X-Osiris-Signature": sign(secret, timestamp, b""),
    }


def pull_health(
    connection: "ChannelConnection", settings: Settings
) -> tuple[str, str | None, datetime]:
    """One signed GET to the stored ``many_base_url`` only; no redirects.

    The outbound target resolver is shared; a lazy import keeps the
    router → health → outbound reference cycle from forming.
    """
    from app.channels.outbound import UnsafeTarget, resolve_target

    try:
        url, hostname = resolve_target(
            connection.many_base_url,
            settings,
            path=HEALTH_PATH.format(connection_id=connection.id),
        )
        headers = signed_health_headers(connection, settings)
        # Preserve the original authority (including a non-default port) for Host.
        authority = f"[{hostname}]" if ":" in hostname else hostname
        if url.port is not None:
            authority += f":{url.port}"
        with _client() as client:
            response = client.get(
                url,
                headers={**headers, "Host": authority},
                extensions={"sni_hostname": hostname},
            )
        if response.status_code != 200 or len(response.content) > HEALTH_RESPONSE_BYTES:
            raise HealthPullFailure("many_invalid_response")
        return parse_health_body(response.content)
    except UnsafeTarget:
        raise HealthPullFailure("invalid_many_target") from None
    except (httpx.HTTPError, OSError):
        raise HealthPullFailure("many_unreachable") from None


def check_health(
    db: OrmSession,
    connection: "ChannelConnection",
    settings: Settings,
    *,
    actor: "User | None" = None,
    source: str = "pull",
) -> None:
    """Apply one health pull to the connection (a single attempt, no retry)."""
    try:
        status, detail, occurred_at = pull_health(connection, settings)
    except HealthPullFailure as failure:
        degrade_health(db, connection, reason=failure.code, actor=actor)
    else:
        apply_health(
            db,
            connection,
            status=status,
            detail=detail,
            occurred_at=occurred_at,
            source=source,
            actor=actor,
        )


def run_channel_health_poll(db: OrmSession, job: "Job", settings: Settings) -> str | None:
    """Poll one connection.

    Active connections only: paused and revoked ones are skipped (the job
    succeeds without touching them). The connection is loaded with tenant and
    bot taken from the job, so a foreign job can never poll another tenant's
    connection. A transient failure (network/secret) raises ``SendRetry`` so
    the queue retries it with backoff; after the retry budget it degrades.
    """
    from app.channels.outbound import SendRetry
    from app.db.models import ChannelConnection

    try:
        connection_id = UUID(str(job.payload.get("connection_id")))
    except (ValueError, TypeError):
        return "Invalid channel connection reference."
    connection = db.scalar(
        select(ChannelConnection)
        .where(
            ChannelConnection.tenant_id == job.tenant_id,
            ChannelConnection.bot_id == job.bot_id,
            ChannelConnection.id == connection_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if connection is None or connection.status != "active":
        return None
    try:
        status, detail, occurred_at = pull_health(connection, settings)
    except HealthPullFailure as failure:
        if failure.code in {"many_unreachable", "secret_unavailable"} and (
            job.attempts < job.max_attempts
        ):
            raise SendRetry(30.0) from None
        degrade_health(db, connection, reason=failure.code, source="poll")
        return None
    apply_health(
        db, connection, status=status, detail=detail, occurred_at=occurred_at, source="poll"
    )
    return None


def schedule_health_polls(
    db: OrmSession, settings: Settings, *, now: datetime | None = None
) -> int:
    """Enqueue one poll job per active connection without a live poll job.

    Called by the worker every ``channel_health_poll_interval_seconds``.
    Concurrency cap: at most ``channel_health_poll_batch`` connections get a
    job per cycle, the run time is jittered inside
    ``channel_health_poll_jitter_seconds``, and migration 0020's partial
    unique index keeps only one live job per connection. Returns the count.
    """
    from app.db.models import ChannelConnection, Job
    from app.jobs.queue import enqueue_job

    current = now or datetime.now(UTC)
    # Several workers run this every cycle. Only one schedules at a time; the
    # others skip the cycle (the next one finds the jobs already queued).
    if not db.scalar(text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": SCHEDULER_LOCK_KEY}):
        return 0
    columns = (
        ChannelConnection.tenant_id,
        ChannelConnection.bot_id,
        ChannelConnection.id,
    )
    poll = aliased(Job)
    last_poll = (
        select(func.max(poll.created_at))
        .where(
            poll.type == "channel_health_poll",
            poll.tenant_id == ChannelConnection.tenant_id,
            poll.payload["connection_id"].astext == cast(ChannelConnection.id, Text),
        )
        .correlate(ChannelConnection)
        .scalar_subquery()
    )
    statement = (
        select(*columns)
        .outerjoin(
            Job,
            (Job.type == "channel_health_poll")
            & (Job.status.in_(("pending", "running")))
            & (Job.payload["connection_id"].astext == cast(ChannelConnection.id, Text)),
        )
        .where(
            ChannelConnection.status == "active",
            Job.id.is_(None),
        )
        # Least recently polled first (never polled = first), so a fleet larger than
        # one batch is still covered over successive cycles.
        .order_by(last_poll.asc().nulls_first(), ChannelConnection.id)
        .limit(settings.channel_health_poll_batch)
    )
    scheduled = 0
    for tenant_id, bot_id, connection_id in db.execute(statement).all():
        try:
            # Savepoint: the partial unique index is the last line of defence
            # if a job slipped in; one conflict must not lose the whole cycle.
            with db.begin_nested():
                job = enqueue_job(
                    db,
                    tenant_id=tenant_id,
                    bot_id=bot_id,
                    job_type="channel_health_poll",
                    payload={"connection_id": str(connection_id)},
                    created_by=None,
                    settings=settings,
                )
        except IntegrityError:
            continue
        job.run_at = current + timedelta(
            seconds=random.uniform(0.0, float(settings.channel_health_poll_jitter_seconds))
        )
        job.max_attempts = max(job.max_attempts, 3)
        scheduled += 1
    db.flush()
    return scheduled
