"""Conversation store + the website chat pipeline glue (P3-03, docs/14 §14).

The pipeline runs ONLY when the conversation mode is `ai` (a human takeover
in later phases switches to mode=human and the AI stays silent). History is
read through the retention window so expired messages drop out immediately
(docs/14 §7). Every write is scoped by (tenant_id, bot, conversation) —
composite FKs make cross-tenant writes impossible at the schema level.

Usage events are idempotent per (tenant, bot, external_key) — turning the
same event twice cannot double-count (docs/14 §7).
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.chat import prompts
from app.chat.history import history_for_turn
from app.chat.models import default_model
from app.chat.prompts import canned
from app.chat.providers import ChatModel, ProviderError
from app.chat.service import ChatReply, _support_contact, chat_answer
from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.core.ratelimit import purge_expired_windows
from app.db.models import Bot, ChannelConnection, Conversation, Message, UsageEvent
from app.inbox.events import add_inbox_event
from app.inbox.handoff import (
    HandoffDecision,
    decide_handoff,
    start_handoff,
    visitor_handoff_reply,
)
from app.knowledge.language import detect_language
from app.quotas.ai import MeteredChatModel
from app.quotas.rag import release, reserve, settle

logger = logging.getLogger(__name__)


def playground_key(user_id: UUID) -> str:
    """Playground threads are scoped to the staff user that started them.

    Stored in ``external_conversation_id`` (``connection_id`` is a UUID foreign key
    to channel connections since migration 0023): ``assigned_user_id`` cannot hold it because that FK needs a tenant membership
    and platform staff running the playground may not have one."""
    return f"playground:{user_id}"


def get_or_create_playground_conversation(
    db: OrmSession, *, tenant_id: UUID, bot_id: UUID, user_id: UUID
) -> Conversation:
    """The dashboard playground keeps ONE open run per (bot, user) (mode=ai)."""
    conversation = (
        db.execute(
            select(Conversation)
            .where(
                Conversation.tenant_id == tenant_id,
                Conversation.bot_id == bot_id,
                Conversation.source == "playground",
                Conversation.external_conversation_id == playground_key(user_id),
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
        external_conversation_id=playground_key(user_id),
        mode="ai",
        status="open",
        source="playground",
    )
    db.add(conversation)
    db.flush()
    return conversation


def resolve_preview_revision(
    db: OrmSession, *, tenant_id: UUID, bot_id: UUID, knowledge: str
) -> UUID | None:
    """The revision the playground should answer from. "published" -> None (the
    normal pointer); "draft" -> this bot's draft revision id, or 409 when the bot
    has no draft. Scoped by tenant + bot like every knowledge query."""
    if knowledge == "published":
        return None
    from app.db.models import KnowledgeRevision

    draft_id = db.scalar(
        select(KnowledgeRevision.id).where(
            KnowledgeRevision.tenant_id == tenant_id,
            KnowledgeRevision.bot_id == bot_id,
            KnowledgeRevision.status == "draft",
        )
    )
    if draft_id is None:
        raise ApiError(409, "NO_DRAFT_REVISION", "This bot has no draft knowledge to preview.")
    return draft_id


def reset_playground_conversation(
    db: OrmSession, *, tenant_id: UUID, bot_id: UUID, user_id: UUID
) -> Conversation:
    """ "New session": close this user's open playground thread(s) and start empty."""
    now = datetime.now(UTC)
    for open_one in db.execute(
        select(Conversation).where(
            Conversation.tenant_id == tenant_id,
            Conversation.bot_id == bot_id,
            Conversation.source == "playground",
            Conversation.external_conversation_id == playground_key(user_id),
            Conversation.status == "open",
        )
    ).scalars():
        open_one.status = "resolved"
        open_one.updated_at = now
        db.add(open_one)
    db.flush()
    conversation = get_or_create_playground_conversation(
        db, tenant_id=tenant_id, bot_id=bot_id, user_id=user_id
    )
    db.commit()
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
        created_at=now,
    )
    db.add(message)
    if conversation.source in {"website", "channel"}:
        add_inbox_event(
            db,
            tenant_id=conversation.tenant_id,
            conversation_id=conversation.id,
            message_id=message.id,
            event_type="message.created",
        )
    conversation.last_message_at = now
    conversation.updated_at = now
    db.add(conversation)
    db.flush()
    return message


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


