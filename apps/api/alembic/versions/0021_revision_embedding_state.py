"""Per-revision embedding completeness (H1).

``knowledge_revisions.embedding_model`` is set only while every chunk of that
revision carries that embedding identity, so the live published revision keeps
hybrid retrieval while a draft is still being embedded.
"""

import sqlalchemy as sa

from alembic import op

revision = "0021_revision_embedding_state"
down_revision = "0020_usage_event_unavailable"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("knowledge_revisions", sa.Column("embedding_model", sa.Text(), nullable=True))
    # Carry the old per-bot flag onto the revisions it was true for: the bot's
    # active model applies to a revision only if all of its chunks carry it.
    op.execute(
        """
        UPDATE knowledge_revisions r SET embedding_model = b.active_embedding_model
        FROM bots b
        WHERE b.tenant_id = r.tenant_id AND b.id = r.bot_id
          AND b.embedding_ready AND b.active_embedding_model IS NOT NULL
          AND r.status IN ('draft', 'published')
          AND NOT EXISTS (
            SELECT 1 FROM chunks c
            WHERE c.tenant_id = r.tenant_id AND c.revision_id = r.id
              AND (c.embedding IS NULL OR c.embedding_model IS DISTINCT FROM b.active_embedding_model)
          )
        """
    )


def downgrade() -> None:
    op.drop_column("knowledge_revisions", "embedding_model")
