"""H1: knowledge_revisions.embedding_model migrates up/down/up and carries old readiness."""

from sqlalchemy import Connection, create_engine, text

from app.db.session import sqlalchemy_url
from tests.conftest import create_database, disposable_url, run_migrations

TENANT = "33333333-3333-4333-8333-333333333333"
BOT_READY = "bbbbbbbb-0000-4000-8000-000000000001"
BOT_PARTIAL = "bbbbbbbb-0000-4000-8000-000000000002"
MODEL = "openai:text-embedding-3-large"


def _columns(connection: Connection) -> set[str]:
    rows = connection.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'knowledge_revisions'"
        )
    )
    return {row[0] for row in rows}


def _seed(connection: Connection, bot_id: str, ready: bool, embed_all: bool) -> str:
    revision_id = bot_id.replace("bbbbbbbb", "cccccccc")
    document_id = bot_id.replace("bbbbbbbb", "dddddddd")
    connection.execute(
        text(
            "INSERT INTO bots(id,tenant_id,name,status,config,active_embedding_model,"
            "embedding_ready,created_at,updated_at) VALUES (:id,:t,'B','draft','{}',:model,"
            ":ready,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
        ),
        {"id": bot_id, "t": TENANT, "model": MODEL, "ready": ready},
    )
    connection.execute(
        text(
            "INSERT INTO knowledge_revisions(id,tenant_id,bot_id,status,created_at) "
            "VALUES (:r,:t,:b,'published',CURRENT_TIMESTAMP)"
        ),
        {"r": revision_id, "t": TENANT, "b": bot_id},
    )
    connection.execute(
        text(
            "INSERT INTO documents(id,tenant_id,bot_id,revision_id,source_id,title,heading,source_url,"
            "page_ref,ordinal,language,priority,text,total_chars,created_at) VALUES "
            "(:d,:t,:b,:r,gen_random_uuid(),'T','','','',0,'en',0,'x',1,CURRENT_TIMESTAMP)"
        ),
        {"d": document_id, "t": TENANT, "b": bot_id, "r": revision_id},
    )
    vector = "[" + ",".join(["0.5"] * 1024) + "]"
    connection.execute(
        text(
            "INSERT INTO chunks(id,tenant_id,bot_id,revision_id,source_id,document_id,title,heading,text,"
            "text_norm,language,priority,content_hash,ordinal,embedding,embedding_model,"
            "embedding_dim,created_at) VALUES (gen_random_uuid(),:t,:b,:r,gen_random_uuid(),:d,'T','','x','x','en',"
            "0,:h,0,CAST(:v AS vector),:m,1024,CURRENT_TIMESTAMP)"
        ),
        {
            "t": TENANT,
            "b": bot_id,
            "r": revision_id,
            "d": document_id,
            "h": "h-" + bot_id,
            "v": vector,
            "m": MODEL,
        },
    )
    if not embed_all:
        connection.execute(
            text(
                "INSERT INTO chunks(id,tenant_id,bot_id,revision_id,source_id,document_id,title,heading,"
                "text,text_norm,language,priority,content_hash,ordinal,created_at) VALUES "
                "(gen_random_uuid(),:t,:b,:r,gen_random_uuid(),:d,'T','','y','y','en',0,:h,1,CURRENT_TIMESTAMP)"
            ),
            {"t": TENANT, "b": bot_id, "r": revision_id, "d": document_id, "h": "p-" + bot_id},
        )
    return revision_id


def test_revision_embedding_state_migrates_up_down_up(base_url: str) -> None:
    name = "revision_embedding_migration_test"
    create_database(base_url, name)
    url = disposable_url(base_url, name)
    run_migrations(url, upgrade_to="0020_usage_event_unavailable", downgrade_to="base")
    engine = create_engine(sqlalchemy_url(url))
    try:
        with engine.begin() as connection:
            # Sources/users are irrelevant to this migration; skip their FK checks.
            connection.execute(text("SET session_replication_role = replica"))
            connection.execute(
                text(
                    "INSERT INTO tenants(id,name,slug,created_at) "
                    f"VALUES ('{TENANT}','Org','org-h1',CURRENT_TIMESTAMP)"
                )
            )
            ready_revision = _seed(connection, BOT_READY, ready=True, embed_all=True)
            partial_revision = _seed(connection, BOT_PARTIAL, ready=True, embed_all=False)
        run_migrations(url, upgrade_to="0021_revision_embedding_state")
        with engine.connect() as connection:
            assert "embedding_model" in _columns(connection)
            values: dict[str, str | None] = {
                str(row[0]): row[1]
                for row in connection.execute(
                    text("SELECT id::text, embedding_model FROM knowledge_revisions")
                )
            }
        assert values[ready_revision] == MODEL
        assert values[partial_revision] is None  # one chunk lacks a vector
        run_migrations(url, upgrade_to="", downgrade_to="0020_usage_event_unavailable")
        with engine.connect() as connection:
            assert "embedding_model" not in _columns(connection)
        run_migrations(url, upgrade_to="0021_revision_embedding_state")
        with engine.connect() as connection:
            assert "embedding_model" in _columns(connection)
    finally:
        with engine.begin() as connection:  # the 0014 downgrade refuses to drop RAG data
            connection.execute(text("SET session_replication_role = replica"))
            for table in ("chunks", "documents", "knowledge_revisions", "bots", "tenants"):
                connection.execute(text(f"DELETE FROM {table}"))
        engine.dispose()
        run_migrations(url, upgrade_to="", downgrade_to="base")
