"""Job execution dispatch (ADR-011): run one claimed job to completion.

Handler results become release decisions in the queue (success / retry with
backoff / failed). A ``JobFatal`` (tenant/bot re-validation) fails the job on
its first attempt — retrying cannot fix a foreign or archived target.
"""

from sqlalchemy.orm import Session as OrmSession

from app.core.config import Settings
from app.db.models import Job
from app.followups.service import mark_follow_up_ready
from app.jobs.queue import release_job
from app.knowledge.ingest import JobFatal, run_ingest_batch
from app.knowledge.storage import Storage


def execute_claimed_job(db: OrmSession, job: Job, settings: Settings, storage: Storage) -> None:
    """Run ``job`` (already claimed and status=running) and release it."""
    error: str | None
    try:
        error = _run(job, db, settings, storage)
        if job.cancel_requested:
            # Cancel wins even when the handler had already finished its work.
            error = None
    except JobFatal as fatal:
        # Permanent: the target tenant/bot is missing, archived or foreign.
        job.attempts = job.max_attempts
        error = str(fatal)
    except Exception:  # noqa: BLE001 - a broken job must never crash the worker
        db.rollback()
        error = "Unexpected error while running the job."
    release_job(db, job, error=error, settings=settings)


def _run(job: Job, db: OrmSession, settings: Settings, storage: Storage) -> str | None:
    if job.type == "ingest_batch":
        return run_ingest_batch(job, db, settings, storage)
    if job.type == "retention_purge":
        from app.chat.conversations import run_retention_purge

        purged = run_retention_purge(db, settings)
        print(f"jobs: retention purge removed {purged} message(s)", flush=True)
        return None
    if job.type == "follow_up_delivery":
        return mark_follow_up_ready(db, job)
    if job.type == "sentiment_classify":
        from app.quotas.sentiment import run_sentiment_job

        return run_sentiment_job(db, job, settings)
    return f"Unknown job type {job.type!r}."
