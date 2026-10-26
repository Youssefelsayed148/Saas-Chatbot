"""Add ManyOsirisChat delegated channel connections and event storage.

Existing conversation connection ids must be NULL: pre-P6 records are website
conversations and channel ids are now UUIDs referencing channel_connections.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0023_manyosiris_channels"
down_revision = "0022_knowledge_hygiene"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    non_null_connection_ids = bind.execute(
        sa.text(
            "SELECT count(*) FROM conversations WHERE connection_id IS NOT NULL "
            "AND source <> 'playground'"
        )
    ).scalar_one()
    if non_null_connection_ids:
        raise RuntimeError(
            "Cannot convert conversations.connection_id to UUID: "
            f"{non_null_connection_ids} existing non-NULL values require owner review."
        )

    op.create_table(
        "channel_connections",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("bot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("many_base_url", sa.Text(), nullable=False),
        sa.Column("many_channel_ref", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), server_default="active", nullable=False),
        sa.Column("ai_enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("secret_ciphertext", sa.Text(), nullable=False),
        sa.Column("secret_key_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("secret_rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("prev_secret_ciphertext", sa.Text(), nullable=True),
        sa.Column("prev_secret_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("health_status", sa.Text(), server_default="unknown", nullable=False),
        sa.Column("health_reason", sa.Text(), nullable=True),
        sa.Column("health_detail", sa.Text(), nullable=True),
        sa.Column("health_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "channel IN ('whatsapp', 'messenger', 'instagram')",
            name="ck_channel_connections_channel",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'paused', 'revoked')", name="ck_channel_connections_status"
        ),
        sa.CheckConstraint(
            "health_status IN ('healthy', 'degraded', 'unhealthy', 'unknown')",
            name="ck_channel_connections_health_status",
        ),
        sa.CheckConstraint("secret_key_version > 0", name="ck_channel_connections_key_version"),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_channel_connections_tenant", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "bot_id"],
            ["bots.tenant_id", "bots.id"],
            name="fk_channel_connections_tenant_bot",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name="fk_channel_connections_creator", ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_channel_connections_tenant_id", "channel_connections", ["tenant_id", "id"], unique=True
    )
    op.create_index(
        "ix_channel_connections_tenant_status",
        "channel_connections",
        ["tenant_id", "status", "created_at"],
    )

    op.create_table(
        "channel_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("connection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", sa.Text(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.Text(), server_default="received", nullable=False),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column(
            "received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('received', 'processed', 'failed', 'ignored')",
            name="ck_channel_events_status",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "connection_id"],
            ["channel_connections.tenant_id", "channel_connections.id"],
            name="fk_channel_events_connection",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_channel_events_connection_event",
        "channel_events",
        ["connection_id", "event_id"],
        unique=True,
    )
    op.create_index(
        "ix_channel_events_tenant_received", "channel_events", ["tenant_id", "received_at"]
    )

    op.add_column("conversations", sa.Column("external_conversation_id", sa.Text(), nullable=True))
    # main stores the per-user playground key ``playground:<user_id>`` in the old
    # free-text connection_id; move it to external_conversation_id before the
    # column becomes a UUID foreign key to channel_connections.
    op.execute(
        "UPDATE conversations SET external_conversation_id = connection_id, "
        "connection_id = NULL WHERE source = 'playground' AND connection_id IS NOT NULL"
    )
    op.alter_column(
        "conversations",
        "connection_id",
        existing_type=sa.Text(),
        type_=postgresql.UUID(as_uuid=True),
        postgresql_using="connection_id::uuid",
    )
    op.add_column(
        "conversations", sa.Column("origin", postgresql.JSONB(astext_type=sa.Text()), nullable=True)
    )
    op.create_foreign_key(
        "fk_conversations_connection",
        "conversations",
        "channel_connections",
        ["tenant_id", "connection_id"],
        ["tenant_id", "id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "uq_conversations_connection_external",
        "conversations",
        ["tenant_id", "connection_id", "external_conversation_id"],
        unique=True,
        postgresql_where=sa.text("connection_id IS NOT NULL"),
    )

    op.add_column(
        "contact_identities",
        sa.Column("connection_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_contact_identities_connection",
        "contact_identities",
        "channel_connections",
        ["tenant_id", "connection_id"],
        ["tenant_id", "id"],
        ondelete="CASCADE",
    )
    op.drop_index("uq_contact_identities_tenant_channel_external", table_name="contact_identities")
    op.create_index(
        "uq_contact_identities_tenant_channel_external",
        "contact_identities",
        ["tenant_id", "channel", "external_id"],
        unique=True,
        postgresql_where=sa.text("connection_id IS NULL"),
    )
    op.create_index(
        "uq_contact_identities_tenant_connection_external",
        "contact_identities",
        ["tenant_id", "connection_id", "external_id"],
        unique=True,
        postgresql_where=sa.text("connection_id IS NOT NULL"),
    )
    op.create_index(
        "uq_messages_channel_inbound_dedupe",
        "messages",
        ["tenant_id", "conversation_id", "channel_message_id"],
        unique=True,
        postgresql_where=sa.text("sender_type = 'visitor' AND channel_message_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_messages_channel_inbound_dedupe", table_name="messages")
    op.drop_index(
        "uq_contact_identities_tenant_connection_external", table_name="contact_identities"
    )
    op.drop_index("uq_contact_identities_tenant_channel_external", table_name="contact_identities")
    op.create_index(
        "uq_contact_identities_tenant_channel_external",
        "contact_identities",
        ["tenant_id", "channel", "external_id"],
        unique=True,
    )
    op.drop_constraint("fk_contact_identities_connection", "contact_identities", type_="foreignkey")
    op.drop_column("contact_identities", "connection_id")

    op.drop_index("uq_conversations_connection_external", table_name="conversations")
    op.drop_constraint("fk_conversations_connection", "conversations", type_="foreignkey")
    op.drop_column("conversations", "origin")
    op.alter_column(
        "conversations",
        "connection_id",
        existing_type=postgresql.UUID(as_uuid=True),
        type_=sa.Text(),
        postgresql_using="connection_id::text",
    )
    op.execute(
        "UPDATE conversations SET connection_id = external_conversation_id "
        "WHERE source = 'playground' AND external_conversation_id IS NOT NULL"
    )
    op.drop_column("conversations", "external_conversation_id")

    op.drop_index("ix_channel_events_tenant_received", table_name="channel_events")
    op.drop_index("uq_channel_events_connection_event", table_name="channel_events")
    op.drop_table("channel_events")
    op.drop_index("ix_channel_connections_tenant_status", table_name="channel_connections")
    op.drop_index("uq_channel_connections_tenant_id", table_name="channel_connections")
    op.drop_table("channel_connections")
