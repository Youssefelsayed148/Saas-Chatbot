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
CHANNELS = ("website", "whatsapp", "messenger", "instagram")


def _window(from_iso: str | None, to_iso: str | None) -> tuple[datetime, datetime]:
    try:
        return _range_window(from_iso, to_iso)
    except ValueError as exc:
        raise ApiError(422, "VALIDATION_ERROR", str(exc)) from exc


def _channel_filter(channel: str | None) -> tuple[str, dict[str, Any]]:
    """Where fragment for the conversation scope of this request (authored).

    Default (no channel) keeps the accepted P5 website-only window. A channel
    value filters by `conversations.channel` and widens the source to include
    delegated-channel conversations (P6-05b insights by channel).
    """
    if channel is None:
        return "source = 'website'", {}
    if channel not in CHANNELS:
        raise ApiError(
            422,
            "VALIDATION_ERROR",
            "channel must be one of website, whatsapp, messenger, instagram.",
        )
    return "channel = :channel AND source IN ('website', 'channel')", {"channel": channel}


def _channel_filter_aliased(prefix: str, channel: str | None) -> tuple[str, dict[str, Any]]:
    """Same fragment qualified for an alias, e.g. `c.`."""
    fragment, params = _channel_filter(channel)
    return fragment.replace("source", f"{prefix}source").replace(
        "channel =", f"{prefix}channel ="
    ).replace("channel IN", f"{prefix}channel IN"), params


_CHANNEL_BREAKDOWN_SQL = text(
    """
    SELECT c.channel AS channel,
           count(*) AS conversations,
           count(*) FILTER (
               WHERE c.mode = 'human' OR c.status = 'waiting_human'
           ) AS handoffs,
           count(*) FILTER (WHERE c.status = 'resolved') AS resolved,
           COALESCE(sum(u.unanswered), 0) AS unanswered,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY fr.seconds) AS median_seconds
    FROM conversations c
    LEFT JOIN LATERAL (
        SELECT count(*) AS unanswered FROM messages m
        WHERE m.tenant_id = c.tenant_id AND m.conversation_id = c.id
          AND m.sender_type = 'ai' AND m.can_answer IS FALSE
    ) u ON TRUE
    LEFT JOIN LATERAL (
        SELECT extract(epoch FROM min(m.created_at) - c.created_at) AS seconds
        FROM messages m
        WHERE m.tenant_id = c.tenant_id AND m.conversation_id = c.id
          AND m.sender_type IN ('agent', 'ai')
    ) fr ON TRUE
    WHERE c.tenant_id = :tenant_id AND c.source IN ('website', 'channel')
      AND c.created_at >= :start AND c.created_at <= :end
    GROUP BY c.channel ORDER BY c.channel
    """
)


def _channel_breakdown(
    context: TenantContextDep, start: datetime, end: datetime
) -> list[dict[str, Any]]:
    rows = (
        context.db.execute(
            _CHANNEL_BREAKDOWN_SQL,
            {"tenant_id": context.tenant_id, "start": start, "end": end},
        )
        .mappings()
        .all()
    )
    breakdown: list[dict[str, Any]] = []
    for row in rows:
        conversations = int(row["conversations"] or 0)
        handoffs = int(row["handoffs"] or 0)
        resolved = int(row["resolved"] or 0)
        median = row["median_seconds"]
        breakdown.append(
            {
                "channel": str(row["channel"]),
                "conversations": conversations,
                "handoff_count": handoffs,
                "handoff_rate": round(handoffs / conversations, 4) if conversations else None,
                "unanswered_questions": int(row["unanswered"] or 0),
                "median_first_response_seconds": float(median) if median is not None else None,
                "resolved_count": resolved,
                "resolved_rate": round(resolved / conversations, 4) if conversations else None,
            }
        )
    return breakdown


def _conversations_by_campaign(
    context: TenantContextDep,
    start: datetime,
    end: datetime,
    channel: str | None = None,
) -> dict[str, int]:
    sql = """
    SELECT c.origin->>'campaign_name' AS campaign, count(*) AS conversations
    FROM conversations c
    WHERE c.tenant_id = :tenant_id AND c.source = 'channel'
      AND c.origin ? 'campaign_name'
      AND c.created_at >= :start AND c.created_at <= :end
    {channel}
    GROUP BY 1 ORDER BY conversations DESC, campaign
    """
    rows = context.db.execute(
        text(sql.format(channel="AND c.channel = :channel" if channel else "")),
        {
            "tenant_id": context.tenant_id,
            "start": start,
            "end": end,
            **({"channel": channel} if channel else {}),
        },
    ).all()
    return {str(campaign): int(conversations) for campaign, conversations in rows}


