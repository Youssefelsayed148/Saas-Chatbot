"""Overview analytics (P4-05, docs/14 §9, docs/10 Overview tab).

Measured data only: usage_events (widget_open/message/lead/feedback_*) and
the REAL conversations/messages rows. Playground threads never count
(source='playground'). Date range via `from`/`to` (inclusive, ISO dates).
Every query is tenant+bot scoped; no invented numbers.
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session as OrmSession


def _range_window(from_iso: str | None, to_iso: str | None) -> tuple[datetime, datetime]:
    """Inclusive date window (UTC); defaults to the last 30 days."""
    now = datetime.now(UTC)
    try:
        start = (
            datetime.fromisoformat(from_iso).replace(tzinfo=UTC, hour=0, minute=0, second=0)
            if from_iso
            else (now - timedelta(days=29)).replace(hour=0, minute=0, second=0, microsecond=0)
        )
        end = (
            datetime.fromisoformat(to_iso).replace(tzinfo=UTC, hour=23, minute=59, second=59)
            if to_iso
            else now
        )
    except ValueError as exc:
        raise ValueError("Dates must be ISO format YYYY-MM-DD.") from exc
    if end < start:
        raise ValueError("The end date must not precede the start date.")
    return start, end


def summary(
    db: OrmSession, *, tenant_id: UUID, bot_id: UUID, start: datetime, end: datetime
) -> dict[str, Any]:
    """Summary metrics per docs/14 §9 (all measured)."""
    row = (
        db.execute(
            text(
                """
        WITH ev AS (
            SELECT kind, count(*) AS n FROM usage_events
            WHERE tenant_id = CAST(:t AS uuid) AND bot_id = CAST(:b AS uuid)
              AND COALESCE(payload->>'source', '') <> 'playground'
              AND created_at >= :start AND created_at <= :end
            GROUP BY kind
        ),
        convs AS (
            SELECT count(*) AS threads,
                   count(*) FILTER (WHERE mode = 'human' OR status = 'waiting_human') AS handoffs
            FROM conversations
            WHERE tenant_id = CAST(:t AS uuid) AND bot_id = CAST(:b AS uuid)
              AND source <> 'playground'
              AND created_at >= :start AND created_at <= :end
        ),
        msgs AS (
            SELECT
                count(*) FILTER (WHERE sender_type = 'visitor') AS visitor_turns,
                count(*) FILTER (WHERE sender_type = 'ai') AS ai_turns,
                count(*) FILTER (WHERE sender_type = 'ai' AND needs_human IS TRUE) AS needs_human,
                count(*) FILTER (WHERE sender_type = 'ai' AND can_answer IS FALSE) AS cannot_answer,
                COALESCE(avg(response_ms) FILTER (WHERE sender_type = 'ai'), 0) AS avg_response_ms
            FROM messages
            WHERE tenant_id = CAST(:t AS uuid) AND bot_id = CAST(:b AS uuid)
              AND conversation_id IN (
                  SELECT id FROM conversations
                  WHERE tenant_id = CAST(:t AS uuid) AND bot_id = CAST(:b AS uuid)
                    AND source <> 'playground')
              AND created_at >= :start AND created_at <= :end
        )
        SELECT
            msgs.visitor_turns AS messages,
            convs.threads AS conversations,
            (SELECT n FROM ev WHERE kind = 'message') AS counted_messages,
            (SELECT n FROM ev WHERE kind = 'widget_open') AS widget_opens,
            (SELECT n FROM ev WHERE kind = 'lead') AS leads,
            (SELECT n FROM ev WHERE kind = 'feedback_up') AS thumbs_up,
            (SELECT n FROM ev WHERE kind = 'feedback_down') AS thumbs_down,
            msgs.needs_human,
            msgs.cannot_answer,
            msgs.ai_turns,
            convs.handoffs,
            msgs.avg_response_ms
        FROM msgs CROSS JOIN convs
        """
            ),
            {"t": str(tenant_id), "b": str(bot_id), "start": start, "end": end},
        )
        .mappings()
        .one()
    )
    messages = int(row["messages"] or 0)
    conversations = int(row["conversations"] or 0)
    widget_opens = int(row["widget_opens"] or 0)
    counted_messages = int(row["counted_messages"] or 0)
    cannot_answer = int(row["cannot_answer"] or 0)
    engagement = round(widget_opens / conversations, 4) if conversations else 0.0
    per_conversation = round(messages / conversations, 2) if conversations else 0.0
    # Distribution buckets of messages per conversation (1,2-3,4-6,7+).
    distribution = {
        "1": 0,
        "2-3": 0,
        "4-6": 0,
        "7+": 0,
    }
    bucket_rows = db.execute(
        text(
            """
            SELECT visitor_count, count(*) FROM (
                SELECT c.id, count(m.id) FILTER (WHERE m.sender_type = 'visitor') AS visitor_count
                FROM conversations c
                LEFT JOIN messages m ON m.conversation_id = c.id
                WHERE c.tenant_id = CAST(:t AS uuid) AND c.bot_id = CAST(:b AS uuid)
                  AND c.source <> 'playground'
                  AND c.created_at >= :start AND c.created_at <= :end
                GROUP BY c.id
            ) buckets GROUP BY visitor_count ORDER BY visitor_count
        """
        ),
        {"t": str(tenant_id), "b": str(bot_id), "start": start, "end": end},
    ).fetchall()
    for visitor_count, count in bucket_rows:
        visitor_count = int(visitor_count or 0)
        if visitor_count <= 1:
            distribution["1"] += int(count)
        elif visitor_count <= 3:
            distribution["2-3"] += int(count)
        elif visitor_count <= 6:
            distribution["4-6"] += int(count)
        else:
            distribution["7+"] += int(count)
    fallback_rate = (
        round(cannot_answer / int(row["ai_turns"] or 0 or 1), 4) if row["ai_turns"] else 0.0
    )
    return {
        "messages": messages,
        "counted_messages": counted_messages,
        "conversations": conversations,
        "widget_opens": widget_opens,
        "engagement_rate": engagement,
        "avg_messages_per_conversation": per_conversation,
        "message_distribution": distribution,
        "fallback_rate": fallback_rate,
        "cannot_answer": cannot_answer,
        "needs_human": int(row["needs_human"] or 0),
        "handoffs": int(row["handoffs"] or 0),
        "avg_response_ms": int(row["avg_response_ms"] or 0),
        "leads": int(row["leads"] or 0),
        "thumbs_up": int(row["thumbs_up"] or 0),
        "thumbs_down": int(row["thumbs_down"] or 0),
    }


def volume_per_day(
    db: OrmSession, *, tenant_id: UUID, bot_id: UUID, start: datetime, end: datetime
) -> list[dict[str, Any]]:
    rows = db.execute(
        text(
            """
        SELECT date_trunc('day', m.created_at)::date AS day,
               count(*) FILTER (WHERE m.sender_type = 'visitor') AS visitor,
               count(*) FILTER (WHERE m.sender_type = 'ai') AS assistant
        FROM messages m
        WHERE m.tenant_id = CAST(:t AS uuid) AND m.bot_id = CAST(:b AS uuid)
          AND m.created_at >= :start AND m.created_at <= :end
          AND m.conversation_id IN (
              SELECT id FROM conversations
              WHERE tenant_id = CAST(:t AS uuid) AND bot_id = CAST(:b AS uuid)
                AND source <> 'playground')
        GROUP BY 1 ORDER BY 1
        """
        ),
        {"t": str(tenant_id), "b": str(bot_id), "start": start, "end": end},
    ).fetchall()
    return [
        {
            "day": day.isoformat(),
            "visitor": int(visitor),
            "assistant": int(assistant),
        }
        for day, visitor, assistant in rows
    ]


def top_questions(
    db: OrmSession,
    *,
    tenant_id: UUID,
    bot_id: UUID,
    start: datetime,
    end: datetime,
    limit: int = 10,
) -> list[dict[str, Any]]:
    rows = db.execute(
        text(
            """
        SELECT left(m.text, 120) AS question, count(*) AS asked
        FROM messages m
        WHERE m.tenant_id = CAST(:t AS uuid) AND m.bot_id = CAST(:b AS uuid)
          AND m.sender_type = 'visitor'
          AND m.created_at >= :start AND m.created_at <= :end
          AND m.conversation_id IN (
              SELECT id FROM conversations
              WHERE tenant_id = CAST(:t AS uuid) AND bot_id = CAST(:b AS uuid)
                AND source <> 'playground')
        GROUP BY 1 ORDER BY asked DESC, 1 LIMIT :limit
        """
        ),
        {"t": str(tenant_id), "b": str(bot_id), "start": start, "end": end, "limit": limit},
    ).fetchall()
    return [{"question": str(question), "asked": int(asked)} for question, asked in rows]


def unanswered_questions(
    db: OrmSession,
    *,
    tenant_id: UUID,
    bot_id: UUID,
    start: datetime,
    end: datetime,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Visitor questions the bot could not confirm (can_answer=false AI replies)."""
    rows = db.execute(
        text(
            """
        SELECT left(q.text, 160) AS question, count(*) AS asked, max(q.created_at) AS last
        FROM messages q
        JOIN messages a ON a.conversation_id = q.conversation_id
            AND a.sender_type = 'ai'
            AND a.created_at >= q.created_at
            AND a.created_at < q.created_at + INTERVAL '1 minute'
        LEFT JOIN messages c ON c.conversation_id = q.conversation_id
            AND c.created_at > q.created_at
            AND c.created_at <= a.created_at
            AND c.sender_type = 'visitor'
        WHERE q.tenant_id = CAST(:t AS uuid) AND q.bot_id = CAST(:b AS uuid)
          AND q.sender_type = 'visitor'
          AND c.text IS NULL
          AND a.can_answer IS FALSE
          AND q.created_at >= :start AND q.created_at <= :end
        GROUP BY 1 ORDER BY last DESC LIMIT :limit
        """
        ),
        {"t": str(tenant_id), "b": str(bot_id), "start": start, "end": end, "limit": limit},
    ).fetchall()
    return [
        {"question": str(question), "asked": int(asked), "last": last.isoformat()}
        for question, asked, last in rows
    ]


