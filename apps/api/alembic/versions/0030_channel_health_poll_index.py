"""Index the last-poll lookup used by the channel health scheduler.

Revision ID: 0030_channel_health_poll_index
Revises: 0029_channel_event_payload_purge
"""

from alembic import op

revision = "0030_channel_health_poll_index"
down_revision = "0029_channel_event_payload_purge"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Serves ``max(created_at)`` per connection (schedule_health_polls ordering); the
    # unique live-job index from 0026 only covers pending/running rows.
    op.execute(
        "CREATE INDEX ix_jobs_channel_health_poll_last ON jobs "
        "(tenant_id, (payload->>'connection_id'), created_at) "
        "WHERE type = 'channel_health_poll'"
    )


def downgrade() -> None:
    op.drop_index("ix_jobs_channel_health_poll_last", table_name="jobs")
