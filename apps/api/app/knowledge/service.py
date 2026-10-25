"""Knowledge service: upload, ingestion jobs, documents, revisions (P2-02/03).

Tenant scoping: every lookup runs against the caller's ``TenantContext`` and
other tenants' ids look like 404 (docs/06). Uploaded files are stored under
generated tenant/bot-namespaced names and never served raw. Roles follow
docs/06: file uploads and ingest are editor+; publish is admin+.
"""

import hashlib
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import BinaryIO
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session as OrmSession

from app.core.audit import record_audit
from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.core.tenancy import TenantContext
from app.db.models import (
    Bot,
    Chunk,
    Document,
    Job,
    KnowledgeRevision,
    Source,
    SourcePage,
)
from app.embeddings.backfill import queue_backfill, sync_bot_readiness
from app.embeddings.providers import EmbeddingError, configured_identity
from app.jobs.queue import enqueue_job, request_cancel, requeue_for_retry
from app.knowledge.csv_qa import CsvStructureError, parse_qa_csv, qa_template_csv
from app.knowledge.ingest import get_or_create_draft_revision
from app.knowledge.parsers import detect_and_validate
from app.knowledge.storage import Storage, get_storage
from app.quotas.rag import check_resources
from app.quotas.service import limits_for, lock_tenant

UPLOAD_CHUNK_SIZE = 256 * 1024

logger = logging.getLogger(__name__)


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

ALWAYS_INCLUDE_KEY = "always_include_source_ids"
# Reserved whole-document slots must leave room for ranked evidence (docs/14 §5).
ALWAYS_INCLUDE_MAX_SOURCES = 3
DUPLICATE_MESSAGE = "This file was already uploaded as “{name}”; nothing new was stored."


@dataclass
class UploadOutcome:
    source: Source
    duplicate: bool = False


def _find_duplicate(db: OrmSession, tenant_id: UUID, bot_id: UUID, digest: str) -> Source | None:
    """The bot's live source with identical bytes, if any (other bots/tenants never match)."""
    return db.execute(
        select(Source)
        .where(
            Source.tenant_id == tenant_id,
            Source.bot_id == bot_id,
            Source.sha256 == digest,
            Source.status != "removed",
        )
        .order_by(Source.created_at, Source.id)
        .limit(1)
    ).scalar_one_or_none()


def upload_files(
    context: TenantContext,
    bot_id: UUID,
    files: Sequence[tuple[str | None, BinaryIO]],
    settings: Settings,
    storage: Storage | None = None,
) -> list[UploadOutcome]:
    """Validate every file (atomic batch), then store and register sources.

    A file whose bytes (sha256) match a live source of the same bot is not stored
    again: that existing source is returned flagged as a duplicate.

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

    # Dedupe by content hash: against the bot's sources and inside this batch.
    outcomes: list[UploadOutcome | None] = []
    fresh: list[tuple[int, str, str, bytes, str]] = []
    batch_digests: dict[str, int] = {}
    for index, (display, kind, data) in enumerate(checked):
        digest = _digest(data)
        existing = _find_duplicate(context.db, context.tenant_id, bot.id, digest)
        if existing is not None:
            outcomes.append(UploadOutcome(existing, duplicate=True))
        elif digest in batch_digests:
            outcomes.append(None)  # resolved to the batch's first copy below
        else:
            batch_digests[digest] = index
            outcomes.append(None)
            fresh.append((index, display, kind, data, digest))
    if not fresh:
        return [outcome for outcome in outcomes if outcome is not None] or []

    check_resources(
        context.db,
        context.tenant_id,
        bot_id,
        settings,
        additions={"storage_bytes": sum(len(data) for _, _, _, data, _ in fresh)},
    )
    created: list[Source] = []
    saved_keys: list[str] = []
    try:
        for index, display, kind, data, _digest_value in fresh:
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
            outcomes[index] = UploadOutcome(source)
        for index, (_display, _kind, data) in enumerate(checked):
            if outcomes[index] is None:
                first = outcomes[batch_digests[_digest(data)]]
                assert first is not None
                outcomes[index] = UploadOutcome(first.source, duplicate=True)
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
                "duplicates_skipped": sum(1 for o in outcomes if o is not None and o.duplicate),
            },
        )
        context.db.commit()
        return [outcome for outcome in outcomes if outcome is not None]
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
                Source.status != "removed",
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
            .where(
                Source.tenant_id == context.tenant_id,
                Source.bot_id == bot_id,
                Source.status != "removed",
            )
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
            Source.status != "removed",
        )
    ).scalar_one_or_none()
    if source is None:
        raise ApiError(404, "NOT_FOUND", "Resource not found.")
    return source


def always_include_source_ids(bot: Bot) -> list[str]:
    """The bot's reserved-evidence source ids (stable across draft copies and re-ingest)."""
    raw = bot.config.get(ALWAYS_INCLUDE_KEY) if isinstance(bot.config, dict) else None
    return [str(value) for value in raw] if isinstance(raw, list) else []


def _is_uuid(value: str) -> bool:
    try:
        UUID(value)
    except (ValueError, TypeError):
        return False
    return True


