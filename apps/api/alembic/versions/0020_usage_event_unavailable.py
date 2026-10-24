"""A usage event kind for turns the assistant could not take (no model configured).

It is deliberately not ``message``: those events are the billable/quota count.
"""

import sqlalchemy as sa

from alembic import op

revision = "0020_usage_event_unavailable"
down_revision = "0019_bot_tone_and_rules"
branch_labels = None
depends_on = None
OLD_KINDS = (
    "kind IN ('message', 'widget_open', 'lead', 'feedback_up', 'feedback_down', "
    "'handoff', 'sentiment_run') OR kind = 'ai_usage'"
)


def upgrade() -> None:
    op.drop_constraint("ck_usage_events_kind", "usage_events", type_="check")
    op.create_check_constraint(
        "ck_usage_events_kind", "usage_events", OLD_KINDS + " OR kind = 'unavailable'"
    )


def downgrade() -> None:
    op.get_bind().execute(sa.text("DELETE FROM usage_events WHERE kind = 'unavailable'"))
    op.drop_constraint("ck_usage_events_kind", "usage_events", type_="check")
    op.create_check_constraint("ck_usage_events_kind", "usage_events", OLD_KINDS)
