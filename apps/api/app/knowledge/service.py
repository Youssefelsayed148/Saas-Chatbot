"""Knowledge service: upload, ingestion jobs, documents, revisions (P2-02/03).

Tenant scoping: every lookup runs against the caller's ``TenantContext`` and
other tenants' ids look like 404 (docs/06). Uploaded files are stored under
generated tenant/bot-namespaced names and never served raw. Roles follow
docs/06: file uploads and ingest are editor+; publish is admin+.
"""

import hashlib
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import BinaryIO
from uuid import UUID, uuid4

from sqlalchemy import func, select, update

from app.core.audit import record_audit
from app.core.config import Settings
from app.core.errors import ApiError
from app.core.tenancy import TenantContext
from app.db.models import (
    Bot,
    Chunk,
    Document,
    Job,
    KnowledgeRevision,
    Source,
)
from app.jobs.queue import enqueue_job, request_cancel, requeue_for_retry
from app.knowledge.csv_qa import CsvStructureError, parse_qa_csv, qa_template_csv
from app.knowledge.parsers import detect_and_validate
from app.knowledge.storage import Storage, get_storage
from app.quotas.service import lock_tenant, limits_for
from app.quotas.rag import check_resources

UPLOAD_CHUNK_SIZE = 256 * 1024


# --- helpers ---------------------------------------------------------------


def get_bot(context: TenantContext, bot_id: UUID) -> Bot:
    bot = context.db.get(Bot, bot_id)
    if bot is None or bot.tenant_id != context.tenant_id:
        raise ApiError(404, "NOT_FOUND", "Resource not found.")
    return bot


def _get_editable_bot(context: TenantContext, bot_id: UUID) -> Bot:
    bot = get_bot(context, bot_id)
    if bot.status == "archived":
        raise ApiError(409, "BOT_ARCHIVED", "An archived bot cannot be modified.")
    return bot


def safe_display_name(name: str) -> str:
    """Only a display copy of the name is kept; storage keys are generated (docs/06)."""
    stem = PurePosixPath(name.replace("\\", "/")).name
    return (stem.strip() or "upload")[:200]


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --- upload ----------------------------------------------------------------


def upload_files(
    context: TenantContext,
    bot_id: UUID,
    files: Sequence[tuple[str | None, BinaryIO]],
    settings: Settings,
    storage: Storage | None = None,
) -> list[Source]:
    """Validate every file (atomic batch), then store and register sources.

    The user-supplied filename is kept as a display label only — file storage
    keys are generated; user input never reaches the filesystem path.
    """
    bot = _get_editable_bot(context, bot_id)
    tenant = lock_tenant(context.db, context.tenant_id)
    limits = limits_for(tenant)
    upload_settings = settings.model_copy(
        update={"max_upload_file_bytes": limits.upload_file_mb * 1024 * 1024}
    )
    if not files:
        raise ApiError(422, "VALIDATION_ERROR", "No files were uploaded.")
    if len(files) > settings.max_upload_files:
        raise ApiError(
            422,
            "VALIDATION_ERROR",
            f"At most {settings.max_upload_files} files per upload batch.",
        )
    storage = storage or get_storage()

    checked: list[tuple[str, str, bytes]] = []
    for filename, stream in files:
        display = safe_display_name(filename or "upload")
        data = read_upload(stream, upload_settings)
        try:
            kind = detect_and_validate(filename, data)
        except ValueError as error:
            raise ApiError(415, "UNSUPPORTED_FILE", str(error)) from None
        if kind == "qa_csv":
            _reject_all_invalid_csv(data)
        checked.append((display, kind, data))

    check_resources(context.db, context.tenant_id, bot_id, settings,
                    additions={"storage_bytes": sum(len(data) for _, _, data in checked)})
    created: list[Source] = []
    saved_keys: list[str] = []
    try:
        for display, kind, data in checked:
            storage_key = storage.save(context.tenant_id, bot.id, kind, data)
            saved_keys.append(storage_key)
            source = Source(
                id=uuid4(),
                tenant_id=context.tenant_id,
                bot_id=bot.id,
                kind=kind,
                original_name=display,
                storage_key=storage_key,
                size_bytes=len(data),
                sha256=_digest(data),
                status="stored",
                created_by=context.user.id,
            )
            if kind == "qa_csv":
                parsed = parse_qa_csv(data)
                source.row_errors = parsed.errors[:200]
                source.total_rows = parsed.total_rows
                source.valid_rows = parsed.valid_rows
            context.db.add(source)
            created.append(source)
        context.db.flush()
        record_audit(
            context.db,
            action="knowledge.sources_uploaded",
            tenant_id=context.tenant_id,
            actor_user_id=context.user.id,
            target_type="bot",
            target_id=str(bot.id),
            metadata={
                "count": len(created),
                "source_ids": [str(source.id) for source in created],
            },
        )
        context.db.commit()
        return created
    except ApiError:
        context.db.rollback()
        for key in saved_keys:
            storage.delete(key)
        raise
    except Exception:  # noqa: BLE001 - storage/db failures never leak details
        context.db.rollback()
        for key in saved_keys:  # atomic batch: nothing remains stored
            storage.delete(key)
        raise ApiError(500, "INTERNAL_ERROR", "The upload could not be stored.") from None
    return created