def validate_always_include(
    db: OrmSession, tenant_id: UUID, bot_id: UUID, source_ids: Sequence[UUID]
) -> None:
    """Every id must be a live source of this bot; the list is capped (reserved slots)."""
    unique = set(source_ids)
    if len(unique) > ALWAYS_INCLUDE_MAX_SOURCES:
        raise ApiError(
            422,
            "VALIDATION_ERROR",
            f"At most {ALWAYS_INCLUDE_MAX_SOURCES} files can be always included.",
        )
    if not unique:
        return
    found = db.scalar(
        select(func.count())
        .select_from(Source)
        .where(
            Source.tenant_id == tenant_id,
            Source.bot_id == bot_id,
            Source.id.in_(unique),
            Source.status != "removed",
        )
    )
    if found != len(unique):
        raise ApiError(
            422, "VALIDATION_ERROR", "An always-include file was not found for this bot."
        )


def _write_always_include(bot: Bot, ids: list[str]) -> None:
    config = dict(bot.config)
    if ids:
        config[ALWAYS_INCLUDE_KEY] = ids
    else:
        config.pop(ALWAYS_INCLUDE_KEY, None)
    bot.config = config
    bot.updated_at = datetime.now(UTC)


def set_source_always_include(
    context: TenantContext, bot_id: UUID, source_id: UUID, enabled: bool
) -> Source:
    bot = _get_editable_bot(context, bot_id)
    source = get_source(context, bot_id, source_id)
    ids = always_include_source_ids(bot)
    key = str(source.id)
    if enabled and key not in ids:
        validate_always_include(
            context.db,
            context.tenant_id,
            bot.id,
            [*(UUID(value) for value in ids if _is_uuid(value)), source.id],
        )
        ids.append(key)
    elif not enabled:
        ids = [value for value in ids if value != key]
    _write_always_include(bot, ids)
    record_audit(
        context.db,
        action="knowledge.always_include_changed",
        tenant_id=context.tenant_id,
        actor_user_id=context.user.id,
        target_type="source",
        target_id=key,
        metadata={"enabled": enabled},
    )
    context.db.commit()
    return source


def always_include_document_ids(
    db: OrmSession, bot: Bot, revision_id: UUID, settings: Settings
) -> set[str]:
    """Documents of the live revision that belong to always-include sources.

    Resolved by source (stable) at query time, because document ids change with every
    draft copy. Capped so ranked evidence keeps at least one slot (docs/14 §5).
    """
    source_ids = [UUID(value) for value in always_include_source_ids(bot) if _is_uuid(value)]
    if not source_ids:
        return set()
    rows = db.execute(
        select(Document.id, func.count(Chunk.id))
        .join(Source, Source.id == Document.source_id)
        .outerjoin(Chunk, Chunk.document_id == Document.id)
        .where(
            Document.tenant_id == bot.tenant_id,
            Document.bot_id == bot.id,
            Document.revision_id == revision_id,
            Document.source_id.in_(source_ids),
            Source.status != "removed",
        )
        .group_by(Document.id, Document.ordinal)
        .order_by(Document.ordinal, Document.id)
    ).all()
    budget = max(settings.retrieval_final_k - 1, 1)
    chosen: set[str] = set()
    used = 0
    for document_id, chunks in rows:
        if chosen and used + int(chunks) > budget:
            break
        chosen.add(str(document_id))
        used += int(chunks)
    return chosen


# --- replace / delete --------------------------------------------------------


def replace_source(
    context: TenantContext,
    bot_id: UUID,
    source_id: UUID,
    filename: str | None,
    stream: BinaryIO,
    settings: Settings,
    storage: Storage | None = None,
) -> UploadOutcome:
    """Upload a new version of a source: same identity, new bytes, status ``stored``.

    The next ingest swaps its documents/chunks in the draft; published knowledge is
    untouched until publish. Identical bytes change nothing.
    """
    bot = _get_editable_bot(context, bot_id)
    tenant = lock_tenant(context.db, context.tenant_id)
    source = get_source(context, bot_id, source_id)
    if source.status == "queued":
        raise ApiError(409, "SOURCE_BUSY", "This file is being ingested; try again shortly.")
    storage = storage or get_storage()
    upload_settings = settings.model_copy(
        update={"max_upload_file_bytes": limits_for(tenant).upload_file_mb * 1024 * 1024}
    )
    data = read_upload(stream, upload_settings)
    try:
        kind = detect_and_validate(filename, data)
    except ValueError as error:
        raise ApiError(415, "UNSUPPORTED_FILE", str(error)) from None
    if kind == "qa_csv":
        _reject_all_invalid_csv(data)
    digest = _digest(data)
    if digest == source.sha256:
        return UploadOutcome(source, duplicate=True)
    other = _find_duplicate(context.db, context.tenant_id, bot.id, digest)
    if other is not None:
        return UploadOutcome(other, duplicate=True)
    check_resources(
        context.db,
        context.tenant_id,
        bot_id,
        settings,
        additions={"storage_bytes": max(len(data) - source.size_bytes, 0)},
    )
    old_key = source.storage_key
    new_key = storage.save(context.tenant_id, bot.id, kind, data)
    try:
        source.kind = kind
        source.original_name = safe_display_name(filename or source.original_name)
        source.storage_key = new_key
        source.size_bytes = len(data)
        source.sha256 = digest
        source.status = "stored"
        source.error = None
        source.created_at = datetime.now(UTC)  # the new version is the "newer" source
        if kind == "qa_csv":
            parsed = parse_qa_csv(data)
            source.row_errors = parsed.errors[:200]
            source.total_rows = parsed.total_rows
            source.valid_rows = parsed.valid_rows
        else:
            source.row_errors = None
            source.total_rows = None
            source.valid_rows = None
        record_audit(
            context.db,
            action="knowledge.source_replaced",
            tenant_id=context.tenant_id,
            actor_user_id=context.user.id,
            target_type="source",
            target_id=str(source.id),
        )
        context.db.commit()
    except Exception:  # noqa: BLE001 - storage/db failures never leak details
        context.db.rollback()
        storage.delete(new_key)
        raise ApiError(500, "INTERNAL_ERROR", "The file could not be replaced.") from None
    storage.delete(old_key)  # only after the commit, so a rollback never loses the file
    return UploadOutcome(source)