def _unavailable_turn(
    db: OrmSession,
    *,
    bot: Bot,
    conversation: Conversation,
    visitor_message: Message,
    language: str,
) -> dict[str, Any]:
    """No model is configured: the visitor gets the canned busy reply (never a 503).

    Not a billable message (no ``message`` usage event, no reservation), no
    handoff; staff see the cause in the trace (provider_error.status
    ``not_configured``)."""
    ai_message = append_message(
        db,
        conversation,
        sender_type="ai",
        text=prompts.canned("busy", language, support_contact=_support_contact(bot)),
        can_answer=False,
        needs_human=True,
    )
    record_usage_event(
        db,
        tenant_id=bot.tenant_id,
        bot_id=bot.id,
        kind="unavailable",
        external_key=f"unavailable:{ai_message.id}",
        message_id=ai_message.id,
        conversation_id=conversation.id,
        payload={
            "rag_trace": {
                "retrieval_mode": "not_run",
                "gate": "not_run",
                "rewrite_used": False,
                "model": None,
                "tokens": None,
                "cost_usd": None,
                "chunks": [],
                "channel": conversation.channel,
                "provider_error": {"status": "not_configured", "http_status": None, "model": None},
            }
        },
    )
    logger.warning("chat.model_not_configured tenant=%s bot=%s", bot.tenant_id, bot.id)
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
            "citations": [],
            "can_answer": False,
            "needs_human": True,
            "response_ms": None,
            "created_at": ai_message.created_at.isoformat(),
        },
        "kind": "busy",
        "language": language,
    }


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
    preview_revision_id: UUID | None = None,
) -> dict[str, Any]:
    """Persist a visitor turn and run the pipeline only in AI mode.

    ``preview_revision_id`` (staff playground only) answers from that DRAFT
    revision instead of the published one; any other conversation source is
    refused here, so the public widget can never reach unpublished knowledge."""
    settings = settings or get_settings()
    if preview_revision_id is not None and conversation.source != "playground":
        raise ApiError(403, "FORBIDDEN", "Draft knowledge is only available in the playground.")
    event_source = "playground" if conversation.source == "playground" else None
    if not question.strip():
        raise ApiError(422, "VALIDATION_ERROR", "The message is empty.")
    if len(question) > 1000:
        raise ApiError(422, "VALIDATION_ERROR", "Messages are limited to 1000 characters.")
    if conversation.source != "website" and conversation.mode != "ai":
        raise ApiError(409, "CONVERSATION_IN_HUMAN_MODE", "The AI is currently silent.")

    language = detect_language(question) or (
        str(bot.config.get("default_language", "en")) if isinstance(bot.config, dict) else "en"
    )
    if conversation.source == "website" and conversation.status == "resolved":
        conversation.status = "open"
        conversation.mode = "ai"
        conversation.assigned_user_id = None
        conversation.handoff_reason = None
        db.add(conversation)
        append_message(
            db,
            conversation,
            sender_type="system",
            text=(
                "تم فتح المحادثة من جديد بعد رسالة الزائر."
                if language == "ar"
                else "The conversation reopened after a new visitor message."
            ),
        )

    visitor_message = append_message(db, conversation, sender_type="visitor", text=question)

    if conversation.mode == "human":
        db.commit()
        return {
            "conversation_id": str(conversation.id),
            "visitor_message": {
                "id": str(visitor_message.id),
                "text": visitor_message.text,
                "created_at": visitor_message.created_at.isoformat(),
            },
            "ai_message": None,
            "kind": "waiting_human",
            "language": language,
        }

    model = model or default_model(bot)
    if model is None:
        if conversation.source != "website":
            db.commit()
            raise ApiError(
                503,
                "MODEL_NOT_CONFIGURED",
                "No chat model is configured. Add the provider key for this deployment.",
            )
        return _unavailable_turn(
            db,
            bot=bot,
            conversation=conversation,
            visitor_message=visitor_message,
            language=language,
        )

    history = history_for_turn(
        db, conversation, settings=settings, exclude_message_id=visitor_message.id
    )
    message_reservation = reserve(
        db,
        tenant_id,
        bot.id,
        settings,
        event_type="message",
        model=None,
        channel=conversation.channel,
        source=event_source,
    )
    model = MeteredChatModel(model, db, tenant_id, bot.id, settings, conversation.channel)
    started = datetime.now(UTC)
    try:
        reply = chat_answer(
            db,
            tenant_id=tenant_id,
            bot=bot,
            question=question,
            history=history.messages,
            history_skipped=history.skipped,
            language_hint=language_hint,
            model=model,
            settings=settings,
            preview_revision_id=preview_revision_id,
        )
    except BaseException:
        # Aborted turn: no answer was stored, so the message must not count.
        db.rollback()
        release(db, tenant_id, bot.id, message_reservation, settings)
        raise
    response_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)
    reply.trace["channel"] = conversation.channel
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
    decision = decide_handoff(
        db,
        bot=bot,
        conversation=conversation,
        question=question,
        language=reply.language,
        reply_kind=reply.kind,
        can_answer=reply.can_answer,
    )
    reply.trace["handoff_reason"] = decision.reason if decision is not None else None
    record_usage_event(
        db,
        tenant_id=tenant_id,
        bot_id=bot.id,
        kind="message",
        external_key=f"message:{ai_message.id}",
        message_id=ai_message.id,
        conversation_id=conversation.id,
        payload={
            "provider_usage": model.usage_totals,
            "rag_trace": reply.trace,
            "ai_metered": True,
            **({"source": event_source} if event_source else {}),
        },
    )
    settle(
        db, tenant_id, bot.id, message_reservation, settings, tokens=0, cost_usd=None, commit=False
    )
    if decision is not None:
        start_handoff(db, bot=bot, conversation=conversation, decision=decision)
        ai_message.text = visitor_handoff_reply(bot, reply.language)
        ai_message.citations = None
        ai_message.can_answer = False
        ai_message.needs_human = True
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