def read_upload(stream: BinaryIO, settings: Settings) -> bytes:
    """Stream-read with a hard size cap (docs/06)."""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = stream.read(UPLOAD_CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > settings.max_upload_file_bytes:
            raise ApiError(
                413,
                "FILE_TOO_LARGE",
                f"Files may be at most {settings.max_upload_file_bytes // (1024 * 1024)} MB.",
            )
        chunks.append(chunk)
    data = b"".join(chunks)
    if not data:
        raise ApiError(422, "VALIDATION_ERROR", "The file is empty.")
    return data


def _reject_all_invalid_csv(data: bytes) -> None:
    """Every Q&A row invalid → reject the upload with the per-row reasons."""
    try:
        parsed = parse_qa_csv(data)
    except CsvStructureError as error:
        raise ApiError(422, "VALIDATION_ERROR", error.reason) from None
    if parsed.valid_rows == 0:
        reasons = "; ".join(f"Row {row['row']}: {row['reason']}" for row in parsed.errors[:3])
        raise ApiError(422, "VALIDATION_ERROR", reasons or "No valid Q&A rows.")


def qa_template() -> bytes:
    """The downloadable Q&A CSV template (docs/05)."""
    return qa_template_csv()


# --- ingestion job ---------------------------------------------------------


def start_ingestion(
    context: TenantContext,
    bot_id: UUID,
    source_ids: Sequence[UUID] | None,
    settings: Settings,
) -> Job:
    bot = _get_editable_bot(context, bot_id)
    if source_ids is None:
        sources = list(
            context.db.execute(
                select(Source)
                .where(
                    Source.tenant_id == context.tenant_id,
                    Source.bot_id == bot.id,
                    Source.status == "stored",
                )
                .order_by(Source.created_at, Source.id)
            ).scalars()
        )
    else:
        sources = list(
            context.db.execute(
                select(Source)
                .where(
                    Source.tenant_id == context.tenant_id,
                    Source.bot_id == bot.id,
                    Source.id.in_(source_ids),
                    Source.status.in_(["stored", "failed"]),
                )
                .order_by(Source.created_at, Source.id)
            ).scalars()
        )
        if len(sources) != len(set(source_ids)):
            raise ApiError(
                404,
                "NOT_FOUND",
                "One of the requested sources was not found for this bot.",
            )
    if not sources:
        raise ApiError(409, "NOTHING_TO_INGEST", "There are no new files to ingest.")
    for source in sources:
        source.status = "queued"
        source.error = None
    job = enqueue_job(
        context.db,
        tenant_id=context.tenant_id,
        bot_id=bot.id,
        job_type="ingest_batch",
        payload={"source_ids": [str(source.id) for source in sources]},
        created_by=context.user.id,
        settings=settings,
    )
    record_audit(
        context.db,
        action="knowledge.ingestion_started",
        tenant_id=context.tenant_id,
        actor_user_id=context.user.id,
        target_type="job",
        target_id=str(job.id),
        metadata={"source_ids": [str(source.id) for source in sources]},
    )
    context.db.commit()
    return job


def list_jobs(context: TenantContext, bot_id: UUID) -> Sequence[Job]:
    get_bot(context, bot_id)  # tenant scope before scanning jobs
    return list(
        context.db.execute(
            select(Job)
            .where(Job.tenant_id == context.tenant_id, Job.bot_id == bot_id)
            .order_by(Job.created_at.desc(), Job.id)
            .limit(100)
        ).scalars()
    )


def get_job_or_404(context: TenantContext, bot_id: UUID, job_id: UUID) -> Job:
    job = context.db.execute(
        select(Job).where(
            Job.id == job_id,
            Job.tenant_id == context.tenant_id,
            Job.bot_id == bot_id,
        )
    ).scalar_one_or_none()
    if job is None:
        raise ApiError(404, "NOT_FOUND", "Resource not found.")
    return job


def cancel_job(context: TenantContext, bot_id: UUID, job_id: UUID) -> Job:
    job = get_job_or_404(context, bot_id, job_id)
    request_cancel(context.db, job)
    record_audit(
        context.db,
        action="knowledge.job_cancelled",
        tenant_id=context.tenant_id,
        actor_user_id=context.user.id,
        target_type="job",
        target_id=str(job.id),
    )
    context.db.commit()
    return job


def retry_job(context: TenantContext, bot_id: UUID, job_id: UUID, settings: Settings) -> Job:
    bot = _get_editable_bot(context, bot_id)
    job = get_job_or_404(context, bot_id, job_id)
    if job.type != "ingest_batch":
        raise ApiError(409, "JOB_NOT_RETRYABLE", "Unknown job type.")
    payload = job.payload if isinstance(job.payload, dict) else {}
    raw_list = payload.get("source_ids")
    raw_ids = [
        UUID(value)
        for value in (raw_list if isinstance(raw_list, list) else [])
        if isinstance(value, str)
    ]
    sources = list(
        context.db.execute(
            select(Source).where(
                Source.tenant_id == context.tenant_id,
                Source.bot_id == bot.id,
                Source.id.in_(raw_ids),
            )
        ).scalars()
    )
    for source in sources:
        source.status = "queued"
        source.error = None
    requeue_for_retry(context.db, job)
    record_audit(
        context.db,
        action="knowledge.job_retried",
        tenant_id=context.tenant_id,
        actor_user_id=context.user.id,
        target_type="job",
        target_id=str(job.id),
    )
    context.db.commit()
    return job


# --- sources, documents, revisions -----------------------------------------


def list_sources(context: TenantContext, bot_id: UUID) -> Sequence[Source]:
    get_bot(context, bot_id)
    return list(
        context.db.execute(
            select(Source)
            .where(Source.tenant_id == context.tenant_id, Source.bot_id == bot_id)
            .order_by(Source.created_at.desc(), Source.id)
            .limit(500)
        ).scalars()
    )


def get_source(context: TenantContext, bot_id: UUID, source_id: UUID) -> Source:
    source = context.db.execute(
        select(Source).where(
            Source.id == source_id,
            Source.tenant_id == context.tenant_id,
            Source.bot_id == bot_id,
        )
    ).scalar_one_or_none()
    if source is None:
        raise ApiError(404, "NOT_FOUND", "Resource not found.")
    return source


def list_documents(
    context: TenantContext,
    bot_id: UUID,
    source_id: UUID | None,
    revision_status: str,
) -> list[tuple[Document, int]]:
    """Documents of the published (default) or draft revision with chunk counts."""
    revision = _lookup_revision(context, bot_id, revision_status)
    if revision is None:
        return []
    statement = (
        select(Document, func.count(Chunk.id))
        .outerjoin(Chunk, Chunk.document_id == Document.id)
        .where(
            Document.tenant_id == context.tenant_id,
            Document.bot_id == bot_id,
            Document.revision_id == revision.id,
        )
        .group_by(Document.id)
        .order_by(Document.created_at, Document.id)
    )
    if source_id is not None:
        get_source(context, bot_id, source_id)  # tenant scope check
        statement = statement.where(Document.source_id == source_id)
    rows = context.db.execute(statement.limit(500)).all()
    return [(document, int(count)) for document, count in rows]


def list_document_chunks(
    context: TenantContext, bot_id: UUID, document_id: UUID
) -> Sequence[Chunk]:
    document = context.db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.tenant_id == context.tenant_id,
            Document.bot_id == bot_id,
        )
    ).scalar_one_or_none()
    if document is None:
        raise ApiError(404, "NOT_FOUND", "Resource not found.")
    return list(
        context.db.execute(
            select(Chunk)
            .where(
                Chunk.tenant_id == context.tenant_id,
                Chunk.revision_id == document.revision_id,
                Chunk.document_id == document.id,
            )
            .order_by(Chunk.ordinal, Chunk.id)
        ).scalars()
    )


