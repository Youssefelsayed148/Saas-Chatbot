"""Knowledge hygiene (H2): removable sources and cross-source duplicate bookkeeping.

``sources.status`` gains ``removed`` (a soft delete: published revisions and
rollback keep their document rows, which still reference the source row) and
``documents.duplicates_removed`` counts identical chunks dropped in favour of
(or in the presence of) another source, shown as a warning in the document list.
"""

import sqlalchemy as sa

from alembic import op

revision = "0022_knowledge_hygiene"
down_revision = "0021_revision_embedding_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_sources_status", "sources", type_="check")
    op.create_check_constraint(
        "ck_sources_status",
        "sources",
        "status IN ('stored', 'queued', 'ingested', 'failed', 'removed')",
    )
    op.add_column(
        "documents",
        sa.Column("duplicates_removed", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("documents", "duplicates_removed")
    op.execute("DELETE FROM sources WHERE status = 'removed'")
    op.drop_constraint("ck_sources_status", "sources", type_="check")
    op.create_check_constraint(
        "ck_sources_status",
        "sources",
        "status IN ('stored', 'queued', 'ingested', 'failed')",
    )
