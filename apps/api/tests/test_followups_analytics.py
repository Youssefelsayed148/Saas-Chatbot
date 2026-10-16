"""P5-05 scheduled website follow-ups and measured analytics."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

import tests.retrieval_helpers as _rh  # noqa: F401
from app.core.config import get_settings
from app.db.models import Conversation, FollowUp, Job, Message
from app.jobs.queue import claim_job
from app.jobs.runner import execute_claimed_job
from app.knowledge.storage import LocalStorage
from tests.test_conversations_view import seed_setup

corpus = _rh.corpus


def test_follow_up_permissions_isolation_cancel_and_widget_delivery(
    app: FastAPI, db: OrmSession, corpus: dict[str, Any]
) -> None:
    users = corpus["users_a"]
    other = corpus["users_b"]
    setup = seed_setup(app, users, db, name="Follow-up")
    conversation_id = setup["turn"]["conversation_id"]
    base = f"/api/v1/tenants/{users.tenant_id}/follow-ups"
    foreign_base = f"/api/v1/tenants/{other.tenant_id}/follow-ups"
    send_at = datetime.now(UTC) + timedelta(hours=1)
    body = {
        "conversation_id": conversation_id,
        "send_at": send_at.isoformat(),
        "text": "Your requested information is ready.",
    }

    assert users.call("viewer", "GET", base).status_code == 200
    assert other.call("viewer", "GET", foreign_base).json()["follow_ups"] == []
    assert users.call("viewer", "POST", base, json=body).status_code == 403
    assert other.call("admin", "POST", foreign_base, json=body).status_code == 404
    assert (
        users.call(
            "admin", "POST", base, json={**body, "send_at": "2030-01-01T12:00:00"}
        ).status_code
        == 422
    )

    scheduled = users.call("editor", "POST", base, json=body)
    assert scheduled.status_code == 201, scheduled.text
    follow_up_id = scheduled.json()["id"]
    assert scheduled.json()["status"] == "scheduled"
    assert users.call("viewer", "DELETE", f"{base}/{follow_up_id}").status_code == 403
    assert other.call("admin", "DELETE", f"{foreign_base}/{follow_up_id}").status_code == 404

    job = db.execute(
        select(Job).where(
            Job.tenant_id == users.tenant_id,
            Job.type == "follow_up_delivery",
            Job.payload["follow_up_id"].astext == follow_up_id,
        )
    ).scalar_one()
    due_at = datetime.now(UTC) - timedelta(seconds=1)
    job.run_at = due_at
    follow_up = db.get(FollowUp, UUID(follow_up_id))
    assert follow_up is not None
    follow_up.send_at = due_at
    db.commit()
    settings = get_settings()
    claimed = claim_job(db, "p5-follow-up-test", settings)
    assert claimed is not None
    execute_claimed_job(db, claimed, settings, LocalStorage(settings))
    db.refresh(claimed)
    assert claimed.status == "succeeded"
    ready_follow_up = db.get(FollowUp, follow_up_id)
    assert ready_follow_up is not None
    db.refresh(ready_follow_up)
    assert ready_follow_up.status == "ready"

    session = setup["client"].get(
        f"/api/public/v1/sessions/{setup['session']['session_id']}/messages",
        headers={"X-Session-Token": setup["session"]["token"]},
    )
    assert session.status_code == 200
    rows = session.json()
    assert sum(row["text"] == body["text"] for row in rows) == 1
    delivered_follow_up = db.get(FollowUp, follow_up_id)
    assert delivered_follow_up is not None
    db.refresh(delivered_follow_up)
    assert delivered_follow_up.status == "delivered"
    # Re-reading the visitor thread is idempotent.
    assert (
        setup["client"]
        .get(
            f"/api/public/v1/sessions/{setup['session']['session_id']}/messages",
            headers={"X-Session-Token": setup["session"]["token"]},
        )
        .json()
        == rows
    )
    inbox = users.call("admin", "GET", f"/api/v1/tenants/{users.tenant_id}/inbox")
    assert inbox.status_code == 200, inbox.text
    inbox_rows = inbox.json()["conversations"]
    assert len(inbox_rows) == 1
    assert inbox_rows[0]["id"] == conversation_id
    assert inbox_rows[0]["last_message"] == body["text"]

    next_schedule = users.call("admin", "POST", base, json={**body, "text": "Cancel me."})
    assert next_schedule.status_code == 201
    cancelled = users.call("editor", "DELETE", f"{base}/{next_schedule.json()['id']}")
    assert cancelled.status_code == 204
    listed = users.call("viewer", "GET", base).json()["follow_ups"]
    assert {row["status"] for row in listed} == {"delivered", "cancelled"}
    assert users.call("editor", "DELETE", f"{base}/{next_schedule.json()['id']}").status_code == 409


def test_tenant_analytics_match_conversations_messages_and_assignments(
    app: FastAPI, db: OrmSession, corpus: dict[str, Any]
) -> None:
    users = corpus["users_a"]
    other = corpus["users_b"]
    setup = seed_setup(app, users, db, name="Analytics")
    conversation_id = setup["turn"]["conversation_id"]
    conversation = db.execute(
        select(Conversation).where(
            Conversation.tenant_id == users.tenant_id,
            Conversation.id == conversation_id,
        )
    ).scalar_one()
    first_reply_at = conversation.created_at + timedelta(seconds=17)
    conversation.handoff_reason = "analytics-test"
    conversation.assigned_user_id = users.users["editor"]["id"]
    conversation.sentiment = "negative"
    db.add(
        Message(
            tenant_id=users.tenant_id,
            bot_id=conversation.bot_id,
            conversation_id=conversation.id,
            sender_type="agent",
            sender_user_id=conversation.assigned_user_id,
            text="I can help with that.",
            created_at=first_reply_at,
        )
    )
    db.commit()

    path = f"/api/v1/tenants/{users.tenant_id}/analytics"
    result = users.call("viewer", "GET", path)
    assert result.status_code == 200, result.text
    data = result.json()
    assert data["total_conversations"] == 1
    assert data["handoff_count"] == 1
    assert data["handoff_rate"] == 1.0
    assert data["average_first_human_reply_seconds"] == 17.0
    assert data["conversations_by_channel"] == {"website": 1}
    assert data["resolved_vs_open"] == {"resolved": 0, "open": 1}
    assert data["sentiment_distribution"] == {"negative": 1}
    assert data["agent_workload"] == {users.users["editor"]["email"]: 1}
    assert (
        other.call("viewer", "GET", f"/api/v1/tenants/{other.tenant_id}/analytics").json()[
            "total_conversations"
        ]
        == 0
    )
