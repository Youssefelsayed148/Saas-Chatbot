"""P7-04 tenant export/delete and tenant audit review."""

import json
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.db.models import (
    ContactIdentity,
    Conversation,
    Message,
    Tenant,
    UsageEvent,
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
        "admin",
        "POST",
        f"/api/v1/tenants/{tenant_a.tenant_id}/contacts",
        json={"display_name": "Export A", "email": "export-a@example.com"},
    )
    assert contact_a.status_code == 201, contact_a.text
    contact_b = tenant_b.call(
        "admin",
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
                citations=[{"chunk_id": "private-chunk", "title": "Private source"}],
            ),
            UsageEvent(
                tenant_id=tenant_a.tenant_id,
                bot_id=UUID(bot_a["id"]),
                kind="message",
                external_key="export-private-trace",
                payload={
                    "rag_trace": {"chunks": ["private-trace-chunk"], "cost_usd": "1.25"},
                    "provider_usage": {"total_tokens": 123},
                },
            ),
        ]
    )
    db.commit()

    base = f"/api/v1/tenants/{tenant_a.tenant_id}/data"
    assert tenant_a.call("viewer", "GET", f"{base}/export").status_code == 403
    assert tenant_b.call("admin", "GET", f"{base}/export").status_code == 404
    assert tenant_a.call("editor", "GET", f"{base}/export").status_code == 403
    response = tenant_a.call("admin", "GET", f"{base}/export")
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
    assert tenant_b.call("admin", "GET", audit_path).status_code == 404
    audit = tenant_a.call("admin", "GET", audit_path)
    assert audit.status_code == 200
    assert audit.json()["events"][0]["action"] == "tenant.data.exported"
    assert all("config" not in row for row in exported["bots"])
    assert all(row["citations"] == [] for row in exported["messages"])
    assert exported["usage_events"][0]["payload"] == {}
    assert "private-trace-chunk" not in json.dumps(exported)
    assert "provider_usage" not in json.dumps(exported)
    for key in (
        "sources",
        "source_files",
        "source_pages",
        "documents",
        "chunks",
        "knowledge_revisions",
        "jobs",
    ):
        assert key not in exported
    staff_export = tenant_a.call(
        "staff", "GET", f"/api/v1/tenants/{tenant_a.tenant_id}/data/export"
    ).json()
    assert "sources" in staff_export and "knowledge_revisions" in staff_export
    assert "config" in staff_export["bots"][0]
    assert staff_export["messages"][0]["citations"][0]["title"] == "Private source"
    assert staff_export["usage_events"][0]["payload"]["rag_trace"]["cost_usd"] == "1.25"
    tenant_a.cleanup()
    tenant_b.cleanup()


