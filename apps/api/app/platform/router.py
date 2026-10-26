"""Platform admin console API (P4-06, docs/11, ADR-018).

Guarded server-side by users.is_platform_staff (never a tenant role); no
impersonation, actor attribution on every staff action. Dedicated organization,
user and bot endpoints replace batch staff onboarding. Historical provisioning
status and CSV readers remain available. Non-staff calls reach 403 FORBIDDEN.
"""

import csv
import io
import json
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import (
    APIRouter,
    Depends,
    Query,
    Response,
)
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session as OrmSession

from app.auth import cookies
from app.bots.factory import create_bot_record
from app.bots.schemas import BotOut
from app.core.audit import audit_action_matches, record_audit
from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.db.models import (
    AuditEvent,
    Bot,
    Conversation,
    Invitation,
    Job,
    Membership,
    Message,
    ProvisioningRequest,
    Tenant,
    UsageEvent,
    User,
)
from app.db.session import get_session
from app.jobs.queue import request_cancel, requeue_for_retry
from app.platform.bots import bot_summary
from app.platform.staff import PlatformStaffDep
from app.quotas.rag import counts_toward_message_quota
from app.quotas.service import PLACEHOLDER_PLAN_LIMITS, PLAN_LABELS

router = APIRouter(prefix="/api/v1/platform")


DbSession = Annotated[OrmSession, Depends(get_session)]
CurrentSettings = Annotated[Settings, Depends(get_settings)]
CsrfOk = Annotated[None, Depends(cookies.require_csrf)]


class PlatformBotCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    plan_label: str = "starter"

    @field_validator("name", mode="before")
    @classmethod
    def trimmed_name(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @field_validator("plan_label")
    @classmethod
    def valid_plan(cls, value: str) -> str:
        if value not in PLAN_LABELS:
            raise ValueError("Unknown plan.")
        return value


class OrganizationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    status: str | None = None

    @field_validator("name", mode="before")
    @classmethod
    def trimmed_optional_name(cls, value: Any) -> Any:
        if value is None:
            raise ValueError("Name cannot be null.")
        return value.strip() if isinstance(value, str) else value

    @field_validator("status")
    @classmethod
    def valid_status(cls, value: str | None) -> str | None:
        if value not in ("active", "archived"):
            raise ValueError("Unknown status.")
        return value


class ReasonAction(BaseModel):
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("reason")
    @classmethod
    def reason_must_contain_text(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 3:
            raise ValueError("Reason must contain at least three non-space characters.")
        return cleaned


class PlanAssignment(ReasonAction):
    plan_label: str = Field(min_length=1, max_length=40)


class QuotaOverride(ReasonAction):
    limits: dict[str, int] = Field(max_length=8)

    @field_validator("limits")
    @classmethod
    def limits_are_nonnegative(cls, value: dict[str, int]) -> dict[str, int]:
        from app.quotas.service import COUNTERS

        if not value or any(key not in COUNTERS or limit < 0 for key, limit in value.items()):
            raise ValueError("Provide known quota names with non-negative integer limits.")
        return value


@router.get("/me")
def platform_me(staff: PlatformStaffDep) -> dict[str, Any]:
    """Staff marker for the console UI — the /platform layout uses this per
    request (server-side guard, no impersonation path exists)."""
    return {"id": str(staff.id), "email": str(staff.email)}


@router.get("/quotas")
def platform_quotas(staff: PlatformStaffDep) -> dict[str, Any]:
    del staff
    return {
        "placeholder": True,
        "plans": {name: limits.__dict__ for name, limits in PLACEHOLDER_PLAN_LIMITS.items()},
    }


@router.get("/tenants")
def platform_tenants(
    staff: PlatformStaffDep,
    db: DbSession,
    q: Annotated[str | None, Query(max_length=100)] = None,
    status: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    """Client list: plan label (internal), status, bot count, seats, message
    usage this month, last activity; search and filter."""
    statement = select(Tenant).order_by(Tenant.created_at.desc(), Tenant.id)
    if status in ("active", "archived"):
        statement = statement.where(Tenant.status == status)
    if q:
        like = f"%{q.strip()}%"
        statement = statement.where(or_(Tenant.name.ilike(like), Tenant.slug.ilike(like)))
    total = db.scalar(select(func.count()).select_from(statement.order_by(None).subquery()))
    tenants = list(db.execute(statement.offset(offset).limit(limit)).scalars())
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
                    counts_toward_message_quota(),
                )
            ).scalar_one()
        )
        clients.append(
            {
                "id": str(tenant.id),
                "name": tenant.name,
                "slug": tenant.slug,
                "status": tenant.status,
                "plan_label": tenant.plan_label,
                "bots": bots,
                "seats": seats,
                "messages_this_month": messages_month,
                "last_activity": last_activity.isoformat() if last_activity else None,
            }
        )
    return {"tenants": clients, "total": total}


