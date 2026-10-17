"""Naming compatibility must preserve audit history, tenant scope and retries."""

import hashlib
import json
from typing import Any

from sqlalchemy import select

from app.core.audit import record_audit
from app.db.models import AuditEvent, ProvisioningRequest
from app.provisioning.service import ProvisioningPayload, _hash_payload
from tests.helpers import seeded_tenant
from tests.test_platform import ONBOARD_FORM, platform_call, staff_login

ACTIONS = {
    "platform.onboarding.owner_invited",
    "platform.onboarding.admin_invited",
    "self_service.owner_assigned",
    "self_service.admin_assigned",
}


def test_audit_readers_search_old_and_new_names_without_rewriting_history(
    app: Any, db: Any
) -> None:
    a = seeded_tenant(app, db, prefix="audit-alias-a")
    b = seeded_tenant(app, db, prefix="audit-alias-b")
    for tenant in (a, b):
        for action in ACTIONS:
            record_audit(db, action=action, tenant_id=tenant.tenant_id, actor_user_id=None)
    db.commit()
    for query in (
        "admin",
        "owner",
        "ADMIN",
        "OWNER_INVITED",
        "admin_invited",
        "owner_invited",
        "admin_assigned",
    ):
        expected = {
            action
            for action in ACTIONS
            if query.lower().replace("owner", "admin") in action.replace("owner", "admin")
        }
        path = f"/api/v1/tenants/{a.tenant_id}/data/audit?q={query}"
        response = a.call("admin", "GET", path)
        assert response.status_code == 200
        assert {event["action"] for event in response.json()["events"]} == expected
        assert len(response.json()["events"]) == len(expected)
        assert b.call("admin", "GET", path).status_code == 404
        assert a.call("viewer", "GET", path).status_code == 403
        platform = a.call("staff", "GET", f"/api/v1/platform/audit?q={query}")
        assert platform.status_code == 200
        assert {event["action"] for event in platform.json()["events"]} == expected
        assert len(platform.json()["events"]) == len(expected) * 2
    assert (
        set(db.scalars(select(AuditEvent.action).where(AuditEvent.tenant_id == a.tenant_id)).all())
        >= ACTIONS
    )


def test_legacy_onboarding_retry_keeps_fingerprint_and_returns_admin_contract(
    app: Any, db: Any
) -> None:
    client = staff_login(app, db, "legacy-retry@example.com")
    first = platform_call(
        client,
        "POST",
        "/onboarding",
        data=ONBOARD_FORM,
        headers={"Idempotency-Key": "legacy-retry"},
    )
    assert first.status_code == 201
    row = db.scalar(
        select(ProvisioningRequest).where(ProvisioningRequest.idempotency_key == "legacy-retry")
    )
    # Simulate the exact JSON and fingerprint persisted by the pre-rename code.
    old_json = json.dumps(
        {
            "client_name": "Provisioned Org",
            "owner_email": "new-admin@example.com",
            "bot_name": "First Bot",
            "plan_label": "starter",
        },
        separators=(",", ":"),
    )
    row.payload_hash = hashlib.sha256(old_json.encode()).hexdigest()
    row.result = {
        "owner_invite": first.json()["result"]["admin_invite"],
        "tenant_id": first.json()["result"]["tenant_id"],
    }
    db.commit()
    assert _hash_payload(ProvisioningPayload(**ONBOARD_FORM), []) == row.payload_hash
    retry = platform_call(
        client,
        "POST",
        "/onboarding",
        data=ONBOARD_FORM,
        headers={"Idempotency-Key": "legacy-retry"},
    )
    assert retry.status_code == 201
    assert retry.json()["replayed"] is True
    assert retry.json()["result"]["admin_invite"] == first.json()["result"]["admin_invite"]
    assert "owner_invite" not in retry.json()["result"]
    db.expire_all()
    assert "owner_invite" in db.get(ProvisioningRequest, row.id).result
