"""Tenant-level measured handoff, response, and workload analytics."""

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query
from sqlalchemy import text

from app.analytics.service import _range_window
from app.core.errors import ApiError
from app.core.tenancy import TenantContextDep

router = APIRouter(prefix="/api/v1/tenants/{tenant_id}/analytics", tags=["analytics"])

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
    rows = context.db.execute(
        _CHANNEL_BREAKDOWN_SQL,
        {"tenant_id": context.tenant_id, "start": start, "end": end},
    ).mappings().all()
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
    alias_filter, alias_params = _channel_filter_aliased("c.", channel)
    base_params: dict[str, Any] = {
        "tenant_id": context.tenant_id,
        "start": start,
        "end": end,
        **channel_params,
    }
    totals = (
        context.db.execute(
            text(
                f"""SELECT count(*) AS total,
                count(*) FILTER (WHERE handoff_reason IS NOT NULL) AS handoffs,
                count(*) FILTER (WHERE status = 'resolved') AS resolved,
                count(*) FILTER (WHERE status <> 'resolved') AS open
            FROM conversations
            WHERE tenant_id = :tenant_id AND {channel_filter}
              AND created_at >= :start AND created_at <= :end"""
            ),
            base_params,
        )
        .mappings()
        .one()
    )
    total = int(totals["total"] or 0)
    handoffs = int(totals["handoffs"] or 0)
    response_time = context.db.execute(
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
        base_params,
    ).scalar_one()
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
        "average_first_human_reply_seconds": float(response_time)
        if response_time is not None
        else None,
        "conversations_by_channel": {str(row["channel"]): int(row["count"]) for row in channels},
        "channel_breakdown": _channel_breakdown(context, start, end),
        "conversations_by_campaign": _conversations_by_campaign(
            context, start, end, channel
        ),
        "resolved_vs_open": {
            "resolved": int(totals["resolved"] or 0),
            "open": int(totals["open"] or 0),
        },
        "sentiment_distribution": {str(row["sentiment"]): int(row["count"]) for row in sentiment},
        "agent_workload": {str(row["member_name"]): int(row["count"]) for row in workload},
    }
