"""Knowledge and ingestion schema (P2-01, docs/08, docs/14 §3–§5, ADR-011).

Structure: ``sources`` (uploaded files) → ``source_pages`` (parsed pages) →
``documents`` (heading sections / Q&A rows) → ``chunks`` (indexed text inside
a ``knowledge_revisions`` snapshot). ``jobs`` is the durable queue (ADR-011).

Every tenant-owned table carries ``tenant_id`` plus a bot scoping column, and
children use composite FKs ``(tenant_id, bot_id[, parent_id])`` against unique
keys on their parents (ADR-010) — a row can never reference a parent of
another tenant, and the ingest worker re-validates tenant + bot per job.
RAG Phase 2 adds model-tagged vector(1024) embeddings alongside the original
GIN-indexed ``fts_en`` / ``fts_simple`` / ``fts_ar`` columns.
"""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Text,
)
from sqlalchemy import (
    text as sa_text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utcnow
from app.db.models.types import TSVECTOR, VECTOR1024

# --- allowed/checked values -------------------------------------------------
SOURCE_KIND_VALUES = ("pdf", "docx", "txt", "md", "qa_csv")
SOURCE_STATUS_VALUES = ("stored", "queued", "ingested", "failed", "removed")
JOB_TYPE_VALUES = (
    "ingest_batch", "retention_purge", "follow_up_delivery", "sentiment_classify",
    "reembed_backfill",
)
JOB_STATUS_VALUES = ("pending", "running", "succeeded", "failed", "cancelled")
REVISION_STATUS_VALUES = ("draft", "published", "archived")
LANGUAGE_VALUES = ("en", "ar")


class Job(Base):
    """Durable job queue row (ADR-011). ``payload`` holds ids, never secrets."""

    __tablename__ = "jobs"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(nullable=False)
    bot_id: Mapped[UUID] = mapped_column(nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    attempts: Mapped[int] = mapped_column(default=0, server_default=sa_text("0"))
    max_attempts: Mapped[int] = mapped_column(default=3, server_default=sa_text("3"))
    # Backoff: the next runnable time. Reclaim also matches expired leases.
    run_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    leased_by: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # One line actionable reason; never contains secrets or file contents.
    error: Mapped[str | None] = mapped_column(Text)
    cancel_requested: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=sa_text("false")
    )
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    __table_args__ = (
        CheckConstraint(
            "type IN ('ingest_batch', 'retention_purge', 'follow_up_delivery', 'sentiment_classify')"
            " OR type = 'reembed_backfill'",
            name="ck_jobs_type",
        ),
        CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed', 'cancelled')",
            name="ck_jobs_status",
        ),
        CheckConstraint("attempts >= 0 AND max_attempts >= 1", name="ck_jobs_attempts"),
        # Composite FK to bots: the job's bot must belong to the job's tenant (ADR-010).
        ForeignKeyConstraint(
            ["tenant_id", "bot_id"],
            ["bots.tenant_id", "bots.id"],
            name="fk_jobs_tenant_bot",
            ondelete="CASCADE",
        ),
        Index("ix_jobs_tenant_bot", "tenant_id", "bot_id"),
        Index("ix_jobs_tenant_bot_created", "tenant_id", "bot_id", "created_at"),
        # Claim scan: pending (or lease-expired, matched via OR in the claim query).
        Index("ix_jobs_claim", "status", "run_at"),
    )