def channel_chat_turn(
    db: OrmSession,
    *,
    tenant_id: UUID,
    bot: Bot,
    conversation: Conversation,
    connection: ChannelConnection,
    visitor_message: Message,
    question: str,
    supported: bool,
    settings: Settings | None = None,
    model: ChatModel | None = None,
) -> Message | None:
    """Run a delegated-channel turn without changing the website turn contract."""
    settings = settings or get_settings()
    language = detect_language(question) or (
        str(bot.config.get("default_language", "en")) if isinstance(bot.config, dict) else "en"
    )

    if conversation.status == "resolved":
        conversation.status = "open"
        conversation.mode = "ai"
        conversation.assigned_user_id = None
        conversation.handoff_reason = None
        db.add(conversation)

    if connection.status != "active" or not connection.ai_enabled:
        conversation.status = "waiting_human"
        db.add(conversation)
        return None
    if conversation.mode == "human":
        return None
    if not supported:
        unsupported_decision = HandoffDecision("unsupported_message", language)
        if conversation.status != "waiting_human":
            start_handoff(db, bot=bot, conversation=conversation, decision=unsupported_decision)
        else:
            conversation.handoff_reason = "unsupported_message"
            db.add(conversation)
        placeholder = canned("unsupported", language)
        cutoff = datetime.now(UTC) - timedelta(hours=1)
        recent_notice = db.scalar(
            select(Message.id)
            .where(
                Message.tenant_id == tenant_id,
                Message.conversation_id == conversation.id,
                Message.sender_type == "ai",
                Message.text == placeholder,
                Message.created_at >= cutoff,
            )
            .limit(1)
        )
        if recent_notice is not None:
            return None
        notice = append_message(
            db,
            conversation,
            sender_type="ai",
            text=placeholder,
            can_answer=False,
            needs_human=True,
        )
        from app.channels.outbound import enqueue_message

        enqueue_message(db, conversation, notice, settings)
        return notice

    pipeline_question = question[:1000]
    history = history_for_turn(
        db, conversation, settings=settings, exclude_message_id=visitor_message.id
    )
    configured_model = model or default_model(bot)
    reservation: UUID | None = None
    response_ms: int | None = None
    metered_model: MeteredChatModel | None = None
    if configured_model is None:
        reply = _channel_busy_reply(bot, language)
    else:
        try:
            reservation = reserve(
                db,
                tenant_id,
                bot.id,
                settings,
                event_type="message",
                model=None,
                channel=conversation.channel,
            )
        except ApiError as exc:
            if exc.code != "QUOTA_EXCEEDED":
                raise
            reply = _channel_busy_reply(bot, language)
        else:
            metered_model = MeteredChatModel(
                configured_model, db, tenant_id, bot.id, settings, conversation.channel
            )
            started = datetime.now(UTC)
            try:
                reply = chat_answer(
                    db,
                    tenant_id=tenant_id,
                    bot=bot,
                    question=pipeline_question,
                    history=history.messages,
                    history_skipped=history.skipped,
                    language_hint=language,
                    model=metered_model,
                    settings=settings,
                )
            except ProviderError:
                release(db, tenant_id, bot.id, reservation, settings)
                reservation = None
                reply = _channel_busy_reply(bot, language)
            except ApiError as exc:
                if exc.code != "QUOTA_EXCEEDED":
                    raise
                release(db, tenant_id, bot.id, reservation, settings)
                reservation = None
                reply = _channel_busy_reply(bot, language)
            response_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)

    reply.trace["channel"] = conversation.channel
    reply.trace["connection_id"] = str(connection.id)
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
    ai_message.delivery_status = "pending"
    record_usage_event(
        db,
        tenant_id=tenant_id,
        bot_id=bot.id,
        kind="message",
        external_key=f"message:{ai_message.id}",
        message_id=ai_message.id,
        conversation_id=conversation.id,
        payload={
            "provider_usage": metered_model.usage_totals if metered_model is not None else {},
            "rag_trace": reply.trace,
            "ai_metered": reservation is not None,
        },
    )
    if reservation is not None:
        settle(
            db,
            tenant_id,
            bot.id,
            reservation,
            settings,
            tokens=0,
            cost_usd=None,
            commit=False,
        )
    decision = decide_handoff(
        db,
        bot=bot,
        conversation=conversation,
        question=pipeline_question,
        language=reply.language,
        reply_kind=reply.kind,
        can_answer=reply.can_answer,
    )
    if decision is not None:
        start_handoff(db, bot=bot, conversation=conversation, decision=decision)
        ai_message.text = visitor_handoff_reply(bot, reply.language)
        ai_message.citations = None
        ai_message.can_answer = False
        ai_message.needs_human = True
    from app.channels.outbound import enqueue_message

    enqueue_message(db, conversation, ai_message, settings)
    return ai_message


