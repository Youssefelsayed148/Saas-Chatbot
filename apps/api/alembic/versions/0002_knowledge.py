"""knowledge schema: sources, source_pages, documents, knowledge_revisions,
chunks, jobs; bots.published_revision_id

Revision ID: 0002_knowledge
Revises: 0001_initial
Create Date: 2026-10-12

P2-01 (docs/08, docs/14 §3–§5, ADR-005/010/011):
- sources → source_pages → documents → chunks inside knowledge_revisions
  snapshots; jobs is the durable DB queue (composite FK (tenant_id, bot_id)
  to bots, payloads hold ids only).
- chunks carries the generated, GIN-indexed tsvector columns fts_en /
  fts_simple. There is NO vector column and NO pgvector extension (ADR-005).

Table creation order: knowledge_revisions first (chunks and the
bots.published_revision_id FK depend on it), then jobs/sources, their children,
and finally the bots column.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.db.models.types import TSVECTOR

revision: str = "0002_knowledge"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "knowledge_revisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("bot_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('draft', 'published', 'archived')",
            name="ck_knowledge_revisions_status",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_knowledge_revisions_created_by",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "bot_id"],
            ["bots.tenant_id", "bots.id"],
            name="fk_knowledge_revisions_tenant_bot",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_knowledge_revisions_bot_status",
        "knowledge_revisions",
        ["tenant_id", "bot_id", "status"],
    )
    # At most one draft and one published revision per bot, enforced by the DB
    # (the publish pointer swap relies on these).
    op.create_index(
        "uq_knowledge_revisions_draft",
        "knowledge_revisions",
        ["tenant_id", "bot_id"],
        unique=True,
        postgresql_where=sa.text("status = 'draft'"),
    )
    op.create_index(
        "uq_knowledge_revisions_published",
        "knowledge_revisions",
        ["tenant_id", "bot_id"],
        unique=True,
        postgresql_where=sa.text("status = 'published'"),
    )
    # Anchors for child composite FKs (chunks revision FK).
    op.create_index(
        "uq_knowledge_revisions_tenant_bot_id",
        "knowledge_revisions",
        ["tenant_id", "bot_id", "id"],
        unique=True,
    )
    op.create_index(
        "uq_knowledge_revisions_tenant_id_id",
        "knowledge_revisions",
        ["tenant_id", "id"],
        unique=True,
    )

    op.create_table(
        "jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("bot_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default=sa.text("3"), nullable=False),
        sa.Column("run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("leased_by", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "cancel_requested", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed', 'cancelled')",
            name="ck_jobs_status",
        ),
        sa.CheckConstraint("type IN ('ingest_batch')", name="ck_jobs_type"),
        sa.CheckConstraint("attempts >= 0 AND max_attempts >= 1", name="ck_jobs_attempts"),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name="fk_jobs_created_by", ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "bot_id"],
            ["bots.tenant_id", "bots.id"],
            name="fk_jobs_tenant_bot",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_jobs_claim", "jobs", ["status", "run_at"])
    op.create_index("ix_jobs_tenant_bot", "jobs", ["tenant_id", "bot_id"])
    op.create_index("ix_jobs_tenant_bot_created", "jobs", ["tenant_id", "bot_id", "created_at"])

    op.create_table(
        "sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("bot_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("original_name", sa.Text(), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("row_errors", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("valid_rows", sa.Integer(), nullable=True),
        sa.Column("total_rows", sa.Integer(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "kind IN ('pdf', 'docx', 'txt', 'md', 'qa_csv')", name="ck_sources_kind"
        ),
        sa.CheckConstraint(
            "status IN ('stored', 'queued', 'ingested', 'failed')", name="ck_sources_status"
        ),
        sa.CheckConstraint("size_bytes >= 0", name="ck_sources_size"),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name="fk_sources_created_by", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "bot_id"],
            ["bots.tenant_id", "bots.id"],
            name="fk_sources_tenant_bot",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key", name="uq_sources_storage_key"),
    )
    op.create_index(
        "ix_sources_tenant_bot_created", "sources", ["tenant_id", "bot_id", "created_at"]
    )
    op.create_index(
        "uq_sources_tenant_bot_id", "sources", ["tenant_id", "bot_id", "id"], unique=True
    )
    op.create_index("uq_sources_tenant_id_id", "sources", ["tenant_id", "id"], unique=True)

    op.create_table(
        "source_pages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("bot_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("page_type", sa.Text(), nullable=True),
        sa.Column("language", sa.Text(), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("language IN ('en', 'ar')", name="ck_source_pages_language"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "bot_id", "source_id"],
            ["sources.tenant_id", "sources.bot_id", "sources.id"],
            name="fk_source_pages_source",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_source_pages_tenant_bot_source", "source_pages", ["tenant_id", "bot_id", "source_id"]
    )
    op.create_index(
        "uq_source_pages_tenant_bot_id", "source_pages", ["tenant_id", "bot_id", "id"], unique=True
    )
    op.create_index(
        "uq_source_pages_tenant_id_id", "source_pages", ["tenant_id", "id"], unique=True
    )

    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("bot_id", sa.Uuid(), nullable=False),
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("heading", sa.Text(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("page_ref", sa.Text(), nullable=False),
        sa.Column("ordinal", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("language", sa.Text(), nullable=False),
        sa.Column("priority", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("total_chars", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("language IN ('en', 'ar')", name="ck_documents_language"),
        sa.CheckConstraint("priority >= 0 AND priority <= 10", name="ck_documents_priority"),
        sa.CheckConstraint("total_chars >= 0", name="ck_documents_total_chars"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "bot_id", "revision_id"],
            [
                "knowledge_revisions.tenant_id",
                "knowledge_revisions.bot_id",
                "knowledge_revisions.id",
            ],
            name="fk_documents_revision",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "bot_id", "source_id"],
            ["sources.tenant_id", "sources.bot_id", "sources.id"],
            name="fk_documents_source",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_documents_tenant_bot_source", "documents", ["tenant_id", "bot_id", "source_id"]
    )
    op.create_index(
        "ix_documents_tenant_bot_revision", "documents", ["tenant_id", "bot_id", "revision_id"]
    )
    op.create_index(
        "uq_documents_tenant_bot_revision_id",
        "documents",
        ["tenant_id", "bot_id", "revision_id", "id"],
        unique=True,
    )
    op.create_index(
        "uq_documents_tenant_bot_id", "documents", ["tenant_id", "bot_id", "id"], unique=True
    )
    op.create_index("uq_documents_tenant_id_id", "documents", ["tenant_id", "id"], unique=True)

    op.create_table(
        "chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("bot_id", sa.Uuid(), nullable=False),
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("heading", sa.Text(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("text_norm", sa.Text(), nullable=False),
        sa.Column("language", sa.Text(), nullable=False),
        sa.Column("priority", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("ordinal", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "fts_en",
            TSVECTOR(),
            sa.Computed(
                "to_tsvector('english', coalesce(title, '') || ' ' || "
                "coalesce(heading, '') || ' ' || \"text\")",
                persisted=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "fts_simple",
            TSVECTOR(),
            sa.Computed("to_tsvector('simple', coalesce(text_norm, ''))", persisted=True),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("language IN ('en', 'ar')", name="ck_chunks_language"),
        sa.CheckConstraint("priority >= 0 AND priority <= 10", name="ck_chunks_priority"),
        sa.CheckConstraint("ordinal >= 0", name="ck_chunks_ordinal"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "bot_id"],
            ["bots.tenant_id", "bots.id"],
            name="fk_chunks_tenant_bot",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "bot_id", "revision_id"],
            [
                "knowledge_revisions.tenant_id",
                "knowledge_revisions.bot_id",
                "knowledge_revisions.id",
            ],
            name="fk_chunks_revision",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "bot_id", "source_id"],
            ["sources.tenant_id", "sources.bot_id", "sources.id"],
            name="fk_chunks_source",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "bot_id", "revision_id", "document_id"],
            ["documents.tenant_id", "documents.bot_id", "documents.revision_id", "documents.id"],
            name="fk_chunks_document",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    # Identical normalised chunk text is stored once per source in a revision.
    op.create_index(
        "uq_chunks_revision_source_hash",
        "chunks",
        ["revision_id", "source_id", "content_hash"],
        unique=True,
    )
    op.create_index(
        "ix_chunks_tenant_bot_revision", "chunks", ["tenant_id", "bot_id", "revision_id"]
    )
    op.create_index("uq_chunks_tenant_id_id", "chunks", ["tenant_id", "id"], unique=True)
    op.create_index("ix_chunks_fts_en", "chunks", ["fts_en"], postgresql_using="gin")
    op.create_index("ix_chunks_fts_simple", "chunks", ["fts_simple"], postgresql_using="gin")

    op.add_column("bots", sa.Column("published_revision_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_bots_published_revision_id",
        "bots",
        "knowledge_revisions",
        ["published_revision_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_bots_published_revision_id", "bots", type_="foreignkey")
    op.drop_column("bots", "published_revision_id")
    op.drop_index("ix_chunks_fts_en", table_name="chunks", postgresql_using="gin")
    op.drop_index("ix_chunks_fts_simple", table_name="chunks", postgresql_using="gin")
    op.drop_index("uq_chunks_tenant_id_id", table_name="chunks")
    op.drop_index("uq_chunks_revision_source_hash", table_name="chunks")
    op.drop_index("ix_chunks_tenant_bot_revision", table_name="chunks")
    op.drop_table("chunks")
    op.drop_index("uq_documents_tenant_id_id", table_name="documents")
    op.drop_index("uq_documents_tenant_bot_id", table_name="documents")
    op.drop_index("uq_documents_tenant_bot_revision_id", table_name="documents")
    op.drop_index("ix_documents_tenant_bot_revision", table_name="documents")
    op.drop_index("ix_documents_tenant_bot_source", table_name="documents")
    op.drop_table("documents")
    op.drop_index("uq_source_pages_tenant_id_id", table_name="source_pages")
    op.drop_index("uq_source_pages_tenant_bot_id", table_name="source_pages")
    op.drop_index("ix_source_pages_tenant_bot_source", table_name="source_pages")
    op.drop_table("source_pages")
    op.drop_index("uq_sources_tenant_id_id", table_name="sources")
    op.drop_index("uq_sources_tenant_bot_id", table_name="sources")
    op.drop_index("ix_sources_tenant_bot_created", table_name="sources")
    op.drop_table("sources")
    op.drop_index("ix_jobs_tenant_bot_created", table_name="jobs")
    op.drop_index("ix_jobs_tenant_bot", table_name="jobs")
    op.drop_index("ix_jobs_claim", table_name="jobs")
    op.drop_table("jobs")
    op.drop_index("uq_knowledge_revisions_tenant_id_id", table_name="knowledge_revisions")
    op.drop_index("uq_knowledge_revisions_tenant_bot_id", table_name="knowledge_revisions")
    op.drop_index(
        "uq_knowledge_revisions_published",
        table_name="knowledge_revisions",
        postgresql_where=sa.text("status = 'published'"),
    )
    op.drop_index(
        "uq_knowledge_revisions_draft",
        table_name="knowledge_revisions",
        postgresql_where=sa.text("status = 'draft'"),
    )
    op.drop_index("ix_knowledge_revisions_bot_status", table_name="knowledge_revisions")
    op.drop_table("knowledge_revisions")
