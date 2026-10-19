"""Register the periodic channel health poll job (PLAN D10, docs/17 §5.2).

Revision ID: 0020_channel_health_poll
Revises: 0019_channel_send
"""

from alembic import op

revision = "0020_channel_health_poll"
down_revision = "0019_channel_send"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_jobs_type", "jobs", type_="check")
    op.create_check_constraint(
        "ck_jobs_type",
        "jobs",
        "type IN ('ingest_batch', "
        "'retention_purge', 'follow_up_delivery', 'sentiment_classify', "
        "'reembed_backfill', 'channel_inbound', 'channel_send', "
        "'channel_health_poll')",
    )
    # Concurrency cap (PLAN D10): one live poll job per tenant connection.
    op.execute(
        "CREATE UNIQUE INDEX uq_channel_health_poll_connection ON jobs "
        "(tenant_id, (payload->>'connection_id')) "
        "WHERE type = 'channel_health_poll' AND status IN ('pending', 'running')"
    )


def downgrade() -> None:
    # Preserve jobs; the owner must explicitly remove new-type rows before downgrade.
    op.drop_index("uq_channel_health_poll_connection", table_name="jobs")
    op.drop_constraint("ck_jobs_type", "jobs", type_="check")
    op.create_check_constraint(
        "ck_jobs_type",
        "jobs",
        "type IN ('ingest_batch', "
        "'retention_purge', 'follow_up_delivery', 'sentiment_classify', "
        "'reembed_backfill', 'channel_inbound', 'channel_send')",
    )
