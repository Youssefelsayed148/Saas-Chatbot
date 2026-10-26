"""Resumable per-bot embedding work in the existing durable Postgres queue."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import ColumnElement, case, func, or_, select, update
from sqlalchemy.orm import Session as OrmSession

from app.core.config import Settings
from app.core.errors import ApiError
from app.db.models import Bot, Chunk, Job, KnowledgeRevision, Tenant
from app.embeddings.providers import DIMENSION, EmbeddingError, configured_identity, from_settings
from app.jobs.queue import enqueue_job
from app.quotas.ai import metered_embed


class LeaseLost(Exception):
    """A replacement worker owns the job; the stale worker must not release it."""


def scoped_bot(db: OrmSession, tenant_id: UUID, bot_id: UUID, *, lock: bool = False) -> Bot:
    query = (
        select(Bot)
        .join(Tenant, Tenant.id == Bot.tenant_id)
        .where(Bot.tenant_id == tenant_id, Bot.id == bot_id, Tenant.status == "active")
    )
    if lock:
        query = query.with_for_update(of=Bot)
    bot = db.scalar(query.execution_options(populate_existing=True))
    if bot is None or bot.status == "archived":
        raise ApiError(404, "NOT_FOUND", "Resource not found.")
    return bot


def embedded_scope(tenant_id: UUID, bot_id: UUID) -> tuple[ColumnElement[bool], ...]:
    """Revisions worth embedding: the draft and the published one (never archived)."""
    return (
        KnowledgeRevision.tenant_id == tenant_id,
        KnowledgeRevision.bot_id == bot_id,
        KnowledgeRevision.status.in_(("draft", "published")),
    )


def sync_bot_readiness(db: OrmSession, bot: Bot) -> None:
    """Mirror the PUBLISHED revision's state onto the per-bot display fields."""
    db.flush()  # sessions here do not autoflush; the revision update must be visible
    model = None
    if bot.published_revision_id is not None:
        model = db.scalar(
            select(KnowledgeRevision.embedding_model).where(
                KnowledgeRevision.tenant_id == bot.tenant_id,
                KnowledgeRevision.bot_id == bot.id,
                KnowledgeRevision.id == bot.published_revision_id,
            )
        )
    if model:
        bot.active_embedding_model = model
    bot.embedding_ready = bool(model)


def queue_backfill(
    db: OrmSession,
    tenant_id: UUID,
    bot_id: UUID,
    settings: Settings,
    *,
    created_by: UUID | None = None,
    model: str | None = None,
) -> Job:
    scoped_bot(db, tenant_id, bot_id, lock=True)
    target = model or configured_identity(settings)
    provider, separator, model_name = target.partition(":")
    if (
        provider not in ("ollama", "openai", "openrouter")
        or not separator
        or not model_name.strip()
    ):
        raise ApiError(422, "VALIDATION_ERROR", "Unsupported embedding model identity.")
    active = db.scalar(
        select(Job)
        .where(
            Job.tenant_id == tenant_id,
            Job.bot_id == bot_id,
            Job.type == "reembed_backfill",
            Job.status.in_(("pending", "running")),
        )
        .with_for_update()
    )
    if active is not None:
        if active.payload.get("embedding_model") != target:
            raise ApiError(409, "BACKFILL_ACTIVE", "Finish or cancel the existing backfill first.")
        if not active.payload.get("scan_complete"):
            return active
        # A handler may have committed its final scan just before the queue
        # releases it. New content needs a successor, not that finished scan.
    # Queuing never touches live retrieval: readiness is recorded per revision.
    return enqueue_job(
        db,
        tenant_id=tenant_id,
        bot_id=bot_id,
        job_type="reembed_backfill",
        payload={
            "embedding_model": target,
            "embedding_dim": DIMENSION,
            "total": 0,
            "done": 0,
            "failed": 0,
        },
        created_by=created_by,
        settings=settings,
    )