def leads_trend(
    db: OrmSession, *, tenant_id: UUID, bot_id: UUID, start: datetime, end: datetime
) -> list[dict[str, Any]]:
    rows = db.execute(
        text(
            """
        SELECT date_trunc('day', u.created_at)::date AS day, count(*) AS leads
        FROM usage_events u
        WHERE u.tenant_id = CAST(:t AS uuid) AND u.bot_id = CAST(:b AS uuid)
          AND u.kind = 'lead'
          AND u.created_at >= :start AND u.created_at <= :end
        GROUP BY 1 ORDER BY 1
        """
        ),
        {"t": str(tenant_id), "b": str(bot_id), "start": start, "end": end},
    ).fetchall()
    return [{"day": day.isoformat(), "leads": int(leads)} for day, leads in rows]


def lead_contacts(
    db: OrmSession, *, tenant_id: UUID, bot_id: UUID, start: datetime, end: datetime
) -> list[dict[str, Any]]:
    """Contacts captured as leads inside the window (for the leads tab/CSV)."""
    rows = db.execute(
        text(
            """
        SELECT DISTINCT c.id, c.display_name, c.email, c.phone, c.stage, c.created_at,
               (SELECT count(*) FROM conversations cv
                 WHERE cv.tenant_id = CAST(:t AS uuid) AND cv.contact_id = c.id) AS conversations
        FROM contacts c
        JOIN usage_events u ON u.external_key LIKE 'lead:%'
            AND u.tenant_id = CAST(:t AS uuid) AND u.bot_id = CAST(:b AS uuid)
            AND u.created_at >= :start AND u.created_at <= :end
        WHERE c.tenant_id = CAST(:t AS uuid)
        ORDER BY c.created_at DESC
        LIMIT 200
        """
        ),
        {"t": str(tenant_id), "b": str(bot_id), "start": start, "end": end},
    ).fetchall()
    return [
        {
            "contact_id": str(row[0]),
            "display_name": row[1] or "",
            "email": row[2],
            "phone": row[3],
            "stage": row[4],
            "created_at": row[5].isoformat(),
            "conversations": int(row[6]),
        }
        for row in rows
    ]


