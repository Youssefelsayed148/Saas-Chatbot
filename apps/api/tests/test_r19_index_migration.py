"""Verify the existing 0030 expression index through actual Alembic transitions."""

import os
from uuid import uuid4

from alembic.config import Config
from sqlalchemy import create_engine, text

from alembic import command
from app.db.session import sqlalchemy_url
from tests.conftest import API_DIR, create_database, disposable_url, run_migrations


def test_health_lookup_index_roundtrip_and_head_drift(base_url: str) -> None:
    name = "many_test_r19_index_" + uuid4().hex[:8] + "_test"
    url = disposable_url(base_url, name)
    assert os.environ["APP_ENV"] == "test" and os.environ["PGHOST"].startswith("/var/tmp/saas-r19-")
    create_database(base_url, name)
    run_migrations(url, upgrade_to="0029_channel_event_payload_purge")
    engine = create_engine(sqlalchemy_url(url))

    def definition() -> str | None:
        with engine.connect() as db:
            return db.scalar(
                text(
                    "SELECT indexdef FROM pg_indexes WHERE schemaname='public' AND indexname='ix_jobs_channel_health_poll_last'"
                )
            )

    assert definition() is None
    run_migrations(url, upgrade_to="0030_channel_health_poll_index")
    index = definition()
    assert index is not None
    assert "tenant_id" in index and "payload ->> 'connection_id'" in index and "created_at" in index
    assert "channel_health_poll" in index
    run_migrations(url, upgrade_to="", downgrade_to="0029_channel_event_payload_purge")
    assert definition() is None
    run_migrations(url)
    config = Config(API_DIR / "alembic.ini")
    config.set_main_option("script_location", str(API_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", sqlalchemy_url(url))
    command.check(config)
    engine.dispose()
