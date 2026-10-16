"""P7-01 staff operations, plan labels, analytics, and audit review."""

from typing import Any
from uuid import uuid4

from sqlalchemy import select

from app.db.models import AuditEvent, Job
from tests.helpers import make_bot, seeded_tenant
from tests.test_platform import platform_call, staff_login


def test_platform_ops_require_staff_reason_and_record_audit(app: Any, db: Any) -> None:
    tenant = seeded_tenant(app, db, prefix="p7ops")
    bot = make_bot(tenant, "Ops bot")
    staff = staff_login(app, db)
    admin = tenant.as_user("admin")
    job = Job(
        id=uuid4(),
        tenant_id=tenant.tenant_id,
        bot_id=bot["id"],
        type="ingest_batch",
        status="failed",
        payload={},
        attempts=1,
        max_attempts=3,
        error="failed safely",
    )
    db.add(job)
    db.commit()

    assert platform_call(admin, "GET", "/operations/jobs").status_code == 403
    invalid = platform_call(staff, "POST", f"/operations/jobs/{job.id}/retry", json={"reason": " "})
    assert invalid.status_code == 422
    retried = platform_call(
        staff,
        "POST",
        f"/operations/jobs/{job.id}/retry",
        json={"reason": "Customer asked for retry"},
    )
    assert retried.status_code == 200, retried.text
    assert retried.json()["status"] == "pending"
    db.expire_all()  # the API committed in its own session; drop this session's cached row
    assert db.execute(select(Job).where(Job.id == job.id)).scalar_one().attempts == 0
    audit = db.execute(
        select(AuditEvent).where(AuditEvent.action == "platform.job.retry")
    ).scalar_one()
    assert audit.actor_user_id is not None
    assert audit.metadata_json["reason"] == "Customer asked for retry"

    cancelled = platform_call(
        staff,
        "POST",
        f"/operations/jobs/{job.id}/cancel",
        json={"reason": "Duplicate upload job"},
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"


def test_plan_assignment_and_platform_analytics_are_measured(app: Any, db: Any) -> None:
    tenant = seeded_tenant(app, db, prefix="p7plan")
    staff = staff_login(app, db)
    assignment = platform_call(
        staff,
        "PATCH",
        f"/tenants/{tenant.tenant_id}/plan",
        json={"plan_label": "pro", "reason": "Owner approved plan change"},
    )
    assert assignment.status_code == 200, assignment.text
    assert assignment.json()["plan_label"] == "pro"
    listing = platform_call(staff, "GET", "/tenants?q=p7plan")
    row = next(item for item in listing.json()["tenants"] if item["id"] == str(tenant.tenant_id))
    assert row["plan_label"] == "pro"
    analytics = platform_call(staff, "GET", "/analytics")
    assert analytics.status_code == 200
    assert any(
        client["tenant_id"] == str(tenant.tenant_id) and client["plan_label"] == "pro"
        for client in analytics.json()["clients"]
    )
    audit = platform_call(staff, "GET", "/audit?q=plan_assigned")
    assert audit.status_code == 200
    assert any(item["action"] == "platform.tenant.plan_assigned" for item in audit.json()["events"])


def test_platform_job_health_and_unknown_job_hidden(app: Any, db: Any) -> None:
    staff = staff_login(app, db)
    result = platform_call(staff, "GET", "/operations/jobs")
    assert result.status_code == 200
    assert isinstance(result.json()["counts"], dict)
    missing = platform_call(
        staff, "POST", f"/operations/jobs/{uuid4()}/cancel", json={"reason": "Unknown job"}
    )
    assert missing.status_code == 404


def test_platform_pause_bot_requires_reason_and_is_audited(app: Any, db: Any) -> None:
    tenant = seeded_tenant(app, db, prefix="p7pause")
    bot = make_bot(tenant, "Pause me")
    staff = staff_login(app, db)
    response = platform_call(
        staff,
        "POST",
        f"/bots/{bot['id']}/pause",
        json={"reason": "Owner requested an incident pause"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "paused"
    db.expire_all()
    audit = db.execute(
        select(AuditEvent).where(AuditEvent.action == "platform.bot.paused")
    ).scalar_one()
    assert audit.actor_user_id is not None
    assert audit.metadata_json["reason"] == "Owner requested an incident pause"
