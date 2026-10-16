"""Add optional bot caps and AI ledger events without rewriting existing rows."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0015_rag_metering"
down_revision = "0014_rag_embeddings"
branch_labels = None
depends_on = None
OLD_KINDS = (
    "kind IN ('message','widget_open','lead','feedback_up',"
    "'feedback_down','handoff','sentiment_run')"
)


def upgrade() -> None:
    op.add_column("bots", sa.Column("rag_limits", JSONB(), nullable=True))
    op.drop_constraint("ck_usage_events_kind", "usage_events", type_="check")
    op.create_check_constraint(
        "ck_usage_events_kind", "usage_events", OLD_KINDS + " OR kind='ai_usage'"
    )


def downgrade() -> None:
    populated = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT EXISTS(SELECT 1 FROM bots WHERE rag_limits IS NOT NULL) "
                "OR EXISTS(SELECT 1 FROM usage_events WHERE kind='ai_usage')"
            )
        )
        .scalar_one()
    )
    if populated:
        raise RuntimeError("Downgrade refused: RAG limits or metering data would be discarded.")
    op.drop_constraint("ck_usage_events_kind", "usage_events", type_="check")
    op.create_check_constraint("ck_usage_events_kind", "usage_events", OLD_KINDS)
    op.drop_column("bots", "rag_limits")