def conversations_csv(
    db: OrmSession, *, tenant_id: UUID, bot_id: UUID, start: datetime, end: datetime
) -> list[dict[str, Any]]:
    """Operator-facing conversation export (docs/14 §9 CSV)."""
    rows = db.execute(
        text(
            """
        SELECT cv.id::text, cv.created_at, cv.last_message_at, cv.status, cv.mode,
               cv.channel, COALESCE(c.display_name, ''), (
                   SELECT count(*) FROM messages m WHERE m.conversation_id = cv.id
               ) AS message_count
        FROM conversations cv
        LEFT JOIN contacts c ON c.id = cv.contact_id
        WHERE cv.tenant_id = CAST(:t AS uuid) AND cv.bot_id = CAST(:b AS uuid)
          AND cv.source <> 'playground'
          AND cv.created_at >= :start AND cv.created_at <= :end
        ORDER BY cv.created_at DESC
        """
        ),
        {"t": str(tenant_id), "b": str(bot_id), "start": start, "end": end},
    ).fetchall()
    return [
        {
            "conversation_id": str(row[0]),
            "created_at": row[1].isoformat(),
            "last_message_at": (row[2] or row[1]).isoformat(),
            "status": str(row[3]),
            "mode": str(row[4]),
            "channel": str(row[5]),
            "contact_name": str(row[6]),
            "message_count": int(row[7]),
        }
        for row in rows
    ]
