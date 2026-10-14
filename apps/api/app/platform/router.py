"""Platform admin console API (P4-06, docs/11, ADR-018).

Guarded server-side by users.is_platform_staff (never a tenant role); no
impersonation, actor attribution on every staff action. Client list and
detail are read views; onboarding goes through the SHARED ProvisioningService
with a REQUIRED Idempotency-Key and returns the owner one-time invite link
(shown once). Non-staff calls reach 403 FORBIDDEN.
"""

import csv
import io
import json
from typing import Annotated, Any
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    Query,
    Response,
    UploadFile,
)
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session as OrmSession

from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.db.models import (
    AuditEvent,
    Bot,
    Job,
    Membership,
    ProvisioningRequest,
    Tenant,
    UsageEvent,
    User,
)
from app.db.session import get_session
from app.platform.staff import PlatformStaffDep
from app.provisioning.service import ProvisioningPayload, ProvisioningService

router = APIRouter(prefix="/api/v1/platform")

DbSession = Annotated[OrmSession, Depends(get_session)]
CurrentSettings = Annotated[Settings, Depends(get_settings)]


@router.get("/me")
def platform_me(staff: PlatformStaffDep) -> dict[str, Any]:
    """Staff marker for the console UI — the /platform layout uses this per
    request (server-side guard, no impersonation path exists)."""
    return {"id": str(staff.id), "email": str(staff.email)}


