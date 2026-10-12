"""Shared P2 helpers: settings, uploads, and running the ingest job in-process."""

from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session as OrmSession

from app.core.config import Settings
from app.db.models import Job
from app.jobs.queue import claim_job
from app.jobs.runner import execute_claimed_job
from app.knowledge.storage import LocalStorage
from tests.conftest import SESSION_SETTINGS

FIXTURES = Path(__file__).parent / "fixtures"
MD_EN = FIXTURES / "skill-output" / "pages" / "001-services.md"
MD_AR = FIXTURES / "skill-output" / "pages" / "002-faq-ar.md"
QA_CSV = FIXTURES / "skill-output" / "qa.csv"
COVERAGE_MD = FIXTURES / "skill-output" / "coverage.md"


def upload_settings(storage_root: Path) -> Settings:
    """Settings for upload/ingest flows with storage rooted in a temp directory."""
    values: dict[str, Any] = dict(SESSION_SETTINGS)
    values.update(
        database_url="postgresql://worker/chatbot_dev_test",
        storage_root=str(storage_root),
        parse_timeout_seconds=60,
        chunk_size=1500,
        chunk_overlap=200,
        job_backoff_seconds=1,
        job_max_attempts=3,
    )
    return Settings.model_construct(**values)


def upload_sources(
    users: Any,
    bot_id: UUID | str,
    files: list[tuple[str, bytes]],
    tmp_root: Path,
    as_role: str = "owner",
) -> Any:
    """POST the files to /sources/files; returns the raw response."""
    client = users.as_user(as_role)
    payload = [("files", (name, data, "application/octet-stream")) for name, data in files]
    return client.post(
        f"/api/v1/tenants/{users.tenant_id}/bots/{bot_id}/sources/files",
        files=payload,
        headers={"X-CSRF-Token": _csrf(client)},
    )


def _csrf(client: TestClient) -> str:
    token = client.cookies.get("chatbot_csrf")
    assert isinstance(token, str)
    return token


def start_ingestion(
    users: Any,
    bot_id: UUID | str,
    source_ids: list[UUID | str] | None = None,
    as_role: str = "owner",
) -> Any:
    client = users.as_user(as_role)
    body: dict[str, Any] = {}
    if source_ids is not None:
        body = {"source_ids": [str(value) for value in source_ids]}
    return client.post(
        f"/api/v1/tenants/{users.tenant_id}/bots/{bot_id}/ingestion",
        json=body,
        headers={"X-CSRF-Token": _csrf(client)},
    )


def run_one_ingest_job(engine: Any, tmp_root: Path, db: OrmSession | None = None) -> Job:
    """Claim + execute one pending ingest job like the real worker loop does."""
    settings = upload_settings(tmp_root)
    storage = LocalStorage(settings)
    session = _worker_session(engine)
    try:
        job = claim_job(session, "worker-test", settings)
        if job is None:
            raise AssertionError("No pending job to claim — nothing was enqueued.")
        execute_claimed_job(session, job, settings, storage)
        return job
    finally:
        session.close()


def _worker_session(engine: Any) -> OrmSession:
    from app.db.session import session_factory

    return session_factory(engine)()


def drain_jobs(engine: Any, tmp_root: Path) -> list[Job]:
    """Run every pending (or expired-lease) job until the queue is idle."""
    from app.db.session import session_factory

    settings = upload_settings(tmp_root)
    storage = LocalStorage(settings)
    session = session_factory(engine)()
    jobs: list[Job] = []
    try:
        while True:
            job = claim_job(session, "worker-test", settings)
            if job is None:
                break
            execute_claimed_job(session, job, settings, storage)
            jobs.append(job)
    finally:
        session.close()
    return jobs


def run_jobs_to_completion(
    engine: Any, tmp_root: Path, db: OrmSession, max_rounds: int = 5
) -> list[Job]:
    """Drain the queue, collapsing retry backoffs (sets run_at to now) until all
    jobs are in a terminal state (succeeded/failed/cancelled)."""

    terminal: list[Job] = []
    for _ in range(max_rounds):
        db.execute(text("UPDATE jobs SET run_at = NOW() WHERE status = 'pending'"))
        db.commit()
        round_jobs = drain_jobs(engine, tmp_root)
        if not round_jobs:
            break
        terminal.extend(round_jobs)
        if all(job.status in ("succeeded", "failed", "cancelled") for job in round_jobs):
            break
    return terminal
