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
from app.db.models import ChannelConnection, Conversation, Membership, UsageEvent
from app.inbox.handoff import add_system_message

router = APIRouter(prefix="/api/v1/tenants/{tenant_id}/conversations")
CsrfOk = Annotated[None, Depends(cookies.require_csrf)]
CurrentSettings = Annotated[Settings, Depends(get_settings)]


class AssignRequest(BaseModel):
    assigned_user_id: UUID | None


class AgentReplyRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class InternalNoteRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


def _conversation(
    context: TenantContext, conversation_id: UUID, *, lock: bool = False
) -> Conversation:
    statement = select(Conversation).where(
        Conversation.id == conversation_id,
        Conversation.tenant_id == context.tenant_id,
        Conversation.source.in_(("website", "channel")),
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
    message_ids = [message.id for message in messages]
    feedback_by_message: dict[UUID, list[str]] = {}
    if message_ids:
        feedback_rows = context.db.execute(
            select(UsageEvent.message_id, UsageEvent.kind).where(
                UsageEvent.tenant_id == context.tenant_id,
                UsageEvent.conversation_id == row.id,
                UsageEvent.message_id.in_(message_ids),
                UsageEvent.kind.in_(("feedback_up", "feedback_down")),
            )
        )
        for message_id, kind in feedback_rows:
            if message_id is not None:
                feedback_by_message.setdefault(message_id, []).append(
                    "up" if kind == "feedback_up" else "down"
                )
    state = _state(row)
    if row.source == "channel":
        connection = context.db.scalar(
            select(ChannelConnection).where(
                ChannelConnection.tenant_id == context.tenant_id,
                ChannelConnection.id == row.connection_id,
            )
        )
        state["connection_status"] = connection.status if connection else "revoked"
        origin = row.origin
        if isinstance(origin, dict):
            campaign_name = origin.get("campaign_name")
            if isinstance(campaign_name, str) and campaign_name.strip():
                state["campaign_name"] = campaign_name.strip()[:120]
    return {
        "conversation": state,
        "messages": [
            {
                "id": str(message.id),
                "sender_type": message.sender_type,
                "sender_user_id": (str(message.sender_user_id) if message.sender_user_id else None),
                "text": message.text,
                "citations": (message.citations or []) if context.user.is_platform_staff else [],
                "can_answer": message.can_answer,
                "needs_human": message.needs_human,
                "feedback": feedback_by_message.get(message.id, []),
                "created_at": message.created_at.isoformat(),
                **(
                    {"delivery_status": message.delivery_status, "error_code": message.error_code}
                    if row.source == "channel" and message.sender_type in {"ai", "agent"}
                    else {}
                ),
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
    settings: CurrentSettings,
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
        from app.quotas.sentiment import enqueue_for_resolved_conversation

        enqueue_for_resolved_conversation(context.db, conversation=row, settings=settings)
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
    settings: CurrentSettings,
) -> dict[str, Any]:
    context.require_role("editor")
    row = _conversation(context, conversation_id, lock=True)
    if row.source == "channel":
        connection = context.db.scalar(
            select(ChannelConnection)
            .where(
                ChannelConnection.tenant_id == context.tenant_id,
                ChannelConnection.id == row.connection_id,
            )
            .with_for_update()
        )
        if connection is None or connection.status != "active":
            raise ApiError(
                409,
                "CONNECTION_PAUSED",
                "This channel connection is paused or revoked. Replies are disabled.",
            )
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
    if row.source == "channel":
        from app.channels.outbound import enqueue_message

        enqueue_message(context.db, row, message, settings)
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


@router.post("/{conversation_id}/notes", status_code=201)
def add_internal_note(
    conversation_id: UUID,
    body: InternalNoteRequest,
    context: TenantContextDep,
    _: CsrfOk,
) -> dict[str, str]:
    """Persist an audited operator-only note in the system event stream."""
    context.require_role("editor")
    row = _conversation(context, conversation_id, lock=True)
    text = body.text.strip()
    if not text:
        raise ApiError(422, "VALIDATION_ERROR", "Note cannot be empty.")
    add_system_message(
        context.db,
        conversation=row,
        text=f"Internal note: {text}",
        action="conversation.note_added",
        actor_user_id=context.user.id,
    )
    context.db.commit()
    return {"status": "created"}
