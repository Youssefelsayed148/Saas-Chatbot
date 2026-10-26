"""Allow channel contacts without website contact fields and inbound jobs."""

from alembic import op

revision = "0024_channel_inbound"
down_revision = "0023_manyosiris_channels"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_jobs_type", "jobs", type_="check")
    op.create_check_constraint(
        "ck_jobs_type",
        "jobs",
        "type IN ('ingest_batch', 'retention_purge', 'follow_up_delivery', "
        "'sentiment_classify', 'reembed_backfill', 'channel_inbound')",
    )
    op.drop_constraint("ck_contacts_reachable", "contacts", type_="check")
    op.create_check_constraint(
        "ck_contacts_reachable",
        "contacts",
        "email IS NOT NULL OR phone IS NOT NULL OR source_channel IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_constraint("ck_contacts_reachable", "contacts", type_="check")
    op.create_check_constraint(
        "ck_contacts_reachable", "contacts", "email IS NOT NULL OR phone IS NOT NULL"
    )
    op.drop_constraint("ck_jobs_type", "jobs", type_="check")
    op.create_check_constraint(
        "ck_jobs_type",
        "jobs",
        "type IN ('ingest_batch', 'retention_purge', 'follow_up_delivery', 'sentiment_classify') "
        "OR type = 'reembed_backfill'",
    )
