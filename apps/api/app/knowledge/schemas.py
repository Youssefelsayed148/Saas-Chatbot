"""Pydantic schemas for the knowledge/inbox endpoints (docs/05 knowledge routes)."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

MAX_UPLOAD_FILES = 20  # docs/14 §3 default; enforced per settings


class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kind: str
    original_name: str
    storage_key: str
    size_bytes: int
    sha256: str
    status: str
    error: str | None = None
    row_errors: list[dict[str, Any]] | None = None
    valid_rows: int | None = None
    total_rows: int | None = None
    created_at: datetime


class SourceDetailOut(SourceOut):
    storage_size: int | None = None
    page_count: int | None = None
    document_count: int | None = None
    chunk_count: int | None = None


class SourceFilesResponse(BaseModel):
    sources: list[SourceOut]
    created_job_id: UUID | None = None


class IngestionStartRequest(BaseModel):
    """All stored sources by default; explicit ids re-run a subset."""

    source_ids: list[UUID] | None = Field(default=None)


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: str
    type: str
    source_ids: list[UUID] = Field(default_factory=list)
    attempts: int
    max_attempts: int
    error: str | None = None
    cancel_requested: bool
    run_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_id: UUID
    title: str
    heading: str | None = None
    source_url: str | None = None
    page_ref: str
    language: str
    priority: int
    text: str
    total_chars: int
    chunk_count: int = 0
    created_at: datetime


class ChunkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_id: UUID
    title: str
    heading: str | None = None
    text: str
    language: str
    priority: int
    ordinal: int


class RevisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: str
    published_at: datetime | None = None
    created_at: datetime
    is_current: bool = False
    document_count: int = 0
    chunk_count: int = 0


class RevisionsResponse(BaseModel):
    revisions: list[RevisionOut]
    published_revision_id: UUID | None


class JobListResponse(BaseModel):
    jobs: list[JobOut]
