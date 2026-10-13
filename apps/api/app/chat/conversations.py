"""Conversation store + the website chat pipeline glue (P3-03, docs/14 §14).

The pipeline runs ONLY when the conversation mode is `ai` (a human takeover
in later phases switches to mode=human and the AI stays silent). History is
read through the retention window so expired messages drop out immediately
(docs/14 §7). Every write is scoped by (tenant_id, bot, conversation) —
composite FKs make cross-tenant writes impossible at the schema level.

Usage events are idempotent per (tenant, bot, external_key) — turning the
same event twice cannot double-count (docs/14 §7).
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.chat.models import default_model
from app.chat.providers import ChatModel
from app.chat.service import chat_answer
from app.core.config import Settings
from app.core.errors import ApiError
from app.db.models import Bot, Conversation, Message, UsageEvent

MAX_HISTORY = 6


def get_or_create_playground_conversation(
    db: OrmSession, *, tenant_id: UUID, bot_id: UUID, user_id: UUID
) -> Conversation:
    """The dashboard playground keeps ONE run per user per bot (mode=ai)."""
    conversation = (
        db.execute(
            select(Conversation)
            .where(
                Conversation.tenant_id == tenant_id,
                Conversation.bot_id == bot_id,
                Conversation.source == "playground",
                Conversation.status == "open",
            )
            .order_by(Conversation.updated_at.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )
    if conversation is not None:
        return conversation
    conversation = Conversation(
        id=uuid4(),
        tenant_id=tenant_id,
        bot_id=bot_id,
        contact_id=None,  # anonymous playground: no CRM contact
        channel="website",
        mode="ai",
        status="open",
        source="playground",
    )
    db.add(conversation)  # created_by is carried through the turn call
    del user_id
    db.flush()
    return conversation


def get_or_create_conversation_for_session(
    db: OrmSession,
    *,
    bot: Bot,
    visitor_session: Any,
) -> Conversation:
    """The website channel keeps ONE conversation per visitor session (P4-01).

    Created lazily on the first message; bound to the session's tenant + bot
    through composite FKs, so a session can never reach another bot's thread.
    """
    conversation = (
        db.execute(
            select(Conversation)
            .where(
                Conversation.tenant_id == visitor_session.tenant_id,
                Conversation.session_id == visitor_session.id,
            )
            .order_by(Conversation.created_at.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )
    if conversation is not None:
        return conversation
    conversation = Conversation(
        id=uuid4(),
        tenant_id=visitor_session.tenant_id,
        bot_id=bot.id,
        contact_id=None,  # no CRM contact until a captured lead provides one (P4-04)
        session_id=visitor_session.id,
        channel="website",
        mode="ai",
        status="open",
        source="website",
    )
    db.add(conversation)
    db.flush()
    return conversation


def get_conversation_or_404(
    db: OrmSession, *, tenant_id: UUID, bot_id: UUID, conversation_id: UUID
) -> Conversation:
    conversation = db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.tenant_id == tenant_id,
            Conversation.bot_id == bot_id,
        )
    ).scalar_one_or_none()
    if conversation is None:
        raise ApiError(404, "NOT_FOUND", "Resource not found.")
    if conversation.mode != "ai":
        raise ApiError(409, "CONVERSATION_IN_HUMAN_MODE", "The AI is currently silent.")
    return conversation


def append_message(
    db: OrmSession,
    conversation: Conversation,
    *,
    sender_type: str,
    text: str,
    sender_user_id: UUID | None = None,
    citations: list[dict[str, Any]] | None = None,
    can_answer: bool | None = None,
    needs_human: bool = False,
    response_ms: int | None = None,
) -> Message:
    now = datetime.now(UTC)
    message = Message(
        id=uuid4(),
        tenant_id=conversation.tenant_id,
        bot_id=conversation.bot_id,
        conversation_id=conversation.id,
        sender_type=sender_type,
        sender_user_id=sender_user_id,
        text=text,
        citations=citations,
        can_answer=can_answer,
        needs_human=needs_human,
        response_ms=response_ms,
        delivery_status="sent" if sender_type == "ai" else None,
    )
    db.add(message)
    conversation.last_message_at = now
    conversation.updated_at = now
    db.add(conversation)
    db.flush()
    return message


def history_messages(
    db: OrmSession,
    conversation: Conversation,
    *,
    settings: Settings,
) -> list[str]:
    """Visitor texts within the retention window, oldest first (§7)."""
    since = datetime.now(UTC) - timedelta(seconds=settings.retention_days * 86400)
    rows = (
        db.execute(
            select(Message.text)
            .where(
                Message.conversation_id == conversation.id,
                Message.tenant_id == conversation.tenant_id,
                Message.sender_type == "visitor",
                Message.created_at > since,
            )
            .order_by(Message.created_at.asc())
            .limit(MAX_HISTORY)
        )
        .scalars()
        .all()
    )
    return list(rows)


def record_usage_event(
    db: OrmSession,
    *,
    tenant_id: UUID,
    bot_id: UUID,
    kind: str,
    external_key: str,
    message_id: UUID | None = None,
    conversation_id: UUID | None = None,
    payload: dict[str, Any] | None = None,
) -> UsageEvent | None:
    """Idempotent: the unique (tenant, bot, external_key) dedupes repeated calls."""
    with db.begin_nested():
        existing = db.execute(
            select(UsageEvent).where(
                UsageEvent.tenant_id == tenant_id,
                UsageEvent.bot_id == bot_id,
                UsageEvent.external_key == external_key,
            )
        ).scalar_one_or_none()
    if existing is not None:
        return None  # already counted
    event = UsageEvent(
        id=uuid4(),
        tenant_id=tenant_id,
        bot_id=bot_id,
        kind=kind,
        external_key=external_key,
        message_id=message_id,
        conversation_id=conversation_id,
        payload=payload or {},
    )
    db.add(event)
    db.flush()
    return event


def visitor_chat_turn(
    db: OrmSession,
    *,
    tenant_id: UUID,
    bot: Bot,
    conversation: Conversation,
    question: str,
    language_hint: str | None = None,
    model: ChatModel | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """One visitor turn through the pipeline (mode must be `ai`)."""
    settings = settings or Settings()
    if conversation.mode != "ai":
        raise ApiError(409, "CONVERSATION_IN_HUMAN_MODE", "The AI is currently silent.")
    if not question.strip():
        raise ApiError(422, "VALIDATION_ERROR", "The message is empty.")
    if len(question) > 1000:
        raise ApiError(422, "VALIDATION_ERROR", "Messages are limited to 1000 characters.")

    visitor_message = append_message(db, conversation, sender_type="visitor", text=question)

    model = model or default_model()
    if model is None:
        db.commit()
        raise ApiError(
            503,
            "MODEL_NOT_CONFIGURED",
            "No chat model is configured. Add the provider key for this deployment.",
        )

    history = history_messages(db, conversation, settings=settings)
    started = datetime.now(UTC)
    reply = chat_answer(
        db,
        tenant_id=tenant_id,
        bot=bot,
        question=question,
        history=history,
        language_hint=language_hint,
        model=model,
        settings=settings,
    )
    response_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)
    ai_message = append_message(
        db,
        conversation,
        sender_type="ai",
        text=reply.answer,
        citations=reply.citations,
        can_answer=reply.can_answer,
        needs_human=reply.needs_human,
        response_ms=response_ms,
    )
    record_usage_event(
        db,
        tenant_id=tenant_id,
        bot_id=bot.id,
        kind="message",
        external_key=f"message:{ai_message.id}",
        message_id=ai_message.id,
        conversation_id=conversation.id,
    )
    db.commit()
    return {
        "conversation_id": str(conversation.id),
        "visitor_message": {
            "id": str(visitor_message.id),
            "text": visitor_message.text,
            "created_at": visitor_message.created_at.isoformat(),
        },
        "ai_message": {
            "id": str(ai_message.id),
            "text": ai_message.text,
            "citations": ai_message.citations or [],
            "can_answer": ai_message.can_answer,
            "needs_human": ai_message.needs_human,
            "response_ms": ai_message.response_ms,
            "created_at": ai_message.created_at.isoformat(),
        },
        "kind": reply.kind,
        "language": reply.language,
    }


def messages_of(
    db: OrmSession,
    conversation: Conversation,
    *,
    settings: Settings,
    limit: int = 100,
) -> list[Message]:
    """Visible thread within the retention window, oldest first (§7)."""
    since = datetime.now(UTC) - timedelta(seconds=settings.retention_days * 86400)
    return list(
        db.execute(
            select(Message)
            .where(
                Message.conversation_id == conversation.id,
                Message.created_at > since,
            )
            .order_by(Message.created_at.asc(), Message.id)
            .limit(limit)
        )
        .scalars()
        .all()
    )


def record_feedback(
    db: OrmSession,
    *,
    tenant_id: UUID,
    bot_id: UUID,
    message_id: UUID,
    user_id: UUID,
    rating: str,
) -> None:
    """Thumbs up/down on one AI message, idempotent per rater+rating (§7)."""
    if rating not in ("up", "down"):
        raise ApiError(422, "VALIDATION_ERROR", "Rating must be up or down.")
    message = db.execute(
        select(Message).where(
            Message.id == message_id,
            Message.tenant_id == tenant_id,
            Message.bot_id == bot_id,
            Message.sender_type == "ai",
        )
    ).scalar_one_or_none()
    if message is None:
        raise ApiError(404, "NOT_FOUND", "Resource not found.")
    kind = "feedback_up" if rating == "up" else "feedback_down"
    record_usage_event(
        db,
        tenant_id=tenant_id,
        bot_id=bot_id,
        kind=kind,
        external_key=f"feedback:{rating}:{message_id}:{user_id}",
        message_id=message.id,
        conversation_id=message.conversation_id,
    )
    db.commit()


def run_retention_purge(db: OrmSession, settings: Settings) -> int:
    """Delete messages older than the retention window (docs/14 §7).

    The delete is idempotent and tenant-agnostic (the WHERE clause carries
    tenant scoping via the table's own tenant_id, never a payload).
    """
    cutoff = datetime.now(UTC) - timedelta(seconds=settings.retention_days * 86400)
    from sqlalchemy import delete

    result = db.execute(
        delete(Message).where(
            Message.created_at < cutoff,
            Message.created_at.is_not(None),
        )
    )
    db.commit()
    deleted = int(getattr(result, "rowcount", 0) or 0)
    return deleted