def _channel_busy_reply(bot: Bot, language: str) -> ChatReply:
    config = bot.config if isinstance(bot.config, dict) else {}
    contact = (
        " / ".join(
            str(value).strip()
            for value in (config.get("support_email"), config.get("support_phone"))
            if isinstance(value, str) and value.strip()
        )
        or "our support team"
    )
    return ChatReply(
        answer=canned("busy", language, support_contact=contact),
        can_answer=False,
        needs_human=True,
        language=language,
        kind="busy",
    )


def messages_of(
    db: OrmSession,
    conversation: Conversation,
    *,
    settings: Settings,
    limit: int = 100,
) -> list[Message]:
    """The newest ``limit`` messages within the retention window, oldest first (§7)."""
    since = datetime.now(UTC) - timedelta(seconds=settings.retention_days * 86400)
    newest = (
        db.execute(
            select(Message)
            .where(
                Message.conversation_id == conversation.id,
                Message.created_at > since,
            )
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return list(reversed(newest))


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
    """Delete messages older than each tenant's retention window (docs/14 §7).

    Per-tenant windows: `tenants.retention_days` (P4-04) overrides the
    deployment default (1–365; NULL = global). The delete is idempotent."""
    from sqlalchemy import delete as _delete
    from sqlalchemy import select

    from app.db.models import Tenant

    now = datetime.now(UTC)
    total = 0
    tenant_ids = db.execute(select(Tenant.id)).scalars().all()
    for tenant_id in tenant_ids:
        tenant = db.get(Tenant, tenant_id)
        days = (
            int(tenant.retention_days)
            if tenant is not None and tenant.retention_days is not None
            else settings.retention_days
        )
        cutoff = now - timedelta(seconds=days * 86400)
        result = db.execute(
            _delete(Message).where(
                Message.tenant_id == tenant_id,
                Message.created_at < cutoff,
                Message.created_at.is_not(None),
            )
        )
        deleted = int(getattr(result, "rowcount", 0) or 0)
        total += deleted
        purge_expired_windows(db, older_than_epoch=int(now.timestamp()) - days * 86400)
    db.commit()
    return total
