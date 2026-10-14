"""website follow-up scheduling and queue type

Revision ID: 0009_follow_ups
Revises: 0008_contacts
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009_follow_ups"
down_revision: str | None = "0008_contacts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_jobs_type", "jobs", type_="check")
    op.create_check_constraint(
        "ck_jobs_type",
        "jobs",
        "type IN ('ingest_batch', 'retention_purge', 'follow_up_delivery')",
    )
    op.create_table(
        "follow_ups",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("bot_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("contact_id", sa.Uuid(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("send_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('scheduled', 'ready', 'delivered', 'cancelled')",
            name="ck_follow_ups_status",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "bot_id", "conversation_id"],
            ["conversations.tenant_id", "conversations.bot_id", "conversations.id"],
            name="fk_follow_ups_conversation",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "contact_id"],
            ["contacts.tenant_id", "contacts.id"],
            name="fk_follow_ups_contact",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name="fk_follow_ups_creator", ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_follow_ups_due", "follow_ups", ["status", "send_at"])
    op.create_index("ix_follow_ups_tenant_bot", "follow_ups", ["tenant_id", "bot_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_follow_ups_tenant_bot", table_name="follow_ups")
    op.drop_index("ix_follow_ups_due", table_name="follow_ups")
    op.drop_table("follow_ups")
    op.drop_constraint("ck_jobs_type", "jobs", type_="check")
    op.create_check_constraint(
        "ck_jobs_type", "jobs", "type IN ('ingest_batch', 'retention_purge')"
    )
