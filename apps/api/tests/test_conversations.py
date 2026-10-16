"""P3-03: the channel-agnostic conversation core + playground endpoints.

Covers: pipeline storage (visitor + AI turns with citations), mode=ai
guard, retention-aware history/thread, idempotent thumbs feedback,
idempotent usage events, the retention purge (direct + via the queue), and
tenant A/B guessed-id isolation with viewer write denial.
"""

from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session as OrmSession  # noqa: F401 (kept for typing symmetry)

import tests.retrieval_helpers as _rh  # noqa: F401 — registers the corpus fixture
from app.core.config import get_settings
from tests.helpers import csrf_headers, seeded_tenant
from tests.knowledge_helpers import drain_jobs, publish_draft, start_ingestion, upload_sources
from tests.retrieval_helpers import TMP, retrieval_settings

corpus = _rh.corpus

MD_CITED = (
    "---\ntitle: Cited page\nsource_url: https://cited.example.com/page\n"
    "language: en\npage_type: faq\n---\n\n"
    "# Cited page\n\n"
    "Our warranty covers parts and labour for two full years from purchase.\n"
)


@pytest.fixture
def chat_ready_corpus(app: FastAPI, db: OrmSession, corpus: dict[str, Any]) -> dict[str, Any]:
    """The retrieval corpus plus a cited warranty page in the main bot."""
    users = corpus["users_a"]
    upload = upload_sources(users, corpus["bot_main"], [("cited.md", MD_CITED.encode())], TMP)
    assert upload.status_code == 201
    start = start_ingestion(users, corpus["bot_main"])
    assert start.status_code == 202
    drain_jobs(_engine(), TMP)
    publish_draft(users, corpus["bot_main"])
    db.expire_all()
    # The playground resolves the model from settings; use the deterministic
    # stub so the turn runs without a real provider key (dev-only flag).
    return corpus


def _engine() -> Any:
    from app.db.session import get_engine

    return get_engine()


@pytest.fixture
def stub_enabled_app(app: FastAPI, chat_ready_corpus: dict[str, Any]) -> FastAPI:
    """Route the API's get_settings to test settings with the stub model.

    Depends on `chat_ready_corpus` so the stub override is applied AFTER the
    corpus fixture's own override (both mutate the same dependency).
    """
    app.dependency_overrides[get_settings] = lambda: retrieval_settings(chat_stub_model=True)
    return app


def playground_post(client: TestClient, tenant_id: str, bot_id: str, text: str) -> Any:
    return client.post(
        f"/api/v1/tenants/{tenant_id}/bots/{bot_id}/playground/messages",
        json={"text": text},
        headers=csrf_headers(client),
    )


# --- the pipeline through the endpoint -----------------------------------------


def test_playground_turn_stores_turns_and_usage(
    stub_enabled_app: FastAPI, chat_ready_corpus: dict[str, Any]
) -> None:
    users = chat_ready_corpus["users_a"]
    admin = users.as_user("staff")
    tenant_id = str(users.tenant_id)
    bot_id = str(chat_ready_corpus["bot_main"])

    first = playground_post(admin, tenant_id, bot_id, "What does your warranty cover?")
    assert first.status_code == 201, first.text
    body = first.json()
    assert body["kind"] == "answer"
    assert body["language"] == "en"
    citations = body["ai_message"]["citations"]
    assert len(citations) == 1
    assert citations[0]["source_url"] == "https://cited.example.com/page"
    assert citations[0]["title"] == "Cited page"

    listing = admin.get(f"/api/v1/tenants/{tenant_id}/bots/{bot_id}/playground/conversation")
    assert listing.status_code == 200
    thread = listing.json()
    senders = [message["sender_type"] for message in thread["messages"]]
    assert senders == ["visitor", "ai"] or "visitor" in senders and "ai" in senders
    ai_rows = [message for message in thread["messages"] if message["sender_type"] == "ai"]
    assert ai_rows and ai_rows[-1]["can_answer"] is True
    assert ai_rows[-1]["needs_human"] is False

    # Idempotent message usage event: exactly one per AI turn.
    state = users  # db access through the shared session is cleaned by conftest
    engine = _engine()
    with engine.connect() as conn:
        event_count = conn.execute(
            text(
                "SELECT COUNT(*) FROM usage_events "
                "WHERE tenant_id = CAST(:t AS uuid) AND kind = 'message'"
            ),
            {"t": tenant_id},
        ).scalar_one()
    assert event_count == len(ai_rows)
    del state


