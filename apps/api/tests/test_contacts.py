"""P5-04 CRM routes: tenant isolation and viewer permissions for every endpoint."""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import FastAPI
from sqlalchemy.orm import Session as OrmSession

import tests.retrieval_helpers as _rh  # noqa: F401
from app.db.models import AuditEvent, ContactIdentity, Conversation, Message
from tests.helpers import make_bot

corpus = _rh.corpus


def test_contacts_crud_merge_export_and_erasure_are_tenant_scoped(
    app: FastAPI, db: OrmSession, corpus: dict[str, Any]
) -> None:
    users = corpus["users_a"]
    other = corpus["users_b"]
    base = f"/api/v1/tenants/{users.tenant_id}/contacts"
    foreign_base = f"/api/v1/tenants/{other.tenant_id}/contacts"

    stages = users.call("owner", "GET", f"{base}/stages")
    assert stages.status_code == 200
    assert {item["name"] for item in stages.json()["stages"]} == {
        "new",
        "qualified",
        "customer",
        "lost",
    }
    assert users.call("viewer", "GET", base).status_code == 200
    assert other.call("viewer", "GET", foreign_base).json()["contacts"] == []
    assert (
        users.call("viewer", "POST", base, json={"email": "viewer@example.com"}).status_code == 403
    )
    assert (
        users.call(
            "viewer", "PATCH", f"{base}/stages", json={"old_name": "new", "name": "fresh"}
        ).status_code
        == 403
    )
    assert (
        users.call(
            "owner", "PATCH", f"{base}/stages", json={"old_name": "qualified", "name": "warm"}
        ).status_code
        == 200
    )

    created = users.call(
        "owner",
        "POST",
        base,
        json={
            "display_name": "Ada",
            "email": "ada@example.com",
            "stage": "warm",
            "tags": ["vip"],
            "custom_fields": {"source": "web"},
        },
    )
    assert created.status_code == 201, created.text
    contact_id = created.json()["id"]
    bot = make_bot(users, "CRM timeline bot")
    now = datetime.now(UTC)
    conversation_id = uuid4()
    db.add(
        Conversation(
            id=conversation_id,
            tenant_id=users.tenant_id,
            bot_id=bot["id"],
            contact_id=contact_id,
            channel="website",
            mode="human",
            status="open",
            source="website",
            created_at=now,
            updated_at=now,
        )
    )
    db.add(
        Message(
            id=uuid4(),
            tenant_id=users.tenant_id,
            bot_id=bot["id"],
            conversation_id=conversation_id,
            sender_type="system",
            text="Internal note: review consent",
            created_at=now,
        )
    )
    db.add(
        ContactIdentity(
            id=uuid4(),
            tenant_id=users.tenant_id,
            contact_id=contact_id,
            channel="website",
            external_id="crm-test-identity",
            created_at=now,
        )
    )
    db.commit()
    viewer = users.call("viewer", "GET", f"{base}/{contact_id}")
    assert viewer.status_code == 200
    assert viewer.json()["contact"]["display_name"] == "Ada"
    assert viewer.json()["identities"][0]["external_id"] == "crm-test-identity"
    assert {item["type"] for item in viewer.json()["timeline"]} == {"conversation", "note"}
    assert (
        users.call(
            "viewer", "PATCH", f"{base}/{contact_id}", json={"display_name": "No"}
        ).status_code
        == 403
    )
    assert (
        users.call(
            "owner", "POST", base, json={"display_name": "Duplicate", "email": "ada@example.com"}
        ).status_code
        == 409
    )
    assert (
        users.call(
            "owner", "PATCH", f"{base}/{contact_id}", json={"email": None, "phone": None}
        ).status_code
        == 422
    )
    assert other.call("owner", "GET", f"{foreign_base}/{contact_id}").status_code == 404
    assert (
        other.call(
            "owner", "PATCH", f"{foreign_base}/{contact_id}", json={"display_name": "No"}
        ).status_code
        == 404
    )
    assert other.call("owner", "DELETE", f"{foreign_base}/{contact_id}").status_code == 404
    assert (
        other.call(
            "owner", "POST", f"{foreign_base}/{contact_id}/merge", params={"target_id": contact_id}
        ).status_code
        == 404
    )
    assert other.call("owner", "GET", f"{foreign_base}/export.csv").status_code == 200
    assert other.call("admin", "GET", f"{foreign_base}/export.csv").status_code == 200
    assert other.call("viewer", "GET", f"{foreign_base}/export.csv").status_code == 403
    assert other.call("owner", "GET", f"{foreign_base}/stages").status_code == 200
    assert (
        other.call(
            "owner", "PATCH", f"{foreign_base}/stages", json={"old_name": "new", "name": "fresh"}
        ).status_code
        == 200
    )

    assert (
        users.call(
            "owner",
            "PATCH",
            f"{base}/{contact_id}",
            json={"custom_fields": {str(i): i for i in range(21)}},
        ).status_code
        == 422
    )
    updated = users.call(
        "editor",
        "PATCH",
        f"{base}/{contact_id}",
        json={"display_name": "Ada Lovelace", "consent": {"website": {"granted": True}}},
    )
    assert updated.status_code == 200
    assert users.call("viewer", "GET", f"{base}/export.csv").status_code == 403
    assert "Ada Lovelace" in users.call("admin", "GET", f"{base}/export.csv").text

    target = users.call(
        "owner", "POST", base, json={"display_name": "Merged", "phone": "+15550000001"}
    )
    assert (
        users.call(
            "viewer",
            "POST",
            f"{base}/{contact_id}/merge",
            params={"target_id": target.json()["id"]},
        ).status_code
        == 403
    )
    merged = users.call(
        "owner", "POST", f"{base}/{contact_id}/merge", params={"target_id": target.json()["id"]}
    )
    assert merged.status_code == 200, merged.text
    assert merged.json()["display_name"] == "Merged"
    target_profile = users.call("viewer", "GET", f"{base}/{target.json()['id']}")
    assert target_profile.status_code == 200
    assert target_profile.json()["identities"][0]["external_id"] == "crm-test-identity"
    assert any(
        row.action == "contact.merge"
        for row in db.query(AuditEvent).filter(AuditEvent.tenant_id == users.tenant_id).all()
    )

    assert users.call("viewer", "DELETE", f"{base}/{target.json()['id']}").status_code == 403
    erased = users.call(
        "admin", "DELETE", f"{base}/{target.json()['id']}", params={"erase_messages": "true"}
    )
    assert erased.status_code == 204
    assert users.call("owner", "GET", f"{base}/{target.json()['id']}").status_code == 404
    assert (
        db.query(Message)
        .filter(Message.tenant_id == users.tenant_id, Message.conversation_id == conversation_id)
        .count()
        == 0
    )
