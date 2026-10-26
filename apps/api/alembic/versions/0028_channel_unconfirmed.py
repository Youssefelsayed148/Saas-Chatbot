"""Delivery state ``unconfirmed`` and ``messages.accepted_at`` (A2, D8).

Revision ID: 0028_channel_unconfirmed
Revises: 0027_channel_ref_unique
"""

import sqlalchemy as sa

from alembic import op

revision = "0028_channel_unconfirmed"
down_revision = "0027_channel_ref_unique"
branch_labels = None
depends_on = None

OLD = (
    "delivery_status IS NULL OR delivery_status IN "
    "('pending', 'sent', 'delivered', 'read', 'failed')"
)
NEW = (
    "delivery_status IS NULL OR delivery_status IN "
    "('pending', 'unconfirmed', 'sent', 'delivered', 'read', 'failed')"
)


def upgrade() -> None:
    op.add_column("messages", sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True))
    op.drop_constraint("ck_messages_delivery_status", "messages", type_="check")
    op.create_check_constraint("ck_messages_delivery_status", "messages", NEW)
    op.create_index(
        "ix_messages_unconfirmed_sweep",
        "messages",
        ["accepted_at"],
        postgresql_where=sa.text("delivery_status = 'pending' AND accepted_at IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_messages_unconfirmed_sweep", table_name="messages")
    op.execute(
        "UPDATE messages SET delivery_status = 'pending' WHERE delivery_status = 'unconfirmed'"
    )
    op.drop_constraint("ck_messages_delivery_status", "messages", type_="check")
    op.create_check_constraint("ck_messages_delivery_status", "messages", OLD)
    op.drop_column("messages", "accepted_at")
