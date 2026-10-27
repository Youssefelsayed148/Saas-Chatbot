"""placeholder quota usage events and sentiment queue

Revision ID: 0012_quota_jobs
Revises: 0011_quota_overrides
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0012_quota_jobs"
down_revision: str | None = "0011_quota_overrides"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_jobs_type", "jobs", type_="check")
    op.create_check_constraint(
        "ck_jobs_type",
        "jobs",
        "type IN ('ingest_batch', 'retention_purge', 'follow_up_delivery', 'sentiment_classify')",
    )
    op.drop_constraint("ck_usage_events_kind", "usage_events", type_="check")
    op.create_check_constraint(
        "ck_usage_events_kind",
        "usage_events",
        "kind IN ('message', 'widget_open', 'lead', 'feedback_up', 'feedback_down', 'handoff', 'sentiment_run')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_usage_events_kind", "usage_events", type_="check")
    op.create_check_constraint(
        "ck_usage_events_kind",
        "usage_events",
        "kind IN ('message', 'widget_open', 'lead', 'feedback_up', 'feedback_down', 'handoff')",
    )
    op.drop_constraint("ck_jobs_type", "jobs", type_="check")
    op.create_check_constraint(
        "ck_jobs_type",
        "jobs",
        "type IN ('ingest_batch', 'retention_purge', 'follow_up_delivery')",
    )
