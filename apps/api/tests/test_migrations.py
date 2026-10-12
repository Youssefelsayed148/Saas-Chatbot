"""P1-02: Alembic migrations upgrade/downgrade on a disposable database."""

import psycopg
from sqlalchemy import create_engine, inspect, make_url
from sqlalchemy.engine import Engine

from app.db.session import sqlalchemy_url
from tests.conftest import create_database, disposable_url, run_migrations

MIGRATION_DB = "chatbot_dev_migration_test"
EXPECTED_TABLES = {
    "users",
    "sessions",
    "tenants",
    "memberships",
    "bots",
    "invitations",
    "audit_events",
    "alembic_version",
}


def test_migrations_up_down_cycle(base_url: str) -> None:
    url = disposable_url(base_url, MIGRATION_DB)
    with psycopg.connect(
        make_url(url).set(database="postgres").render_as_string(hide_password=False),
        autocommit=True,
    ) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{MIGRATION_DB}"')
    create_database(base_url, MIGRATION_DB)
    engine: Engine = create_engine(sqlalchemy_url(url))

    try:
        # --- upgrade head from an empty database ---
        run_migrations(url)
        tables = set(inspect(engine).get_table_names())
        assert EXPECTED_TABLES <= tables, f"missing tables: {EXPECTED_TABLES - tables}"

        # citext is a real column type on users.email (docs/04)
        with engine.connect() as conn:
            citext = conn.exec_driver_sql(
                "SELECT udt_name FROM information_schema.columns "
                "WHERE table_name='users' AND column_name='email'"
            ).scalar()
            assert citext == "citext"
            extension = conn.exec_driver_sql(
                "SELECT extname FROM pg_extension WHERE extname='citext'"
            ).scalar()
            assert extension == "citext"

        # --- downgrade base ---
        run_migrations(url, upgrade_to="", downgrade_to="base")
        tables = set(inspect(engine).get_table_names())
        assert tables == {"alembic_version"}, tables
        with engine.connect() as conn:
            extension = conn.exec_driver_sql(
                "SELECT extname FROM pg_extension WHERE extname='citext'"
            ).scalar()
            assert extension is None

        # --- upgrade head again (idempotent re-run) ---
        run_migrations(url)
        tables = set(inspect(engine).get_table_names())
        assert EXPECTED_TABLES <= tables
    finally:
        engine.dispose()  # release pooled connections before dropping the database
        with psycopg.connect(
            make_url(url).set(database="postgres").render_as_string(hide_password=False),
            autocommit=True,
        ) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{MIGRATION_DB}"')
