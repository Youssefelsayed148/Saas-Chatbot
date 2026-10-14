"""Transactional write helper for the tenant-scoped inbox event cursor."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import InboxEvent


def add_inbox_event(
    db: Session,
    *,
    tenant_id: UUID,
    conversation_id: UUID,
    event_type: str,
    message_id: UUID | None = None,
) -> InboxEvent:
    """Add an event under a tenant transaction lock so cursor IDs commit in order.

    PostgreSQL sequences allocate IDs before transaction commit. The per-tenant
    transaction advisory lock makes event insertion and commit order match, so
    an API process cannot advance a Last-Event-ID past another uncommitted row.
    """
    lock_key = int.from_bytes(tenant_id.bytes[:8], byteorder="big", signed=True)
    db.execute(select(func.pg_advisory_xact_lock(lock_key)))
    event = InboxEvent(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        message_id=message_id,
        event_type=event_type,
        created_at=datetime.now(UTC),
    )
    db.add(event)
    return event
