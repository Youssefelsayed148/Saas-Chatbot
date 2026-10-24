"""Test fixtures (P1-02).

Guard: tests may only touch disposable databases whose name ends with
``_test``. The database URL must be supplied explicitly through
``TEST_DATABASE_URL`` or ``DATABASE_URL``. Migrations run
via Alembic against that disposable database — never ``create_all``.
"""

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from pydantic import SecretStr
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import make_url, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session as OrmSession

from alembic import command
from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.session import create_db_engine, session_factory, set_engine, sqlalchemy_url

API_DIR = Path(__file__).resolve().parents[1]

# Force dotenv loading off before test modules import the application factory.
os.environ["ENVIRONMENT"] = "test"

SESSION_SETTINGS = {
    "environment": "test",
    "embedding_test_stub": True,
    # Plain-HTTP test client: Secure cookie would be dropped by httpx.
    "cookie_secure": False,
    "session_lifetime_seconds": 14 * 24 * 3600,
    "login_rate_limit_attempts": 5,
    "login_rate_limit_window_seconds": 300,
    # The API suite exercises existing tenant creation flows; feature-gate
    # behavior has explicit tests with the flag disabled.
    "self_serve_signup": True,
}


def _base_database_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "No DATABASE_URL/TEST_DATABASE_URL found; the disposable test database "
            "cannot be resolved."
        )
    return url


def disposable_url(base_url: str, db_name: str) -> str:
    """Attach a database name to a URL; refuse any name not ending with ``_test``."""
    if not db_name.endswith("_test"):
        raise RuntimeError(f"Refusing non-disposable test database name: {db_name!r}")
    url = make_url(base_url)
    return url.set(database=db_name).render_as_string(hide_password=False)


def create_database(base_url: str, db_name: str) -> None:
    """Create the disposable test database if it does not exist yet."""
    db_name = db_name  # name must satisfy the guard via disposable_url
    url = disposable_url(base_url, db_name)
    database = make_url(url).database
    assert database is not None and str(database).endswith("_test")
    maintenance_url = make_url(url).set(database="postgres").render_as_string(hide_password=False)
    import psycopg

    with psycopg.connect(maintenance_url, autocommit=True) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (database,)
        ).fetchone()
        if exists is None:
            conn.execute(f'CREATE DATABASE "{database}"')


def run_migrations(database_url: str, *, upgrade_to: str = "head", downgrade_to: str = "") -> None:
    """Run Alembic migrations programmatically against the disposable database."""
    config = Config(API_DIR / "alembic.ini")
    config.set_main_option("script_location", str(API_DIR / "alembic"))
    # Force the psycopg3 dialect for the migration engine as well.
    config.set_main_option("sqlalchemy.url", sqlalchemy_url(database_url))
    if downgrade_to:
        command.downgrade(config, downgrade_to)
    if upgrade_to:
        command.upgrade(config, upgrade_to)


def truncate_all(engine: Engine) -> None:
    tables = ", ".join(f'"{t}"' for t in sorted(Base.metadata.tables))
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE TABLE {tables} CASCADE"))


def build_test_settings(database_url: str | None = None, **overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "database_url": SecretStr(database_url) if database_url else None,
        **SESSION_SETTINGS,
    }
    values.update(overrides)
    return Settings.model_construct(**values)


@pytest.fixture(scope="session")
def base_url() -> Iterator[str]:
    """The development/base database URL (never used directly by tests)."""
    yield _base_database_url()


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    base_url = _base_database_url()
    main_url = disposable_url(base_url, str(make_url(base_url).database) + "_test")
    create_database(base_url, str(make_url(main_url).database))
    os.environ["DATABASE_URL"] = main_url
    os.environ["ENVIRONMENT"] = "test"
    get_settings.cache_clear()
    engine = create_db_engine(build_test_settings(main_url))
    set_engine(engine)
    run_migrations(main_url)
    yield engine
    set_engine(None)


@pytest.fixture(autouse=True)
def clean_tables(engine: Engine) -> Iterator[None]:
    """Every test starts with empty tables; leftovers from a failure are removed too."""
    yield
    truncate_all(engine)


@pytest.fixture(autouse=True)
def reset_embed_breaker() -> Iterator[None]:
    """The query-embedding circuit breaker is process memory: start every test closed."""
    from app.retrieval import hybrid

    hybrid.reset_embed_breaker()
    yield
    hybrid.reset_embed_breaker()


@pytest.fixture
def db(engine: Engine) -> Iterator[OrmSession]:
    """A raw session for direct DB manipulation in tests (cleaned by clean_tables)."""
    session = session_factory(engine)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def app(engine: Engine) -> Iterator[FastAPI]:
    from app.main import create_app

    application = create_app()
    application.dependency_overrides[get_settings] = lambda: build_test_settings()
    yield application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def csrf_headers(client: TestClient) -> dict[str, str]:
    """Build the double-submit CSRF header from the client's csrf cookie."""
    token = client.cookies.get("chatbot_csrf")
    if not token:
        raise RuntimeError("No CSRF cookie present; authenticate first.")
    return {"X-CSRF-Token": token}


__all__ = [
    "API_DIR",
    "SESSION_SETTINGS",
    "create_database",
    "csrf_headers",
    "disposable_url",
    "run_migrations",
    "build_test_settings",
    "truncate_all",
]