def _current_job(db: OrmSession, job: Job, owner: str | None) -> Job:
    current = db.scalar(
        select(Job)
        .where(
            Job.tenant_id == job.tenant_id,
            Job.bot_id == job.bot_id,
            Job.id == job.id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if current is None or current.status != "running" or current.leased_by != owner:
        raise LeaseLost("Embedding worker lease is no longer owned by this worker.")
    return current


def _chunk_text(chunk: Chunk) -> str:
    return " ".join(part for part in (chunk.title, chunk.heading, chunk.text) if part)


def run_backfill(job: Job, db: OrmSession, settings: Settings) -> str | None:
    target = str(job.payload.get("embedding_model", ""))
    owner = job.leased_by
    # Bounded by config (le=128): 128 chunks of <=~1.9k chars stay under the
    # provider's per-request input-token limit even at one token per character.
    batch_size = settings.embedding_batch_size
    while True:
        # Match queue_backfill's Bot -> Job lock order to avoid a deadlock
        # between ingestion/operator requests and a completing worker.
        bot = scoped_bot(db, job.tenant_id, job.bot_id, lock=True)
        current = _current_job(db, job, owner)
        if current.cancel_requested:
            db.commit()
            return None
        scope = db.scalars(
            select(KnowledgeRevision).where(*embedded_scope(current.tenant_id, current.bot_id))
        ).all()
        base = (
            Chunk.tenant_id == current.tenant_id,
            Chunk.bot_id == current.bot_id,
            Chunk.revision_id.in_([revision.id for revision in scope]),
        )
        total = int(db.scalar(select(func.count()).select_from(Chunk).where(*base)) or 0)
        pending = or_(
            Chunk.embedding.is_(None),
            Chunk.embedding_model != target,
            Chunk.embedding_dim != DIMENSION,
        )
        # Published content first, so a rolled-back revision recovers hybrid soonest.
        live_first = case((Chunk.revision_id == bot.published_revision_id, 0), else_=1)
        chunks = db.scalars(
            select(Chunk).where(*base, pending).order_by(live_first, Chunk.id).limit(batch_size)
        ).all()
        remaining = int(
            db.scalar(select(func.count()).select_from(Chunk).where(*base, pending)) or 0
        )
        current.payload = {**current.payload, "total": total, "done": total - remaining}
        current.lease_expires_at = datetime.now(UTC) + timedelta(seconds=settings.job_lease_seconds)
        if not chunks:
            # A revision becomes ready only once every one of its chunks has the
            # target identity. Failed/cancelled work leaves other revisions untouched.
            for revision in scope:
                revision.embedding_model = target
            sync_bot_readiness(db, bot)
            current.payload = {**current.payload, "done": total, "failed": 0, "scan_complete": True}
            db.commit()
            return None
        captured = {chunk.id: chunk.content_hash for chunk in chunks}
        texts = [_chunk_text(chunk) for chunk in chunks]
        db.commit()  # provider I/O holds no row locks; the lease fences the write below
        try:
            batch = metered_embed(
                db,
                job.tenant_id,
                job.bot_id,
                settings,
                identity=target,
                texts=texts,
                embed=from_settings(settings, target).embed,
                event_type="embed_ingest",
                channel="ingestion",
            )
        except ApiError as error:
            db.rollback()
            return error.message
        except EmbeddingError:
            current = _current_job(db, job, owner)
            current.payload = {**current.payload, "failed": 1}
            db.commit()
            return "Embedding provider unavailable; completed chunks are preserved for retry."
        bot = scoped_bot(db, job.tenant_id, job.bot_id, lock=True)
        current = _current_job(db, job, owner)
        if current.cancel_requested:
            db.commit()
            return None
        locked = db.scalars(
            select(Chunk)
            .where(
                Chunk.tenant_id == current.tenant_id,
                Chunk.bot_id == current.bot_id,
                Chunk.id.in_(list(captured)),
            )
            .order_by(Chunk.id)
            .with_for_update()
        ).all()
        vectors = dict(zip(captured, batch.vectors, strict=True))
        written = 0
        touched: set[UUID] = set()
        for chunk in locked:
            if chunk.content_hash != captured[chunk.id]:
                continue
            chunk.embedding, chunk.embedding_model, chunk.embedding_dim = (
                vectors[chunk.id],
                target,
                DIMENSION,
            )
            touched.add(chunk.revision_id)
            written += 1
        if touched:
            # Rewriting chunks under a different identity ends that revision's
            # readiness in the same transaction as the write (invariant: a set
            # revision.embedding_model means all its chunks carry it).
            db.flush()
            db.execute(
                update(KnowledgeRevision)
                .where(
                    KnowledgeRevision.tenant_id == current.tenant_id,
                    KnowledgeRevision.id.in_(touched),
                    KnowledgeRevision.embedding_model.is_not(None),
                    KnowledgeRevision.embedding_model != target,
                )
                .values(embedding_model=None)
            )
            db.expire_all()
            bot = scoped_bot(db, job.tenant_id, job.bot_id)
            current = _current_job(db, job, owner)
            sync_bot_readiness(db, bot)
        previous_done = current.payload.get("done", 0)
        current.payload = {
            **current.payload,
            "done": (previous_done if isinstance(previous_done, int) else 0) + written,
            "failed": 0,
        }
        db.commit()  # per-batch checkpoint: a killed worker never loses committed progress
