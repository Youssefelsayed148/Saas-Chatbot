"""P2-01: the DB job queue — atomic claim, lease/lease-expiry retry, cancel,
and tenant/bot re-validation of the ingest handler."""

import threading
import uuid as uuid_module
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.core.config import Settings
from app.db.models import Bot, Job, Tenant
from app.jobs.queue import (
    claim_job,
    enqueue_job,
    release_job,
    request_cancel,
    requeue_for_retry,
)
from app.jobs.runner import execute_claimed_job


def job_settings() -> Settings:
    # Test settings without a real DB (the queue does not open connections).
    return Settings.model_construct(job_backoff_seconds=1)


def make_tenant_and_bot(db: OrmSession) -> tuple[Tenant, Bot]:
    """Seeds one tenant + bot (a plain helper, not a fixture — fixtures
    cannot be called directly and every call creates its own rows)."""
    tenant = Tenant(id=uuid4(), name="Job tenant", slug=f"jt-{uuid_module.uuid4().hex[:8]}")
    db.add(tenant)
    db.flush()  # the tenant row must exist before its bot's FK resolves
    bot = Bot(tenant_id=tenant.id, id=uuid4(), name="Job bot", status="active")
    db.add(bot)
    db.commit()
    return tenant, bot


def make_job(db: OrmSession, tenant_id: Any, bot_id: Any) -> Job:
    job = enqueue_job(
        db,
        tenant_id=tenant_id,
        bot_id=bot_id,
        job_type="ingest_batch",
        payload={"source_ids": []},
        created_by=None,
        settings=job_settings(),
    )
    db.commit()
    return job


def _worker_session(engine: Any) -> OrmSession:
    from app.db.session import session_factory

    return session_factory(engine)()


def test_job_foreign_bot_rejected_by_composite_fk(app: Any, db: OrmSession) -> None:
    """A job's (tenant_id, bot_id) pair must reference a bot of the same tenant."""
    tenant_a, _bot_a = make_tenant_and_bot(db)
    tenant_b = Tenant(id=uuid4(), name="Other", slug=f"jt-{uuid_module.uuid4().hex[:8]}")
    bot_b = Bot(tenant_id=tenant_b.id, id=uuid4(), name="B bot", status="active")
    db.add(tenant_b)
    db.flush()  # FK: tenants before bots
    db.add(bot_b)
    db.commit()
    # A "tenant A job" pointing at tenant B's bot violates the composite FK
    # (fk_jobs_tenant_bot) — such a row can never be inserted.
    foreign = Job(
        id=uuid4(),
        tenant_id=tenant_a.id,
        bot_id=bot_b.id,
        type="ingest_batch",
        payload={},
        status="pending",
    )
    db.add(foreign)
    with pytest.raises(Exception) as error:  # noqa: PT011 - IntegrityError expected
        db.commit()
    db.rollback()
    assert "fk_jobs_tenant_bot" in str(error.value)