def _totals(
    db: Session,
    tenant_id: UUID,
    start: datetime,
    end: datetime,
    channel: str | None = None,
) -> dict[str, Any]:
    """Conversation totals and mean first human reply for one window.

    Default (no channel) is website-only; a channel widens to delegated channels.
    """
    channel_filter, channel_params = _channel_filter(channel)
    alias_filter, _ = _channel_filter_aliased("c.", channel)
    params: dict[str, Any] = {"tenant_id": tenant_id, "start": start, "end": end, **channel_params}
    counts = (
        db.execute(
            text(
                f"""SELECT count(*) AS total,
                count(*) FILTER (WHERE handoff_reason IS NOT NULL) AS handoffs,
                count(*) FILTER (WHERE status = 'resolved') AS resolved,
                count(*) FILTER (WHERE status <> 'resolved') AS open
            FROM conversations
            WHERE tenant_id = :tenant_id AND {channel_filter}
              AND created_at >= :start AND created_at <= :end"""
            ),
            params,
        )
        .mappings()
        .one()
    )
    seconds = db.execute(
        text(
            f"""WITH first_replies AS (
                SELECT c.id, min(m.created_at) AS first_reply_at, c.created_at
                FROM conversations c
                JOIN messages m ON m.tenant_id = c.tenant_id
                  AND m.conversation_id = c.id AND m.sender_type = 'agent'
                WHERE c.tenant_id = :tenant_id AND {alias_filter}
                  AND c.created_at >= :start AND c.created_at <= :end
                GROUP BY c.id, c.created_at
            )
            SELECT avg(extract(epoch FROM (first_reply_at - created_at))) AS seconds
            FROM first_replies"""
        ),
        params,
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
    channel: Annotated[str | None, Query(max_length=32)] = None,
) -> dict[str, Any]:
    context.require_role("viewer")
    start, end = _window(from_iso, to_iso)
    channel_filter, channel_params = _channel_filter(channel)
    alias_filter, _ = _channel_filter_aliased("c.", channel)
    base_params: dict[str, Any] = {
        "tenant_id": context.tenant_id,
        "start": start,
        "end": end,
        **channel_params,
    }
    totals = _totals(context.db, context.tenant_id, start, end, channel)
    total = totals["total"]
    handoffs = totals["handoffs"]
    response_time = totals["response_seconds"]
    span = end - start
    previous_end = start - timedelta(seconds=1)
    previous_start = previous_end - span
    previous = _totals(context.db, context.tenant_id, previous_start, previous_end, channel)
    channels = (
        context.db.execute(
            text(
                f"""SELECT channel, count(*) AS count FROM conversations
            WHERE tenant_id = :tenant_id AND {channel_filter}
              AND created_at >= :start AND created_at <= :end
            GROUP BY channel ORDER BY channel"""
            ),
            base_params,
        )
        .mappings()
        .all()
    )
    sentiment = (
        context.db.execute(
            text(
                f"""SELECT sentiment, count(*) AS count FROM conversations
            WHERE tenant_id = :tenant_id AND {channel_filter}
              AND created_at >= :start AND created_at <= :end
              AND sentiment IS NOT NULL
            GROUP BY sentiment ORDER BY sentiment"""
            ),
            base_params,
        )
        .mappings()
        .all()
    )
    workload = (
        context.db.execute(
            text(
                f"""SELECT users.email AS member_name, count(*) AS count
            FROM conversations c
            JOIN users ON users.id = c.assigned_user_id
            WHERE c.tenant_id = :tenant_id AND {alias_filter}
              AND c.created_at >= :start AND c.created_at <= :end
              AND c.status <> 'resolved'
              AND c.assigned_user_id IS NOT NULL
            GROUP BY users.email ORDER BY users.email"""
            ),
            base_params,
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
        "channel_breakdown": _channel_breakdown(context, start, end),
        "conversations_by_campaign": _conversations_by_campaign(context, start, end, channel),
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
