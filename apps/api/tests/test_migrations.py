"""P1-02: Alembic migrations upgrade/downgrade on a disposable database."""

import psycopg
from sqlalchemy import create_engine, insert, inspect, make_url
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
        # Upgrade a real legacy owner membership/invitation in place.
        run_migrations(url, upgrade_to="", downgrade_to="0012_quota_jobs")
        from datetime import UTC, datetime, timedelta
        from uuid import uuid4

        from sqlalchemy import text

        from app.db.models import Membership, Session, Tenant, User
        from scripts.seed_demo import demo_id

        uid, tid, iid = uuid4(), uuid4(), uuid4()
        legacy_demo_user = demo_id("user/owner")
        canonical_demo_user = demo_id("user/admin")
        demo_tid = demo_id("tenant")
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO users(id,email,password_hash,created_at) "
                    "VALUES (:id,'legacy@example.com','test',CURRENT_TIMESTAMP)"
                ),
                {"id": uid},
            )
            conn.execute(
                text(
                    "INSERT INTO tenants(id,name,slug,created_at) "
                    "VALUES (:id,'Legacy','legacy',CURRENT_TIMESTAMP)"
                ),
                {"id": tid},
            )
            conn.execute(
                text(
                    "INSERT INTO memberships(tenant_id,user_id,role,created_at) "
                    "VALUES (:tid,:uid,'owner',CURRENT_TIMESTAMP)"
                ),
                {"tid": tid, "uid": uid},
            )
            conn.execute(
                text(
                    "INSERT INTO invitations "
                    "(id,tenant_id,email,role,token_hash,expires_at,created_by,created_at) "
                    "VALUES (:id,:tid,'invite@example.com','owner','migration-test-token',"
                    "CURRENT_TIMESTAMP + INTERVAL '1 day',:uid,CURRENT_TIMESTAMP)"
                ),
                {"id": iid, "tid": tid, "uid": uid},
            )
        with engine.begin() as conn:
            conn.execute(
                insert(Tenant).values(
                    id=demo_tid, name="Demo Dental Clinic", slug="demo-dental-clinic"
                )
            )
            for user_id, role in [(legacy_demo_user, "owner"), (canonical_demo_user, "admin")]:
                conn.execute(
                    insert(User).values(
                        id=user_id,
                        email=f"demo-{role}@example.com",
                        password_hash="test-legacy-hash",
                    )
                )
                conn.execute(
                    insert(Membership).values(
                        tenant_id=demo_tid, user_id=user_id, role=role
                    )
                )
            conn.execute(
                insert(Session).values(
                    id=uuid4(),
                    token_hash="migration-demo-session",
                    user_id=legacy_demo_user,
                    expires_at=datetime.now(UTC) + timedelta(days=1),
                )
            )
        run_migrations(url)
        with engine.connect() as conn:
            legacy = conn.execute(
                text("SELECT role,status FROM memberships WHERE tenant_id=:tid AND user_id=:uid"),
                {"tid": demo_tid, "uid": legacy_demo_user},
            ).one()
            assert tuple(legacy) == ("admin", "revoked")
            assert (
                conn.execute(
                    text("SELECT status FROM memberships WHERE tenant_id=:tid AND user_id=:uid"),
                    {"tid": demo_tid, "uid": canonical_demo_user},
                ).scalar_one()
                == "active"
            )
            assert (
                conn.execute(
                    text("SELECT revoked_at FROM sessions WHERE user_id=:uid"),
                    {"uid": legacy_demo_user},
                ).scalar_one()
                is not None
            )
            assert (
                conn.execute(
                    text("SELECT password_hash FROM users WHERE id=:uid"), {"uid": legacy_demo_user}
                ).scalar_one()
                == "!retired-demo-login"
            )
            assert (
                conn.execute(
                    text("SELECT role FROM memberships WHERE tenant_id=:id"), {"id": tid}
                ).scalar_one()
                == "admin"
            )
            assert (
                conn.execute(
                    text("SELECT role FROM invitations WHERE id=:id"), {"id": iid}
                ).scalar_one()
                == "admin"
            )
            assert {"change_requests", "organization_deletions"} <= set(
                inspect(engine).get_table_names()
            )
    finally:
        engine.dispose()  # release pooled connections before dropping the database
        with psycopg.connect(
            make_url(url).set(database="postgres").render_as_string(hide_password=False),
            autocommit=True,
        ) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{MIGRATION_DB}"')
