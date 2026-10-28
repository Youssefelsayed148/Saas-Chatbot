"""A16 transactional erasure and serialization with inbound/outbound channel work."""

import hashlib
import json
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, func, or_, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.audit import record_audit
from app.db.models import (
    ChannelConnection,
    ChannelEvent,
    Contact,
    ContactIdentity,
    Conversation,
    FollowUp,
    Job,
    Message,
    UsageEvent,
)
from app.db.models.channels import ChannelErasureFence


def identity_digest(tenant_id: UUID, connection_id: UUID, external_id: str) -> str:
    """Keep no raw identity in the fence; domain-separate and scope the digest.

    This is a pseudonymous replay-prevention record, not anonymous analytics.
    It remains tenant-owned and cascades with its connection/tenant.
    """
    data = json.dumps(
        ["manyosiris-contact-erasure-v1", str(tenant_id), str(connection_id), external_id],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


@contextmanager
def channel_work_lock(
    db: Session, tenant_id: UUID, identities: Sequence[tuple[UUID, str]]
) -> Iterator[None]:
    """Session locks survive commits inside AI turns; sorted acquisition avoids deadlocks.

    All channel inbound/send work takes this lock before touching its recipient.
    Erasure takes every connection of an explicitly merged contact before purging.
    """
    bind = db.get_bind()
    connection = bind.connect()  # type: ignore[union-attr]
    keys = sorted(
        {
            f"channel-work:{identity_digest(tenant_id, connection_id, external_id)}"
            for connection_id, external_id in identities
        }
    )
    acquired: list[str] = []
    try:
        for key in keys:
            connection.execute(
                text("SELECT pg_advisory_lock(hashtextextended(:key, 0))"), {"key": key}
            )
            acquired.append(key)
        yield
    finally:
        for key in reversed(acquired):
            connection.execute(
                text("SELECT pg_advisory_unlock(hashtextextended(:key, 0))"), {"key": key}
            )
        connection.close()


def event_is_erased(db: Session, event: ChannelEvent) -> bool:
    payload = event.payload or {}
    external_id = payload.get("external_contact_id")
    if not isinstance(external_id, str):
        return False
    fence = db.scalar(
        select(ChannelErasureFence).where(
            ChannelErasureFence.tenant_id == event.tenant_id,
            ChannelErasureFence.connection_id == event.connection_id,
            ChannelErasureFence.identity_digest
            == identity_digest(event.tenant_id, event.connection_id, external_id),
        )
    )
    if fence is None:
        return False
    occurred = datetime.fromisoformat(str(payload["occurred_at"]).replace("Z", "+00:00"))
    return event.received_at <= fence.received_through or occurred <= fence.occurred_through


def conversation_recipient(db: Session, conversation: Conversation) -> str | None:
    """Resolve a recipient without guessing after several CRM identities merge.

    New conversations retain their original external identity. Legacy rows
    can use one uniquely recorded processed inbound identity, or their sole
    current identity when no historical association remains. Ambiguity fails
    closed; contact/connection membership alone cannot choose between people.
    """
    identities = select(ContactIdentity.external_id).where(
        ContactIdentity.tenant_id == conversation.tenant_id,
        ContactIdentity.connection_id == conversation.connection_id,
        ContactIdentity.contact_id == conversation.contact_id,
    )
    if conversation.external_contact_id is not None:
        return db.scalar(
            identities.where(ContactIdentity.external_id == conversation.external_contact_id)
        )
    historical = list(
        db.scalars(
            select(ChannelEvent.payload["external_contact_id"].as_string())
            .where(
                ChannelEvent.tenant_id == conversation.tenant_id,
                ChannelEvent.connection_id == conversation.connection_id,
                ChannelEvent.event_type == "message.received",
                ChannelEvent.status == "processed",
                ChannelEvent.payload["external_conversation_id"].as_string()
                == conversation.external_conversation_id,
                ChannelEvent.payload["external_contact_id"].as_string().is_not(None),
            )
            .distinct()
            .limit(2)
        )
    )
    if len(historical) == 1:
        return db.scalar(identities.where(ContactIdentity.external_id == historical[0]))
    if historical:
        return None
    current = list(db.scalars(identities.order_by(ContactIdentity.id).limit(2)))
    return current[0] if len(current) == 1 else None


def _linked_identities(
    db: Session, connection: ChannelConnection, external_id: str
) -> tuple[UUID | None, list[tuple[UUID, str]]]:
    contact_id = db.scalar(
        select(ContactIdentity.contact_id).where(
            ContactIdentity.tenant_id == connection.tenant_id,
            ContactIdentity.connection_id == connection.id,
            ContactIdentity.external_id == external_id,
        )
    )
    if contact_id is None:
        return None, [(connection.id, external_id)]
    rows = db.execute(
        select(ContactIdentity.connection_id, ContactIdentity.external_id).where(
            ContactIdentity.tenant_id == connection.tenant_id,
            ContactIdentity.contact_id == contact_id,
            ContactIdentity.connection_id.is_not(None),
        )
    )
    return contact_id, [(UUID(str(conn)), str(ext)) for conn, ext in rows]


def erase_channel_contact(db: Session, event: ChannelEvent, job_id: UUID) -> None:
    """Erase atomically, retain opaque dedupe, and fence delayed pre-erasure input.

    The connection's tenant is the sole authority. A missing identity still
    purges queued payloads and installs the fence (idempotent erasure).
    """
    connection = db.scalar(
        select(ChannelConnection).where(
            ChannelConnection.tenant_id == event.tenant_id,
            ChannelConnection.id == event.connection_id,
        )
    )
    assert connection is not None and event.payload is not None
    external_id = str(event.payload["external_contact_id"])
    _contact_id, identities = _linked_identities(db, connection, external_id)
    with channel_work_lock(db, event.tenant_id, identities):
        # Another erasure may have finished while this job waited on its lock.
        db.refresh(event)
        if event.payload is None or event.status in {"processed", "ignored"}:
            return
        locked_identities = set(identities)
        contact_id, identities = _linked_identities(db, connection, external_id)
        if not set(identities).issubset(locked_identities):
            raise RuntimeError("Contact identity set changed during erasure.")
        now = datetime.now(UTC)
        # Server processing time fences delayed work even when the erasure
        # request itself spent time queued before acceptance/processing.
        occurred = now
        tenant_id = connection.tenant_id
        # The contact row prevents concurrent staff merge/delete from rewriting it.
        if contact_id is not None:
            locked_contact = db.scalar(
                select(Contact)
                .where(Contact.tenant_id == tenant_id, Contact.id == contact_id)
                .with_for_update()
            )
            if locked_contact is None:
                raise RuntimeError("Contact changed while erasure acquired its row lock.")
        final_contact_id, final_identities = _linked_identities(db, connection, external_id)
        if final_contact_id != contact_id or set(final_identities) != set(identities):
            # Staff merge does not use the channel lock. Re-resolve after the
            # contact row lock, with scalar columns (not a stale identity-map
            # object), before writing any fence, purge or completion audit.
            raise RuntimeError("Contact identity mapping changed during erasure.")
        conversations = (
            list(
                db.scalars(
                    select(Conversation).where(
                        Conversation.tenant_id == tenant_id, Conversation.contact_id == contact_id
                    )
                )
            )
            if contact_id is not None
            else []
        )
        conversation_ids = [row.id for row in conversations]
        messages = (
            list(
                db.scalars(
                    select(Message).where(
                        Message.tenant_id == tenant_id,
                        Message.conversation_id.in_(conversation_ids),
                    )
                )
            )
            if conversation_ids
            else []
        )
        message_ids = [row.id for row in messages]
        follow_up_ids = (
            list(
                db.scalars(
                    select(FollowUp.id).where(
                        FollowUp.tenant_id == tenant_id,
                        FollowUp.conversation_id.in_(conversation_ids),
                    )
                )
            )
            if conversation_ids
            else []
        )
        matches = [ChannelEvent.id == event.id]
        for conn_id, ext_id in identities:
            matches.append(
                (ChannelEvent.connection_id == conn_id)
                & (ChannelEvent.payload["external_contact_id"].as_string() == ext_id)
            )
            external_conversations = [
                row.external_conversation_id
                for row in conversations
                if row.connection_id == conn_id and row.external_conversation_id
            ]
            if external_conversations:
                matches.append(
                    (ChannelEvent.connection_id == conn_id)
                    & ChannelEvent.payload["external_conversation_id"]
                    .as_string()
                    .in_(external_conversations)
                )
            digest = identity_digest(tenant_id, conn_id, ext_id)
            statement = insert(ChannelErasureFence).values(
                tenant_id=tenant_id,
                connection_id=conn_id,
                identity_digest=digest,
                occurred_through=occurred,
                received_through=now,
            )
            db.execute(
                statement.on_conflict_do_update(
                    index_elements=["tenant_id", "connection_id", "identity_digest"],
                    set_={
                        "occurred_through": func.greatest(
                            ChannelErasureFence.occurred_through, occurred
                        ),
                        "received_through": func.greatest(
                            ChannelErasureFence.received_through, now
                        ),
                    },
                )
            )
        if message_ids:
            matches.append(
                ChannelEvent.connection_id.in_([item[0] for item in identities])
                & ChannelEvent.payload["message_id"].as_string().in_([str(x) for x in message_ids])
            )
            provider_ids = [row.channel_message_id for row in messages if row.channel_message_id]
            if provider_ids:
                linked_connections = [item[0] for item in identities]
                matches.append(
                    ChannelEvent.connection_id.in_(linked_connections)
                    & ChannelEvent.payload["external_message_id"].as_string().in_(provider_ids)
                )
        events = list(
            db.scalars(
                select(ChannelEvent).where(ChannelEvent.tenant_id == tenant_id, or_(*matches))
            )
        )
        event_ids = [str(row.id) for row in events]
        job_matches = [Job.payload["channel_event_id"].as_string().in_(event_ids)]
        for key, ids in (
            ("conversation_id", conversation_ids),
            ("message_id", message_ids),
            ("follow_up_id", follow_up_ids),
        ):
            if ids:
                job_matches.append(Job.payload[key].as_string().in_([str(x) for x in ids]))
        jobs = list(
            db.scalars(
                select(Job).where(Job.tenant_id == tenant_id, Job.id != job_id, or_(*job_matches))
            )
        )
        for pending in jobs:
            pending.payload = {}
            pending.error = None
            if pending.status in {"pending", "running"}:
                pending.cancel_requested = True
                pending.status = "cancelled"
                pending.finished_at = now
                pending.lease_expires_at = None
                pending.leased_by = None
        for stored in events:
            stored.payload = None
            if stored.id != event.id and stored.status not in {"processed", "ignored"}:
                stored.status = "ignored"
                stored.error_code = "contact_erased"
                stored.processed_at = now
        if conversation_ids:
            accounting = db.scalars(
                select(UsageEvent).where(
                    UsageEvent.tenant_id == tenant_id,
                    or_(
                        UsageEvent.conversation_id.in_(conversation_ids),
                        UsageEvent.message_id.in_(message_ids),
                    ),
                )
            )
            for usage in accounting:
                # Erasure must not refund consumed quotas or retain rag_trace
                # (which can contain the customer's query/rewrite). Keep only
                # measured counters and the flags used by quota accounting.
                previous = usage.payload or {}
                clean: dict[str, object] = {}
                if isinstance(previous.get("ai_metered"), bool):
                    clean["ai_metered"] = previous["ai_metered"]
                source = previous.get("source")
                if isinstance(source, str) and source in {"playground", "channel", "website"}:
                    clean["source"] = source
                provider = previous.get("provider_usage")
                if isinstance(provider, dict):
                    clean["provider_usage"] = {
                        key: value
                        for key, value in provider.items()
                        if key in {"prompt_tokens", "completion_tokens", "total_tokens"}
                        and isinstance(value, int)
                        and not isinstance(value, bool)
                    }
                usage.payload = clean
                usage.message_id = None
                usage.conversation_id = None
                usage.external_key = f"erased:{usage.id}"
            # Cascades delete messages, followups, read cursors, tags and inbox events.
            db.execute(
                delete(Conversation).where(
                    Conversation.tenant_id == tenant_id, Conversation.id.in_(conversation_ids)
                )
            )
        if contact_id is not None:
            db.execute(
                delete(Contact).where(Contact.tenant_id == tenant_id, Contact.id == contact_id)
            )
        event.status = "processed"
        event.processed_at = now
        event.error_code = None
        record_audit(
            db,
            action="contact.erasure",
            tenant_id=tenant_id,
            actor_user_id=None,
            target_type="contact_erasure",
            metadata={
                "contacts_erased": int(contact_id is not None),
                "conversations_erased": len(conversation_ids),
                "messages_erased": len(message_ids),
                "payloads_purged": len(events),
                "jobs_cancelled": len(jobs),
            },
        )
        # Commit before releasing the session locks; no stale worker may recreate content.
        db.commit()
