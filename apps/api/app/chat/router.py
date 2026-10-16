"""Playground + feedback endpoints (P3-03/04): the dashboard chat surface
over the same pipeline the public widget will use (P4-01)."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from app.auth import cookies
from app.chat.conversations import (
    get_or_create_playground_conversation,
    messages_of,
    record_feedback,
    visitor_chat_turn,
)
from app.core.config import Settings, get_settings
from app.core.tenancy import TenantContextDep

router = APIRouter(prefix="/api/v1/tenants/{tenant_id}/bots/{bot_id}")

CsrfOk = Annotated[None, Depends(cookies.require_csrf)]


class PlaygroundTurnRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1000)


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    sender_type: str
    text: str
    citations: list[dict[str, Any]] | None = None
    can_answer: bool | None = None
    needs_human: bool = False
    response_ms: int | None = None
    created_at: str


class PlaygroundTurnResponse(BaseModel):
    conversation_id: str
    mode: str
    status: str
    visitor_message: dict[str, Any]
    ai_message: dict[str, Any]
    kind: str
    language: str


class PlaygroundConversationResponse(BaseModel):
    conversation_id: str
    message_count: int
    messages: list[MessageOut]


class FeedbackRequest(BaseModel):
    rating: str = Field(pattern="^(up|down)$")


@router.post("/playground/messages", response_model=PlaygroundTurnResponse, status_code=201)
def playground_turn(
    tenant_id: UUID,
    bot_id: UUID,
    body: PlaygroundTurnRequest,
    context: TenantContextDep,
    _: CsrfOk,
    settings: Annotated[Settings, Depends(get_settings)],
) -> PlaygroundTurnResponse:
    """One dashboard playground turn (editor+: it runs the pipeline)."""
    context.require_operator()
    from app.chat.models import model_from_settings
    from app.knowledge.service import get_bot as get_bot_scoped

    bot = get_bot_scoped(context, bot_id)
    model = model_from_settings(settings)
    if model is None:
        from app.core.errors import ApiError

        raise ApiError(
            503, "MODEL_NOT_CONFIGURED", "No chat model is configured for this deployment."
        )
    conversation = get_or_create_playground_conversation(
        context.db, tenant_id=context.tenant_id, bot_id=bot_id, user_id=context.user.id
    )
    result = visitor_chat_turn(
        context.db,
        tenant_id=context.tenant_id,
        bot=bot,
        conversation=conversation,
        question=body.text,
        model=model,
        settings=settings,
    )
    return PlaygroundTurnResponse(
        conversation_id=str(result["conversation_id"]),
        mode="ai",
        status="open",
        visitor_message=result["visitor_message"],
        ai_message=result["ai_message"],
        kind=result["kind"],
        language=result["language"],
    )


@router.get("/playground/conversation", response_model=PlaygroundConversationResponse)
def playground_conversation(
    tenant_id: UUID,
    bot_id: UUID,
    context: TenantContextDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> PlaygroundConversationResponse:
    from app.knowledge.service import get_bot as get_bot_scoped

    get_bot_scoped(context, bot_id)  # tenant scope (hidden bot → 404)
    conversation = get_or_create_playground_conversation(
        context.db,
        tenant_id=context.tenant_id,
        bot_id=bot_id,
        user_id=context.user.id,
    )
    rows = messages_of(context.db, conversation, settings=settings)
    return PlaygroundConversationResponse(
        conversation_id=str(conversation.id),
        message_count=len(rows),
        messages=[
            MessageOut(
                id=str(message.id),
                sender_type=message.sender_type,
                text=message.text,
                citations=message.citations,
                can_answer=message.can_answer,
                needs_human=message.needs_human,
                response_ms=message.response_ms,
                created_at=message.created_at.isoformat(),
            )
            for message in rows
        ],
    )


@router.post("/messages/{message_id}/feedback", status_code=200)
def message_feedback(
    tenant_id: UUID,
    bot_id: UUID,
    message_id: UUID,
    body: FeedbackRequest,
    context: TenantContextDep,
    _: CsrfOk,
) -> dict[str, object]:
    """Thumbs up/down on one AI message; idempotent per rater+rating (§7)."""
    context.require_operator()
    record_feedback(
        context.db,
        tenant_id=context.tenant_id,
        bot_id=bot_id,
        message_id=message_id,
        user_id=context.user.id,
        rating=body.rating,
    )
    return {"status": "ok"}
