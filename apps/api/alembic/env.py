"""Alembic environment. Reads DATABASE_URL from app settings; never prints secrets."""

from logging.config import fileConfig

from sqlalchemy import pool

from alembic import context
from app.core.config import get_settings
from app.db.base import Base
from app.db.models import *  # noqa: F401,F403 - register all tables on metadata
from app.db.session import sqlalchemy_url

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def resolve_url() -> str:
    configured = config.get_main_option("sqlalchemy.url") or ""
    if configured:
        return configured
    settings = get_settings()
    if settings.database_url is None:
        raise RuntimeError("DATABASE_URL is not configured for Alembic.")
    return sqlalchemy_url(settings.database_url.get_secret_value())


def run_migrations_offline() -> None:
    context.configure(
        url=resolve_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    from sqlalchemy import create_engine

    engine = create_engine(resolve_url(), poolclass=pool.NullPool)

    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()

    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
