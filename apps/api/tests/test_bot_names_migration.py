"""#9: the legacy bots.name is copied into config.assistant_name without data loss."""

from sqlalchemy import Connection, create_engine, text

from app.db.session import sqlalchemy_url
from tests.conftest import create_database, disposable_url, run_migrations

TENANT = "22222222-2222-4222-8222-222222222222"


def _bot(connection: Connection, bot_id: str, name: str, config: str) -> None:
    connection.execute(
        text(
            "INSERT INTO bots(id,tenant_id,name,status,config,created_at,updated_at) "
            "VALUES (:id,:tenant,:name,'draft',CAST(:config AS jsonb),"
            "CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
        ),
        {"id": bot_id, "tenant": TENANT, "name": name, "config": config},
    )


def test_bot_name_backfill_keeps_existing_values(base_url: str) -> None:
    name = "bot_names_migration_test"
    create_database(base_url, name)
    url = disposable_url(base_url, name)
    run_migrations(url, upgrade_to="0017_staff_members", downgrade_to="base")
    engine = create_engine(sqlalchemy_url(url))
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO tenants(id,name,slug,created_at) "
                    f"VALUES ('{TENANT}','Org','org-names',CURRENT_TIMESTAMP)"
                )
            )
            _bot(connection, "aaaaaaaa-0000-4000-8000-000000000001", "Legacy", "{}")
            _bot(
                connection,
                "aaaaaaaa-0000-4000-8000-000000000002",
                "Old name",
                '{"assistant_name": "Aida", "colour": "#112233"}',
            )
            _bot(
                connection,
                "aaaaaaaa-0000-4000-8000-000000000003",
                "Blank assistant",
                '{"assistant_name": "  ", "business_name": "Shop"}',
            )
        run_migrations(url)
        with engine.connect() as connection:
            rows = {
                str(row[0]): (row[1], row[2])
                for row in connection.execute(text("SELECT id, name, config FROM bots"))
            }
        legacy = rows["aaaaaaaa-0000-4000-8000-000000000001"]
        assert legacy[0] == "Legacy" and legacy[1] == {"assistant_name": "Legacy"}
        kept = rows["aaaaaaaa-0000-4000-8000-000000000002"]
        assert kept[1] == {"assistant_name": "Aida", "colour": "#112233"}
        blank = rows["aaaaaaaa-0000-4000-8000-000000000003"]
        assert blank[1] == {"assistant_name": "Blank assistant", "business_name": "Shop"}
    finally:
        engine.dispose()
        run_migrations(url, upgrade_to="", downgrade_to="base")
