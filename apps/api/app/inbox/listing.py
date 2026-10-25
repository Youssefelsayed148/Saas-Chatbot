"""Inbox list, unread state, and database-backed SSE cursor (P5-02)."""

import json
import time
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import and_, func, or_, select, tuple_
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import aliased

from app.auth import cookies
from app.core.errors import ApiError
from app.core.tenancy import TenantContext, TenantContextDep
from app.db.models import (
    Contact,
    Conversation,
    ConversationRead,
    ConversationTag,
    InboxEvent,
    Membership,
    Message,
)
from app.db.session import get_engine, session_factory
from app.inbox.events import add_inbox_event

router = APIRouter(prefix="/api/v1/tenants/{tenant_id}/inbox", tags=["inbox"])
CsrfOk = Annotated[None, Depends(cookies.require_csrf)]
INBOX_POLL_SECONDS = 2.0
MAX_SSE_BATCH = 200


class TagRequest(BaseModel):
    tag: str = Field(min_length=1, max_length=32)

    @field_validator("tag")
    @classmethod
    def normalize_tag(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if not normalized or any(ord(char) < 32 for char in normalized):
            raise ValueError("Tag must contain printable characters.")
        return normalized


def _unread_count(tenant_id: UUID, user_id: UUID, conversation_id: Any) -> Any:
    read_alias = aliased(ConversationRead)
    message_alias = aliased(Message)
    read_at = (
        select(read_alias.last_read_at)
        .where(
            read_alias.tenant_id == tenant_id,
            read_alias.conversation_id == conversation_id,
            read_alias.user_id == user_id,
        )
        # The conversation belongs to the outer inbox query, two SELECT levels
        # up. Auto-correlation only considers the immediate unread-message query.
        .correlate(Conversation)
        .scalar_subquery()
    )
    read_id = (
        select(read_alias.last_read_message_id)
        .where(
            read_alias.tenant_id == tenant_id,
            read_alias.conversation_id == conversation_id,
            read_alias.user_id == user_id,
        )
        .correlate(Conversation)
        .scalar_subquery()
    )
    inbound = or_(
        message_alias.sender_type == "visitor",
        and_(
            message_alias.sender_type == "agent",
            message_alias.sender_user_id != user_id,
        ),
    )
    after_read = or_(
        read_at.is_(None),
        tuple_(message_alias.created_at, message_alias.id) > tuple_(read_at, read_id),
    )
    return (
        select(func.count(message_alias.id))
        .where(
            message_alias.tenant_id == tenant_id,
            message_alias.conversation_id == conversation_id,
            inbound,
            after_read,
        )
        .scalar_subquery()
    )


def _conversation_or_404(context: TenantContext, conversation_id: UUID) -> Conversation:
    row = context.db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.tenant_id == context.tenant_id,
            Conversation.source == "website",
        )
    ).scalar_one_or_none()
    if row is None:
        raise ApiError(404, "NOT_FOUND", "Resource not found.")
    return row


