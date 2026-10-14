"""Channel-agnostic conversation core (P3-03, docs/14 §14, ADR-015).

``contacts`` hold one person per tenant (light-CRM extension fields arrive
in P5-04); ``contact_identities`` map external channel ids onto a contact;
``conversations`` carry the cross-channel state machine (mode ai|human,
status open|waiting_human|resolved) without any Meta ownership; ``messages``
store the turns (visitor/ai/agent/system) with the AI contract fields
(``can_answer``, ``needs_human``, ``response_ms``, citations JSONB and the
delivery lifecycle for external channels); ``usage_events`` are idempotent
counters (unique external key per tenant+bot).

Every tenant-owned table is tenant-scoped with composite FKs; chat tables
must never reference a bot/conversation of another tenant (ADR-010).
"""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    Text,
)
from sqlalchemy import (
    text as sa_text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utcnow
from app.db.models.types import CITEXT

CHANNEL_VALUES = ("website", "whatsapp", "messenger", "instagram")
CONVERSATION_MODE_VALUES = ("ai", "human")
CONVERSATION_STATUS_VALUES = ("open", "waiting_human", "resolved")
SENDER_TYPE_VALUES = ("visitor", "ai", "agent", "system")
DELIVERY_STATUS_VALUES = ("pending", "sent", "delivered", "read", "failed")


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    display_name: Mapped[str] = mapped_column(Text, nullable=False, default="")
    email: Mapped[str | None] = mapped_column(CITEXT)
    phone: Mapped[str | None] = mapped_column(Text)
    # P5-04 makes stages/tags/custom fields editable tenant-level words.
    stage: Mapped[str] = mapped_column(Text, nullable=False, default="new")
    tags: Mapped[list[object]] = mapped_column(JSONB, nullable=False, default=list)
    custom_fields: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    # Consent per channel: {"whatsapp": true, ...} (doc/14 §16).
    consent: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    source_channel: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    __table_args__ = (
        CheckConstraint("email IS NOT NULL OR phone IS NOT NULL", name="ck_contacts_reachable"),
        Index(
            "uq_contacts_tenant_email",
            "tenant_id",
            "email",
            unique=True,
            postgresql_where=sa_text("email IS NOT NULL"),
        ),
        Index("uq_contacts_tenant_id_id", "tenant_id", "id", unique=True),
        Index("ix_contacts_tenant", "tenant_id", "created_at"),
    )


class ContactIdentity(Base):
    __tablename__ = "contact_identities"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(nullable=False)
    contact_id: Mapped[UUID] = mapped_column(nullable=False)
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    external_id: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    __table_args__ = (
        CheckConstraint(
            "channel IN ('website', 'whatsapp', 'messenger', 'instagram')",
            name="ck_contact_identities_channel",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "contact_id"],
            ["contacts.tenant_id", "contacts.id"],
            name="fk_contact_identities_contact",
            ondelete="CASCADE",
        ),
        Index(
            "uq_contact_identities_tenant_channel_external",
            "tenant_id",
            "channel",
            "external_id",
            unique=True,
        ),
    )


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(nullable=False)
    bot_id: Mapped[UUID] = mapped_column(nullable=False)
    contact_id: Mapped[UUID | None] = mapped_column()
    # The widget visitor session that owns this website conversation (P4-01);
    # NULL for playground (and later channels).
    session_id: Mapped[UUID | None] = mapped_column()
    # The Meta channel value is channel=s mandate (P6) — never a Meta token here.
    channel: Mapped[str] = mapped_column(Text, nullable=False, default="website")
    connection_id: Mapped[str | None] = mapped_column(Text)
    mode: Mapped[str] = mapped_column(Text, nullable=False, default="ai")
    status: Mapped[str] = mapped_column(Text, nullable=False, default="open")
    assigned_user_id: Mapped[UUID | None] = mapped_column()
    handoff_reason: Mapped[str | None] = mapped_column(Text)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # set later by the sentiment job (P5-05): never computed in the chat path.
    sentiment: Mapped[str | None] = mapped_column(Text)
    # Where the conversation came from; playground conversations are excluded
    # from operator-facing analytics/inbox in later phases.
    source: Mapped[str] = mapped_column(Text, nullable=False, default="website")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    __table_args__ = (
        CheckConstraint(
            "channel IN ('website', 'whatsapp', 'messenger', 'instagram')",
            name="ck_conversations_channel",
        ),
        CheckConstraint("mode IN ('ai', 'human')", name="ck_conversations_mode"),
        CheckConstraint(
            "status IN ('open', 'waiting_human', 'resolved')",
            name="ck_conversations_status",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "bot_id"],
            ["bots.tenant_id", "bots.id"],
            name="fk_conversations_tenant_bot",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "contact_id"],
            ["contacts.tenant_id", "contacts.id"],
            name="fk_conversations_contact",
            ondelete="SET NULL",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "session_id"],
            ["visitor_sessions.tenant_id", "visitor_sessions.id"],
            name="fk_conversations_session",
            ondelete="SET NULL",
        ),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_conversations_tenant_anchor",
            ondelete="CASCADE",
        ),
        # assigned_user_id may point at a user of any tenant? — the assigned
        # user must be a member of THIS tenant; composite anchor:
        ForeignKeyConstraint(
            ["tenant_id", "assigned_user_id"],
            ["memberships.tenant_id", "memberships.user_id"],
            name="fk_conversations_assigned_member",
            ondelete="SET NULL",
        ),
        Index("uq_conversations_tenant_id_id", "tenant_id", "id", unique=True),
        Index(
            "uq_conversations_tenant_bot_id",
            "tenant_id",
            "bot_id",
            "id",
            unique=True,
        ),
        Index("ix_conversations_bot_active", "tenant_id", "bot_id", "status"),
        Index("ix_conversations_last_message", "tenant_id", "last_message_at"),
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(nullable=False)
    bot_id: Mapped[UUID] = mapped_column(nullable=False)
    conversation_id: Mapped[UUID] = mapped_column(nullable=False)
    sender_type: Mapped[str] = mapped_column(Text, nullable=False)
    sender_user_id: Mapped[UUID | None] = mapped_column()  # agents only
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # AI turns only: validated citations [{"chunk_id","title","heading",
    # "source_url","page_ref"}] produced by the chat service contract.
    citations: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    can_answer: Mapped[bool | None] = mapped_column(Boolean)
    needs_human: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=sa_text("false")
    )
    response_ms: Mapped[int | None] = mapped_column(Integer)
    # Meta channel delivery (P6); website turns use sent or NULL.
    channel_message_id: Mapped[str | None] = mapped_column(Text)
    delivery_status: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    __table_args__ = (
        CheckConstraint(
            "sender_type IN ('visitor', 'ai', 'agent', 'system')",
            name="ck_messages_sender_type",
        ),
        CheckConstraint(
            "delivery_status IS NULL OR delivery_status IN "
            "('pending', 'sent', 'delivered', 'read', 'failed')",
            name="ck_messages_delivery_status",
        ),
        CheckConstraint("response_ms IS NULL OR response_ms >= 0", name="ck_messages_response_ms"),
        ForeignKeyConstraint(
            ["tenant_id", "bot_id", "conversation_id"],
            [
                "conversations.tenant_id",
                "conversations.bot_id",
                "conversations.id",
            ],
            name="fk_messages_conversation",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "bot_id"],
            ["bots.tenant_id", "bots.id"],
            name="fk_messages_tenant_bot",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "sender_user_id"],
            ["memberships.tenant_id", "memberships.user_id"],
            name="fk_messages_sender_member",
            ondelete="SET NULL",
        ),
        Index("ix_messages_conversation_created", "conversation_id", "created_at"),
        # Retention purge scans by tenant + created_at.
        Index("ix_messages_tenant_created", "tenant_id", "created_at"),
    )


