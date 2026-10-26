"""Register the durable channel send job and enforce one job per message.

Revision ID: 0025_channel_send
Revises: 0024_channel_inbound
"""

from alembic import op

revision = "0025_channel_send"
down_revision = "0024_channel_inbound"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_jobs_type", "jobs", type_="check")
    op.create_check_constraint(
        "ck_jobs_type",
        "jobs",
        "type IN ('ingest_batch', "
        "'retention_purge', 'follow_up_delivery', 'sentiment_classify', "
        "'reembed_backfill', 'channel_inbound', 'channel_send')",
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_channel_send_message ON jobs "
        "(tenant_id, (payload->>'message_id')) WHERE type = 'channel_send'"
    )


def downgrade() -> None:
    # Preserve jobs; the owner must explicitly remove new-type rows before downgrade.
    op.drop_index("uq_channel_send_message", table_name="jobs")
    op.drop_constraint("ck_jobs_type", "jobs", type_="check")
    op.create_check_constraint(
        "ck_jobs_type",
        "jobs",
        "type IN ('ingest_batch', "
        "'retention_purge', 'follow_up_delivery', 'sentiment_classify', "
        "'reembed_backfill', 'channel_inbound')",
    )
