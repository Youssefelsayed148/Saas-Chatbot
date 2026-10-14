"""Worker and widget delivery steps for scheduled website follow-ups."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.db.models import Conversation, FollowUp, Job, Message, VisitorSession
from app.inbox.events import add_inbox_event
from app.knowledge.ingest import JobFatal


def mark_follow_up_ready(db: OrmSession, job: Job) -> str | None:
    follow_up_id = job.payload.get("follow_up_id")
    if not isinstance(follow_up_id, str):
        raise JobFatal("Follow-up job payload is invalid.")
    try:
        parsed_id = UUID(follow_up_id)
    except ValueError as exc:
        raise JobFatal("Follow-up job payload is invalid.") from exc
    row = db.execute(
        select(FollowUp)
        .where(
            FollowUp.tenant_id == job.tenant_id,
            FollowUp.bot_id == job.bot_id,
            FollowUp.id == parsed_id,
        )
        .with_for_update()
    ).scalar_one_or_none()
    if row is None:
        raise JobFatal("The scheduled follow-up no longer exists.")
    if row.status == "scheduled":
        row.status = "ready"
    return None


def deliver_ready_follow_ups(
    db: OrmSession,
    *,
    conversation: Conversation,
    visitor_session: VisitorSession,
) -> bool:
    """Materialize due agent messages only when the widget reads its own thread."""
    if conversation.session_id != visitor_session.id:
        return False
    now = datetime.now(UTC)
    rows = (
        db.execute(
            select(FollowUp)
            .where(
                FollowUp.tenant_id == visitor_session.tenant_id,
                FollowUp.bot_id == visitor_session.bot_id,
                FollowUp.conversation_id == conversation.id,
                FollowUp.status == "ready",
                FollowUp.send_at <= now,
            )
            .order_by(FollowUp.send_at, FollowUp.id)
            .with_for_update(skip_locked=True)
        )
        .scalars()
        .all()
    )
    for row in rows:
        message = Message(
            tenant_id=row.tenant_id,
            bot_id=row.bot_id,
            conversation_id=row.conversation_id,
            sender_type="agent",
            sender_user_id=row.created_by,
            text=row.text,
            created_at=now,
        )
        db.add(message)
        db.flush()
        add_inbox_event(
            db,
            tenant_id=row.tenant_id,
            conversation_id=row.conversation_id,
            message_id=message.id,
            event_type="follow_up",
        )
        row.status = "delivered"
        row.delivered_at = now
        conversation.last_message_at = now
        conversation.updated_at = now
        db.add(row)
    return bool(rows)
