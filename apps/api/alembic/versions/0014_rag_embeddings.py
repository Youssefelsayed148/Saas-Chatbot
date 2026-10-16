"""Additive 1024-dimensional RAG foundation; no existing rows rewritten.

Revision ID: 0014_rag_embeddings
Revises: 0013_roles_operator_control
"""

import sqlalchemy as sa

from alembic import op
from app.db.models.types import VECTOR1024

revision = "0014_rag_embeddings"
down_revision = "0013_roles_operator_control"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.add_column("chunks", sa.Column("embedding", VECTOR1024(), nullable=True))
    op.add_column("chunks", sa.Column("embedding_model", sa.Text(), nullable=True))
    op.add_column("chunks", sa.Column("embedding_dim", sa.Integer(), nullable=True))
    op.create_check_constraint(
        "ck_chunks_embedding",
        "chunks",
        "(embedding IS NULL AND embedding_model IS NULL AND embedding_dim IS NULL) OR "
        "(embedding IS NOT NULL AND embedding_model IS NOT NULL AND embedding_dim = 1024)",
    )
    op.execute(
        "CREATE INDEX ix_chunks_embedding_hnsw ON chunks "
        "USING hnsw (embedding vector_cosine_ops) WHERE embedding IS NOT NULL"
    )
    for name, default in (
        ("retrieval_mode", "hybrid"),
        ("generation_provider", "openrouter"),
        ("tier", "standard"),
    ):
        op.add_column("bots", sa.Column(name, sa.Text(), nullable=False, server_default=default))
    op.add_column("bots", sa.Column("active_embedding_model", sa.Text(), nullable=True))
    op.add_column("bots", sa.Column("generation_model", sa.Text(), nullable=True))
    op.add_column(
        "bots",
        sa.Column("embedding_ready", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_check_constraint(
        "ck_bots_retrieval_mode", "bots", "retrieval_mode IN ('hybrid','fts_only')"
    )
    op.create_check_constraint(
        "ck_bots_generation_provider", "bots", "generation_provider IN ('openrouter','openai')"
    )
    op.create_check_constraint("ck_bots_tier", "bots", "tier IN ('standard','premium')")
    op.drop_constraint("ck_jobs_type", "jobs", type_="check")
    op.create_check_constraint(
        "ck_jobs_type",
        "jobs",
        "type IN ('ingest_batch','retention_purge','follow_up_delivery',"
        "'sentiment_classify','reembed_backfill')",
    )


def downgrade() -> None:
    # Refuse a rollback that would discard embedding/settings data. Empty test
    # databases can still exercise the migration cycle without destructive SQL.
    bind = op.get_bind()
    has_data = bind.execute(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM chunks WHERE embedding IS NOT NULL) "
            "OR EXISTS(SELECT 1 FROM jobs WHERE type='reembed_backfill') "
            "OR EXISTS(SELECT 1 FROM bots WHERE active_embedding_model IS NOT NULL "
            "OR generation_model IS NOT NULL OR retrieval_mode <> 'hybrid' "
            "OR generation_provider <> 'openrouter' OR tier <> 'standard')"
        )
    ).scalar_one()
    if has_data:
        raise RuntimeError(
            "Rollback would discard RAG data; owner-approved export/rollback required."
        )
    op.drop_constraint("ck_jobs_type", "jobs", type_="check")
    op.create_check_constraint(
        "ck_jobs_type",
        "jobs",
        "type IN ('ingest_batch','retention_purge','follow_up_delivery','sentiment_classify')",
    )
    for name in ("ck_bots_retrieval_mode", "ck_bots_generation_provider", "ck_bots_tier"):
        op.drop_constraint(name, "bots", type_="check")
    for name in (
        "retrieval_mode",
        "generation_provider",
        "tier",
        "active_embedding_model",
        "generation_model",
        "embedding_ready",
    ):
        op.drop_column("bots", name)
    op.drop_index("ix_chunks_embedding_hnsw", table_name="chunks")
    op.drop_constraint("ck_chunks_embedding", "chunks", type_="check")
    for name in ("embedding", "embedding_model", "embedding_dim"):
        op.drop_column("chunks", name)
    # Do not drop a shared extension: other applications may also use pgvector.
