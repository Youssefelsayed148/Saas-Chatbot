"""The P2 worker: ``python -m app.worker`` (ADR-011).

Same codebase/image as the API (no separate worker app, no Redis). Each loop
claims one runnable job (atomic FOR UPDATE SKIP LOCKED claim with a lease),
runs it, and releases the result (success, retry with backoff, or failure).
A heartbeat file powers the Compose healthcheck; SIGTERM stops after the
current job.
"""

import os
import signal
import socket
import sys
import time
import uuid
from datetime import UTC, datetime

from app.chat.conversations import run_retention_purge
from app.core.config import get_settings
from app.db.session import create_db_engine, session_factory, set_engine
from app.jobs.queue import claim_job
from app.jobs.runner import execute_claimed_job
from app.knowledge.storage import LocalStorage


def _check_database_guard() -> None:
    """Tests/E2E run the worker only against disposable ``_test`` databases."""
    settings = get_settings()
    if settings.database_url is None:
        print("worker: DATABASE_URL is not configured.", file=sys.stderr)
        raise SystemExit(1)
    database = (settings.database_url.get_secret_value().rsplit("/", 1)[-1]).split("?")[0]
    if settings.worker_allow_only_test_db and not database.endswith("_test"):
        print(
            "worker: refusing to run against a non-_test database "
            f"(WORKER_ALLOW_ONLY_TEST_DB is set): {database}",
            file=sys.stderr,
        )
        raise SystemExit(1)


def _heartbeat_file_touch() -> None:
    try:
        with open(get_settings().worker_heartbeat_file, "w", encoding="utf-8") as handle:
            handle.write(datetime.now(UTC).isoformat())
    except OSError:
        # A missing heartbeat file is a health concern, never a crash.
        pass


def _heartbeat_stale() -> None:
    try:
        from pathlib import Path

        Path(get_settings().worker_heartbeat_file).unlink(missing_ok=True)
    except OSError:
        pass


def main() -> None:
    settings = get_settings()
    _check_database_guard()
    engine = create_db_engine(settings)
    set_engine(engine)
    storage = LocalStorage(settings)
    worker_id = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
    stop = False

    def _stop(_signum: object, _frame: object) -> None:
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    print(f"worker: {worker_id} started", flush=True)
    last_purge = 0.0  # monotonic seconds; first purge runs after the interval
    started = time.monotonic()
    try:
        while not stop:
            _heartbeat_file_touch()
            if time.monotonic() - started - last_purge >= settings.retention_purge_interval_seconds:
                session = session_factory(engine)()
                try:
                    run_retention_purge(session, settings)
                finally:
                    session.close()
                last_purge = time.monotonic() - started
            session = session_factory(engine)()
            try:
                job = claim_job(session, worker_id, settings)
                if job is None:
                    _sleep(settings.worker_poll_seconds)
                    continue
                execute_claimed_job(session, job, settings, storage)
            finally:
                session.close()
    finally:
        set_engine(None)
        _heartbeat_stale()
        print(f"worker: {worker_id} stopped", flush=True)


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


if __name__ == "__main__":
    main()
