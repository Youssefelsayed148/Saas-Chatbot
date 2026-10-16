"""Tenant-level measured handoff, response, and workload analytics."""

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query
from sqlalchemy import text

from app.analytics.service import _range_window
from app.core.errors import ApiError
from app.core.tenancy import TenantContextDep

router = APIRouter(prefix="/api/v1/tenants/{tenant_id}/analytics", tags=["analytics"])


def _window(from_iso: str | None, to_iso: str | None) -> tuple[datetime, datetime]:
    try:
        return _range_window(from_iso, to_iso)
    except ValueError as exc:
        raise ApiError(422, "VALIDATION_ERROR", str(exc)) from exc


@router.get("")
def handoff_analytics(
    context: TenantContextDep,
    from_iso: Annotated[str | None, Query(alias="from")] = None,
    to_iso: Annotated[str | None, Query(alias="to")] = None,
) -> dict[str, Any]:
    context.require_role("viewer")
    start, end = _window(from_iso, to_iso)
    totals = (
        context.db.execute(
            text(
                """SELECT count(*) AS total,
                count(*) FILTER (WHERE handoff_reason IS NOT NULL) AS handoffs,
                count(*) FILTER (WHERE status = 'resolved') AS resolved,
                count(*) FILTER (WHERE status <> 'resolved') AS open
            FROM conversations
            WHERE tenant_id = :tenant_id AND source = 'website'
              AND created_at >= :start AND created_at <= :end"""
            ),
            {"tenant_id": context.tenant_id, "start": start, "end": end},
        )
        .mappings()
        .one()
    )
    total = int(totals["total"] or 0)
    handoffs = int(totals["handoffs"] or 0)
    response_time = context.db.execute(
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
        {"tenant_id": context.tenant_id, "start": start, "end": end},
    ).scalar_one()
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
        "average_first_human_reply_seconds": float(response_time)
        if response_time is not None
        else None,
        "conversations_by_channel": {str(row["channel"]): int(row["count"]) for row in channels},
        "resolved_vs_open": {
            "resolved": int(totals["resolved"] or 0),
            "open": int(totals["open"] or 0),
        },
        "sentiment_distribution": {str(row["sentiment"]): int(row["count"]) for row in sentiment},
        "agent_workload": {str(row["member_name"]): int(row["count"]) for row in workload},
    }