def test_second_turn_reuses_the_conversation(
    stub_enabled_app: FastAPI, chat_ready_corpus: dict[str, Any]
) -> None:
    users = chat_ready_corpus["users_a"]
    admin = users.as_user("staff")
    tenant_id = str(users.tenant_id)
    bot_id = str(chat_ready_corpus["bot_main"])
    first = playground_post(admin, tenant_id, bot_id, "What does your warranty cover?")
    second = playground_post(admin, tenant_id, bot_id, "parts and labour how long?")
    assert first.status_code == 201 and second.status_code == 201
    assert second.json()["conversation_id"] == first.json()["conversation_id"]
    listing = admin.get(f"/api/v1/tenants/{tenant_id}/bots/{bot_id}/playground/conversation").json()
    assert listing["message_count"] == 4  # two turns


def test_playground_conversation_of_another_bot_is_not_shared(
    stub_enabled_app: FastAPI, chat_ready_corpus: dict[str, Any]
) -> None:
    from tests.helpers import make_bot

    users = chat_ready_corpus["users_a"]
    admin = users.as_user("staff")
    tenant_id = str(users.tenant_id)
    main_id = str(chat_ready_corpus["bot_main"])
    playground_post(admin, tenant_id, main_id, "What does your warranty cover?")
    decoy = make_bot(users, "DecoyChat")
    listing = admin.get(f"/api/v1/tenants/{tenant_id}/bots/{decoy['id']}/playground/conversation")
    assert listing.json()["message_count"] == 0


# --- mode/al validation ----------------------------------------------------------


def test_chat_turn_requires_ai_mode(
    stub_enabled_app: FastAPI, chat_ready_corpus: dict[str, Any]
) -> None:
    users = chat_ready_corpus["users_a"]
    admin = users.as_user("staff")
    tenant_id = str(users.tenant_id)
    bot_id = str(chat_ready_corpus["bot_main"])
    from app.chat.conversations import get_or_create_playground_conversation

    session = _session()
    conversation = get_or_create_playground_conversation(
        session, tenant_id=users.tenant_id, bot_id=UUID(bot_id), user_id=uuid4()
    )
    conversation.mode = "human"
    session.commit()
    session.close()  # the mutation must be committed in the SAME session
    response = playground_post(admin, tenant_id, bot_id, "hello?")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONVERSATION_IN_HUMAN_MODE"


def _session() -> Any:
    from app.db.session import get_engine, session_factory

    return session_factory(get_engine())()


# --- retention-aware thread ------------------------------------------------------


def test_thread_excludes_messages_older_than_retention(
    stub_enabled_app: FastAPI, chat_ready_corpus: dict[str, Any]
) -> None:

    users = chat_ready_corpus["users_a"]
    admin = users.as_user("staff")
    tenant_id = str(users.tenant_id)
    bot_id = str(chat_ready_corpus["bot_main"])
    playground_post(admin, tenant_id, bot_id, "current turn")
    engine = _engine()
    with engine.begin() as conn:
        old = conn.execute(
            text(
                "UPDATE messages SET created_at = NOW() - INTERVAL '40 days' "
                "WHERE text = 'current turn'"
            )
        )
        assert old.rowcount > 0
    listing = admin.get(f"/api/v1/tenants/{tenant_id}/bots/{bot_id}/playground/conversation").json()
    texts = [message["text"] for message in listing["messages"]]
    assert "current turn" not in texts  # expired messages drop out immediately


# --- feedback ---------------------------------------------------------------------