def test_two_workers_never_claim_one_job(app: Any, db: OrmSession, engine: Any) -> None:
    tenant, bot = make_tenant_and_bot(db)
    job = make_job(db, tenant.id, bot.id)

    barrier = threading.Barrier(2)
    claimed: list[str] = []
    errors: list[str] = []

    def worker(worker_id: str) -> None:
        session = _worker_session(engine)
        try:
            barrier.wait(timeout=10)
            claimed_job = claim_job(session, worker_id, job_settings())
            if claimed_job is not None:
                claimed.append(str(claimed_job.id))
        except Exception as error:  # noqa: BLE001 - surface thread errors
            errors.append(repr(error))
        finally:
            session.close()

    threads = [threading.Thread(target=worker, args=(f"w{index}",)) for index in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert errors == []
    assert claimed == [str(job.id)]
    db.expire_all()
    winner = db.get(Job, job.id)
    assert winner is not None
    assert winner.status == "running"
    assert winner.leased_by in {"w0", "w1"}
    assert winner.attempts == 1


def test_crashed_job_lease_expiry_is_reclaimed_then_retries(app: Any, db: OrmSession) -> None:
    tenant, bot = make_tenant_and_bot(db)
    job = make_job(db, tenant.id, bot.id)

    # Worker A claims, then "crashes": the lease lapses unreleased.
    first = claim_job(db, "worker-crash", job_settings())
    assert first is not None and first.id == job.id
    first.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()

    # Worker B reclaims the expired-lease job (this is the retry mechanism).
    reclaimed = claim_job(db, "worker-b", job_settings())
    assert reclaimed is not None and reclaimed.id == job.id
    assert reclaimed.attempts == 2  # every claim counts as an attempt

    # A failing run schedules a retry with backoff until attempts run out.
    release_job(db, reclaimed, error="boom", settings=job_settings())
    db.expire_all()
    after_failure = db.get(Job, job.id)
    assert after_failure is not None
    assert after_failure.status == "pending"
    assert after_failure.attempts == 2
    assert after_failure.run_at > datetime.now(UTC)

    # Claim and fail once more → attempts == max_attempts → failed.
    # Fast-forward the backoff so the job is claimable again immediately.
    after_run = db.get(Job, job.id)
    assert after_run is not None
    after_run.run_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()
    third = claim_job(db, "worker-c", job_settings())
    assert third is not None
    release_job(db, third, error="boom again", settings=job_settings())
    db.expire_all()
    failed = db.get(Job, job.id)
    assert failed is not None
    assert failed.status == "failed"
    assert failed.error == "boom again"
    assert failed.finished_at is not None


def test_pending_job_run_at_gates_the_claim(app: Any, db: OrmSession) -> None:
    tenant, bot = make_tenant_and_bot(db)
    job = make_job(db, tenant.id, bot.id)
    job.run_at = datetime.now(UTC) + timedelta(minutes=5)
    db.commit()
    assert claim_job(db, "worker", job_settings()) is None
    job.run_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()
    claimed = claim_job(db, "worker", job_settings())
    assert claimed is not None and claimed.id == job.id


def test_cancel_pending_immediately_and_running_via_flag(app: Any, db: OrmSession) -> None:
    tenant, bot = make_tenant_and_bot(db)
    pending = make_job(db, tenant.id, bot.id)
    request_cancel(db, pending)
    db.commit()
    assert claim_job(db, "worker", job_settings()) is None
    db.expire_all()
    pending_row = db.get(Job, pending.id)
    assert pending_row is not None
    assert pending_row.status == "cancelled"

    running = make_job(db, tenant.id, bot.id)
    claimed = claim_job(db, "worker", job_settings())
    assert claimed is not None and claimed.id == running.id
    request_cancel(db, claimed)
    db.commit()  # the worker sees cancel_requested between units of work
    release_job(db, claimed, error=None, settings=job_settings())
    db.expire_all()
    running_row = db.get(Job, running.id)
    assert running_row is not None
    assert running_row.status == "cancelled"


def test_retry_resets_attempts(app: Any, db: OrmSession) -> None:
    tenant, bot = make_tenant_and_bot(db)
    job = make_job(db, tenant.id, bot.id)
    claimed = claim_job(db, "worker", job_settings())
    assert claimed is not None
    release_job(db, claimed, error=None, settings=job_settings())
    db.expire_all()
    succeeded = db.get(Job, job.id)
    assert succeeded is not None
    assert succeeded.status == "succeeded"
    row = db.get(Job, job.id)
    assert row is not None
    requeue_for_retry(db, row)
    db.commit()
    db.expire_all()
    requeued = db.get(Job, job.id)
    assert requeued is not None
    assert requeued.status == "pending"
    assert requeued.attempts == 0
    assert requeued.started_at is None


def test_ingest_job_revalidates_tenant_and_bot(app: Any, db: OrmSession) -> None:
    """run_ingest_batch refuses invalid tenant/bot targets without acting.

    The foreign-bot pairing is impossible at DB level (see the composite-FK
    test above), so the handler re-validation is exercised via the paths that
    a stored job row CAN carry: an archived bot and an archived tenant.
    """
    tenant, bot = make_tenant_and_bot(db)

    # Archived bot → permanent failure on the first attempt.
    bot.status = "archived"
    db.commit()
    archived_job = make_job(db, tenant.id, bot.id)
    claimed = claim_job(db, "worker", job_settings())
    assert claimed is not None
    execute_claimed_job(db, claimed, job_settings(), storage=None)  # type: ignore[arg-type]
    db.expire_all()
    finished = db.get(Job, archived_job.id)
    assert finished is not None
    assert finished.status == "failed"
    assert "archived" in (finished.error or "")
    assert finished.attempts >= finished.max_attempts

    # Archived tenant → permanent failure.
    tenant.status = "archived"
    db.commit()
    tenant_job = make_job(db, tenant.id, bot.id)
    claimed_tenant = claim_job(db, "worker", job_settings())
    assert claimed_tenant is not None
    execute_claimed_job(db, claimed_tenant, job_settings(), storage=None)  # type: ignore[arg-type]
    db.expire_all()
    tenant_failed = db.get(Job, tenant_job.id)
    assert tenant_failed is not None
    assert tenant_failed.status == "failed"
    assert "Tenant missing or archived" in (tenant_failed.error or "")


def test_jobs_are_listed_per_bot(app: Any, db: OrmSession) -> None:
    tenant, bot = make_tenant_and_bot(db)
    make_job(db, tenant.id, bot.id)
    rows = list(db.execute(select(Job).where(Job.tenant_id == tenant.id)).scalars())
    assert len(rows) == 1
    assert rows[0].status == "pending"
