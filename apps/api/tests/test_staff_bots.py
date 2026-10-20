"""Staff bot creation, summary isolation, immutability and retired onboarding."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.models import AuditEvent, Bot, Job, Tenant
from app.db.models.knowledge import KnowledgeRevision, Source
from tests.helpers import seeded_tenant
from tests.test_platform import ONBOARD_FORM, legacy_onboard, platform_call, staff_login


def organization(staff: TestClient, name: str = "Bot organization") -> str:
    response = platform_call(
        staff, "POST", "/tenants", json={"name": name, "plan_label": "business"}
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def create(staff: TestClient, tenant: str, name: str = "First bot") -> Any:
    return platform_call(staff, "POST", "/bots", json={"organization_id": tenant, "name": name})


def test_staff_creates_bot_with_unique_locator_and_audit(app: Any, db: Any) -> None:
    staff = staff_login(app, db)
    tenant = organization(staff)
    first, second = create(staff, tenant, "  First bot  "), create(staff, tenant, "Second bot")
    assert first.status_code == second.status_code == 201
    a, b = first.json(), second.json()
    assert a["name"] == "First bot" and a["tenant_id"] == tenant
    assert a["status"] == "draft" and a["config"] == {}
    assert a["widget_locator"] and a["widget_locator"] != b["widget_locator"]
    assert a["widget_locator"].startswith("w")
    actor = platform_call(staff, "GET", "/me").json()["id"]
    events = list(db.scalars(select(AuditEvent).where(AuditEvent.action == "platform.bot.created")))
    assert len(events) == 2
    assert {e.target_id for e in events} == {a["id"], b["id"]}
    assert all(str(e.actor_user_id) == actor and str(e.tenant_id) == tenant for e in events)
    listing = platform_call(staff, "GET", f"/bots?organization_id={tenant}").json()
    assert listing["total"] == 2
    assert all(
        row["widget_state"] == "configured"
        and row["source_count"] == 0
        and row["last_ingestion_job_status"] is None
        and row["published_revision_id"] is None
        for row in listing["bots"]
    )
    assert (
        TestClient(app).get(f"/api/public/v1/widgets/{a['widget_locator']}/config").status_code
        == 200
    )


@pytest.mark.parametrize("name", ["", "   ", "x" * 101, None, 123])
def test_create_name_validation(app: Any, db: Any, name: Any) -> None:
    staff = staff_login(app, db)
    tenant = organization(staff)
    response = create(staff, tenant, name)
    assert response.status_code == 422
    assert not list(db.scalars(select(Bot)))


def test_create_rejects_unknown_archived_and_exhausted_organizations(app: Any, db: Any) -> None:
    staff = staff_login(app, db)
    assert create(staff, str(uuid4())).status_code == 404
    tenant = organization(staff)
    row = db.get(Tenant, UUID(tenant))
    row.status = "archived"
    db.commit()
    assert create(staff, tenant).status_code == 404
    row.status, row.quota_overrides = "active", {"bots": 0}
    db.commit()
    result = create(staff, tenant)
    assert result.status_code == 429
    assert result.json()["error"]["code"] == "QUOTA_EXCEEDED"
    assert "Contact us" in result.json()["error"]["message"]
    assert "Traceback" not in result.text and "INSERT" not in result.text
    assert not list(db.scalars(select(Bot)))


@pytest.mark.parametrize("method", ["GET", "POST"])
def test_global_bots_staff_only(app: Any, db: Any, method: str) -> None:
    users = seeded_tenant(app, db)
    for role in ("admin", "editor", "viewer"):
        assert users.call(role, method, "/api/v1/platform/bots", json={}).status_code == 403
    assert TestClient(app).request(method, "/api/v1/platform/bots", json={}).status_code == 401


def test_bot_organization_is_immutable(app: Any, db: Any) -> None:
    staff = staff_login(app, db)
    a, b = organization(staff, "A"), organization(staff, "B")
    bot = create(staff, a).json()
    path = f"/api/v1/tenants/{a}/bots/{bot['id']}"
    for field in ("organization_id", "tenant_id"):
        result = staff.patch(
            path, json={field: b}, headers={"X-CSRF-Token": staff.cookies.get("chatbot_csrf") or ""}
        )
        assert result.status_code == 422
        assert str(db.get(Bot, UUID(bot["id"])).tenant_id) == a


def test_bot_list_summaries_do_not_cross_organization(app: Any, db: Any) -> None:
    staff = staff_login(app, db)
    a, b = organization(staff, "A"), organization(staff, "B")
    bot_a, bot_b = create(staff, a, "Alpha").json(), create(staff, b, "Beta").json()
    actor = UUID(platform_call(staff, "GET", "/me").json()["id"])
    revision = KnowledgeRevision(
        tenant_id=UUID(a),
        bot_id=UUID(bot_a["id"]),
        status="published",
        created_by=actor,
        published_at=datetime.now(UTC),
    )
    db.add(revision)
    db.flush()
    db.get(Bot, UUID(bot_a["id"])).published_revision_id = revision.id
    for tenant, bot, status, count in ((a, bot_a, "failed", 1), (b, bot_b, "succeeded", 2)):
        for i in range(count):
            db.add(
                Source(
                    tenant_id=UUID(tenant),
                    bot_id=UUID(bot["id"]),
                    kind="md",
                    original_name=f"fixture-{i}.md",
                    storage_key=f"fixture/{tenant}/{i}",
                    size_bytes=10,
                    sha256="0" * 64,
                    created_by=actor,
                )
            )
        db.add(
            Job(tenant_id=UUID(tenant), bot_id=UUID(bot["id"]), type="ingest_batch", status=status)
        )
    db.commit()
    result = platform_call(staff, "GET", f"/bots?organization_id={a}&q=ALP").json()
    assert result["total"] == 1
    row = result["bots"][0]
    assert row["id"] == bot_a["id"] and row["organization"] == {"id": a, "name": "A"}
    assert row["source_count"] == 1 and row["last_ingestion_job_status"] == "failed"
    assert row["published_revision_id"] == str(revision.id)
    assert bot_b["id"] not in str(result) and "Beta" not in str(result)
    assert platform_call(staff, "GET", "/bots?limit=1&offset=1").json()["total"] == 2
    detail = platform_call(staff, "GET", f"/tenants/{a}").json()["bots"][0]
    assert detail["source_count"] == row["source_count"]
    assert detail["last_ingestion_job_status"] == row["last_ingestion_job_status"]


def test_legacy_history_readers_remain_after_post_retirement(app: Any, db: Any) -> None:
    staff = staff_login(app, db)
    record = legacy_onboard(app, db, staff, ONBOARD_FORM, "history")
    response = platform_call(staff, "GET", f"/onboarding/{record['request_id']}")
    assert response.status_code == 200 and response.json()["status"] == "ready"
    csv = platform_call(staff, "GET", "/onboarding.csv")
    assert csv.status_code == 200 and record["request_id"] in csv.text
    assert platform_call(staff, "POST", "/onboarding", data=ONBOARD_FORM).status_code in (404, 405)