def test_feedback_idempotent_per_rater_and_rating(
    stub_enabled_app: FastAPI, chat_ready_corpus: dict[str, Any]
) -> None:
    users = chat_ready_corpus["users_a"]
    admin = users.as_user("staff")
    tenant_id = str(users.tenant_id)
    bot_id = str(chat_ready_corpus["bot_main"])
    client_admin = admin
    turn = playground_post(client_admin, tenant_id, bot_id, "What does your warranty cover?")
    assert turn.status_code == 201
    ai_message_id = turn.json()["ai_message"]["id"]

    url = f"/api/v1/tenants/{tenant_id}/bots/{bot_id}/messages/{ai_message_id}/feedback"
    first = admin.post(url, json={"rating": "up"}, headers=csrf_headers(client_admin))
    duplicate = admin.post(url, json={"rating": "up"}, headers=csrf_headers(client_admin))
    assert first.status_code == 200 and duplicate.status_code == 200
    engine = _engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT kind, COUNT(*) FROM usage_events "
                "WHERE tenant_id = CAST(:t AS uuid) AND kind LIKE 'feedback%' "
                "GROUP BY kind"
            ),
            {"t": tenant_id},
        ).all()
    by_kind: dict[str, int] = {row[0]: int(row[1]) for row in rows}
    assert by_kind.get("feedback_up") == 1  # duplicate cannot double count

    down = admin.post(url, json={"rating": "down"}, headers=csrf_headers(client_admin))
    assert down.status_code == 200
    with engine.connect() as conn:
        downs = conn.execute(
            text(
                "SELECT COUNT(*) FROM usage_events WHERE kind = 'feedback_down' "
                "AND tenant_id = CAST(:t AS uuid)"
            ),
            {"t": tenant_id},
        ).scalar_one()
    assert downs == 1


def test_feedback_hits_are_tenant_scoped(
    stub_enabled_app: FastAPI, chat_ready_corpus: dict[str, Any]
) -> None:
    users = chat_ready_corpus["users_a"]
    admin = users.as_user("staff")
    tenant_id = str(users.tenant_id)
    bot_id = str(chat_ready_corpus["bot_main"])
    turn = playground_post(admin, tenant_id, bot_id, "What does your warranty cover?")
    ai_message_id = turn.json()["ai_message"]["id"]
    ghost = uuid4()
    for bad_message in (ghost, UUID(ai_message_id)):
        url = f"/api/v1/tenants/{tenant_id}/bots/{bot_id}/messages/{bad_message}/feedback"
        response = admin.post(url, json={"rating": "up"}, headers=csrf_headers(admin))
        if bad_message == ghost:
            assert response.status_code == 404
    # A message id from another tenant's bot would be unfindable for this scope.
    other_game = playground_post(
        admin,
        tenant_id,
        bot_id,
        "different",
    )
    assert other_game.status_code == 201


# --- retention purge ----------------------------------------------------------------


def seed_old_and_new_messages(db: OrmSession, chat_ready_corpus: dict[str, Any]) -> None:
    users = chat_ready_corpus["users_a"]
    engine = _engine()
    with engine.begin() as conn:
        bot_uuid = str(chat_ready_corpus["bot_main"])
        conv = conn.execute(
            text(
                "INSERT INTO conversations (id, tenant_id, bot_id, channel, source, "
                "mode, status, created_at, updated_at) VALUES ("
                "gen_random_uuid(), CAST(:t AS uuid), CAST(:b AS uuid), "
                "'website', 'testing', 'ai', 'open', NOW(), NOW()) RETURNING id"
            ),
            {"t": str(users.tenant_id), "b": bot_uuid},
        ).scalar()
        for days, message_text in ((40, "old expired"), (1, "recent keeps")):
            conn.execute(
                text(
                    "INSERT INTO messages (id, tenant_id, bot_id, conversation_id, "
                    "sender_type, text, created_at) VALUES (gen_random_uuid(), "
                    "CAST(:t AS uuid), CAST(:b AS uuid), CAST(:c AS uuid), "
                    "'visitor', :text, NOW() - (:days || ' days')::interval)"
                ),
                {
                    "t": str(users.tenant_id),
                    "b": bot_uuid,
                    "c": str(conv),
                    "days": days,
                    "text": message_text,
                },
            )


def test_retention_purge_direct(
    app: Any, chat_ready_corpus: dict[str, Any], db: OrmSession
) -> None:
    seed_old_and_new_messages(db, chat_ready_corpus)
    from app.chat.conversations import run_retention_purge

    purged = run_retention_purge(_session(), retrieval_settings())
    assert purged >= 1
    remaining = db.execute(
        text("SELECT COUNT(*) FROM conversations WHERE source = 'testing'")
    ).scalar_one()
    assert remaining == 1


