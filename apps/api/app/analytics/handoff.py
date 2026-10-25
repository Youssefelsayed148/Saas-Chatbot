"""Tenant-level measured handoff, response, and workload analytics."""

from datetime import datetime, timedelta
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.analytics.service import _range_window
from app.core.errors import ApiError
from app.core.tenancy import TenantContextDep

router = APIRouter(prefix="/api/v1/tenants/{tenant_id}/analytics", tags=["analytics"])
MAX_TIMESERIES_DAYS = 366


def _window(from_iso: str | None, to_iso: str | None) -> tuple[datetime, datetime]:
    try:
        return _range_window(from_iso, to_iso)
    except ValueError as exc:
        raise ApiError(422, "VALIDATION_ERROR", str(exc)) from exc


def _totals(db: Session, tenant_id: UUID, start: datetime, end: datetime) -> dict[str, Any]:
    """Website-conversation totals and mean first human reply for one window."""
    counts = (
        db.execute(
            text(
                """SELECT count(*) AS total,
                count(*) FILTER (WHERE handoff_reason IS NOT NULL) AS handoffs,
                count(*) FILTER (WHERE status = 'resolved') AS resolved,
                count(*) FILTER (WHERE status <> 'resolved') AS open
            FROM conversations
            WHERE tenant_id = :tenant_id AND source = 'website'
              AND created_at >= :start AND created_at <= :end"""
            ),
            {"tenant_id": tenant_id, "start": start, "end": end},
        )
        .mappings()
        .one()
    )
    seconds = db.execute(
        text(
            """WITH first_replies AS (
                SELECT c.id, min(m.created_at) AS first_reply_at, c.created_at
                FROM conversations c
                JOIN messages m ON m.tenant_id = c.tenant_id
                  AND m.conversation_id = c.id AND m.sender_type = 'agent'
                WHERE c.tenant_id = :tenant_id AND c.source = 'website'
                  AND c.created_at >= :start AND c.created_at <= :end
                GROUP BY c.id, c.created_at
            )
            SELECT avg(extract(epoch FROM (first_reply_at - created_at))) AS seconds
            FROM first_replies"""
        ),
        {"tenant_id": tenant_id, "start": start, "end": end},
    ).scalar_one()
    return {
        "total": int(counts["total"] or 0),
        "handoffs": int(counts["handoffs"] or 0),
        "resolved": int(counts["resolved"] or 0),
        "open": int(counts["open"] or 0),
        "response_seconds": float(seconds) if seconds is not None else None,
    }


@router.get("")
def handoff_analytics(
    context: TenantContextDep,
    from_iso: Annotated[str | None, Query(alias="from")] = None,
    to_iso: Annotated[str | None, Query(alias="to")] = None,
) -> dict[str, Any]:
    context.require_role("viewer")
    start, end = _window(from_iso, to_iso)
    totals = _totals(context.db, context.tenant_id, start, end)
    total = totals["total"]
    handoffs = totals["handoffs"]
    response_time = totals["response_seconds"]
    span = end - start
    previous_end = start - timedelta(seconds=1)
    previous_start = previous_end - span
    previous = _totals(context.db, context.tenant_id, previous_start, previous_end)
    channels = (
        context.db.execute(
            text(
                """SELECT channel, count(*) AS count FROM conversations
            WHERE tenant_id = :tenant_id AND source = 'website'
              AND created_at >= :start AND created_at <= :end
            GROUP BY channel ORDER BY channel"""
            ),
            {"tenant_id": context.tenant_id, "start": start, "end": end},
        )
        .mappings()
        .all()
    )
    sentiment = (
        context.db.execute(
            text(
                """SELECT sentiment, count(*) AS count FROM conversations
            WHERE tenant_id = :tenant_id AND source = 'website'
              AND created_at >= :start AND created_at <= :end
              AND sentiment IS NOT NULL
            GROUP BY sentiment ORDER BY sentiment"""
            ),
            {"tenant_id": context.tenant_id, "start": start, "end": end},
        )
        .mappings()
        .all()
    )
    workload = (
        context.db.execute(
            text(
                """SELECT users.email AS member_name, count(*) AS count
            FROM conversations
            JOIN users ON users.id = conversations.assigned_user_id
            WHERE conversations.tenant_id = :tenant_id AND conversations.source = 'website'
              AND conversations.created_at >= :start AND conversations.created_at <= :end
              AND conversations.status <> 'resolved'
              AND conversations.assigned_user_id IS NOT NULL
            GROUP BY users.email ORDER BY users.email"""
            ),
            {"tenant_id": context.tenant_id, "start": start, "end": end},
        )
        .mappings()
        .all()
    )
    return {
        "total_conversations": total,
        "handoff_count": handoffs,
        "handoff_rate": handoffs / total if total else None,
        "average_first_human_reply_seconds": response_time,
        "conversations_by_channel": {str(row["channel"]): int(row["count"]) for row in channels},
        "resolved_vs_open": {
            "resolved": totals["resolved"],
            "open": totals["open"],
        },
        "sentiment_distribution": {str(row["sentiment"]): int(row["count"]) for row in sentiment},
        "agent_workload": {str(row["member_name"]): int(row["count"]) for row in workload},
        "previous": {
            "from": previous_start.date().isoformat(),
            "to": previous_end.date().isoformat(),
            "total_conversations": previous["total"],
            "handoff_count": previous["handoffs"],
            "handoff_rate": previous["handoffs"] / previous["total"] if previous["total"] else None,
            "average_first_human_reply_seconds": previous["response_seconds"],
        },
    }


@router.get("/timeseries")
def conversation_timeseries(
    context: TenantContextDep,
    from_iso: Annotated[str | None, Query(alias="from")] = None,
    to_iso: Annotated[str | None, Query(alias="to")] = None,
) -> dict[str, Any]:
    """Per-day website conversations, handoffs and resolved, zero-filled over the window."""
    context.require_role("viewer")
    start, end = _window(from_iso, to_iso)
    if (end.date() - start.date()).days >= MAX_TIMESERIES_DAYS:
        raise ApiError(
            422, "VALIDATION_ERROR", f"The window must not exceed {MAX_TIMESERIES_DAYS} days."
        )
    rows = (
        context.db.execute(
            text(
                """SELECT d.day::date AS day,
                count(c.id) AS conversations,
                count(c.id) FILTER (WHERE c.handoff_reason IS NOT NULL) AS handoffs,
                count(c.id) FILTER (WHERE c.status = 'resolved') AS resolved
            FROM generate_series(
                CAST(:start_day AS date), CAST(:end_day AS date), INTERVAL '1 day'
            ) AS d(day)
            LEFT JOIN conversations c
              ON c.tenant_id = :tenant_id AND c.source = 'website'
             AND c.created_at >= :start AND c.created_at <= :end
             AND (c.created_at AT TIME ZONE 'UTC')::date = d.day::date
            GROUP BY d.day ORDER BY d.day"""
            ),
            {
                "tenant_id": context.tenant_id,
                "start": start,
                "end": end,
                "start_day": start.date(),
                "end_day": end.date(),
            },
        )
        .mappings()
        .all()
    )
    return {
        "from": start.date().isoformat(),
        "to": end.date().isoformat(),
        "days": [
            {
                "day": row["day"].isoformat(),
                "conversations": int(row["conversations"]),
                "handoffs": int(row["handoffs"]),
                "resolved": int(row["resolved"]),
            }
            for row in rows
        ],
    }
