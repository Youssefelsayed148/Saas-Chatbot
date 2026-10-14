"""P7-04 tenant export/delete and tenant audit review."""

import json
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.db.models import (
    AuditEvent,
    Contact,
    ContactIdentity,
    Conversation,
    Message,
    Tenant,
)
from tests.helpers import make_bot, seeded_tenant


def test_export_contains_contacts_conversations_and_identities_scoped_to_tenant(
    app: Any, db: Any
) -> None:
    tenant_a = seeded_tenant(app, db, prefix="export-a")
    tenant_b = seeded_tenant(app, db, prefix="export-b")
    bot_a = make_bot(tenant_a)
    bot_b = make_bot(tenant_b)
    contact_a = tenant_a.call(
        "owner",
        "POST",
        f"/api/v1/tenants/{tenant_a.tenant_id}/contacts",
        json={"display_name": "Export A", "email": "export-a@example.com"},
    )
    assert contact_a.status_code == 201, contact_a.text
    contact_b = tenant_b.call(
        "owner",
        "POST",
        f"/api/v1/tenants/{tenant_b.tenant_id}/contacts",
        json={"display_name": "Export B", "email": "export-b@example.com"},
    )
    assert contact_b.status_code == 201, contact_b.text
    conversation_a = Conversation(
        tenant_id=tenant_a.tenant_id,
        bot_id=UUID(bot_a["id"]),
        contact_id=UUID(contact_a.json()["id"]),
        status="resolved",
        channel="website",
        source="website",
    )
    conversation_b = Conversation(
        tenant_id=tenant_b.tenant_id,
        bot_id=UUID(bot_b["id"]),
        contact_id=UUID(contact_b.json()["id"]),
        status="resolved",
        channel="website",
        source="website",
    )
    db.add_all([conversation_a, conversation_b])
    db.flush()
    db.add_all(
        [
            ContactIdentity(
                tenant_id=tenant_a.tenant_id,
                contact_id=UUID(contact_a.json()["id"]),
                channel="website",
                external_id="session-export-a",
            ),
            ContactIdentity(
                tenant_id=tenant_b.tenant_id,
                contact_id=UUID(contact_b.json()["id"]),
                channel="website",
                external_id="session-export-b",
            ),
            Message(
                tenant_id=tenant_a.tenant_id,
                bot_id=UUID(bot_a["id"]),
                conversation_id=conversation_a.id,
                sender_type="visitor",
                text="A private conversation",
            ),
        ]
    )
    db.commit()

    base = f"/api/v1/tenants/{tenant_a.tenant_id}/data"
    assert tenant_a.call("viewer", "GET", f"{base}/export").status_code == 403
    assert tenant_b.call("owner", "GET", f"{base}/export").status_code == 404
    response = tenant_a.call("owner", "GET", f"{base}/export")
    assert response.status_code == 200, response.text
    exported = response.json()
    assert [row["display_name"] for row in exported["contacts"]] == ["Export A"]
    assert exported["contact_identities"][0]["external_id"] == "session-export-a"
    assert exported["conversations"][0]["id"] == str(conversation_a.id)
    assert exported["messages"][0]["text"] == "A private conversation"
    assert "password_hash" not in json.dumps(exported)
    assert "token_hash" not in json.dumps(exported)
    assert any(row["action"] == "tenant.data.exported" for row in exported["audit_events"])

    audit_path = f"{base}/audit?q=tenant.data.exported"
    assert tenant_a.call("viewer", "GET", audit_path).status_code == 403
    assert tenant_b.call("owner", "GET", audit_path).status_code == 404
    audit = tenant_a.call("owner", "GET", audit_path)
    assert audit.status_code == 200
    assert audit.json()["events"][0]["action"] == "tenant.data.exported"
    tenant_a.cleanup()
    tenant_b.cleanup()


def test_tenant_delete_requires_owner_confirmation_and_cascades_data(app: Any, db: Any) -> None:
    tenant_a = seeded_tenant(app, db, prefix="delete-a")
    tenant_b = seeded_tenant(app, db, prefix="delete-b")
    bot = make_bot(tenant_a)
    tenant_id = tenant_a.tenant_id
    contact = Contact(
        tenant_id=tenant_id,
        display_name="Delete me",
        email="delete-me@example.com",
    )
    db.add(contact)
    db.flush()
    conversation = Conversation(
        tenant_id=tenant_id,
        bot_id=UUID(bot["id"]),
        contact_id=contact.id,
        status="open",
        channel="website",
        source="website",
    )
    db.add(conversation)
    db.commit()
    path = f"/api/v1/tenants/{tenant_id}/data"
    body = {"confirm_name": "Org delete-a", "reason": "Owner requested full data removal"}
    assert tenant_a.call("viewer", "DELETE", path, json=body).status_code == 403
    assert tenant_b.call("owner", "DELETE", path, json=body).status_code == 404
    mismatch = tenant_a.call("owner", "DELETE", path, json={**body, "confirm_name": "wrong"})
    assert mismatch.status_code == 422
    deleted = tenant_a.call("owner", "DELETE", path, json=body)
    assert deleted.status_code == 204
    db.expire_all()
    assert db.execute(select(Tenant).where(Tenant.id == tenant_id)).scalar_one_or_none() is None
    assert db.execute(select(Contact).where(Contact.id == contact.id)).scalar_one_or_none() is None
    assert db.execute(
        select(AuditEvent).where(
            AuditEvent.action == "tenant.data.deleted", AuditEvent.target_id == str(tenant_id)
        )
    ).scalar_one().metadata_json["reason"] == body["reason"]
    tenant_a.cleanup()
    tenant_b.cleanup()
