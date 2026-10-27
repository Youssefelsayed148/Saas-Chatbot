"""P6-01 migration 0023 reversible round-trip preserving website rows."""

from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.db.models import Bot, Contact, ContactIdentity, Conversation, Tenant
from tests.conftest import run_migrations


def test_channel_migration_up_down_up_preserves_website_rows(db: Session, engine: Engine) -> None:
    tenant_id, bot_id, contact_id, conversation_id = uuid4(), uuid4(), uuid4(), uuid4()
    identity_id = uuid4()
    tenant = Tenant(id=tenant_id, name="P6 Migration", slug=f"p6-migration-{tenant_id.hex[:12]}")
    db.add(tenant)
    db.flush()
    bot = Bot(
        id=bot_id,
        tenant_id=tenant_id,
        name="Website bot",
        status="active",
        config={},
        widget_locator=f"w{uuid4().hex}",
    )
    db.add(bot)
    db.flush()
    contact = Contact(
        id=contact_id,
        tenant_id=tenant_id,
        display_name="Website visitor",
        email=f"visitor-{tenant_id.hex[:12]}@example.test",
    )
    conversation = Conversation(
        id=conversation_id,
        tenant_id=tenant_id,
        bot_id=bot_id,
        contact_id=contact_id,
        channel="website",
        connection_id=None,
        mode="ai",
        status="open",
        source="website",
    )
    identity = ContactIdentity(
        id=identity_id,
        tenant_id=tenant_id,
        contact_id=contact_id,
        channel="website",
        external_id=f"visitor-{tenant_id.hex}",
        connection_id=None,
    )
    db.add_all([contact, conversation, identity])
    db.commit()
    before = (tenant_id, bot_id, contact_id, conversation_id, identity_id)
    database_url = engine.url.render_as_string(hide_password=False)
    db.close()

    run_migrations(database_url, upgrade_to="", downgrade_to="0022_knowledge_hygiene")
    with engine.connect() as connection:
        version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        column_type = connection.execute(
            text(
                "SELECT data_type FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name='conversations' "
                "AND column_name='connection_id'"
            )
        ).scalar_one()
        website_row = connection.execute(
            text(
                "SELECT tenant_id, bot_id, contact_id, id, connection_id "
                "FROM conversations WHERE id = :id"
            ),
            {"id": conversation_id},
        ).one()
        identity_row = connection.execute(
            text(
                "SELECT id, tenant_id, contact_id, channel, external_id "
                "FROM contact_identities WHERE id=:id"
            ),
            {"id": identity_id},
        ).one()
    assert version == "0022_knowledge_hygiene"
    assert column_type == "text"
    assert tuple(website_row[:4]) == before[:4] and website_row.connection_id is None
    assert tuple(identity_row[:3]) == (identity_id, tenant_id, contact_id)
    assert identity_row.channel == "website"
    assert identity_row.external_id == f"visitor-{tenant_id.hex}"
    print("migration 0023 downgrade: at 0022, connection_id is text, website rows preserved")

    # main keeps the per-user playground key in the old text connection_id.
    playground_id = uuid4()
    playground_key = f"playground:{uuid4()}"
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO conversations (id, tenant_id, bot_id, channel, connection_id, "
                "mode, status, source, created_at, updated_at) SELECT :pid, tenant_id, bot_id, "
                "'website', :key, "
                "'ai', 'open', 'playground', now(), now() FROM conversations WHERE id = :id"
            ),
            {"pid": playground_id, "key": playground_key, "id": conversation_id},
        )

    run_migrations(database_url)
    with engine.connect() as connection:
        playground_row = connection.execute(
            text("SELECT connection_id, external_conversation_id FROM conversations WHERE id=:id"),
            {"id": playground_id},
        ).one()
    assert playground_row.connection_id is None
    assert playground_row.external_conversation_id == playground_key
    with engine.connect() as connection:
        version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        column_type = connection.execute(
            text(
                "SELECT data_type FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name='conversations' "
                "AND column_name='connection_id'"
            )
        ).scalar_one()
        website_row = connection.execute(
            text(
                "SELECT tenant_id, bot_id, contact_id, id, channel, source, connection_id "
                "FROM conversations WHERE id = :id"
            ),
            {"id": conversation_id},
        ).one()
        identity_row = connection.execute(
            text(
                "SELECT id, tenant_id, contact_id, channel, external_id, connection_id "
                "FROM contact_identities WHERE id=:id"
            ),
            {"id": identity_id},
        ).one()
        channel_tables = connection.execute(
            text(
                "SELECT count(*) FROM information_schema.tables WHERE table_schema='public' "
                "AND table_name IN ('channel_connections', 'channel_events')"
            )
        ).scalar_one()
    assert version == "0029_channel_event_payload_purge"
    assert column_type == "uuid"
    assert tuple(website_row[:4]) == before[:4]
    assert tuple(website_row[4:6]) == ("website", "website")
    assert website_row.connection_id is None
    assert tuple(identity_row[:3]) == (identity_id, tenant_id, contact_id)
    assert identity_row.channel == "website"
    assert identity_row.external_id == f"visitor-{tenant_id.hex}"
    assert identity_row.connection_id is None
    assert channel_tables == 2
    print("migration 0023 upgrade: UUID schema and channel tables created; website rows unchanged")
    print("migration 0023 upgrade again: completed at head with website rows unchanged")