class Source(Base):
    """One uploaded file (PDF/DOCX/TXT/MD/Q&A CSV). Never served raw."""

    __tablename__ = "sources"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(nullable=False)
    bot_id: Mapped[UUID] = mapped_column(nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    # Display only: storage uses generated tenant/bot-namespaced names (docs/06).
    original_name: Mapped[str] = mapped_column(Text, nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="stored")
    error: Mapped[str | None] = mapped_column(Text)
    # Q&A CSV row-level report: [{"row": 4, "reason": "..."}].
    row_errors: Mapped[list[dict[str, int | str]] | None] = mapped_column(JSONB)
    valid_rows: Mapped[int | None] = mapped_column()
    total_rows: Mapped[int | None] = mapped_column()
    created_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    __table_args__ = (
        CheckConstraint("kind IN ('pdf', 'docx', 'txt', 'md', 'qa_csv')", name="ck_sources_kind"),
        CheckConstraint(
            "status IN ('stored', 'queued', 'ingested', 'failed', 'removed')",
            name="ck_sources_status"
        ),
        CheckConstraint("size_bytes >= 0", name="ck_sources_size"),
        ForeignKeyConstraint(
            ["tenant_id", "bot_id"],
            ["bots.tenant_id", "bots.id"],
            name="fk_sources_tenant_bot",
            ondelete="CASCADE",
        ),
        Index("uq_sources_tenant_id_id", "tenant_id", "id", unique=True),
        # Anchor for child composite FKs (tenant_id, bot_id, source_id).
        Index("uq_sources_tenant_bot_id", "tenant_id", "bot_id", "id", unique=True),
        Index("ix_sources_tenant_bot_created", "tenant_id", "bot_id", "created_at"),
    )


class SourcePage(Base):
    """One parsed page (PDF page, markdown/txt page, or CSV sheet container)."""

    __tablename__ = "source_pages"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(nullable=False)
    bot_id: Mapped[UUID] = mapped_column(nullable=False)
    source_id: Mapped[UUID] = mapped_column(nullable=False)
    page_number: Mapped[int | None] = mapped_column()
    title: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    page_type: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str] = mapped_column(Text, nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    __table_args__ = (
        CheckConstraint("language IN ('en', 'ar')", name="ck_source_pages_language"),
        ForeignKeyConstraint(
            ["tenant_id", "bot_id", "source_id"],
            ["sources.tenant_id", "sources.bot_id", "sources.id"],
            name="fk_source_pages_source",
            ondelete="CASCADE",
        ),
        Index("uq_source_pages_tenant_id_id", "tenant_id", "id", unique=True),
        Index("uq_source_pages_tenant_bot_id", "tenant_id", "bot_id", "id", unique=True),
        Index("ix_source_pages_tenant_bot_source", "tenant_id", "bot_id", "source_id"),
    )


class Document(Base):
    """A heading section (or one Q&A row) inside a revision snapshot.

    Documents are revision-scoped: an ingest never mutates the documents a
    published revision points at (a failed job can't touch published
    knowledge); a fresh draft is built as a copy of the current revision.
    """

    __tablename__ = "documents"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(nullable=False)
    bot_id: Mapped[UUID] = mapped_column(nullable=False)
    revision_id: Mapped[UUID] = mapped_column(nullable=False)
    source_id: Mapped[UUID] = mapped_column(nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    heading: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    # Machine-readable provenance for the UI: "Page 3", "Section 2", "Row 12".
    page_ref: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Position within the source run; keeps preview order deterministic.
    ordinal: Mapped[int] = mapped_column(default=0, server_default=sa_text("0"))
    language: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[int] = mapped_column(default=0, server_default=sa_text("0"))
    text: Mapped[str] = mapped_column(Text, nullable=False)
    total_chars: Mapped[int] = mapped_column(nullable=False)
    # Identical chunks of other sources dropped around this document (H2).
    duplicates_removed: Mapped[int] = mapped_column(default=0, server_default=sa_text("0"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    __table_args__ = (
        CheckConstraint("language IN ('en', 'ar')", name="ck_documents_language"),
        CheckConstraint("priority >= 0 AND priority <= 10", name="ck_documents_priority"),
        CheckConstraint("total_chars >= 0", name="ck_documents_total_chars"),
        ForeignKeyConstraint(
            ["tenant_id", "bot_id", "revision_id"],
            [
                "knowledge_revisions.tenant_id",
                "knowledge_revisions.bot_id",
                "knowledge_revisions.id",
            ],
            name="fk_documents_revision",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "bot_id", "source_id"],
            ["sources.tenant_id", "sources.bot_id", "sources.id"],
            name="fk_documents_source",
            ondelete="CASCADE",
        ),
        Index("uq_documents_tenant_id_id", "tenant_id", "id", unique=True),
        Index("uq_documents_tenant_bot_id", "tenant_id", "bot_id", "id", unique=True),
        # Anchor for the chunk → document composite FK.
        Index(
            "uq_documents_tenant_bot_revision_id",
            "tenant_id",
            "bot_id",
            "revision_id",
            "id",
            unique=True,
        ),
        Index("ix_documents_tenant_bot_source", "tenant_id", "bot_id", "source_id"),
        Index("ix_documents_tenant_bot_revision", "tenant_id", "bot_id", "revision_id"),
    )


class KnowledgeRevision(Base):
    """A bot knowledge snapshot: draft → published → archived (docs/08)."""

    __tablename__ = "knowledge_revisions"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(nullable=False)
    bot_id: Mapped[UUID] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="draft")
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Set only while EVERY chunk of this revision carries this embedding identity
    # (the backfill sets it; ingest into the draft clears it). NULL = keyword-only.
    embedding_model: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'published', 'archived')",
            name="ck_knowledge_revisions_status",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "bot_id"],
            ["bots.tenant_id", "bots.id"],
            name="fk_knowledge_revisions_tenant_bot",
            ondelete="CASCADE",
        ),
        Index("uq_knowledge_revisions_tenant_id_id", "tenant_id", "id", unique=True),
        Index(
            "uq_knowledge_revisions_tenant_bot_id",
            "tenant_id",
            "bot_id",
            "id",
            unique=True,
        ),
        # At most one draft and one published revision per bot, enforced by the DB.
        Index(
            "uq_knowledge_revisions_draft",
            "tenant_id",
            "bot_id",
            unique=True,
            postgresql_where=sa_text("status = 'draft'"),
        ),
        Index(
            "uq_knowledge_revisions_published",
            "tenant_id",
            "bot_id",
            unique=True,
            postgresql_where=sa_text("status = 'published'"),
        ),
        Index(
            "ix_knowledge_revisions_bot_status",
            "tenant_id",
            "bot_id",
            "status",
        ),
    )