@router.get("")
def list_inbox(
    context: TenantContextDep,
    status: Literal["open", "waiting_human", "resolved"] | None = None,
    mode: Literal["ai", "human"] | None = None,
    channel: Literal["website", "whatsapp", "messenger", "instagram"] | None = None,
    assignee: str | None = Query(default=None, max_length=36),
    tag: str | None = Query(default=None, min_length=1, max_length=32),
    unread: bool | None = None,
    q: str | None = Query(default=None, max_length=200),
    created_from: date | None = None,
    created_to: date | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100_000),
) -> dict[str, Any]:
    """Tenant-scoped inbox page with filters, search, and per-user unread counts."""
    statement = select(Conversation).where(
        Conversation.tenant_id == context.tenant_id,
        Conversation.source == "website",
    )
    if status is not None:
        statement = statement.where(Conversation.status == status)
    if mode is not None:
        statement = statement.where(Conversation.mode == mode)
    if channel is not None:
        statement = statement.where(Conversation.channel == channel)
    if created_from is not None:
        statement = statement.where(
            Conversation.created_at >= datetime.combine(created_from, datetime.min.time(), UTC)
        )
    if created_to is not None:
        # Inclusive calendar day: everything before the start of the next day.
        statement = statement.where(
            Conversation.created_at
            < datetime.combine(created_to + timedelta(days=1), datetime.min.time(), UTC)
        )
    if assignee == "me":
        statement = statement.where(Conversation.assigned_user_id == context.user.id)
    elif assignee == "unassigned":
        statement = statement.where(Conversation.assigned_user_id.is_(None))
    elif assignee is not None:
        try:
            assigned_user_id = UUID(assignee)
        except ValueError as exc:
            raise ApiError(422, "VALIDATION_ERROR", "Invalid assignee filter.") from exc
        statement = statement.where(Conversation.assigned_user_id == assigned_user_id)
    if tag is not None:
        normalized_tag = tag.strip().casefold()
        statement = statement.where(
            Conversation.id.in_(
                select(ConversationTag.conversation_id).where(
                    ConversationTag.tenant_id == context.tenant_id,
                    ConversationTag.tag == normalized_tag,
                )
            )
        )
    search = q.strip() if q else ""
    if search:
        matching = select(Message.conversation_id).where(
            Message.tenant_id == context.tenant_id,
            func.to_tsvector("simple", Message.text).op("@@")(
                func.websearch_to_tsquery("simple", search)
            ),
        )
        statement = statement.where(Conversation.id.in_(matching))

    unread_expr = _unread_count(context.tenant_id, context.user.id, Conversation.id).label(
        "unread_count"
    )
    total_statement = select(func.count()).select_from(statement.order_by(None).subquery())
    total = int(context.db.scalar(total_statement) or 0)
    if unread is not None:
        statement = statement.where((unread_expr > 0) if unread else (unread_expr == 0))
        total_statement = select(func.count()).select_from(statement.order_by(None).subquery())
        total = int(context.db.scalar(total_statement) or 0)

    latest_text = (
        select(Message.text)
        .where(
            Message.tenant_id == context.tenant_id,
            Message.conversation_id == Conversation.id,
        )
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(1)
        .correlate(Conversation)
        .scalar_subquery()
    )
    contact_name = (
        select(Contact.display_name)
        .where(Contact.tenant_id == context.tenant_id, Contact.id == Conversation.contact_id)
        .correlate(Conversation)
        .scalar_subquery()
    )
    rows = context.db.execute(
        statement.add_columns(unread_expr, latest_text, contact_name)
        .order_by(Conversation.last_message_at.desc().nullslast(), Conversation.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    ids = [row.id for row, _, _, _ in rows]
    tags_by_conversation: dict[UUID, list[str]] = defaultdict(list)
    if ids:
        tag_rows = context.db.execute(
            select(ConversationTag.conversation_id, ConversationTag.tag).where(
                ConversationTag.tenant_id == context.tenant_id,
                ConversationTag.conversation_id.in_(ids),
            )
        )
        for conversation_id, value in tag_rows:
            tags_by_conversation[conversation_id].append(value)
    conversations = [
        {
            "id": str(row.id),
            "bot_id": str(row.bot_id),
            "contact_id": str(row.contact_id) if row.contact_id else None,
            "contact_name": name or None,
            "created_at": row.created_at.isoformat(),
            "channel": row.channel,
            "mode": row.mode,
            "status": row.status,
            "assigned_user_id": str(row.assigned_user_id) if row.assigned_user_id else None,
            "handoff_reason": row.handoff_reason,
            "last_message_at": row.last_message_at.isoformat() if row.last_message_at else None,
            "last_message": text,
            "unread_count": int(count or 0),
            "tags": sorted(tags_by_conversation[row.id]),
        }
        for row, count, text, name in rows
    ]
    return {"conversations": conversations, "total": total, "limit": limit, "offset": offset}


@router.get("/counts")
def notification_counts(context: TenantContextDep) -> dict[str, int]:
    base = select(Conversation).where(
        Conversation.tenant_id == context.tenant_id,
        Conversation.source == "website",
    )
    waiting = context.db.scalar(
        select(func.count()).select_from(
            base.where(Conversation.status == "waiting_human").subquery()
        )
    )
    assigned = context.db.scalar(
        select(func.count()).select_from(
            base.where(
                Conversation.status != "resolved",
                Conversation.assigned_user_id == context.user.id,
            ).subquery()
        )
    )
    rows = context.db.execute(
        select(
            Conversation.id,
            _unread_count(context.tenant_id, context.user.id, Conversation.id),
        ).where(
            Conversation.tenant_id == context.tenant_id,
            Conversation.source == "website",
        )
    )
    unread_messages = 0
    unread_conversations = 0
    for _, count in rows:
        unread_messages += int(count or 0)
        unread_conversations += int((count or 0) > 0)
    return {
        "waiting_human": int(waiting or 0),
        "assigned_to_me": int(assigned or 0),
        "unread_messages": unread_messages,
        "unread_conversations": unread_conversations,
    }


@router.get("/assignees")
def list_assignees(context: TenantContextDep) -> list[dict[str, object]]:
    context.require_role("editor")
    from app.tenants.service import TenantService

    return [
        {
            "user_id": user.id,
            "email": user.email,
            "role": member.role,
            "status": member.status,
            "joined_at": member.created_at,
        }
        for member, user in TenantService(context.db).members_of(context.tenant_id)
        if member.role in ("admin", "editor")
    ]


@router.post("/{conversation_id}/read")
def mark_read(
    conversation_id: UUID,
    context: TenantContextDep,
    _: CsrfOk,
) -> dict[str, int]:
    context.require_role("editor")
    row = _conversation_or_404(context, conversation_id)
    latest = context.db.execute(
        select(Message.created_at, Message.id)
        .where(
            Message.tenant_id == context.tenant_id,
            Message.conversation_id == row.id,
        )
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(1)
    ).first()
    read = context.db.get(ConversationRead, (context.tenant_id, row.id, context.user.id))
    if read is None:
        read = ConversationRead(
            tenant_id=context.tenant_id,
            conversation_id=row.id,
            user_id=context.user.id,
        )
        context.db.add(read)
    read.last_read_at = latest[0] if latest else datetime.now(UTC)
    read.last_read_message_id = latest[1] if latest else UUID(int=0)
    read.updated_at = datetime.now(UTC)
    context.db.commit()
    count = context.db.scalar(select(_unread_count(context.tenant_id, context.user.id, row.id)))
    return {"unread_count": int(count or 0)}


def _add_cursor_event(context: TenantContext, conversation: Conversation, event_type: str) -> None:
    add_inbox_event(
        context.db,
        tenant_id=context.tenant_id,
        conversation_id=conversation.id,
        event_type=event_type,
    )


@router.post("/{conversation_id}/tags", status_code=201)
def add_tag(
    conversation_id: UUID,
    body: TagRequest,
    context: TenantContextDep,
    _: CsrfOk,
) -> dict[str, list[str]]:
    context.require_role("editor")
    conversation = _conversation_or_404(context, conversation_id)
    existing = context.db.get(ConversationTag, (context.tenant_id, conversation.id, body.tag))
    if existing is None:
        context.db.add(
            ConversationTag(
                tenant_id=context.tenant_id,
                conversation_id=conversation.id,
                tag=body.tag,
            )
        )
        _add_cursor_event(context, conversation, "conversation.tag_added")
        context.db.commit()
    return {"tags": _tags_for(context.db, context.tenant_id, conversation.id)}


@router.delete("/{conversation_id}/tags/{tag}")
def remove_tag(
    conversation_id: UUID,
    tag: str,
    context: TenantContextDep,
    _: CsrfOk,
) -> dict[str, list[str]]:
    context.require_role("editor")
    conversation = _conversation_or_404(context, conversation_id)
    normalized = tag.strip().casefold()
    existing = context.db.get(ConversationTag, (context.tenant_id, conversation.id, normalized))
    if existing is not None:
        context.db.delete(existing)
        _add_cursor_event(context, conversation, "conversation.tag_removed")
        context.db.commit()
    return {"tags": _tags_for(context.db, context.tenant_id, conversation.id)}


def _tags_for(db: OrmSession, tenant_id: UUID, conversation_id: UUID) -> list[str]:
    return list(
        db.execute(
            select(ConversationTag.tag)
            .where(
                ConversationTag.tenant_id == tenant_id,
                ConversationTag.conversation_id == conversation_id,
            )
            .order_by(ConversationTag.tag)
        ).scalars()
    )


def _cursor(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    if not value.isascii() or not value.isdecimal() or len(value) > 19:
        raise ApiError(400, "INVALID_EVENT_CURSOR", "Last-Event-ID must be a numeric inbox cursor.")
    return int(value)


def _sse(event: str, data: dict[str, Any], event_id: int | None = None) -> str:
    prefix = f"id: {event_id}\n" if event_id is not None else ""
    payload = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    return f"{prefix}event: {event}\ndata: {payload}\n\n"


@router.get("/events")
def stream_events(
    context: TenantContextDep,
    last_event_id_header: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> StreamingResponse:
    cursor = _cursor(last_event_id_header)
    return StreamingResponse(
        event_stream(context.tenant_id, context.user.id, cursor),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


def event_stream(tenant_id: UUID, user_id: UUID, cursor: int | None) -> Any:
    """Yield SSE events from the durable tenant cursor; shared by every process."""
    with session_factory(get_engine())() as db:
        cursor_query = select(func.max(InboxEvent.id)).where(InboxEvent.tenant_id == tenant_id)
        if cursor is None:
            cursor = int(db.scalar(cursor_query) or 0)
        else:
            # A foreign or stale cursor must not let a client skip this tenant's
            # events. Resume from the nearest cursor this tenant has actually seen.
            cursor = int(
                db.scalar(
                    select(func.max(InboxEvent.id)).where(
                        InboxEvent.tenant_id == tenant_id,
                        InboxEvent.id <= cursor,
                    )
                )
                or 0
            )
        counts = _notification_counts_for(db, tenant_id, user_id)
        yield _sse("inbox.ready", {"counts": counts}, cursor)
        while True:
            active = db.scalar(
                select(Membership.user_id).where(
                    Membership.tenant_id == tenant_id,
                    Membership.user_id == user_id,
                    Membership.status == "active",
                )
            )
            if active is None:
                yield _sse("inbox.access_revoked", {})
                return
            found = db.execute(
                select(InboxEvent, Message, Conversation)
                .join(
                    Conversation,
                    and_(
                        Conversation.tenant_id == InboxEvent.tenant_id,
                        Conversation.id == InboxEvent.conversation_id,
                    ),
                )
                .outerjoin(
                    Message,
                    and_(
                        Message.id == InboxEvent.message_id,
                        Message.tenant_id == InboxEvent.tenant_id,
                        Message.conversation_id == InboxEvent.conversation_id,
                    ),
                )
                .where(
                    InboxEvent.tenant_id == tenant_id,
                    InboxEvent.id > cursor,
                    Conversation.source == "website",
                )
                .order_by(InboxEvent.id)
                .limit(MAX_SSE_BATCH)
            ).all()
            if not found:
                yield ": keep-alive\n\n"
                time.sleep(INBOX_POLL_SECONDS)
                continue
            for event_row, message, conversation in found:
                cursor = event_row.id
                message_out = None
                if message is not None:
                    message_out = {
                        "id": str(message.id),
                        "sender_type": message.sender_type,
                        "sender_user_id": (
                            str(message.sender_user_id) if message.sender_user_id else None
                        ),
                        "text": message.text,
                        "created_at": message.created_at.isoformat(),
                    }
                data = {
                    "conversation_id": str(conversation.id),
                    "event_type": event_row.event_type,
                    "message": message_out,
                    "status": conversation.status,
                    "mode": conversation.mode,
                    "assigned_user_id": (
                        str(conversation.assigned_user_id)
                        if conversation.assigned_user_id
                        else None
                    ),
                }
                yield _sse("inbox.update", data, cursor)
            if len(found) == MAX_SSE_BATCH:
                continue
            time.sleep(INBOX_POLL_SECONDS)


def _notification_counts_for(db: OrmSession, tenant_id: UUID, user_id: UUID) -> dict[str, int]:
    waiting = int(
        db.scalar(
            select(func.count(Conversation.id)).where(
                Conversation.tenant_id == tenant_id,
                Conversation.source == "website",
                Conversation.status == "waiting_human",
            )
        )
        or 0
    )
    assigned = int(
        db.scalar(
            select(func.count(Conversation.id)).where(
                Conversation.tenant_id == tenant_id,
                Conversation.source == "website",
                Conversation.status != "resolved",
                Conversation.assigned_user_id == user_id,
            )
        )
        or 0
    )
    unread_rows = db.execute(
        select(
            Conversation.id,
            _unread_count(tenant_id, user_id, Conversation.id),
        ).where(
            Conversation.tenant_id == tenant_id,
            Conversation.source == "website",
        )
    )
    unread_messages = 0
    unread_conversations = 0
    for _, count in unread_rows:
        unread_messages += int(count or 0)
        unread_conversations += int((count or 0) > 0)
    return {
        "waiting_human": waiting,
        "assigned_to_me": assigned,
        "unread_messages": unread_messages,
        "unread_conversations": unread_conversations,
    }
