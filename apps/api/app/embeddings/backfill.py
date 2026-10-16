"""Resumable per-bot embedding work in the existing durable Postgres queue."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session as OrmSession

from app.core.config import Settings
from app.core.errors import ApiError
from app.db.models import Bot, Chunk, Job, Tenant
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


def queue_backfill(
    db: OrmSession,
    tenant_id: UUID,
    bot_id: UUID,
    settings: Settings,
    *,
    created_by: UUID | None = None,
    model: str | None = None,
) -> Job:
    bot = scoped_bot(db, tenant_id, bot_id, lock=True)
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
        if not bot.embedding_ready:
            return active
        # A handler may have committed its final pointer flip just before the
        # queue releases it. New ingestion needs a successor, not that finished scan.
    bot.embedding_ready = False
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


def run_backfill(job: Job, db: OrmSession, settings: Settings) -> str | None:
    target = str(job.payload.get("embedding_model", ""))
    owner = job.leased_by
    while True:
        # Match queue_backfill's Bot -> Job lock order to avoid a deadlock
        # between ingestion/operator requests and a completing worker.
        bot = scoped_bot(db, job.tenant_id, job.bot_id, lock=True)
        current = _current_job(db, job, owner)
        if current.cancel_requested:
            bot.embedding_ready = False
            db.commit()
            return None
        base = (Chunk.tenant_id == current.tenant_id, Chunk.bot_id == current.bot_id)
        total = int(db.scalar(select(func.count()).select_from(Chunk).where(*base)) or 0)
        pending = or_(
            Chunk.embedding.is_(None),
            Chunk.embedding_model != target,
            Chunk.embedding_dim != DIMENSION,
        )
        chunk = db.scalar(select(Chunk).where(*base, pending).order_by(Chunk.id).limit(1))
        remaining = int(
            db.scalar(select(func.count()).select_from(Chunk).where(*base, pending)) or 0
        )
        current.payload = {**current.payload, "total": total, "done": total - remaining}
        current.lease_expires_at = datetime.now(UTC) + timedelta(seconds=settings.job_lease_seconds)
        if chunk is None:
            # The pointer and ready flag become visible together only after every
            # chunk has the target identity. Failed/cancelled work keeps FTS serving.
            bot.active_embedding_model = target
            bot.embedding_ready = True
            current.payload = {**current.payload, "done": total, "failed": 0}
            db.commit()
            return None
        chunk_id, content_hash = chunk.id, chunk.content_hash
        text = " ".join(part for part in (chunk.title, chunk.heading, chunk.text) if part)
        db.commit()  # provider I/O holds no row locks; the lease fences the write below
        try:
            batch = metered_embed(
                db,
                job.tenant_id,
                job.bot_id,
                settings,
                identity=target,
                texts=[text],
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
        current = _current_job(db, job, owner)
        if current.cancel_requested:
            db.commit()
            return None
        chunk = db.scalar(
            select(Chunk)
            .where(
                Chunk.tenant_id == current.tenant_id,
                Chunk.bot_id == current.bot_id,
                Chunk.id == chunk_id,
                Chunk.content_hash == content_hash,
            )
            .with_for_update()
        )
        if chunk is not None:
            chunk.embedding, chunk.embedding_model, chunk.embedding_dim = (
                batch.vectors[0],
                target,
                DIMENSION,
            )
            previous_done = current.payload.get("done", 0)
            current.payload = {
                **current.payload,
                "done": (previous_done if isinstance(previous_done, int) else 0) + 1,
                "failed": 0,
            }
        db.commit()  # per-chunk checkpoint: a killed worker never loses committed progress