def delete_source(
    context: TenantContext, bot_id: UUID, source_id: UUID, storage: Storage | None = None
) -> None:
    """Remove a source from the DRAFT revision and mark it ``removed`` (soft delete).

    Published and archived revisions keep their rows, so live answers and rollback are
    unchanged until the next publish. The stored file is deleted after the commit.
    """
    bot = _get_editable_bot(context, bot_id)
    source = get_source(context, bot_id, source_id)
    if source.status == "queued":
        raise ApiError(409, "SOURCE_BUSY", "This file is being ingested; try again shortly.")
    storage = storage or get_storage()
    draft = get_or_create_draft_revision(context.db, bot, context.user.id)
    context.db.execute(
        delete(Chunk).where(
            Chunk.tenant_id == context.tenant_id,
            Chunk.revision_id == draft.id,
            Chunk.source_id == source.id,
        )
    )
    context.db.execute(
        delete(Document).where(
            Document.tenant_id == context.tenant_id,
            Document.revision_id == draft.id,
            Document.source_id == source.id,
        )
    )
    context.db.execute(
        delete(SourcePage).where(
            SourcePage.tenant_id == context.tenant_id, SourcePage.source_id == source.id
        )
    )
    storage_key = source.storage_key
    source.status = "removed"
    source.error = None
    source.size_bytes = 0  # the file is gone: its bytes stop counting against the quota
    ids = [value for value in always_include_source_ids(bot) if value != str(source.id)]
    _write_always_include(bot, ids)
    record_audit(
        context.db,
        action="knowledge.source_removed",
        tenant_id=context.tenant_id,
        actor_user_id=context.user.id,
        target_type="source",
        target_id=str(source.id),
    )
    context.db.commit()
    storage.delete(storage_key)


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


def list_revisions(
    context: TenantContext, bot_id: UUID, settings: Settings | None = None
) -> list[dict[str, object]]:
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
    try:
        configured: str | None = configured_identity(settings or get_settings())
    except EmbeddingError:
        configured = None
    fts_only = bot.retrieval_mode == "fts_only"
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
        identity = revision.embedding_model or configured
        embedded = 0
        if identity and chunk_count:
            embedded = int(
                context.db.execute(
                    select(func.count())
                    .select_from(Chunk)
                    .where(
                        Chunk.tenant_id == context.tenant_id,
                        Chunk.revision_id == revision.id,
                        Chunk.embedding.is_not(None),
                        Chunk.embedding_model == identity,
                    )
                ).scalar_one()
            )
        ready = revision.embedding_model is not None
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
                "embedding": {
                    "ready": ready,
                    "embedded_chunks": embedded,
                    "chunk_count": chunk_count,
                    "retrieval_mode": "hybrid" if ready and not fts_only else "keyword_only",
                },
            }
        )
    return result


# --- publish / rollback ----------------------------------------------------


def publish_revision(
    context: TenantContext, bot_id: UUID, revision_id: UUID, settings: Settings | None = None
) -> dict[str, object]:
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
    sync_bot_readiness(context.db, bot)
    try:
        context.db.commit()
    except Exception:  # noqa: BLE001 - concurrent publish raced the unique index
        context.db.rollback()
        raise ApiError(409, "CONFLICT", "The revision pointer changed concurrently.") from None
    embedding_ready = revision.embedding_model is not None
    if not embedding_ready:
        # Publishing never waits for vectors: FTS serves the revision meanwhile and
        # the backfill (re)embeds it (this also covers a rollback to an archived one).
        try:
            queue_backfill(context.db, context.tenant_id, bot.id, settings or get_settings())
            context.db.commit()
        except (ApiError, EmbeddingError):
            context.db.rollback()
            logger.warning("publish.backfill_not_queued bot=%s", bot.id)
    return {
        "revision_id": str(revision.id),
        "status": "published",
        "changed": True,
        "embedding_ready": embedding_ready,
        "retrieval_mode": "hybrid" if embedding_ready else "keyword_only",
    }
