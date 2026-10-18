"""Automatic handoff rules for website conversations (docs/14 §15)."""

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.core.audit import record_audit
from app.db.models import Bot, Conversation, Message

PERSON_KEYWORDS = {
    "en": ("human", "person", "agent", "someone", "representative", "talk to a person"),
    "ar": ("إنسان", "شخص", "موظف", "ممثل", "أكلم شخص", "أريد التحدث مع شخص"),
}


@dataclass(frozen=True)
class HandoffDecision:
    reason: str
    language: str


def _contains(text: str, words: object) -> bool:
    if not isinstance(words, (list, tuple)):
        return False
    normalized = text.casefold()
    return any(
        isinstance(word, str) and word.strip() and word.casefold() in normalized for word in words
    )


def decide_handoff(
    db: OrmSession,
    *,
    bot: Bot,
    conversation: Conversation,
    question: str,
    language: str,
    reply_kind: str,
    can_answer: bool,
) -> HandoffDecision | None:
    """Return the first matching rule for website and channel conversations."""
    if conversation.source not in {"website", "channel"} or conversation.status == "waiting_human":
        return None
    config = bot.config if isinstance(bot.config, dict) else {}
    if reply_kind == "busy":
        return HandoffDecision("provider_failure", language)
    if not bool(config.get("handoff_enabled", True)):
        return None
    if reply_kind == "handoff":
        return HandoffDecision("order_account", language)
    built_in = PERSON_KEYWORDS.get(language, PERSON_KEYWORDS["en"])
    configured = config.get(f"handoff_keywords_{language}", [])
    if _contains(question, built_in) or _contains(question, configured):
        return HandoffDecision("visitor_requested", language)
    threshold = config.get("handoff_after_unanswered", 2)
    if not isinstance(threshold, int) or isinstance(threshold, bool) or not 1 <= threshold <= 3:
        threshold = 2
    if can_answer:
        return None
    recent = list(
        db.execute(
            select(Message.can_answer)
            .where(
                Message.tenant_id == conversation.tenant_id,
                Message.conversation_id == conversation.id,
                Message.sender_type == "ai",
            )
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(threshold)
        ).scalars()
    )
    if len(recent) >= threshold and all(value is False for value in recent):
        return HandoffDecision("unanswered_threshold", language)
    return None


def handoff_text(language: str) -> str:
    if language == "ar":
        return "تم تحويل هذه المحادثة إلى فريق الدعم."
    return "This conversation has been sent to our support team."


def visitor_handoff_reply(bot: Bot, language: str) -> str:
    from app.chat.prompts import canned

    config = bot.config if isinstance(bot.config, dict) else {}
    contact = (
        " / ".join(
            str(value).strip()
            for value in (config.get("support_email"), config.get("support_phone"))
            if isinstance(value, str) and value.strip()
        )
        or "our support team"
    )
    return canned("handoff", language, support_contact=contact)


def start_handoff(
    db: OrmSession,
    *,
    bot: Bot,
    conversation: Conversation,
    decision: HandoffDecision,
) -> bool:
    """Persist a handoff exactly once for a conversation waiting on an agent."""
    from app.chat.conversations import append_message, record_usage_event

    if conversation.status == "waiting_human":
        return False
    conversation.status = "waiting_human"
    conversation.handoff_reason = decision.reason
    db.add(conversation)
    append_message(
        db,
        conversation,
        sender_type="system",
        text=handoff_text(decision.language),
    )
    record_usage_event(
        db,
        tenant_id=conversation.tenant_id,
        bot_id=bot.id,
        kind="handoff",
        external_key=f"handoff:{conversation.id}",
        conversation_id=conversation.id,
    )
    record_audit(
        db,
        action="conversation.handoff",
        tenant_id=conversation.tenant_id,
        actor_user_id=None,
        target_type="conversation",
        target_id=str(conversation.id),
        metadata={"reason": decision.reason},
    )
    return True


def add_system_message(
    db: OrmSession,
    *,
    conversation: Conversation,
    text: str,
    action: str,
    actor_user_id: UUID,
    metadata: dict[str, Any] | None = None,
) -> None:
    from app.chat.conversations import append_message

    append_message(db, conversation, sender_type="system", text=text)
    record_audit(
        db,
        action=action,
        tenant_id=conversation.tenant_id,
        actor_user_id=actor_user_id,
        target_type="conversation",
        target_id=str(conversation.id),
        metadata=metadata,
    )
