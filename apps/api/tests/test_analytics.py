"""P4-05: overview analytics endpoints (docs/14 §9) — measured data only.

Imports REAL visitor flows through the widget (messages, leads, feedback via
the idempotent usage events) and asserts the numbers; playground threads are
excluded by construction. Tenant A/B isolation with every endpoint."""

from typing import Any

import tests.retrieval_helpers as _rh  # noqa: F401 — registers the corpus fixture
from tests.test_widget_public import (
    _override_widget_settings,
    make_active_bot_with_knowledge,
)

corpus = _rh.corpus


def _seed_activity(
    app: Any,
    db: Any,
    corpus: dict[str, Any],
) -> dict[str, Any]:

    from fastapi.testclient import TestClient

    users = corpus["users_a"]
    _override_widget_settings(app)
    bot_a = make_active_bot_with_knowledge(app, users, db, name="Metrics A")
    bot_b = make_active_bot_with_knowledge(app, corpus["users_b"], db, name="Metrics B")
    client = TestClient(app)

    # session 1: one message + lead
    s1 = client.post(f"/api/public/v1/widgets/{bot_a['widget_locator']}/sessions", json={}).json()
    turn1 = client.post(
        f"/api/public/v1/sessions/{s1['session_id']}/messages",
        json={"text": "What are your opening hours?"},
        headers={"X-Session-Token": s1["token"]},
    )
    assert turn1.status_code == 201, turn1.text
    ai_id = turn1.json()["ai_message"]["id"]
    client.post(
        f"/api/public/v1/sessions/{s1['session_id']}/messages/{ai_id}/feedback",
        json={"rating": "up"},
        headers={"X-Session-Token": s1["token"]},
    )
    lead1 = client.post(
        f"/api/public/v1/sessions/{s1['session_id']}/lead",
        json={"name": "Lead One", "email": "one@example.com", "consent_accepted": True},
        headers={"X-Session-Token": s1["token"]},
    )
    assert lead1.status_code == 201, lead1.text

    # session 2: two messages (one unanswerable → cannot_confirm/can_answer=false)
    s2 = client.post(f"/api/public/v1/widgets/{bot_a['widget_locator']}/sessions", json={}).json()
    client.post(
        f"/api/public/v1/sessions/{s2['session_id']}/messages",
        json={"text": "What are your opening hours?"},
        headers={"X-Session-Token": s2["token"]},
    )
    turn2 = client.post(
        f"/api/public/v1/sessions/{s2['session_id']}/messages",
        json={"text": "Do you ship to Antarctica?"},
        headers={"X-Session-Token": s2["token"]},
    )
    assert turn2.status_code == 201, turn2.text
    assert turn2.json()["ai_message"]["needs_human"] is True
    return {
        "client": client,
        "bot_a": bot_a,
        "bot_b": bot_b,
        "users_a": users,
        "users_b": corpus["users_b"],
    }


def path_of(bot: dict[str, Any], tenant_id: str) -> str:
    return f"/api/v1/tenants/{tenant_id}/bots/{bot['id']}/analytics"


def test_summary_counts_measured_messages_leads_and_feedback(
    app: Any, db: Any, corpus: dict[str, Any]
) -> None:
    mesh = _seed_activity(app, db, corpus)
    client = corpus["users_a"].as_user("owner")
    summary = client.get(f"{path_of(mesh['bot_a'], str(mesh['users_a'].tenant_id))}/summary")
    assert summary.status_code == 200, summary.text
    body = summary.json()
    assert body["messages"] == 3  # 1 + 2 visitor turns (real), NOT usage events
    assert body["conversations"] == 2
    assert body["widget_opens"] == 2
    assert body["leads"] == 1
    assert body["thumbs_up"] == 1
    assert body["thumbs_down"] == 0
    assert body["cannot_answer"] >= 1  # the Antarctica turn abstained
    assert body["avg_response_ms"] >= 0
    assert abs(body["avg_messages_per_conversation"] - (3 / 2)) < 0.01
    assert 0.0 <= body["fallback_rate"] <= 1.0
    assert body["message_distribution"]["1"] >= 1
    assert body["message_distribution"]["2-3"] >= 1


def test_volume_top_questions_unanswered_leads(app: Any, db: Any, corpus: dict[str, Any]) -> None:
    mesh = _seed_activity(app, db, corpus)
    client = corpus["users_a"].as_user("owner")
    base = path_of(mesh["bot_a"], str(mesh["users_a"].tenant_id))
    volume = client.get(f"{base}/volume")
    assert volume.status_code == 200
    days = volume.json()["days"]
    assert len(days) >= 1
    assert sum(day["visitor"] for day in days) == 3
    assert sum(day["assistant"] for day in days) == 3

    top = client.get(f"{base}/top-questions")
    assert top.status_code == 200
    questions = top.json()["questions"]
    assert any("opening hours" in row["question"].lower() for row in questions)

    unanswered = client.get(f"{base}/unanswered")
    assert unanswered.status_code == 200
    rows = unanswered.json()["questions"]
    assert any("antarctica" in row["question"].lower() for row in rows)

    leads = client.get(f"{base}/leads")
    assert leads.status_code == 200
    body = leads.json()
    assert body["trend"] and body["trend"][-1]["leads"] >= 1
    contacts = body["contacts"]
    assert any(row["display_name"] == "Lead One" for row in contacts)


