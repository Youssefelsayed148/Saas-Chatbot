"""Postgres-backed fixed-window abuse counters (P4-01, docs/14 §7).

Counters live in ``rate_limit_counters`` so they survive restarts and are
shared by every API process (the P1 in-process login limiter is folded into
this service). One atomic upsert per check; the caller raises 429 when the
returned count exceeds the limit.
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session as OrmSession


def rate_limit(
    db: OrmSession,
    *,
    key: str,
    limit: int,
    window_seconds: int,
    now: datetime | None = None,
) -> tuple[int, int]:
    """Count one attempt in a fixed window; returns (count, limit_exceeded).

    The upsert is atomic: a window that has aged out resets at 1 in the same
    statement. The return is ``(count, remaining_is_zero)`` where count is
    the value AFTER the increment; the caller compares against ``limit``.
    """
    current = now or datetime.now(UTC)
    window_start = int(current.timestamp()) // max(window_seconds, 1) * max(window_seconds, 1)
    row = db.execute(
        text(
            """
            INSERT INTO rate_limit_counters (bucket_key, window_start, count, updated_at)
            VALUES (:key, :window_start, 1, NOW())
            ON CONFLICT (bucket_key) DO UPDATE SET
                count = CASE
                    WHEN rate_limit_counters.window_start < :window_start THEN 1
                    ELSE rate_limit_counters.count + 1
                END,
                window_start = CASE
                    WHEN rate_limit_counters.window_start < :window_start THEN :window_start
                    ELSE rate_limit_counters.window_start
                END,
                updated_at = NOW()
            RETURNING count
            """
        ),
        {"key": key, "window_start": window_start},
    ).scalar_one()
    count = int(row)
    return count, max(0, limit - count)


def purge_expired_windows(db: OrmSession, *, older_than_epoch: int) -> int:
    """Housekeeping for aged windows; called from the retention purge job."""
    result = db.execute(
        text("DELETE FROM rate_limit_counters WHERE window_start < :cutoff"),
        {"cutoff": older_than_epoch},
    )
    return int(getattr(result, "rowcount", 0) or 0)


def enforce_or_429(
    db: OrmSession,
    *,
    key: str,
    limit: int,
    window_seconds: int,
    message: str,
) -> None:
    """Count one attempt and raise the standard 429 ApiError over the cap."""
    from app.core.errors import ApiError

    count, _remaining = rate_limit(db, key=key, limit=limit, window_seconds=window_seconds)
    if count > limit:
        raise ApiError(429, "RATE_LIMITED", message)


def client_ip(request: Any) -> str:
    """Best-effort client IP for abuse scoping (never logged; docs/18 #3)."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return str(forwarded.split(",")[0].strip())
    return str(request.client.host) if request.client else "unknown"