class ConversationRead(Base):
    """Per-member read cursor for inbox unread counts (P5-02)."""

    __tablename__ = "conversation_reads"

    tenant_id: Mapped[UUID] = mapped_column(primary_key=True)
    conversation_id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(primary_key=True)
    last_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_read_message_id: Mapped[UUID | None] = mapped_column()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            ["conversations.tenant_id", "conversations.id"],
            name="fk_conversation_reads_conversation",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["memberships.tenant_id", "memberships.user_id"],
            name="fk_conversation_reads_member",
            ondelete="CASCADE",
        ),
        Index("ix_conversation_reads_member", "tenant_id", "user_id", "updated_at"),
    )


class ConversationTag(Base):
    """Tenant-owned conversation tag (P5-02 filter; editing is shared with P5-03)."""

    __tablename__ = "conversation_tags"

    tenant_id: Mapped[UUID] = mapped_column(primary_key=True)
    conversation_id: Mapped[UUID] = mapped_column(primary_key=True)
    tag: Mapped[str] = mapped_column(Text, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            ["conversations.tenant_id", "conversations.id"],
            name="fk_conversation_tags_conversation",
            ondelete="CASCADE",
        ),
        Index("ix_conversation_tags_lookup", "tenant_id", "tag", "conversation_id"),
    )


class InboxEvent(Base):
    """Durable, tenant-scoped cursor for cross-process SSE (P5-02)."""

    __tablename__ = "inbox_events"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(nullable=False)
    conversation_id: Mapped[UUID] = mapped_column(nullable=False)
    message_id: Mapped[UUID | None] = mapped_column()
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            ["conversations.tenant_id", "conversations.id"],
            name="fk_inbox_events_conversation",
            ondelete="CASCADE",
        ),
        Index("ix_inbox_events_tenant_cursor", "tenant_id", "id"),
    )


class UsageEvent(Base):
    """Idempotent analytics counters (docs/14 §9/§7). One external key per row."""

    __tablename__ = "usage_events"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(nullable=False)
    bot_id: Mapped[UUID] = mapped_column(nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    message_id: Mapped[UUID | None] = mapped_column()
    conversation_id: Mapped[UUID | None] = mapped_column()
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    # Idempotency: caller-supplied, e.g. f"message:{message_id}" or
    # f"feedback:up:{message_id}:{user_id}".
    external_key: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    __table_args__ = (
        CheckConstraint(
            "kind IN ('message', 'widget_open', 'lead', 'feedback_up', 'feedback_down', 'handoff')",
            name="ck_usage_events_kind",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "bot_id"],
            ["bots.tenant_id", "bots.id"],
            name="fk_usage_events_tenant_bot",
            ondelete="CASCADE",
        ),
        Index(
            "uq_usage_events_bot_key",
            "tenant_id",
            "bot_id",
            "external_key",
            unique=True,
        ),
        Index("ix_usage_events_bot_kind", "tenant_id", "bot_id", "kind", "created_at"),
    )


__all__ = [
    "Contact",
    "ContactIdentity",
    "Conversation",
    "ConversationRead",
    "ConversationTag",
    "InboxEvent",
    "Message",
    "UsageEvent",
]
