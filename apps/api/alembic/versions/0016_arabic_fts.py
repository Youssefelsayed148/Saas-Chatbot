"""Index Arabic chunks with PostgreSQL's real ``arabic`` text-search configuration.

Arabic keyword search used the ``simple`` configuration (no stemming, no stop
words). PostgreSQL ships a Snowball ``arabic`` configuration; this adds a
generated ``fts_ar`` column over the already-normalised ``text_norm``
(diacritics/tatweel removed, alef and ya variants folded at ingest) and a GIN
index. Adding a stored generated column rewrites ``chunks``, which IS the
re-index of existing rows; later edits re-index automatically.

``fts_simple`` is kept so the change can be rolled back (downgrade drops only the
new column). Re-index path after any future configuration change: downgrade one
revision and upgrade again, or ``ALTER TABLE chunks ALTER COLUMN fts_ar SET
EXPRESSION AS (...)`` on PostgreSQL 17+, followed by ``REINDEX INDEX
ix_chunks_fts_ar``.

Arabic recall with this configuration is UNVERIFIED (no real-corpus evaluation).
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import TSVECTOR

from alembic import op

revision = "0016_arabic_fts"
down_revision = "0015_rag_metering"
branch_labels = None
depends_on = None


def upgrade() -> None:
    available = (
        op.get_bind()
        .execute(sa.text("SELECT EXISTS(SELECT 1 FROM pg_ts_config WHERE cfgname = 'arabic')"))
        .scalar_one()
    )
    if not available:
        raise RuntimeError(
            "This PostgreSQL has no 'arabic' text-search configuration; "
            "use PostgreSQL 15+ before applying 0016_arabic_fts."
        )
    op.add_column(
        "chunks",
        sa.Column(
            "fts_ar",
            TSVECTOR(),
            sa.Computed("to_tsvector('arabic', coalesce(text_norm, ''))", persisted=True),
            nullable=False,
        ),
    )
    op.create_index("ix_chunks_fts_ar", "chunks", ["fts_ar"], postgresql_using="gin")


def downgrade() -> None:
    op.drop_index("ix_chunks_fts_ar", table_name="chunks", postgresql_using="gin")
    op.drop_column("chunks", "fts_ar")