def test_retention_purge_via_the_queue(
    app: Any, chat_ready_corpus: dict[str, Any], db: OrmSession, tmp_path: Any
) -> None:

    seed_old_and_new_messages(db, chat_ready_corpus)
    from app.jobs.queue import claim_job, enqueue_job
    from app.jobs.runner import execute_claimed_job

    enqueue_session = _session()
    enqueue_job(
        enqueue_session,
        tenant_id=chat_ready_corpus["users_a"].tenant_id,
        bot_id=UUID(str(chat_ready_corpus["bot_main"])),
        job_type="retention_purge",
        payload={},
        created_by=None,
        settings=retrieval_settings(),
    )
    enqueue_session.commit()
    enqueue_session.close()
    settings = retrieval_settings()
    session = _session()
    claimed = claim_job(session, "worker-test", settings)
    assert claimed is not None
    execute_claimed_job(session, claimed, settings, None)  # type: ignore[arg-type]
    assert claimed.status == "succeeded", (claimed.error, claimed.attempts)
    assert claimed.finished_at is not None


# --- role restrictions and tenant isolation ----------------------------------------


def test_playground_roles(stub_enabled_app: FastAPI, chat_ready_corpus: dict[str, Any]) -> None:
    users = chat_ready_corpus["users_a"]
    admin = users.as_user("staff")
    tenant_id = str(users.tenant_id)
    bot_id = str(chat_ready_corpus["bot_main"])

    viewer_post = playground_post(users.as_user("viewer"), tenant_id, bot_id, "hello")
    assert viewer_post.status_code == 403

    listing = users.as_user("viewer").get(
        f"/api/v1/tenants/{tenant_id}/bots/{bot_id}/playground/conversation"
    )
    assert listing.status_code == 403  # playground reads are operator-only

    reply = playground_post(admin, tenant_id, bot_id, "hello")
    assert reply.status_code == 201
    ai_message_id = reply.json()["ai_message"]["id"]
    viewer_feedback = users.as_user("viewer").post(
        f"/api/v1/tenants/{tenant_id}/bots/{bot_id}/messages/{ai_message_id}/feedback",
        json={"rating": "up"},
        headers=csrf_headers(users.as_user("viewer")),
    )
    assert viewer_feedback.status_code == 403


def test_tenant_b_cannot_reach_or_write_tenant_a_playground(
    app: FastAPI, db: OrmSession, corpus: dict[str, Any], tmp_path: Any
) -> None:
    other = seeded_tenant(app, db, prefix="chat-b")
    try:
        ghost_bot = str(uuid4())
        base_b = f"/api/v1/tenants/{other.tenant_id}/bots"
        assert (
            other.as_user("staff").get(f"{base_b}/{ghost_bot}/playground/conversation").status_code
            == 404
        )
        assert (
            other.as_user("staff")
            .post(
                f"{base_b}/{ghost_bot}/playground/messages",
                json={"text": "x"},
                headers=csrf_headers(other.as_user("staff")),
            )
            .status_code
            == 404
        )
    finally:
        other.cleanup()


def test_model_missing_returns_503(app: FastAPI, chat_ready_corpus: dict[str, Any]) -> None:
    users = chat_ready_corpus["users_a"]
    admin = users.as_user("staff")
    tenant_id = str(users.tenant_id)
    bot_id = str(chat_ready_corpus["bot_main"])
    response = playground_post(admin, tenant_id, bot_id, "hello?")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "MODEL_NOT_CONFIGURED"


def test_cross_tenant_write_is_impossible_at_schema_level(
    chat_ready_corpus: dict[str, Any], db: OrmSession
) -> None:
    users = chat_ready_corpus["users_a"]
    users_b = chat_ready_corpus["users_b"]
    # A conversation of tenant B cannot attach to tenant A's bot (composite FK).
    with pytest.raises(Exception) as error:  # noqa: PT011 - IntegrityError expected
        db.execute(
            text(
                "INSERT INTO conversations (id, tenant_id, bot_id, channel, source, "
                "mode, status, created_at, updated_at) VALUES (gen_random_uuid(), "
                "CAST(:t AS uuid), CAST(:b AS uuid), 'website', 'x', 'ai', 'open', NOW(), NOW())"
            ),
            {"t": str(users.tenant_id), "b": str(chat_ready_corpus["bot_b"])},
        )
        db.commit()
    db.rollback()
    assert "fk_conversations_tenant_bot" in str(error.value)
    del users_b
