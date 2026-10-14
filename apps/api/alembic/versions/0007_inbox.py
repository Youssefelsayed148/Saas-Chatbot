"""inbox read state, tags, and durable live-update cursor

Revision ID: 0007_inbox
Revises: 0006_provisioning
Create Date: 2026-10-14

P5-02: per-user read cursors, conversation tags, and tenant-scoped events for
SSE replay across independent API processes.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007_inbox"
down_revision: str | None = "0006_provisioning"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "conversation_reads",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("last_read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_read_message_id", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            ["conversations.tenant_id", "conversations.id"],
            name="fk_conversation_reads_conversation",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["memberships.tenant_id", "memberships.user_id"],
            name="fk_conversation_reads_member",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "conversation_id", "user_id"),
    )
    op.create_index(
        "ix_conversation_reads_member",
        "conversation_reads",
        ["tenant_id", "user_id", "updated_at"],
    )

    op.create_table(
        "conversation_tags",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("tag", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            ["conversations.tenant_id", "conversations.id"],
            name="fk_conversation_tags_conversation",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "conversation_id", "tag"),
    )
    op.create_index(
        "ix_conversation_tags_lookup",
        "conversation_tags",
        ["tenant_id", "tag", "conversation_id"],
    )

    op.create_table(
        "inbox_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            ["conversations.tenant_id", "conversations.id"],
            name="fk_inbox_events_conversation",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_inbox_events_tenant_cursor", "inbox_events", ["tenant_id", "id"])


def downgrade() -> None:
    op.drop_index("ix_inbox_events_tenant_cursor", table_name="inbox_events")
    op.drop_table("inbox_events")
    op.drop_index("ix_conversation_tags_lookup", table_name="conversation_tags")
    op.drop_table("conversation_tags")
    op.drop_index("ix_conversation_reads_member", table_name="conversation_reads")
    op.drop_table("conversation_reads")
