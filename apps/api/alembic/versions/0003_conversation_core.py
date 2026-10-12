"""conversation core: contacts, contact_identities, conversations, messages, usage_events

Revision ID: 0003_conversation_core
Revises: 0002_knowledge
Create Date: 2026-10-12

P3-03 (docs/14 §14, ADR-015): the channel-agnostic conversation core.
All tables tenant-scoped; children use composite FKs against their parents
(ADR-010). usage_events dedupe per (tenant, bot, external_key). The jobs
type check widens to include the retention_purge job.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.db.models.types import CITEXT

revision: str = "0003_conversation_core"
down_revision: str | None = "0002_knowledge"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "contacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("email", CITEXT(), nullable=True),
        sa.Column("phone", sa.Text(), nullable=True),
        sa.Column("stage", sa.Text(), nullable=False),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("custom_fields", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("consent", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_channel", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("email IS NOT NULL OR phone IS NOT NULL", name="ck_contacts_reachable"),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_contacts_tenant", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_contacts_tenant_email",
        "contacts",
        ["tenant_id", "email"],
        unique=True,
        postgresql_where=sa.text("email IS NOT NULL"),
    )
    # Anchor for child composite FKs (contact_identities, conversations).
    op.create_index("uq_contacts_tenant_id_id", "contacts", ["tenant_id", "id"], unique=True)
    op.create_index("ix_contacts_tenant", "contacts", ["tenant_id", "created_at"])

    op.create_table(
        "contact_identities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("contact_id", sa.Uuid(), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "channel IN ('website', 'whatsapp', 'messenger', 'instagram')",
            name="ck_contact_identities_channel",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "contact_id"],
            ["contacts.tenant_id", "contacts.id"],
            name="fk_contact_identities_contact",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_contact_identities_tenant_channel_external",
        "contact_identities",
        ["tenant_id", "channel", "external_id"],
        unique=True,
    )

    op.create_table(
        "conversations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("bot_id", sa.Uuid(), nullable=False),
        sa.Column("contact_id", sa.Uuid(), nullable=True),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("connection_id", sa.Text(), nullable=True),
        sa.Column("mode", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("assigned_user_id", sa.Uuid(), nullable=True),
        sa.Column("handoff_reason", sa.Text(), nullable=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sentiment", sa.Text(), nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "channel IN ('website', 'whatsapp', 'messenger', 'instagram')",
            name="ck_conversations_channel",
        ),
        sa.CheckConstraint("mode IN ('ai', 'human')", name="ck_conversations_mode"),
        sa.CheckConstraint(
            "status IN ('open', 'waiting_human', 'resolved')",
            name="ck_conversations_status",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_conversations_tenant_anchor",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "assigned_user_id"],
            ["memberships.tenant_id", "memberships.user_id"],
            name="fk_conversations_assigned_member",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "bot_id"],
            ["bots.tenant_id", "bots.id"],
            name="fk_conversations_tenant_bot",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "contact_id"],
            ["contacts.tenant_id", "contacts.id"],
            name="fk_conversations_contact",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_conversations_bot_active", "conversations", ["tenant_id", "bot_id", "status"]
    )
    # Anchor for the messages composite FK.
    op.create_index(
        "uq_conversations_tenant_bot_id",
        "conversations",
        ["tenant_id", "bot_id", "id"],
        unique=True,
    )
    op.create_index(
        "ix_conversations_last_message", "conversations", ["tenant_id", "last_message_at"]
    )
    op.create_index(
        "uq_conversations_tenant_id_id", "conversations", ["tenant_id", "id"], unique=True
    )

    op.create_table(
        "messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("bot_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("sender_type", sa.Text(), nullable=False),
        sa.Column("sender_user_id", sa.Uuid(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("citations", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("can_answer", sa.Boolean(), nullable=True),
        sa.Column("needs_human", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("response_ms", sa.Integer(), nullable=True),
        sa.Column("channel_message_id", sa.Text(), nullable=True),
        sa.Column("delivery_status", sa.Text(), nullable=True),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "delivery_status IS NULL OR delivery_status IN "
            "('pending', 'sent', 'delivered', 'read', 'failed')",
            name="ck_messages_delivery_status",
        ),
        sa.CheckConstraint(
            "sender_type IN ('visitor', 'ai', 'agent', 'system')",
            name="ck_messages_sender_type",
        ),
        sa.CheckConstraint(
            "response_ms IS NULL OR response_ms >= 0", name="ck_messages_response_ms"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "bot_id", "conversation_id"],
            ["conversations.tenant_id", "conversations.bot_id", "conversations.id"],
            name="fk_messages_conversation",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "bot_id"],
            ["bots.tenant_id", "bots.id"],
            name="fk_messages_tenant_bot",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "sender_user_id"],
            ["memberships.tenant_id", "memberships.user_id"],
            name="fk_messages_sender_member",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_messages_conversation_created",
        "messages",
        ["conversation_id", "created_at"],
    )
    op.create_index("ix_messages_tenant_created", "messages", ["tenant_id", "created_at"])

    op.create_table(
        "usage_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("bot_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=True),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("external_key", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "kind IN ('message', 'widget_open', 'lead', 'feedback_up', 'feedback_down', 'handoff')",
            name="ck_usage_events_kind",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "bot_id"],
            ["bots.tenant_id", "bots.id"],
            name="fk_usage_events_tenant_bot",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_usage_events_bot_kind",
        "usage_events",
        ["tenant_id", "bot_id", "kind", "created_at"],
    )
    op.create_index(
        "uq_usage_events_bot_key",
        "usage_events",
        ["tenant_id", "bot_id", "external_key"],
        unique=True,
    )

    # jobs.type widens: the retention purge job runs like any other job.
    op.execute("ALTER TABLE jobs DROP CONSTRAINT ck_jobs_type")
    op.create_check_constraint(
        "ck_jobs_type", "jobs", "type IN ('ingest_batch', 'retention_purge')"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE jobs DROP CONSTRAINT ck_jobs_type")
    op.create_check_constraint("ck_jobs_type", "jobs", "type IN ('ingest_batch')")
    op.drop_index("uq_usage_events_bot_key", table_name="usage_events")
    op.drop_index("ix_usage_events_bot_kind", table_name="usage_events")
    op.drop_table("usage_events")
    op.drop_index("ix_messages_tenant_created", table_name="messages")
    op.drop_index("ix_messages_conversation_created", table_name="messages")
    op.drop_table("messages")
    op.drop_index("uq_conversations_tenant_id_id", table_name="conversations")
    op.drop_index("ix_conversations_last_message", table_name="conversations")
    op.drop_index("uq_conversations_tenant_bot_id", table_name="conversations")
    op.drop_index("ix_conversations_bot_active", table_name="conversations")
    op.drop_table("conversations")
    op.drop_index("uq_contact_identities_tenant_channel_external", table_name="contact_identities")
    op.drop_table("contact_identities")
    op.drop_index("ix_contacts_tenant", table_name="contacts")
    op.drop_index("uq_contacts_tenant_id_id", table_name="contacts")
    op.drop_index(
        "uq_contacts_tenant_email",
        table_name="contacts",
        postgresql_where=sa.text("email IS NOT NULL"),
    )
    op.drop_table("contacts")