@router.get("/tenants")
def platform_tenants(
    staff: PlatformStaffDep,
    db: DbSession,
    q: Annotated[str | None, Query(max_length=100)] = None,
    status: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> dict[str, Any]:
    """Client list: plan label (internal), status, bot count, seats, message
    usage this month, last activity; search and filter."""
    statement = select(Tenant).order_by(Tenant.created_at.desc())
    if status in ("active", "archived"):
        statement = statement.where(Tenant.status == status)
    if q:
        like = f"%{q.strip()}%"
        statement = statement.where(or_(Tenant.name.ilike(like), Tenant.slug.ilike(like)))
    tenants = list(db.execute(statement.limit(limit)).scalars())
    month_start = func.date_trunc("month", func.now())
    clients: list[dict[str, Any]] = []
    for tenant in tenants:
        bots = int(
            db.execute(
                select(func.count())
                .select_from(Bot)
                .where(Bot.tenant_id == tenant.id, Bot.status != "archived")
            ).scalar_one()
        )
        seats = int(
            db.execute(
                select(func.count())
                .select_from(Membership)
                .where(Membership.tenant_id == tenant.id, Membership.status == "active")
            ).scalar_one()
        )
        last_activity = db.execute(
            select(func.max(Bot.updated_at)).where(Bot.tenant_id == tenant.id)
        ).scalar()
        messages_month = int(
            db.execute(
                select(func.count())
                .select_from(UsageEvent)
                .where(
                    UsageEvent.tenant_id == tenant.id,
                    UsageEvent.kind == "message",
                    UsageEvent.created_at >= month_start,
                )
            ).scalar_one()
        )
        clients.append(
            {
                "id": str(tenant.id),
                "name": tenant.name,
                "slug": tenant.slug,
                "status": tenant.status,
                "plan_label": "starter",
                "bots": bots,
                "seats": seats,
                "messages_this_month": messages_month,
                "last_activity": last_activity.isoformat() if last_activity else None,
            }
        )
    return {"tenants": clients, "total": len(clients)}


@router.get("/tenants/{tenant_id}")
def platform_tenant_detail(
    tenant_id: UUID,
    staff: PlatformStaffDep,
    db: DbSession,
) -> dict[str, Any]:
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise ApiError(404, "NOT_FOUND", "Resource not found.")
    bots = [
        {
            "id": str(bot.id),
            "name": bot.name,
            "status": bot.status,
            "published": bot.published_revision_id is not None,
        }
        for bot in db.execute(
            select(Bot).where(Bot.tenant_id == tenant.id).order_by(Bot.created_at.desc())
        ).scalars()
    ]
    failed_jobs = [
        {"id": str(job.id), "type": job.type, "error": job.error}
        for job in db.execute(
            select(Job)
            .where(Job.tenant_id == tenant.id, Job.status == "failed")
            .order_by(Job.updated_at.desc())
            .limit(10)
        ).scalars()
    ]
    members = [
        {
            "user_id": str(member.id),
            "email": str(member.email),
            "role": membership.role,
        }
        for membership, member in db.execute(
            select(Membership, User)
            .join(User, User.id == Membership.user_id)
            .where(Membership.tenant_id == tenant.id)
            .order_by(Membership.created_at)
        ).all()
    ]
    audit_rows = list(
        db.execute(
            select(AuditEvent)
            .where(AuditEvent.tenant_id == tenant.id)
            .order_by(AuditEvent.created_at.desc())
            .limit(15)
        ).scalars()
    )
    usage = int(
        db.execute(
            select(func.count()).select_from(UsageEvent).where(UsageEvent.tenant_id == tenant.id)
        ).scalar_one()
    )
    return {
        "tenant": {
            "id": str(tenant.id),
            "name": tenant.name,
            "slug": tenant.slug,
            "status": tenant.status,
        },
        "bots": bots,
        "failed_jobs": failed_jobs,
        "members": members,
        "recent_audit": [
            {
                "action": row.action,
                "actor": str(row.actor_user_id) if row.actor_user_id else None,
                "target": f"{row.target_type}:{row.target_id}" if row.target_type else None,
                "at": row.created_at.isoformat(),
            }
            for row in audit_rows
        ],
        "usage_events": usage,
    }


@router.get("/onboarding/{request_id}")
def platform_onboarding_status(
    request_id: UUID,
    staff: PlatformStaffDep,
    db: DbSession,
) -> dict[str, Any]:
    """The durable request record: progress and retry evidence (docs/11)."""
    row = db.get(ProvisioningRequest, request_id)
    if row is None:
        raise ApiError(404, "NOT_FOUND", "Resource not found.")
    return {
        "request_id": str(row.id),
        "status": row.status,
        "mode": row.mode,
        "error": row.error,
        "payload": dict(row.payload),
        "result": dict(row.result),
    }


def _staff_csv(filename: str, fieldnames: list[str], rows: list[dict[str, Any]]) -> Response:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return Response(
        content=buffer.getvalue().encode("utf-8"),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/onboarding.csv")
def platform_provisioning_csv(
    staff: PlatformStaffDep,
    db: DbSession,
) -> Response:
    """Durable request trail (CSV aid for support). Actor is attributed."""
    rows: list[dict[str, Any]] = []
    for row in db.execute(
        select(ProvisioningRequest).order_by(ProvisioningRequest.created_at.desc()).limit(500)
    ).scalars():
        rows.append(
            {
                "request_id": str(row.id),
                "mode": row.mode,
                "status": row.status,
                "tenant_id": str(row.tenant_id or ""),
                "actor": str(row.actor_user_id or ""),
                "payload": json.dumps(dict(row.payload)),
                "error": row.error or "",
                "created_at": row.created_at.isoformat(),
            }
        )
    return _staff_csv(
        "provisioning.csv",
        ["request_id", "mode", "status", "tenant_id", "actor", "payload", "error", "created_at"],
        rows,
    )


@router.post("/onboarding", status_code=201)
async def platform_onboarding(
    staff: PlatformStaffDep,
    db: DbSession,
    settings: CurrentSettings,
    client_name: Annotated[str, Form(min_length=1, max_length=200)],
    owner_email: Annotated[str, Form()],
    bot_name: Annotated[str | None, Form(max_length=100)] = None,
    plan_label: Annotated[str, Form(max_length=40)] = "starter",
    notes: Annotated[str | None, Form(max_length=500)] = None,
    files: Annotated[list[UploadFile], File()] | None = None,
    idempotency_key: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Staff onboarding through the SHARED ProvisioningService. Idempotency-Key
    REQUIRED (a replay re-reads the durable row and returns it). The actor is
    the staff user; the owner one-time invite link is returned once."""
    if not idempotency_key or not idempotency_key.strip():
        raise ApiError(400, "VALIDATION_ERROR", "Idempotency-Key header is required.")
    payload = ProvisioningPayload(
        client_name=client_name,
        owner_email=owner_email,
        bot_name=bot_name or None,
        plan_label=plan_label or "starter",
        notes=notes,
    )
    uploads: list[tuple[str, Any]] = [
        (file.filename or f"upload-{index}", file.file) for index, file in enumerate(files or [])
    ]
    service = ProvisioningService(db, settings)
    result = service.onboard_platform_client(
        actor=staff, payload=payload, idempotency_key=idempotency_key.strip(), files=uploads
    )
    return dict(result)