def test_playground_threads_are_never_counted(app: Any, db: Any, corpus: dict[str, Any]) -> None:
    """Only measured visitor data: even with a playground turn on the same bot
    the analytics stay equal to the visitor-only numbers."""
    mesh = _seed_activity(app, db, corpus)
    from uuid import UUID

    from app.chat.conversations import append_message, get_or_create_playground_conversation
    from app.db.models import Bot
    from tests.retrieval_helpers import published_revision_id

    users = mesh["users_a"]
    bot = Bot(
        id=UUID(str(mesh["bot_a"]["id"])),
        tenant_id=users.tenant_id,
        name="Metrics A",
        status="active",
        published_revision_id=UUID(
            published_revision_id(db, users.tenant_id, str(mesh["bot_a"]["id"]))
        ),
        config={},
    )
    conversation = get_or_create_playground_conversation(
        db, tenant_id=users.tenant_id, bot_id=bot.id, user_id=users.users["owner"]["id"]
    )
    append_message(db, conversation, sender_type="visitor", text="playground probe")
    db.commit()
    client = users.as_user("owner")
    base = f"/api/v1/tenants/{users.tenant_id}/bots/{bot.id}/analytics"
    summary = client.get(f"{base}/summary").json()
    assert summary["messages"] == 3  # the playground turn is EXCLUDED
    assert summary["conversations"] == 2


def test_bot_scoping_and_csv_exports(app: Any, db: Any, corpus: dict[str, Any]) -> None:
    mesh = _seed_activity(app, db, corpus)
    users_a = mesh["users_a"]
    users_b = mesh["users_b"]
    client_a = users_a.as_user("owner")
    client_b = users_b.as_user("owner")
    base_a = path_of(mesh["bot_a"], str(users_a.tenant_id))
    base_b = f"/api/v1/tenants/{users_a.tenant_id}/bots/{mesh['bot_b']['id']}/analytics"
    # tenant B bot reached via tenant A's URL → 404 (per-bot isolation)
    assert client_a.get(base_b + "/summary").status_code == 404
    assert client_a.get(base_b + "/conversations.csv").status_code == 404
    # numbers never mix: tenant B has its OWN but their bot traffic is empty
    summary_b = client_b.get(
        f"/api/v1/tenants/{users_b.tenant_id}/bots/{mesh['bot_b']['id']}/analytics/summary"
    )
    assert summary_b.status_code == 200
    assert summary_b.json()["messages"] == 0 and summary_b.json()["leads"] == 0

    assert users_a.as_user("viewer").get(f"{base_a}/conversations.csv").status_code == 403
    assert users_a.as_user("editor").get(f"{base_a}/leads.csv").status_code == 403
    csv_conversations = users_a.as_user("admin").get(f"{base_a}/conversations.csv")
    assert csv_conversations.status_code == 200
    assert csv_conversations.headers["content-type"].startswith("text/csv")
    body = csv_conversations.text
    assert "conversation_id" in body and body.count("\n") >= 3
    csv_leads = users_a.as_user("admin").get(f"{base_a}/leads.csv")
    assert csv_leads.status_code == 200
    assert "display_name" in csv_leads.text and "Lead One" in csv_leads.text


def test_viewer_can_read_but_date_validation_works(
    app: Any, db: Any, corpus: dict[str, Any]
) -> None:
    mesh = _seed_activity(app, db, corpus)
    users = mesh["users_a"]
    viewer = users.as_user("viewer")
    base = path_of(mesh["bot_a"], str(users.tenant_id))
    assert viewer.get(f"{base}/summary").status_code == 200  # read allowed
    bad = users.as_user("owner").get(
        f"{base}/summary?from=not-a-date",
    )
    assert bad.status_code == 422
    inverted = users.as_user("owner").get(
        f"{base}/summary?from=2026-06-01&to=2026-05-01",
    )
    assert inverted.status_code == 422


def test_analytics_dates_filter_the_window(app: Any, db: Any, corpus: dict[str, Any]) -> None:
    import datetime as dt

    mesh = _seed_activity(app, db, corpus)
    users = mesh["users_a"]
    client = users.as_user("owner")
    base = path_of(mesh["bot_a"], str(users.tenant_id))
    today = dt.date.today()
    in_window = client.get(
        f"{base}/summary?from={today - dt.timedelta(days=2):%Y-%m-%d}&to={today:%Y-%m-%d}"
    )
    assert in_window.status_code == 200
    assert in_window.json()["messages"] == 3
    # strictly-past window contains nothing measured today
    past = client.get(
        f"{base}/summary?from={today - dt.timedelta(days=10):%Y-%m-%d}"
        f"&to={today - dt.timedelta(days=2):%Y-%m-%d}"
    )
    assert past.json()["messages"] == 0
