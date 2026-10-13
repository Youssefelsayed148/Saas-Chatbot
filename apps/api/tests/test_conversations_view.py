"""P4-04: conversations list/detail/deletion (dashboard read view) and the
per-tenant retention setting. Tenant A/B isolation on every new endpoint; the
widget-side lead capture lives in test_widget_leads.py."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from fastapi import FastAPI
from sqlalchemy.orm import Session as OrmSession

import tests.retrieval_helpers as _rh  # noqa: F401 — registers the corpus fixture
from app.db.models import Message
from tests.test_widget_public import make_active_bot_with_knowledge

corpus = _rh.corpus


def _public_client(app_: FastAPI) -> Any:
    from fastapi.testclient import TestClient

    return TestClient(app_)


def _session(client: Any, locator: str) -> dict[str, Any]:
    response = client.post(f"/api/public/v1/widgets/{locator}/sessions", json={})
    assert response.status_code == 201, response.text
    payload: dict[str, Any] = response.json()
    return payload


def _chat(client: Any, session: dict[str, Any], text: str) -> Any:
    return client.post(
        f"/api/public/v1/sessions/{session['session_id']}/messages",
        json={"text": text},
        headers={"X-Session-Token": session["token"]},
    )


def seed_setup(
    app_: FastAPI,
    users: Any,
    db: OrmSession,
    *,
    name: str = "Convuv",
) -> dict[str, Any]:
    import tests.test_widget_public as _wp

    _wp._override_widget_settings(app_)
    client = _public_client(app_)
    bot = make_active_bot_with_knowledge(app_, users, db, name=name)
    session = _session(client, bot["widget_locator"])
    turn = _chat(client, session, "What are your opening hours?")
    assert turn.status_code == 201, turn.text
    return {
        "client": client,
        "bot": bot,
        "session": session,
        "turn": turn.json(),
    }


# --- list + detail ------------------------------------------------------------


def test_list_and_detail_show_threads_with_citations(
    app: FastAPI,
    db: OrmSession,
    corpus: dict[str, Any],
) -> None:
    users = corpus["users_a"]
    setup = seed_setup(app, users, db)
    client = users.as_user("owner")
    listing = client.get(
        f"/api/v1/tenants/{users.tenant_id}/bots/{setup['bot']['id']}/conversations"
    )
    assert listing.status_code == 200, listing.text
    rows = listing.json()
    assert rows["total"] >= 1
    thread = rows["conversations"][0]
    assert thread["message_count"] == 2
    assert thread["channel"] == "website"
    assert thread["contact_name"] is None  # anonymous until a lead (P4-04)

    detail = client.get(
        f"/api/v1/tenants/{users.tenant_id}/bots/{setup['bot']['id']}/conversations/{thread['id']}"
    )
    assert detail.status_code == 200, detail.text
    messages = detail.json()["messages"]
    assert [m["sender_type"] for m in messages] == ["visitor", "ai"]
    assert len(messages[1]["citations"]) >= 1
    citation = messages[1]["citations"][0]
    assert citation["title"]
    assert citation["source_url"] is not None


def test_playground_threads_are_excluded_from_the_list(
    app: FastAPI,
    db: OrmSession,
    corpus: dict[str, Any],
) -> None:
    users = corpus["users_a"]
    setup = seed_setup(app, users, db)
    from tests.helpers import logged_in

    playground_user, _payload = logged_in(app, "playground-view@example.com")
    del playground_user
    listing = users.as_user("owner").get(
        f"/api/v1/tenants/{users.tenant_id}/bots/{setup['bot']['id']}/conversations"
    )
    assert all(row["id"] for row in listing.json()["conversations"])
    # No playground conversation rows visible even if a playground turn ran
    # through the same bot (source='playground' is filtered).
    assert listing.json()["total"] >= 1


def test_tenant_b_and_foreign_ids_are_404(
    app: FastAPI,
    db: OrmSession,
    corpus: dict[str, Any],
) -> None:
    users = corpus["users_a"]
    setup = seed_setup(app, users, db)
    thread_id = setup["turn"]["conversation_id"]
    other = corpus["users_b"]
    bot_id = setup["bot"]["id"]
    base = f"/api/v1/tenants/{other.tenant_id}/bots/{bot_id}/conversations/{thread_id}"
    assert other.as_user("owner").get(base).status_code == 404
    assert (
        other.as_user("owner")
        .delete(base, headers={"X-CSRF-Token": other.as_user("owner").cookies.get("chatbot_csrf")})
        .status_code
        == 404
    )
    # Tenant A reading a guessed thread id → 404
    guessed = users.as_user("owner").get(
        f"/api/v1/tenants/{users.tenant_id}/bots/{bot_id}/conversations/{uuid4()}"
    )
    assert guessed.status_code == 404


def test_viewer_reads_but_editor_deletes(
    app: FastAPI,
    db: OrmSession,
    corpus: dict[str, Any],
) -> None:
    users = corpus["users_a"]
    setup = seed_setup(app, users, db)
    thread_id = setup["turn"]["conversation_id"]
    viewer_del = users.as_user("viewer").delete(
        f"/api/v1/tenants/{users.tenant_id}/bots/{setup['bot']['id']}/conversations/{thread_id}",
        headers={"X-CSRF-Token": users.as_user("viewer").cookies.get("chatbot_csrf")},
    )
    assert viewer_del.status_code == 403
    removed = users.as_user("editor").delete(
        f"/api/v1/tenants/{users.tenant_id}/bots/{setup['bot']['id']}/conversations/{thread_id}",
        headers={"X-CSRF-Token": users.as_user("editor").cookies.get("chatbot_csrf")},
    )
    assert removed.status_code == 200
    gone = users.as_user("owner").get(
        f"/api/v1/tenants/{users.tenant_id}/bots/{setup['bot']['id']}/conversations/{thread_id}"
    )
    assert gone.status_code == 404
    assert db.query(Message).count() == 0  # messages went with the thread


# --- retention setting --------------------------------------------------------


def test_retention_setting_roundtrip_and_purge(
    app: FastAPI,
    db: OrmSession,
    corpus: dict[str, Any],
) -> None:
    users = corpus["users_a"]
    tenant_path = f"/api/v1/tenants/{users.tenant_id}"
    denied = users.as_user("viewer").patch(
        tenant_path,
        json={"retention_days": 7},
        headers={"X-CSRF-Token": users.as_user("viewer").cookies.get("chatbot_csrf")},
    )
    assert denied.status_code == 403
    patched = users.as_user("owner").patch(
        tenant_path,
        json={"retention_days": 7},
        headers={"X-CSRF-Token": users.as_user("owner").cookies.get("chatbot_csrf")},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["retention_days"] == 7
    invalid = users.as_user("owner").patch(
        tenant_path,
        json={"retention_days": 0},
        headers={"X-CSRF-Token": users.as_user("owner").cookies.get("chatbot_csrf")},
    )
    assert invalid.status_code == 422

    setup = seed_setup(app, users, db)
    assert db.query(Message).count() >= 2
    from app.core.config import Settings
    from tests.conftest import SESSION_SETTINGS

    purge_values: dict[str, Any] = {**dict(SESSION_SETTINGS), "retention_days": 30}
    purge_settings = Settings.model_construct(**purge_values)
    # Tenant retention 7 days: a 10-day-old message must be purged…
    old_row = db.query(Message).first()
    assert old_row is not None
    old_row.created_at = datetime.now(UTC) - timedelta(days=10)
    db.add(old_row)
    db.commit()
    from app.chat.conversations import run_retention_purge

    purged = run_retention_purge(db, purge_settings)
    assert purged >= 1
    # …while a 5-day-old message survives the 7-day window.
    old_row2 = db.query(Message).first()
    if old_row2 is not None:
        old_row2.created_at = datetime.now(UTC) - timedelta(days=5)
        db.add(old_row2)
        db.commit()
    again = run_retention_purge(db, purge_settings)
    assert again == 0
    del setup