def test_org_delete_name_mismatch_and_soft_delete(app: Any, db: Any, tmp_path: Any) -> None:
    from datetime import UTC, datetime, timedelta

    from app.core.config import get_settings
    from app.db.models import Bot, OrganizationDeletion, RateLimitCounter, Source, VisitorSession
    from app.knowledge.storage import get_storage
    from app.tenants.deletion import purge_deleted_organizations
    from tests.conftest import build_test_settings
    from tests.knowledge_helpers import upload_sources

    settings = build_test_settings(storage_root=str(tmp_path), org_deletion_grace_days=2)
    app.dependency_overrides[get_settings] = lambda: settings
    a, b = seeded_tenant(app, db, prefix="delete-a"), seeded_tenant(app, db, prefix="delete-b")
    bot = make_bot(a)
    visitor = VisitorSession(
        tenant_id=a.tenant_id,
        bot_id=UUID(bot["id"]),
        token_hash="delete-test-visitor",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    db.add(visitor)
    db.flush()
    counter_key = f"widget:msg:127.0.0.1:{visitor.id}"
    unrelated_counter = "widget:msg:127.0.0.1:unrelated-session"
    db.add_all(
        [
            RateLimitCounter(bucket_key=counter_key, count=1),
            RateLimitCounter(bucket_key=unrelated_counter, count=1),
        ]
    )
    db.commit()
    path = f"/api/v1/tenants/{a.tenant_id}/data"
    body = {"confirm_name": "Org delete-a", "reason": "Requested full data removal"}
    uploaded = upload_sources(a, bot["id"], [("test.md", b"# Delete me")], tmp_path)
    assert uploaded.status_code == 201, uploaded.text
    orphan_key = get_storage(settings).save(a.tenant_id, UUID(bot["id"]), "txt", b"orphaned upload")
    storage_key = db.scalar(select(Source.storage_key).where(Source.tenant_id == a.tenant_id))
    change = a.call(
        "admin",
        "POST",
        f"/api/v1/tenants/{a.tenant_id}/change-requests",
        data={"type": "delete_org", "text": "Please remove this organization"},
        files=[("files", ("evidence.txt", b"deletion evidence", "text/plain"))],
    )
    assert change.status_code == 201
    from app.db.models import ChangeRequest

    attachment_key = db.scalar(
        select(ChangeRequest).where(ChangeRequest.tenant_id == a.tenant_id)
    ).attachments[0]["storage_key"]
    for role in ("viewer", "editor", "admin"):
        assert a.call(role, "DELETE", path, json=body).status_code == 403
        assert a.call(role, "GET", f"{path}/deletion-preview").status_code == 403
    assert b.call("admin", "DELETE", path, json=body).status_code == 404
    assert a.call("staff", "DELETE", path, json={"reason": body["reason"]}).status_code == 422
    assert a.call("staff", "DELETE", path).status_code == 422
    assert build_test_settings().org_deletion_grace_days == 30
    for name in ["wrong", " Org delete-a", "Org delete-a ", "org delete-a"]:
        mismatch = a.call("staff", "DELETE", path, json={**body, "confirm_name": name})
        assert mismatch.status_code == 422
    assert a.call("staff", "GET", f"{path}/deletion-preview").json()["counts"]["bots"] == 1
    assert a.call("staff", "DELETE", path, json=body).status_code == 204
    db.expire_all()
    tenant = db.get(Tenant, a.tenant_id)
    assert tenant is not None and tenant.status == "archived"
    assert db.get(Bot, UUID(bot["id"])).status == "archived"
    record = db.scalar(
        select(OrganizationDeletion).where(OrganizationDeletion.tenant_id == a.tenant_id)
    )
    assert record is not None and record.purged_at is None
    assert record.purge_after.astimezone(UTC) - record.requested_at.astimezone(UTC) == timedelta(
        days=2
    )
    assert get_storage(settings).open(storage_key) == b"# Delete me"
    # Existing sessions are invalid immediately; a new login cannot access this organization.
    assert a.call("admin", "GET", path + "/audit").status_code == 401
    from tests.helpers import PASSWORD

    login = a.as_user("admin").post(
        "/api/v1/auth/login", json={"email": a.users["admin"]["email"], "password": PASSWORD}
    )
    assert login.status_code == 200 and login.json()["memberships"] == []
    assert a.call("admin", "GET", f"/api/v1/tenants/{a.tenant_id}").status_code == 404
    assert (
        a.call("staff", "GET", f"/api/public/v1/widgets/{bot['widget_locator']}/config").status_code
        == 404
    )
    assert purge_deleted_organizations(db, settings) == 0
    record.purge_after = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()
    # Failure leaves the ledger and tenant available for a retry.
    from unittest.mock import patch

    with patch(
        "app.knowledge.storage.LocalStorage.delete_strict",
        side_effect=OSError("test storage failure"),
    ):
        import pytest

        with pytest.raises(OSError):
            purge_deleted_organizations(db, settings)
    db.rollback()
    assert db.get(Tenant, a.tenant_id) is not None
    assert purge_deleted_organizations(db, settings) == 1
    db.expire_all()
    assert db.get(Tenant, a.tenant_id) is None
    assert db.get(Tenant, b.tenant_id) is not None
    assert db.get(RateLimitCounter, counter_key) is None
    assert db.get(RateLimitCounter, unrelated_counter) is not None
    assert db.get(OrganizationDeletion, record.id).purged_at is not None
    import pytest

    with pytest.raises(FileNotFoundError):
        get_storage(settings).open(storage_key)
    with pytest.raises(FileNotFoundError):
        get_storage(settings).open(orphan_key)
    with pytest.raises(FileNotFoundError):
        get_storage(settings).open(attachment_key)
    assert purge_deleted_organizations(db, settings) == 0
    a.cleanup()
    b.cleanup()