@router.post("/tenants", status_code=201)
def platform_create_organization(
    payload: OrganizationCreate,
    staff: PlatformStaffDep,
    db: DbSession,
    _: CsrfOk,
) -> dict[str, Any]:
    from app.tenants.service import TenantService

    tenant = Tenant(
        id=uuid4(),
        name=payload.name,
        slug=TenantService(db)._unique_slug(payload.name),
        plan_label=payload.plan_label,
        status="active",
        quota_overrides={},
    )
    db.add(tenant)
    db.flush()
    record_audit(
        db,
        action="platform.organization.created",
        tenant_id=tenant.id,
        actor_user_id=staff.id,
        target_type="tenant",
        target_id=str(tenant.id),
        metadata={"name": tenant.name, "plan_label": tenant.plan_label},
    )
    db.commit()
    return {
        "id": str(tenant.id),
        "name": tenant.name,
        "slug": tenant.slug,
        "plan_label": tenant.plan_label,
        "status": tenant.status,
        "created_at": tenant.created_at.isoformat(),
    }


@router.patch("/tenants/{tenant_id}")
def platform_update_organization(
    tenant_id: UUID,
    payload: OrganizationUpdate,
    staff: PlatformStaffDep,
    db: DbSession,
    _: CsrfOk,
) -> dict[str, Any]:
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise ApiError(404, "NOT_FOUND", "Resource not found.")
    changes = {
        key: value
        for key, value in payload.model_dump(exclude_unset=True).items()
        if getattr(tenant, key) != value
    }
    if changes:
        before = {key: getattr(tenant, key) for key in changes}
        for key, value in changes.items():
            setattr(tenant, key, value)
        record_audit(
            db,
            action="platform.organization.updated",
            tenant_id=tenant.id,
            actor_user_id=staff.id,
            target_type="tenant",
            target_id=str(tenant.id),
            metadata={"before": before, "after": changes, "fields": list(changes)},
        )
        db.commit()
    return {
        "id": str(tenant.id),
        "name": tenant.name,
        "slug": tenant.slug,
        "plan_label": tenant.plan_label,
        "status": tenant.status,
        "created_at": tenant.created_at.isoformat(),
    }