def _lookup_revision(
    context: TenantContext, bot_id: UUID, revision_status: str
) -> KnowledgeRevision | None:
    bot = get_bot(context, bot_id)
    if revision_status == "draft":
        return context.db.execute(
            select(KnowledgeRevision).where(
                KnowledgeRevision.tenant_id == context.tenant_id,
                KnowledgeRevision.bot_id == bot_id,
                KnowledgeRevision.status == "draft",
            )
        ).scalar_one_or_none()
    if bot.published_revision_id is None:
        return None
    return context.db.get(KnowledgeRevision, bot.published_revision_id)


def list_revisions(context: TenantContext, bot_id: UUID) -> list[dict[str, object]]:
    bot = get_bot(context, bot_id)
    revisions = (
        context.db.execute(
            select(KnowledgeRevision)
            .where(
                KnowledgeRevision.tenant_id == context.tenant_id,
                KnowledgeRevision.bot_id == bot.id,
            )
            .order_by(KnowledgeRevision.created_at.desc(), KnowledgeRevision.id)
            .limit(50)
        )
        .scalars()
        .all()
    )
    result: list[dict[str, object]] = []
    for revision in revisions:
        document_count = int(
            context.db.execute(
                select(func.count())
                .select_from(Document)
                .where(Document.revision_id == revision.id)
            ).scalar_one()
        )
        chunk_count = int(
            context.db.execute(
                select(func.count()).select_from(Chunk).where(Chunk.revision_id == revision.id)
            ).scalar_one()
        )
        result.append(
            {
                "id": str(revision.id),
                "status": revision.status,
                "published_at": revision.published_at.isoformat()
                if revision.published_at
                else None,
                "created_at": revision.created_at.isoformat(),
                "is_current": revision.id == bot.published_revision_id,
                "document_count": document_count,
                "chunk_count": chunk_count,
            }
        )
    return result


