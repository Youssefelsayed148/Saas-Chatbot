"""Conversations read view (P4-04, docs/10 Conversations tab, docs/14 §14).

Read-only history with citations for the dashboard (viewer included). The
thread view mirrors the widget retention window (docs/14 §7). Playground
conversations (source='playground') are excluded from operator-facing lists.
Deletion is an editor+ explicit action (retention/GDPR-style erasure).
"""

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import delete, func, select

from app.auth import cookies
from app.chat.conversations import messages_of
from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.core.tenancy import TenantContextDep
from app.db.models import Contact, Conversation, Message
from app.knowledge.service import get_bot

router = APIRouter(prefix="/api/v1/tenants/{tenant_id}/bots/{bot_id}")

CsrfOk = Annotated[None, Depends(cookies.require_csrf)]


class ConversationSummary(BaseModel):
    id: str
    channel: str
    mode: str
    status: str
    contact_name: str | None = None
    last_message_at: datetime | None = None
    message_count: int = 0
    created_at: datetime


class ConversationListResponse(BaseModel):
    conversations: list[ConversationSummary]
    total: int


class ConversationDetailResponse(BaseModel):
    conversation: ConversationSummary
    messages: list[dict[str, Any]]


def get_conversation_scoped(
    context: TenantContextDep, bot_id: UUID, conversation_id: UUID
) -> Conversation:
    conversation = (
        context.db.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.tenant_id == context.tenant_id,
                Conversation.bot_id == bot_id,
                Conversation.source != "playground",
            )
        )
        .scalars()
        .one_or_none()
    )
    if conversation is None:
        raise ApiError(404, "NOT_FOUND", "Resource not found.")
    return conversation


def _summary(db: Any, conversation: Conversation) -> Any:
    from app.db.models import Message

    message_count = db.execute(
        select(func.count()).select_from(Message).where(Message.conversation_id == conversation.id)
    ).scalar_one()
    contact_name: str | None = None
    if conversation.contact_id is not None:
        contact = db.get(Contact, conversation.contact_id)
        if contact is not None:
            contact_name = contact.display_name or str(contact.email or contact.phone or "")
    return ConversationSummary(
        id=str(conversation.id),
        channel=conversation.channel,
        mode=conversation.mode,
        status=conversation.status,
        contact_name=contact_name,
        last_message_at=conversation.last_message_at,
        message_count=int(message_count),
        created_at=conversation.created_at,
    )


@router.get("/conversations", response_model=ConversationListResponse)
def list_conversations(
    bot_id: UUID,
    context: TenantContextDep,
    status: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> ConversationListResponse:
    """Read-only conversation list for this bot; hidden ids are 404 via the bot scoping."""
    get_bot(context, bot_id)
    query = (
        select(Conversation)
        .where(
            Conversation.tenant_id == context.tenant_id,
            Conversation.bot_id == bot_id,
            Conversation.source != "playground",
        )
        .order_by(Conversation.last_message_at.desc().nullslast())
        .limit(limit)
    )
    if status in ("open", "waiting_human", "resolved"):
        query = query.where(Conversation.status == status)
    rows = list(context.db.execute(query).scalars())
    total = context.db.execute(
        select(func.count())
        .select_from(Conversation)
        .where(
            Conversation.tenant_id == context.tenant_id,
            Conversation.bot_id == bot_id,
            Conversation.source != "playground",
        )
    ).scalar_one()
    return ConversationListResponse(
        conversations=[_summary(context.db, row) for row in rows],
        total=int(total),
    )


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailResponse)
def conversation_detail(
    bot_id: UUID,
    conversation_id: UUID,
    context: TenantContextDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> ConversationDetailResponse:
    """Thread with citations (title + source URL), within the retention window."""
    get_bot(context, bot_id)
    conversation = get_conversation_scoped(context, bot_id, conversation_id)
    rows = messages_of(
        context.db,
        conversation,
        settings=settings,
        limit=200,
    )
    return ConversationDetailResponse(
        conversation=_summary(context.db, conversation),
        messages=[
            {
                "id": str(message.id),
                "sender_type": message.sender_type,
                "text": message.text,
                "citations": (message.citations or []) if context.user.is_platform_staff else [],
                "can_answer": message.can_answer,
                "needs_human": message.needs_human,
                "created_at": message.created_at.isoformat(),
            }
            for message in rows
            if isinstance(message, Message)
        ],
    )


@router.delete("/conversations/{conversation_id}", status_code=200)
def delete_conversation(
    bot_id: UUID,
    conversation_id: UUID,
    context: TenantContextDep,
    _: CsrfOk,
) -> dict[str, str]:
    """Explicit deletion of one conversation and its messages (retention era
    evidence; GDPR-style erasure before P5's contact flows exist)."""
    context.require_role("admin")
    get_bot(context, bot_id)
    conversation = get_conversation_scoped(context, bot_id, conversation_id)
    context.db.execute(delete(Message).where(Message.conversation_id == conversation.id))
    context.db.delete(conversation)
    context.db.commit()
    return {"status": "deleted"}
