"""Durable pseudonymous cutoffs for A16 contact erasure.

Revision ID: 0031_contact_erasure
Revises: 0030_channel_health_poll_index
"""

import sqlalchemy as sa

from alembic import op

revision = "0031_contact_erasure"
down_revision = "0030_channel_health_poll_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Legacy recipients are intentionally not guessed during migration.
    op.add_column("conversations", sa.Column("external_contact_id", sa.Text(), nullable=True))
    op.create_table(
        "channel_erasure_fences",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column("identity_digest", sa.Text(), nullable=False),
        sa.Column("occurred_through", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_through", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("tenant_id", "connection_id", "identity_digest"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "connection_id"],
            ["channel_connections.tenant_id", "channel_connections.id"],
            name="fk_channel_erasure_fences_connection",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("length(identity_digest) = 64", name="ck_channel_erasure_digest"),
    )


def downgrade() -> None:
    op.drop_table("channel_erasure_fences")
    op.drop_column("conversations", "external_contact_id")
