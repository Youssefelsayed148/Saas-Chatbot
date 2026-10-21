"""Account migration round trip on a dedicated disposable database."""

from sqlalchemy import create_engine, inspect, text

from app.db.session import sqlalchemy_url
from tests.conftest import create_database, disposable_url, run_migrations


def test_staff_members_migration_preserves_existing_users(base_url: str) -> None:
    name = "staff_members_migration_test"
    create_database(base_url, name)
    url = disposable_url(base_url, name)
    run_migrations(url, upgrade_to="0016_arabic_fts", downgrade_to="base")
    engine = create_engine(sqlalchemy_url(url))
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO users(id,email,password_hash,created_at) VALUES "
                    "('11111111-1111-4111-8111-111111111111',"
                    "'migration@example.com','fixture',CURRENT_TIMESTAMP)"
                )
            )
        run_migrations(url)
        with engine.connect() as connection:
            assert connection.execute(text("SELECT phone,is_active FROM users")).one() == (
                None,
                True,
            )
        run_migrations(url, upgrade_to="", downgrade_to="0016_arabic_fts")
        assert not {"phone", "is_active"} & {
            c["name"] for c in inspect(engine).get_columns("users")
        }
        run_migrations(url)
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT is_active FROM users")) is True
    finally:
        engine.dispose()
        run_migrations(url, upgrade_to="", downgrade_to="base")