class Chunk(Base):
    """Indexed retrieval unit (docs/14 §4–§5). GIN-indexed generated tsvector columns."""

    __tablename__ = "chunks"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(nullable=False)
    bot_id: Mapped[UUID] = mapped_column(nullable=False)
    revision_id: Mapped[UUID] = mapped_column(nullable=False)
    source_id: Mapped[UUID] = mapped_column(nullable=False)
    document_id: Mapped[UUID] = mapped_column(nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    heading: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # Arabic-normalised (docs/14 §2); fts_simple and fts_ar are built from it.
    text_norm: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[int] = mapped_column(default=0, server_default=sa_text("0"))
    # SHA-256 of text_norm; dedupe key per (revision, source) (docs/14 §3).
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(VECTOR1024())
    embedding_model: Mapped[str | None] = mapped_column(Text)
    embedding_dim: Mapped[int | None] = mapped_column()
    ordinal: Mapped[int] = mapped_column(default=0, server_default=sa_text("0"))
    fts_en: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('english', coalesce(title, '') || ' ' || "
            "coalesce(heading, '') || ' ' || \"text\")",
            persisted=True,
        ),
        nullable=False,
    )
    fts_simple: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('simple', coalesce(text_norm, ''))", persisted=True),
        nullable=False,
    )
    fts_ar: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('arabic', coalesce(text_norm, ''))", persisted=True),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    __table_args__ = (
        CheckConstraint("language IN ('en', 'ar')", name="ck_chunks_language"),
        CheckConstraint("priority >= 0 AND priority <= 10", name="ck_chunks_priority"),
        CheckConstraint("ordinal >= 0", name="ck_chunks_ordinal"),
        CheckConstraint(
            "(embedding IS NULL AND embedding_model IS NULL AND embedding_dim IS NULL) OR "
            "(embedding IS NOT NULL AND embedding_model IS NOT NULL AND embedding_dim = 1024)",
            name="ck_chunks_embedding",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "bot_id"],
            ["bots.tenant_id", "bots.id"],
            name="fk_chunks_tenant_bot",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "bot_id", "revision_id"],
            [
                "knowledge_revisions.tenant_id",
                "knowledge_revisions.bot_id",
                "knowledge_revisions.id",
            ],
            name="fk_chunks_revision",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "bot_id", "source_id"],
            ["sources.tenant_id", "sources.bot_id", "sources.id"],
            name="fk_chunks_source",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "bot_id", "revision_id", "document_id"],
            [
                "documents.tenant_id",
                "documents.bot_id",
                "documents.revision_id",
                "documents.id",
            ],
            name="fk_chunks_document",
            ondelete="CASCADE",
        ),
        Index("uq_chunks_tenant_id_id", "tenant_id", "id", unique=True),
        # Identical normalized chunk text is stored once per source in a revision.
        Index(
            "uq_chunks_revision_source_hash",
            "revision_id",
            "source_id",
            "content_hash",
            unique=True,
        ),
        Index("ix_chunks_tenant_bot_revision", "tenant_id", "bot_id", "revision_id"),
        Index("ix_chunks_fts_en", "fts_en", postgresql_using="gin"),
        Index("ix_chunks_fts_simple", "fts_simple", postgresql_using="gin"),
        Index("ix_chunks_fts_ar", "fts_ar", postgresql_using="gin"),
        Index("ix_chunks_embedding_hnsw", "embedding", postgresql_using="hnsw",
              postgresql_ops={"embedding": "vector_cosine_ops"},
              postgresql_where=sa_text("embedding IS NOT NULL")),
    )


__all__ = [
    "Chunk",
    "Document",
    "Job",
    "KnowledgeRevision",
    "Source",
    "SourcePage",
]