@router.get("/operations/jobs")
def platform_job_health(
    staff: PlatformStaffDep,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> dict[str, Any]:
    del staff
    counts: dict[str, int] = {
        status: int(count)
        for status, count in db.execute(select(Job.status, func.count()).group_by(Job.status))
    }
    jobs = list(db.execute(select(Job).order_by(Job.created_at.desc()).limit(limit)).scalars())
    return {
        "counts": counts,
        "jobs": [
            {
                "id": str(job.id),
                "tenant_id": str(job.tenant_id),
                "bot_id": str(job.bot_id),
                "type": job.type,
                "status": job.status,
                "attempts": job.attempts,
                "run_at": job.run_at.isoformat(),
                "updated_at": job.updated_at.isoformat(),
                "error": job.error,
            }
            for job in jobs
        ],
    }


@router.post("/operations/jobs/{job_id}/retry")
def platform_retry_job(
    job_id: UUID, payload: ReasonAction, staff: PlatformStaffDep, db: DbSession
) -> dict[str, Any]:
    job = db.get(Job, job_id)
    if job is None:
        raise ApiError(404, "NOT_FOUND", "Resource not found.")
    requeue_for_retry(db, job)
    record_audit(
        db,
        action="platform.job.retry",
        tenant_id=job.tenant_id,
        actor_user_id=staff.id,
        target_type="job",
        target_id=str(job.id),
        metadata={"reason": payload.reason.strip()},
    )
    db.commit()
    return {"id": str(job.id), "status": job.status}


@router.post("/operations/jobs/{job_id}/cancel")
def platform_cancel_job(
    job_id: UUID, payload: ReasonAction, staff: PlatformStaffDep, db: DbSession
) -> dict[str, Any]:
    job = db.get(Job, job_id)
    if job is None:
        raise ApiError(404, "NOT_FOUND", "Resource not found.")
    request_cancel(db, job)
    record_audit(
        db,
        action="platform.job.cancel",
        tenant_id=job.tenant_id,
        actor_user_id=staff.id,
        target_type="job",
        target_id=str(job.id),
        metadata={"reason": payload.reason.strip()},
    )
    db.commit()
    return {"id": str(job.id), "status": job.status}


@router.patch("/tenants/{tenant_id}/plan")
def platform_assign_plan(
    tenant_id: UUID, payload: PlanAssignment, staff: PlatformStaffDep, db: DbSession
) -> dict[str, Any]:
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise ApiError(404, "NOT_FOUND", "Resource not found.")
    label = payload.plan_label.strip()
    if label.lower() not in PLAN_LABELS:
        raise ApiError(
            422, "VALIDATION_ERROR", "Choose a PLACEHOLDER plan: free, starter, pro, or business."
        )
    previous = tenant.plan_label
    tenant.plan_label = label.lower()
    record_audit(
        db,
        action="platform.tenant.plan_assigned",
        tenant_id=tenant.id,
        actor_user_id=staff.id,
        target_type="tenant",
        target_id=str(tenant.id),
        metadata={"reason": payload.reason.strip(), "from": previous, "to": label.lower()},
    )
    db.commit()
    return {"tenant_id": str(tenant.id), "plan_label": label.lower()}


@router.patch("/tenants/{tenant_id}/quota-overrides")
def platform_quota_override(
    tenant_id: UUID, payload: QuotaOverride, staff: PlatformStaffDep, db: DbSession
) -> dict[str, Any]:
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise ApiError(404, "NOT_FOUND", "Resource not found.")
    tenant.quota_overrides = {**tenant.quota_overrides, **payload.limits}
    record_audit(
        db,
        action="platform.tenant.quota_override",
        tenant_id=tenant.id,
        actor_user_id=staff.id,
        target_type="tenant",
        target_id=str(tenant.id),
        metadata={"reason": payload.reason, "limits": payload.limits},
    )
    db.commit()
    return {"tenant_id": str(tenant.id), "limits": tenant.quota_overrides}


@router.post("/tenants/{tenant_id}/bots", response_model=BotOut, status_code=201)
def platform_create_bot(
    tenant_id: UUID,
    payload: PlatformBotCreate,
    staff: PlatformStaffDep,
    db: DbSession,
    _: CsrfOk,
) -> BotOut:
    bot = create_bot_record(
        db, tenant_id=tenant_id, name=payload.name, actor=staff, audit_action="platform.bot.created"
    )
    db.commit()
    return BotOut.model_validate(bot)


@router.delete("/tenants/{tenant_id}/bots/{bot_id}", response_model=BotOut, status_code=200)
def platform_archive_bot(
    tenant_id: UUID, bot_id: UUID, staff: PlatformStaffDep, db: DbSession, _: CsrfOk
) -> BotOut:
    from datetime import UTC, datetime

    bot = db.execute(
        select(Bot).where(Bot.id == bot_id, Bot.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if bot is None:
        raise ApiError(404, "NOT_FOUND", "Resource not found.")
    if bot.status != "archived":
        bot.status = "archived"
        bot.updated_at = datetime.now(UTC)
        record_audit(
            db,
            action="platform.bot.archived",
            tenant_id=tenant_id,
            actor_user_id=staff.id,
            target_type="bot",
            target_id=str(bot.id),
        )
        db.commit()
    return BotOut.model_validate(bot)


@router.post("/bots/{bot_id}/pause")
def platform_pause_bot(
    bot_id: UUID, payload: ReasonAction, staff: PlatformStaffDep, db: DbSession
) -> dict[str, Any]:
    bot = db.get(Bot, bot_id)
    if bot is None:
        raise ApiError(404, "NOT_FOUND", "Resource not found.")
    if bot.status == "archived":
        raise ApiError(409, "BOT_ARCHIVED", "Archived bots cannot be paused.")
    bot.status = "paused"
    record_audit(
        db,
        action="platform.bot.paused",
        tenant_id=bot.tenant_id,
        actor_user_id=staff.id,
        target_type="bot",
        target_id=str(bot.id),
        metadata={"reason": payload.reason.strip()},
    )
    db.commit()
    return {"bot_id": str(bot.id), "status": bot.status}


@router.get("/analytics")
def platform_analytics(staff: PlatformStaffDep, db: DbSession) -> dict[str, Any]:
    del staff
    tenant_count = int(db.execute(select(func.count()).select_from(Tenant)).scalar_one())
    bot_count = int(db.execute(select(func.count()).select_from(Bot)).scalar_one())
    conversation_count = int(
        db.execute(select(func.count()).select_from(Conversation)).scalar_one()
    )
    message_count = int(db.execute(select(func.count()).select_from(Message)).scalar_one())
    handoff_count = int(
        db.execute(
            select(func.count())
            .select_from(Conversation)
            .where(Conversation.handoff_reason.is_not(None))
        ).scalar_one()
    )
    tenant_rows = db.execute(
        select(Tenant.id, Tenant.name, Tenant.plan_label).order_by(Tenant.name)
    ).all()
    per_client: list[dict[str, Any]] = []
    for tenant_id, name, plan_label in tenant_rows:
        event_rows = db.execute(
            select(UsageEvent.kind, func.count())
            .where(UsageEvent.tenant_id == tenant_id)
            .group_by(UsageEvent.kind)
        )
        events = {kind: int(count) for kind, count in event_rows}
        # Source label: staff playground turns are listed apart from client traffic.
        playground = int(
            db.execute(
                select(func.count())
                .select_from(UsageEvent)
                .where(
                    UsageEvent.tenant_id == tenant_id,
                    UsageEvent.kind == "message",
                    ~counts_toward_message_quota(),
                )
            ).scalar_one()
        )
        events["message"] = max(0, events.get("message", 0) - playground)
        events["playground_message"] = playground
        per_client.append(
            {
                "tenant_id": str(tenant_id),
                "name": name,
                "plan_label": plan_label,
                "usage": events,
            }
        )
    return {
        "tenants": tenant_count,
        "bots": bot_count,
        "conversations": conversation_count,
        "messages": message_count,
        "handoffs": handoff_count,
        "handoff_rate": handoff_count / conversation_count if conversation_count else 0,
        "clients": per_client,
        "ai_cost": None,
    }


@router.get("/audit")
def platform_audit_review(
    staff: PlatformStaffDep,
    db: DbSession,
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> dict[str, Any]:
    statement = select(AuditEvent).order_by(AuditEvent.created_at.desc())
    if q:
        pattern = f"%{q.strip()}%"
        statement = statement.where(
            or_(audit_action_matches(q), AuditEvent.target_type.ilike(pattern))
        )
    rows = list(db.execute(statement.limit(limit)).scalars())
    return {
        "events": [
            {
                "tenant_id": str(row.tenant_id) if row.tenant_id else None,
                "action": row.action,
                "actor_user_id": str(row.actor_user_id) if row.actor_user_id else None,
                "target_type": row.target_type,
                "target_id": row.target_id,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]
    }


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
        bot_summary(db, bot)
        for bot in db.scalars(
            select(Bot).where(Bot.tenant_id == tenant.id).order_by(Bot.created_at.desc())
        )
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
            "status": membership.status,
        }
        for membership, member in db.execute(
            select(Membership, User)
            .join(User, User.id == Membership.user_id)
            .where(Membership.tenant_id == tenant.id, Membership.status == "active")
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
    from app.quotas.service import usage_snapshot

    return {
        "tenant": {
            "id": str(tenant.id),
            "name": tenant.name,
            "slug": tenant.slug,
            "status": tenant.status,
            "plan_label": tenant.plan_label,
            "created_at": tenant.created_at.isoformat(),
        },
        "bots": bots,
        "counts": {"members": len(members), "bots": len(bots)},
        "failed_jobs": failed_jobs,
        "members": members,
        "pending_invitations": [
            {"id": str(invite.id), "email": invite.email, "role": invite.role}
            for invite in db.scalars(
                select(Invitation)
                .where(
                    Invitation.tenant_id == tenant.id,
                    Invitation.accepted_at.is_(None),
                    Invitation.revoked_at.is_(None),
                    Invitation.expires_at > datetime.now(UTC),
                )
                .order_by(Invitation.created_at)
            )
        ],
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
        "quota": usage_snapshot(db, tenant),
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
