"""``channel_events.payload`` becomes nullable so retention can purge it (B3).

Revision ID: 0029_channel_event_payload_purge
Revises: 0028_channel_unconfirmed
"""

from alembic import op

revision = "0029_channel_event_payload_purge"
down_revision = "0028_channel_unconfirmed"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("channel_events", "payload", nullable=True)


def downgrade() -> None:
    op.execute("UPDATE channel_events SET payload = '{}'::jsonb WHERE payload IS NULL")
    op.alter_column("channel_events", "payload", nullable=False)
