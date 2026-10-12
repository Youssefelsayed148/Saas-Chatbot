"""Engine and session wiring. SQLAlchemy 2.0 with the psycopg3 driver (ADR-003)."""

from collections.abc import Iterator

from sqlalchemy import Engine, create_engine, make_url
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings


def sqlalchemy_url(database_url: str) -> str:
    """Force the psycopg3 dialect; raw postgresql:// would default to psycopg2, which is absent."""
    url = make_url(database_url)
    url = url.set(drivername="postgresql+psycopg")
    return url.render_as_string(hide_password=False)


def create_db_engine(settings: Settings) -> Engine:
    if settings.database_url is None:
        raise RuntimeError("DATABASE_URL is not configured.")
    return create_engine(
        sqlalchemy_url(settings.database_url.get_secret_value()),
        pool_pre_ping=True,
        # Bounded pool for a modular monolith; timeouts are enforced by Postgres itself.
        pool_size=5,
        max_overflow=5,
    )


_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_db_engine(get_settings())
    return _engine


def set_engine(engine: Engine | None) -> None:
    """Used by tests to swap the engine for a disposable database."""
    global _engine
    _engine = engine


def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """FastAPI dependency: one session per request."""
    with session_factory(get_engine())() as session:
        yield session