# --- publish / rollback ----------------------------------------------------


def publish_revision(context: TenantContext, bot_id: UUID, revision_id: UUID) -> dict[str, object]:
    """Atomic knowledge pointer swap (docs/08): demote current, promote target.

    Admin+ only (docs/06). Publishing an archived revision is a rollback.
    """
    bot = get_bot(context, bot_id)
    if bot.status == "archived":
        raise ApiError(409, "BOT_ARCHIVED", "An archived bot cannot publish knowledge.")
    revision = context.db.execute(
        select(KnowledgeRevision).where(
            KnowledgeRevision.id == revision_id,
            KnowledgeRevision.tenant_id == context.tenant_id,
            KnowledgeRevision.bot_id == bot.id,
        )
    ).scalar_one_or_none()
    if revision is None:
        raise ApiError(404, "NOT_FOUND", "Resource not found.")
    if bot.published_revision_id == revision.id:
        # Idempotent: already live knowledge.
        return {"revision_id": str(revision.id), "status": "published", "changed": False}
    chunk_count = int(
        context.db.execute(
            select(func.count()).select_from(Chunk).where(Chunk.revision_id == revision.id)
        ).scalar_one()
    )
    if chunk_count == 0:
        raise ApiError(409, "KNOWLEDGE_EMPTY", "There is nothing to publish in that revision.")

    is_rollback = revision.status == "archived"
    now = datetime.now(UTC)
    current_id = bot.published_revision_id
    # Core statements in explicit order: demote the current published row
    # first (the partial unique index on status='published' must never see two).
    if current_id is not None and current_id != revision.id:
        context.db.execute(
            update(KnowledgeRevision)
            .where(
                KnowledgeRevision.id == current_id,
                KnowledgeRevision.tenant_id == context.tenant_id,
                KnowledgeRevision.status == "published",
            )
            .values(status="archived", published_at=None)
        )
    if revision.status == "draft":
        context.db.execute(
            update(KnowledgeRevision)
            .where(
                KnowledgeRevision.tenant_id == context.tenant_id,
                KnowledgeRevision.bot_id == bot.id,
                KnowledgeRevision.status == "draft",
                KnowledgeRevision.id != revision.id,
            )
            .values(status="archived")
        )
    context.db.execute(
        update(KnowledgeRevision)
        .where(
            KnowledgeRevision.id == revision.id,
            KnowledgeRevision.tenant_id == context.tenant_id,
        )
        .values(status="published", published_at=now)
    )
    context.db.execute(
        update(Bot)
        .where(Bot.id == bot.id, Bot.tenant_id == context.tenant_id)
        .values(published_revision_id=revision.id, updated_at=now)
    )
    # Re-read the ORM state (the updates above bypass the session cache).
    context.db.expire_all()
    record_audit(
        context.db,
        action="knowledge.rolled_back" if is_rollback else "knowledge.published",
        tenant_id=context.tenant_id,
        actor_user_id=context.user.id,
        target_type="bot",
        target_id=str(bot.id),
        metadata={"revision_id": str(revision.id)},
    )
    try:
        context.db.commit()
    except Exception:  # noqa: BLE001 - concurrent publish raced the unique index
        context.db.rollback()
        raise ApiError(409, "CONFLICT", "The revision pointer changed concurrently.") from None
    return {"revision_id": str(revision.id), "status": "published", "changed": True}
