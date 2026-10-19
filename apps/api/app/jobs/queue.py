"""Durable Postgres job queue (ADR-011, P2-01).

- Atomic claim: ``SELECT ... FOR UPDATE SKIP LOCKED`` — two workers can never
  claim the same job, and a crashed worker's expired lease is reclaimed.
- Lease: the claim sets ``lease_expires_at``; a lost worker's job becomes
  claimable again once the lease lapses (retry via a fresh claim + backoff).
- Retry: a failed claim keeps the job pending with exponential backoff until
  ``max_attempts`` is reached, then fails it permanently.
- Cancel: ``cancel_requested``; pending jobs are cancelled at once, running
  jobs check the flag between units of work.
Job payloads hold ids only — never secrets or file contents.
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.core.config import Settings
from app.core.errors import ApiError
from app.db.models import Job

# Claimable states: plain pending, or a running job whose lease has expired
# (the lease expiry is enforced in the WHERE clause directly).


def enqueue_job(
    db: OrmSession,
    *,
    tenant_id: UUID,
    bot_id: UUID,
    job_type: str,
    payload: dict[str, Any],
    created_by: UUID | None,
    settings: Settings,
) -> Job:
    """Create one pending job (caller commits)."""
    job = Job(
        id=uuid4(),
        tenant_id=tenant_id,
        bot_id=bot_id,
        type=job_type,
        payload=payload,
        status="pending",
        attempts=0,
        max_attempts=settings.job_max_attempts,
        run_at=datetime.now(UTC),
        created_by=created_by,
    )
    db.add(job)
    db.flush()
    return job


class JobClaim:
    """The outcome of a claim attempt."""

    __slots__ = ("job", "cancelled")

    def __init__(self, job: Job | None, *, cancelled: bool = False) -> None:
        self.job = job
        self.cancelled = cancelled


def claim_job(db: OrmSession, worker_id: str, settings: Settings) -> Job | None:
    """Atomically claim one runnable job for ``worker_id``; returns None if idle.

    Cancel requests on still-pending jobs are resolved here instead
    (the job never runs).
    """
    now = datetime.now(UTC)
    job = db.execute(
        select(Job)
        .where(
            (Job.status == "pending") & (Job.run_at <= now)
            | (Job.status == "running") & (Job.lease_expires_at < now)
        )
        .order_by(Job.created_at, Job.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    ).scalar_one_or_none()
    if job is None:
        return None
    if job.cancel_requested:
        job.status = "cancelled"
        job.finished_at = now
        job.error = None if job.started_at is None else job.error
    else:
        job.status = "running"
        job.attempts += 1
        job.lease_expires_at = now + timedelta(seconds=settings.job_lease_seconds)
        job.leased_by = worker_id
        job.started_at = now if job.started_at is None else job.started_at
    job.updated_at = now
    db.commit()
    return job if job.status == "running" else None


def release_job(
    db: OrmSession,
    job: Job,
    *,
    error: str | None,
    settings: Settings,
    retry_after_seconds: float | None = None,
) -> Job:
    """Finish a claimed job: success forever, failure retries with backoff.

    ``attempts`` was already incremented at claim time, so ``attempts`` here is
    the number of the attempt that just ended.
    """
    now = datetime.now(UTC)
    job.updated_at = now
    job.lease_expires_at = None
    job.leased_by = None
    if job.cancel_requested:
        job.status = "cancelled"
        job.finished_at = now
        job.error = error
        db.commit()
        return job
    if error is None:
        job.status = "succeeded"
        job.finished_at = now
        db.commit()
        return job
    if job.attempts >= job.max_attempts:
        job.status = "failed"
        job.finished_at = now
        job.error = error
        db.commit()
        return job
    # Retry with exponential backoff: 1x, 2x, 4x the base interval.
    backoff = settings.job_backoff_seconds * (2 ** max(0, job.attempts - 1))
    job.status = "pending"
    job.error = error
    job.run_at = now + timedelta(
        seconds=backoff if retry_after_seconds is None else retry_after_seconds
    )
    db.commit()
    return job


def requeue_for_retry(db: OrmSession, job: Job) -> Job:
    """Explicit user retry: a fresh cycle (attempts reset). Caller commits."""
    if job.status not in ("failed", "succeeded", "cancelled"):
        raise ApiError(409, "JOB_NOT_RETRYABLE", "Only a finished job can be retried.")
    now = datetime.now(UTC)
    job.status = "pending"
    job.error = None
    job.finished_at = None
    job.started_at = None
    job.lease_expires_at = None
    job.leased_by = None
    job.attempts = 0
    job.run_at = now
    job.updated_at = now
    db.add(job)
    return job


def request_cancel(db: OrmSession, job: Job) -> Job:
    """Cancel a pending job immediately; ask a running worker to abort."""
    if job.status in ("succeeded", "failed", "cancelled"):
        raise ApiError(409, "JOB_FINISHED", "The job already finished.")
    now = datetime.now(UTC)
    job.cancel_requested = True
    if job.status == "pending":
        job.status = "cancelled"
        job.finished_at = now
        job.error = None
    job.updated_at = now
    db.add(job)
    return job
