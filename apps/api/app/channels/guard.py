"""Per-turn guards for delegated channels: flood throttle, busy-reply cap, lock."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session as OrmSession

from app.channels import config
from app.db.models import Conversation, Message


@contextmanager
def conversation_turn_lock(db: OrmSession, connection_id: UUID, external_id: str) -> Iterator[None]:
    """Serialize all work on one channel conversation across workers.

    A PostgreSQL session advisory lock on a DEDICATED connection: ``reserve`` and
    other helpers commit the ORM session mid-turn, which would drop a row lock
    or a transaction-scoped lock. Keyed on (connection, external conversation)
    so conversation creation is serialized too. Blocks until it is free."""
    bind = db.get_bind()
    lock_connection = bind.connect()  # type: ignore[union-attr]
    key = f"channel-turn:{connection_id}:{external_id}"
    try:
        lock_connection.execute(
            text("SELECT pg_advisory_lock(hashtextextended(:key, 0))"), {"key": key}
        )
        try:
            yield
        finally:
            lock_connection.execute(
                text("SELECT pg_advisory_unlock(hashtextextended(:key, 0))"), {"key": key}
            )
    finally:
        lock_connection.close()


def inbound_rate_exceeded(
    db: OrmSession,
    conversation: Conversation,
    *,
    limit: int | None = None,
    now: datetime | None = None,
) -> bool:
    """True when this contact sent more than ``limit`` messages in the last minute
    on this connection (counted over all of the contact's conversations on it)."""
    limit = config.INBOUND_PER_MINUTE if limit is None else limit
    since = (now or datetime.now(UTC)) - timedelta(seconds=60)
    count = db.scalar(
        select(func.count(Message.id))
        .join(
            Conversation,
            (Conversation.tenant_id == Message.tenant_id)
            & (Conversation.id == Message.conversation_id),
        )
        .where(
            Message.tenant_id == conversation.tenant_id,
            Message.sender_type == "visitor",
            Message.created_at >= since,
            Conversation.connection_id == conversation.connection_id,
            Conversation.contact_id == conversation.contact_id,
        )
    )
    return int(count or 0) > limit


def busy_reply_recent(
    db: OrmSession, conversation: Conversation, busy_texts: set[str], *, now: datetime | None = None
) -> bool:
    """A busy/quota reply already went out in this conversation inside the window."""
    since = (now or datetime.now(UTC)) - timedelta(seconds=config.BUSY_REPLY_WINDOW_SECONDS)
    found = db.scalar(
        select(Message.id)
        .where(
            Message.tenant_id == conversation.tenant_id,
            Message.conversation_id == conversation.id,
            Message.sender_type == "ai",
            Message.text.in_(busy_texts),
            Message.created_at >= since,
        )
        .limit(1)
    )
    return found is not None
