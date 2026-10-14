"""Tenant-scoped inbox conversation actions (P5-01)."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.auth import cookies
from app.chat.conversations import append_message, messages_of
from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.core.tenancy import TenantContext, TenantContextDep
from app.db.models import Conversation, Membership
from app.inbox.handoff import add_system_message

router = APIRouter(prefix="/api/v1/tenants/{tenant_id}/conversations")
CsrfOk = Annotated[None, Depends(cookies.require_csrf)]
CurrentSettings = Annotated[Settings, Depends(get_settings)]


class AssignRequest(BaseModel):
    assigned_user_id: UUID | None


class AgentReplyRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


def _conversation(
    context: TenantContext, conversation_id: UUID, *, lock: bool = False
) -> Conversation:
    statement = select(Conversation).where(
        Conversation.id == conversation_id,
        Conversation.tenant_id == context.tenant_id,
        Conversation.source == "website",
    )
    if lock:
        statement = statement.with_for_update()
    row = context.db.execute(statement).scalar_one_or_none()
    if row is None:
        raise ApiError(404, "NOT_FOUND", "Resource not found.")
    return row


def _state(row: Conversation) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "bot_id": str(row.bot_id),
        "contact_id": str(row.contact_id) if row.contact_id else None,
        "channel": row.channel,
        "mode": row.mode,
        "status": row.status,
        "assigned_user_id": str(row.assigned_user_id) if row.assigned_user_id else None,
        "handoff_reason": row.handoff_reason,
        "last_message_at": row.last_message_at.isoformat() if row.last_message_at else None,
        "created_at": row.created_at.isoformat(),
    }


@router.get("/{conversation_id}")
def conversation_detail(
    conversation_id: UUID,
    context: TenantContextDep,
    settings: CurrentSettings,
) -> dict[str, Any]:
    row = _conversation(context, conversation_id)
    messages = messages_of(context.db, row, settings=settings, limit=200)
    return {
        "conversation": _state(row),
        "messages": [
            {
                "id": str(message.id),
                "sender_type": message.sender_type,
                "sender_user_id": (str(message.sender_user_id) if message.sender_user_id else None),
                "text": message.text,
                "citations": message.citations or [],
                "can_answer": message.can_answer,
                "needs_human": message.needs_human,
                "created_at": message.created_at.isoformat(),
            }
            for message in messages
        ],
    }


@router.post("/{conversation_id}/takeover")
def takeover(
    conversation_id: UUID,
    context: TenantContextDep,
    _: CsrfOk,
) -> dict[str, Any]:
    context.require_role("editor")
    row = _conversation(context, conversation_id, lock=True)
    if row.status == "resolved":
        raise ApiError(
            409, "CONVERSATION_RESOLVED", "A resolved conversation cannot be taken over."
        )
    if row.mode == "human":
        if row.assigned_user_id == context.user.id:
            return {"conversation": _state(row)}
        raise ApiError(
            409,
            "TAKEOVER_CONFLICT",
            "Another agent already took over this conversation.",
            details={"assigned_user_id": str(row.assigned_user_id or "")},
        )
    row.mode = "human"
    row.status = "open"
    row.assigned_user_id = context.user.id
    add_system_message(
        context.db,
        conversation=row,
        text="An agent took over this conversation.",
        action="conversation.taken_over",
        actor_user_id=context.user.id,
    )
    context.db.commit()
    return {"conversation": _state(row)}


@router.post("/{conversation_id}/return-to-ai")
def return_to_ai(
    conversation_id: UUID,
    context: TenantContextDep,
    _: CsrfOk,
) -> dict[str, Any]:
    context.require_role("editor")
    row = _conversation(context, conversation_id, lock=True)
    if row.status == "resolved":
        raise ApiError(
            409, "CONVERSATION_RESOLVED", "A resolved conversation cannot be returned to AI."
        )
    if row.mode == "ai":
        return {"conversation": _state(row)}
    row.mode = "ai"
    row.status = "open"
    row.assigned_user_id = None
    add_system_message(
        context.db,
        conversation=row,
        text="The assistant is handling this conversation again.",
        action="conversation.returned_to_ai",
        actor_user_id=context.user.id,
    )
    context.db.commit()
    return {"conversation": _state(row)}


@router.post("/{conversation_id}/resolve")
def resolve(
    conversation_id: UUID,
    context: TenantContextDep,
    _: CsrfOk,
) -> dict[str, Any]:
    context.require_role("editor")
    row = _conversation(context, conversation_id, lock=True)
    if row.status != "resolved":
        row.status = "resolved"
        add_system_message(
            context.db,
            conversation=row,
            text="This conversation was resolved.",
            action="conversation.resolved",
            actor_user_id=context.user.id,
        )
        context.db.commit()
    return {"conversation": _state(row)}


@router.post("/{conversation_id}/assign")
def assign(
    conversation_id: UUID,
    body: AssignRequest,
    context: TenantContextDep,
    _: CsrfOk,
) -> dict[str, Any]:
    context.require_role("editor")
    row = _conversation(context, conversation_id, lock=True)
    assigned_id = body.assigned_user_id
    if assigned_id is not None:
        membership = context.db.execute(
            select(Membership).where(
                Membership.tenant_id == context.tenant_id,
                Membership.user_id == assigned_id,
                Membership.status == "active",
            )
        ).scalar_one_or_none()
        if membership is None:
            raise ApiError(404, "NOT_FOUND", "Assignee not found.")
    if row.assigned_user_id != assigned_id:
        row.assigned_user_id = assigned_id
        add_system_message(
            context.db,
            conversation=row,
            text="Conversation assignment changed.",
            action="conversation.assigned",
            actor_user_id=context.user.id,
            metadata={"assigned_user_id": str(assigned_id) if assigned_id else None},
        )
        context.db.commit()
    return {"conversation": _state(row)}


@router.post("/{conversation_id}/messages", status_code=201)
def agent_reply(
    conversation_id: UUID,
    body: AgentReplyRequest,
    context: TenantContextDep,
    _: CsrfOk,
) -> dict[str, Any]:
    context.require_role("editor")
    row = _conversation(context, conversation_id, lock=True)
    if row.status == "resolved":
        raise ApiError(
            409, "CONVERSATION_RESOLVED", "A resolved conversation cannot receive a reply."
        )
    if row.mode != "human":
        raise ApiError(409, "TAKEOVER_REQUIRED", "Take over the conversation before replying.")
    message = append_message(
        context.db,
        row,
        sender_type="agent",
        sender_user_id=context.user.id,
        text=body.text.strip(),
    )
    context.db.commit()
    return {
        "message": {
            "id": str(message.id),
            "sender_type": message.sender_type,
            "sender_user_id": str(context.user.id),
            "text": message.text,
            "citations": [],
            "created_at": message.created_at.isoformat(),
        }
    }
