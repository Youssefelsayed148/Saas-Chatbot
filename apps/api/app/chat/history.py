"""Conversation history for the model prompt (shared by buffered and streamed turns).

History carries the conversation only, never facts: an exchange is a visitor
message plus the AI reply to it, and the assistant turn is the reply text alone
(no sources, no trace). The Evidence block stays current-turn only.

Exchanges whose AI reply was a refusal or a failure (can_answer false,
needs_human true: cannot_confirm, busy, invalid_output, handoff) are skipped, as is a visitor
message with no AI reply. So are conversational exchanges (a greeting, thanks, "who are
you"): the router answered them from bot settings, they carry no facts and would only
use up a history slot. Replies from human agents are never assistant turns.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TypedDict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.chat.routing import is_conversational
from app.core.config import Settings
from app.db.models import Conversation, Message

# Most recent visitor/ai rows examined while looking for usable exchanges.
SCAN_LIMIT = 60


class HistoryMessage(TypedDict):
    role: str  # "user" | "assistant"
    content: str


@dataclass
class History:
    messages: list[HistoryMessage] = field(default_factory=list)
    exchanges: int = 0
    skipped: int = 0


def normalize_history(history: "list[str] | list[HistoryMessage] | None") -> list[HistoryMessage]:
    """Bare strings (older callers, eval scripts) are visitor turns."""
    turns: list[HistoryMessage] = []
    for item in history or []:
        turn: HistoryMessage = (
            {"role": "user", "content": item} if isinstance(item, str) else dict(item)  # type: ignore[assignment]
        )
        if turn["content"].strip():
            turns.append(turn)
    return turns


def visitor_texts(history: list[HistoryMessage]) -> list[str]:
    return [turn["content"] for turn in history if turn["role"] == "user"]


def _window_start(settings: Settings) -> datetime:
    days = settings.chat_history_window_days or settings.retention_days
    return datetime.now(UTC) - timedelta(days=min(days, settings.retention_days))


def history_for_turn(
    db: OrmSession,
    conversation: Conversation,
    *,
    settings: Settings,
    exclude_message_id: UUID | None = None,
) -> History:
    """The last ``chat_history_exchanges`` usable exchanges, oldest first."""
    wanted = settings.chat_history_exchanges
    if wanted <= 0:
        return History()
    rows = list(
        db.execute(
            select(Message)
            .where(
                Message.conversation_id == conversation.id,
                Message.tenant_id == conversation.tenant_id,
                Message.bot_id == conversation.bot_id,
                Message.id != exclude_message_id,
                Message.sender_type.in_(("visitor", "ai")),
                Message.created_at > _window_start(settings),
            )
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(SCAN_LIMIT)
        )
        .scalars()
        .all()
    )
    rows.reverse()
    exchanges: list[tuple[Message, Message | None]] = []
    for row in rows:
        if row.sender_type == "visitor":
            exchanges.append((row, None))
        elif exchanges and exchanges[-1][1] is None:
            exchanges[-1] = (exchanges[-1][0], row)
    usable: list[tuple[Message, Message]] = []
    skipped = 0
    for visitor, reply in reversed(exchanges):
        if len(usable) >= wanted:
            break
        if (
            reply is None
            or reply.can_answer is not True
            or reply.needs_human
            or not reply.text.strip()
            or is_conversational(visitor.text)
        ):
            skipped += 1
            continue
        usable.append((visitor, reply))
    usable.reverse()
    messages: list[HistoryMessage] = []
    for visitor, reply in usable:
        messages.append({"role": "user", "content": visitor.text})
        messages.append({"role": "assistant", "content": reply.text})
    return History(messages=messages, exchanges=len(usable), skipped=skipped)
