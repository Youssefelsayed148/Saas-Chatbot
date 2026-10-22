"""P4-01: public widget API — locator config, visitor capability sessions,
the public message pipeline, abuse limits and bot-bound session isolation
(docs/09, docs/05 public rows, docs/14 §7).

Abuse/bot-scoped tests replace the usual tenant-A/B header tests on public
endpoints: sessions are capability-token scoped, the pipeline always
resolves the bot FROM the session (cross-bot misuse is impossible by
construction), rate limits are Postgres-backed fixed windows.

Tenant A/B isolation of the conversations created here is asserted at the
schema level (the conversation row carries the session's tenant) and the
dashboard-facing isolation is covered in test_conversations/test_p4_conversations.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session as OrmSession

import tests.retrieval_helpers as _rh  # noqa: F401 — registers the corpus fixture
from app.core.config import Settings, get_settings
from app.db.models import Bot, VisitorSession
from app.widget.service import hash_session_token
from tests.helpers import make_bot
from tests.knowledge_helpers import (
    drain_jobs,
    publish_draft,
    start_ingestion,
    upload_sources,
)
from tests.retrieval_helpers import MD_HOURS, retrieval_settings

corpus = _rh.corpus

WIDGET_SETTINGS_OVERRIDES = {
    "widget_sessions_per_minute_per_ip": 2,
    "widget_messages_per_minute": 3,
    "widget_daily_message_cap": 5,
    # The deterministic offline stub model (dev/test only): the public
    # pipeline must run without network/paid providers in tests.
    "chat_stub_model": True,
}


def rate_limited_settings() -> Settings:
    """Test settings with tightened widget abuse limits (docs/14 §7)."""
    values = dict(retrieval_settings().__dict__)
    values.update(WIDGET_SETTINGS_OVERRIDES)
    return Settings.model_construct(**values)


def _override_widget_settings(app: FastAPI) -> None:
    app.dependency_overrides[get_settings] = lambda: rate_limited_settings()


def app_client(app: FastAPI) -> TestClient:
    return TestClient(app)


def make_active_bot_with_knowledge(
    app: FastAPI,
    users: Any,
    db: OrmSession,
    name: str = "Public bot",
) -> dict[str, Any]:
    """Bot + published revision (through the REAL pipeline) + active status."""
    bot = make_bot(users, name)
    patched = users.call(
        "staff",
        "PATCH",
        f"/api/v1/tenants/{users.tenant_id}/bots/{bot['id']}",
        json={
            "config": {
                "assistant_name": "Aida",
                "business_name": "Acme Ltd",
                "default_language": "en",
            }
        },
    )
    assert patched.status_code == 200, patched.text
    storage_root = Path(retrieval_settings().storage_root)
    upload = upload_sources(users, bot["id"], [("hours.md", MD_HOURS.encode())], storage_root)
    assert upload.status_code == 201, upload.text
    start = start_ingestion(users, bot["id"])
    assert start.status_code == 202, start.text
    drain_jobs(_engine(), storage_root)
    publish_draft(users, bot["id"])
    _set_bot_status(db, users, bot_id=str(bot["id"]), status="active")
    return {**bot, "widget_locator": _locator_of(db, str(bot["id"]))}


def _engine() -> Any:
    from app.db.session import get_engine

    return get_engine()


def _set_bot_status(db: OrmSession, users: Any, *, bot_id: str, status: str) -> None:
    """draft→active is an admin action whose UI/API arrives in later tickets;
    scoped to the tenant (the UPDATE never touches other tenants' rows)."""
    db.execute(
        text(
            "UPDATE bots SET status = :status "
            "WHERE id = CAST(:b AS uuid) AND tenant_id = CAST(:t AS uuid)"
        ),
        {"status": status, "b": bot_id, "t": str(users.tenant_id)},
    )
    db.commit()
    db.expire_all()


def _locator_of(db: OrmSession, bot_id: str) -> str:
    row = db.get(Bot, UUID(bot_id))
    assert row is not None and row.widget_locator, "bot must carry a widget locator"
    return str(row.widget_locator)


# --- config ------------------------------------------------------------


def test_config_by_locator_returns_safe_fields_only(
    db: OrmSession, app: FastAPI, corpus: dict[str, Any]
) -> None:
    users = corpus["users_a"]
    bot = make_active_bot_with_knowledge(app, users, db)
    client = app_client(app)
    response = client.get(f"/api/public/v1/widgets/{bot['widget_locator']}/config")
    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is True
    config = payload["config"]
    assert config["assistant_name"] == "Aida"
    assert set(config) <= {
        "assistant_name",
        "bot_name",
        "business_name",
        "welcome_message",
        "opening_questions",
        "colour",
        "position",
        "avatar",
        "default_language",
        "dir",
    }
    # Internal config never leaks (docs/09: no tenant secrets in the embed).
    for secret_key in (
        "allowed_domains",
        "always_include_document_ids",
        "support_email",
        "support_phone",
    ):
        assert secret_key not in config


def test_invalid_locator_is_404_and_leaks_nothing(app: FastAPI) -> None:
    client = app_client(app)
    response = client.get("/api/public/v1/widgets/some-unknown-locator/config")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_session_boots_with_capability_token_and_config(
    db: OrmSession, app: FastAPI, corpus: dict[str, Any]
) -> None:
    users = corpus["users_a"]
    bot = make_active_bot_with_knowledge(app, users, db)
    client = app_client(app)
    response = client.post(
        f"/api/public/v1/widgets/{bot['widget_locator']}/sessions",
        json={"page_origin": "https://example.com/"},
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["session_id"]
    assert len(payload["token"]) >= 32  # capability token (single-use shown)
    assert datetime.fromisoformat(payload["expires_at"]) > datetime.now(UTC)
    assert payload["config"]["assistant_name"] == "Aida"
    # Only the SHA-256 of the token is stored (docs/06 session discipline).
    stored = db.get(VisitorSession, UUID(payload["session_id"]))
    assert stored is not None and stored.bot_id == UUID(bot["id"])
    assert stored.token_hash == hash_session_token(payload["token"])
    assert stored.token_hash != payload["token"]


# --- sessions: expiry, cross-bot misuse, disabled bot -------------------


def test_expired_session_is_rejected_with_specific_code(
    db: OrmSession, app: FastAPI, corpus: dict[str, Any]
) -> None:
    users = corpus["users_a"]
    bot = make_active_bot_with_knowledge(app, users, db)
    client = app_client(app)
    session = client.post(
        f"/api/public/v1/widgets/{bot['widget_locator']}/sessions", json={}
    ).json()
    row = (
        db.query(VisitorSession)
        .filter(VisitorSession.token_hash == hash_session_token(session["token"]))
        .one()
    )
    db.query(VisitorSession).filter(VisitorSession.id == row.id).update(
        {"expires_at": datetime.now(UTC) - timedelta(seconds=1)}
    )
    db.commit()
    response = client.post(
        f"/api/public/v1/sessions/{row.id}/messages",
        json={"text": "What are your opening hours?"},
        headers={"X-Session-Token": session["token"]},
    )
    assert response.status_code == 401, response.text
    assert response.json()["error"]["code"] == "SESSION_EXPIRED"


def test_cross_bot_session_misuse_is_never_possible(
    db: OrmSession, app: FastAPI, corpus: dict[str, Any]
) -> None:
    """A session token bound to bot A can never address bot B (or a made-up
    session): every public call resolves the bot FROM the session."""
    users = corpus["users_a"]
    bot_a = make_active_bot_with_knowledge(app, users, db, name="Bot A")
    bot_b = make_active_bot_with_knowledge(app, users, db, name="Bot B")
    client = app_client(app)
    session_a = client.post(
        f"/api/public/v1/widgets/{bot_a['widget_locator']}/sessions", json={}
    ).json()
    session_b = client.post(
        f"/api/public/v1/widgets/{bot_b['widget_locator']}/sessions", json={}
    ).json()
    # A's token carrying B's session id: 401, the thread is never reached.
    response = client.post(
        f"/api/public/v1/sessions/{session_b['session_id']}/messages",
        json={"text": "What are your opening hours?"},
        headers={"X-Session-Token": session_a["token"]},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "SESSION_INVALID"
    # A guessed session id: 401 regardless of the token.
    guessed = client.post(
        f"/api/public/v1/sessions/{uuid4()}/messages",
        json={"text": "hi"},
        headers={"X-Session-Token": session_a["token"]},
    )
    assert guessed.status_code == 401


def test_disabled_bot_is_controlled_for_config_and_messages(
    db: OrmSession, app: FastAPI, corpus: dict[str, Any]
) -> None:
    users = corpus["users_a"]
    bot = make_active_bot_with_knowledge(app, users, db, name="Pausable")
    session = client_session(app, bot["widget_locator"])
    _set_bot_status(db, users, bot_id=str(bot["id"]), status="paused")
    client = app_client(app)
    config = client.get(f"/api/public/v1/widgets/{bot['widget_locator']}/config")
    assert config.status_code == 200
    payload = config.json()
    assert payload["available"] is False
    assert payload["reason"] == "paused"
    response = client.post(
        f"/api/public/v1/sessions/{session['session_id']}/messages",
        json={"text": "What are your opening hours?"},
        headers={"X-Session-Token": session["token"]},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "BOT_PAUSED"
    # A bot without published knowledge is "not ready" (docs/18 P3 pattern).
    draft_bot = make_bot(users, "Draft only")
    _set_bot_status(db, users, bot_id=str(draft_bot["id"]), status="active")
    draft_config = client.get(
        f"/api/public/v1/widgets/{_locator_of(db, str(draft_bot['id']))}/config"
    )
    assert draft_config.json()["reason"] == "not_ready"
    draft_session = client.post(
        f"/api/public/v1/widgets/{_locator_of(db, str(draft_bot['id']))}/sessions", json={}
    )
    assert draft_session.status_code == 409
    assert draft_session.json()["error"]["code"] == "BOT_NOT_READY"


def client_session(app: FastAPI, locator: str, *, expect: int = 201) -> Any:
    client = app_client(app)
    response = client.post(f"/api/public/v1/widgets/{locator}/sessions", json={})
    assert response.status_code == expect, response.text
    return response.json()


def test_unallowed_domain_is_rejected_as_defence_signal(
    db: OrmSession, app: FastAPI, corpus: dict[str, Any]
) -> None:
    """Allowed-domain check: defence signal, not auth (docs/06/09) — the
    PAGE origin (sent by the loader script) is compared, not the iframe's."""
    users = corpus["users_a"]
    bot = make_active_bot_with_knowledge(app, users, db, name="Domainbound")
    patched = users.call(
        "staff",
        "PATCH",
        f"/api/v1/tenants/{users.tenant_id}/bots/{bot['id']}",
        json={"config": {"allowed_domains": ["example.com"]}},
    )
    assert patched.status_code == 200, patched.text
    client = app_client(app)
    good = client.post(
        f"/api/public/v1/widgets/{bot['widget_locator']}/sessions",
        json={"page_origin": "https://www.example.com/page"},
    )
    assert good.status_code == 201, good.text
    bad = client.post(
        f"/api/public/v1/widgets/{bot['widget_locator']}/sessions",
        json={"page_origin": "https://not-example.com/page"},
    )
    assert bad.status_code == 403
    assert bad.json()["error"]["code"] == "DOMAIN_NOT_ALLOWED"
    missing = client.post(f"/api/public/v1/widgets/{bot['widget_locator']}/sessions", json={})
    assert missing.status_code == 403


def test_allowed_domains_accept_bare_hostname_page_origin(
    db: OrmSession, app: FastAPI, corpus: dict[str, Any]
) -> None:
    """A2.1 (#32): the loader forwards the EMBEDDING page's location.hostname —
    a bare hostname — as page_origin. The match stays hostname-only, so bare
    hostnames, full origins and subdomains of an allowed entry all pass and
    non-listed hosts still fail."""
    users = corpus["users_a"]
    bot = make_active_bot_with_knowledge(app, users, db, name="Hostbound")
    patched = users.call(
        "staff",
        "PATCH",
        f"/api/v1/tenants/{users.tenant_id}/bots/{bot['id']}",
        json={"config": {"allowed_domains": ["example.com"]}},
    )
    assert patched.status_code == 200, patched.text
    client = app_client(app)
    for origin in ("example.com", "www.Example.COM", "example.com/some/path"):
        allowed = client.post(
            f"/api/public/v1/widgets/{bot['widget_locator']}/sessions",
            json={"page_origin": origin},
        )
        assert allowed.status_code == 201, allowed.text
    bad = client.post(
        f"/api/public/v1/widgets/{bot['widget_locator']}/sessions",
        json={"page_origin": "not-example.com"},
    )
    assert bad.status_code == 403
    assert bad.json()["error"]["code"] == "DOMAIN_NOT_ALLOWED"


# --- abuse limits ------------------------------------------------------


def test_session_creation_abuse_limit(db: OrmSession, app: FastAPI, corpus: dict[str, Any]) -> None:
    users = corpus["users_a"]
    bot = make_active_bot_with_knowledge(app, users, db, name="Abused")
    _override_widget_settings(app)
    locator = bot["widget_locator"]
    first = client_session(app, locator)
    second = client_session(app, locator)
    assert first["session_id"] != second["session_id"]
    third_response = app_client(app).post(f"/api/public/v1/widgets/{locator}/sessions", json={})
    assert third_response.status_code == 429
    assert third_response.json()["error"]["code"] == "RATE_LIMITED"


def test_message_rate_limit_window(db: OrmSession, app: FastAPI, corpus: dict[str, Any]) -> None:
    users = corpus["users_a"]
    bot = make_active_bot_with_knowledge(app, users, db, name="Slowdown")
    _override_widget_settings(app)
    session = client_session(app, bot["widget_locator"])
    client = app_client(app)
    for index in range(3):
        response = client.post(
            f"/api/public/v1/sessions/{session['session_id']}/messages",
            json={"text": f"What are your opening hours? ({index})"},
            headers={"X-Session-Token": session["token"]},
        )
        assert response.status_code == 201, (index, response.text)
    fourth = client.post(
        f"/api/public/v1/sessions/{session['session_id']}/messages",
        json={"text": "What are your opening hours? (4)"},
        headers={"X-Session-Token": session["token"]},
    )
    assert fourth.status_code == 429
    assert fourth.json()["error"]["code"] == "RATE_LIMITED"


def test_message_window_resets_next_window(
    db: OrmSession, app: FastAPI, corpus: dict[str, Any]
) -> None:
    """Fixed windows reset in Postgres (survives restarts/docs/14 §7): age
    the window row past its boundary directly, the next message passes."""
    users = corpus["users_a"]
    bot = make_active_bot_with_knowledge(app, users, db, name="Resetable")
    _override_widget_settings(app)
    session = client_session(app, bot["widget_locator"])
    client = app_client(app)
    for index in range(3):
        response = client.post(
            f"/api/public/v1/sessions/{session['session_id']}/messages",
            json={"text": f"What are your opening hours? ({index})"},
            headers={"X-Session-Token": session["token"]},
        )
        assert response.status_code == 201, response.text
    capped = client.post(
        f"/api/public/v1/sessions/{session['session_id']}/messages",
        json={"text": "What are your opening hours?"},
        headers={"X-Session-Token": session["token"]},
    )
    assert capped.status_code == 429
    db.execute(
        text("UPDATE rate_limit_counters SET window_start = 0 WHERE bucket_key LIKE 'widget:msg:%'")
    )
    db.commit()
    recovered = client.post(
        f"/api/public/v1/sessions/{session['session_id']}/messages",
        json={"text": "What are your opening hours?"},
        headers={"X-Session-Token": session["token"]},
    )
    assert recovered.status_code == 201, recovered.text


def test_daily_message_quota_hook(db: OrmSession, app: FastAPI, corpus: dict[str, Any]) -> None:
    """QUOTA_EXCEEDED comes from measured usage events, not a guess (the
    per-plan quota enforcement of P7 hooks the same counter)."""
    from app.chat.conversations import record_usage_event

    users = corpus["users_a"]
    bot = make_active_bot_with_knowledge(app, users, db, name="Quotaed")
    _override_widget_settings(app)
    for _ in range(5):
        record_usage_event(
            db,
            tenant_id=users.tenant_id,
            bot_id=bot["id"],
            kind="message",
            external_key=f"message:quota:{uuid4()}",
        )
    db.commit()
    session = client_session(app, bot["widget_locator"])
    client = app_client(app)
    response = client.post(
        f"/api/public/v1/sessions/{session['session_id']}/messages",
        json={"text": "What are your opening hours?"},
        headers={"X-Session-Token": session["token"]},
    )
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "QUOTA_EXCEEDED"


# --- grounded pipeline + thread ----------------------------------------


def test_message_endpoint_runs_the_pipeline_with_citations(
    db: OrmSession, app: FastAPI, corpus: dict[str, Any]
) -> None:
    users = corpus["users_a"]
    _override_widget_settings(app)  # stub model for the pipeline
    bot = make_active_bot_with_knowledge(app, users, db, name="Answerable")
    session = client_session(app, bot["widget_locator"])
    client = app_client(app)
    response = client.post(
        f"/api/public/v1/sessions/{session['session_id']}/messages",
        json={"text": "What are your opening hours?"},
        headers={"X-Session-Token": session["token"]},
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    ai = payload["ai_message"]
    assert ai["text"]
    assert ai["citations"] == []
    assert ai["can_answer"] is True
    assert ai["needs_human"] is False
    assert payload["kind"] == "answer"
    history = client.get(
        f"/api/public/v1/sessions/{session['session_id']}/messages",
        headers={"X-Session-Token": session["token"]},
    )
    assert history.status_code == 200
    rows = history.json()
    assert len(rows) == 2  # visitor + ai, oldest first
    assert rows[0]["sender_type"] == "visitor"
    assert rows[1]["sender_type"] == "ai"
    assert all(row["citations"] == [] for row in rows)


def test_widget_feedback_recorded_idempotently(
    db: OrmSession, app: FastAPI, corpus: dict[str, Any]
) -> None:
    users = corpus["users_a"]
    _override_widget_settings(app)  # stub model for the pipeline
    bot = make_active_bot_with_knowledge(app, users, db, name="Feedbackable")
    session = client_session(app, bot["widget_locator"])
    client = app_client(app)
    turn = client.post(
        f"/api/public/v1/sessions/{session['session_id']}/messages",
        json={"text": "What are your opening hours?"},
        headers={"X-Session-Token": session["token"]},
    )
    message_id = turn.json()["ai_message"]["id"]
    for _ in range(2):
        response = client.post(
            f"/api/public/v1/sessions/{session['session_id']}/messages/{message_id}/feedback",
            json={"rating": "up"},
            headers={"X-Session-Token": session["token"]},
        )
        assert response.status_code == 200
    counted = (
        db.execute(
            text(
                "SELECT count(*) FROM usage_events "
                "WHERE kind = 'feedback_up' AND message_id = CAST(:m AS uuid)"
            ),
            {"m": message_id},
        )
        .scalars()
        .one()
    )
    assert int(counted) == 1  # idempotent per message+session (docs/14 §7)


def test_conversation_rows_belong_to_the_session_tenant(
    db: OrmSession, app: FastAPI, corpus: dict[str, Any]
) -> None:
    """Isolation at the schema level: the website conversation carries the
    session's OWN tenant + bot, session-bound (composite FKs)."""
    users_a = corpus["users_a"]
    _override_widget_settings(app)  # stub model for the pipeline
    bot_a = make_active_bot_with_knowledge(app, users_a, db, name="AA")
    session_a = client_session(app, bot_a["widget_locator"])
    client = app_client(app)
    turn = client.post(
        f"/api/public/v1/sessions/{session_a['session_id']}/messages",
        json={"text": "What are your opening hours?"},
        headers={"X-Session-Token": session_a["token"]},
    )
    assert turn.status_code == 201
    row = db.execute(
        text(
            "SELECT c.tenant_id, c.channel, c.source, c.session_id IS NOT NULL "
            "FROM conversations c WHERE c.id = CAST(:i AS uuid)"
        ),
        {"i": turn.json()["conversation_id"]},
    ).first()
    assert row is not None
    assert str(row[0]) == str(users_a.tenant_id)
    assert row[1] == "website"
    assert row[2] == "website"
    assert row[3] is True
    assert str(row[0]) != str(corpus["users_b"].tenant_id)
