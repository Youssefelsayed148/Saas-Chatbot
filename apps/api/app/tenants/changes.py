"""Admin requests with bounded attachments; staff triage without membership."""

from datetime import UTC, datetime
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.auth import cookies
from app.core.audit import record_audit
from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.core.tenancy import TenantContextDep
from app.db.models import ChangeRequest, Tenant
from app.db.session import get_session
from app.knowledge.service import read_upload, safe_display_name
from app.knowledge.storage import get_storage
from app.platform.staff import PlatformStaffDep
from app.quotas.service import lock_tenant

router = APIRouter(tags=["change-requests"])
CsrfOk = Annotated[None, Depends(cookies.require_csrf)]
CurrentSettings = Annotated[Settings, Depends(get_settings)]
DbSession = Annotated[OrmSession, Depends(get_session)]
RequestType = Literal["knowledge", "text_change", "domain", "delete_org", "other"]


class ChangeRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    tenant_id: UUID
    requester_id: UUID | None
    type: RequestType
    text: str
    attachments: list[dict[str, Any]]
    status: str
    created_at: datetime
    updated_at: datetime


class TriageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["pending", "triaged", "in_progress", "completed", "rejected"]


def _out(row: ChangeRequest) -> ChangeRequestOut:
    out = ChangeRequestOut.model_validate(row)
    out.attachments = [
        {"id": item["id"], "name": item["name"], "size_bytes": item["size_bytes"]}
        for item in row.attachments
    ]
    return out


@router.get("/api/v1/tenants/{tenant_id}/change-requests", response_model=list[ChangeRequestOut])
def list_change_requests(context: TenantContextDep) -> list[ChangeRequestOut]:
    context.require_role("admin")
    return [
        _out(row)
        for row in context.db.scalars(
            select(ChangeRequest)
            .where(
                ChangeRequest.tenant_id == context.tenant_id,
            )
            .order_by(ChangeRequest.created_at.desc())
            .limit(200)
        )
    ]


@router.post(
    "/api/v1/tenants/{tenant_id}/change-requests", response_model=ChangeRequestOut, status_code=201
)
def create_change_request(
    context: TenantContextDep,
    settings: CurrentSettings,
    _: CsrfOk,
    type: Annotated[RequestType, Form()],
    text: Annotated[str, Form(min_length=1, max_length=10000)],
    files: Annotated[list[UploadFile] | None, File()] = None,
) -> ChangeRequestOut:
    context.require_role("admin")
    lock_tenant(context.db, context.tenant_id)
    if not text.strip():
        raise ApiError(422, "VALIDATION_ERROR", "Describe the requested change.")
    uploads = files or []
    if len(uploads) > settings.max_upload_files:
        raise ApiError(422, "VALIDATION_ERROR", "Too many attachments.")
    # Validate/read all bounded inputs before persisting any files.
    data = [
        (safe_display_name(file.filename or "attachment"), read_upload(file.file, settings))
        for file in uploads
    ]
    row = ChangeRequest(
        id=uuid4(),
        tenant_id=context.tenant_id,
        requester_id=context.user.id,
        type=type,
        text=text.strip(),
        attachments=[],
        status="pending",
    )
    storage = get_storage(settings)
    saved: list[str] = []
    try:
        attachments = []
        for name, raw in data:
            key = storage.save(context.tenant_id, row.id, "txt", raw)
            saved.append(key)
            attachments.append(
                {"id": str(uuid4()), "name": name, "storage_key": key, "size_bytes": len(raw)}
            )
        row.attachments = attachments
        context.db.add(row)
        record_audit(
            context.db,
            action="change_request.created",
            tenant_id=context.tenant_id,
            actor_user_id=context.user.id,
            target_type="change_request",
            target_id=str(row.id),
        )
        context.db.commit()
    except Exception:
        context.db.rollback()
        for key in saved:
            storage.delete(key)
        raise
    return _out(row)


@router.get("/api/v1/tenants/{tenant_id}/change-requests/{request_id}/attachments/{attachment_id}")
def download_change_attachment(
    request_id: UUID, attachment_id: UUID, context: TenantContextDep, settings: CurrentSettings
) -> Response:
    context.require_role("admin")
    row = context.db.scalar(
        select(ChangeRequest).where(
            ChangeRequest.id == request_id, ChangeRequest.tenant_id == context.tenant_id
        )
    )
    attachment = (
        next((item for item in row.attachments if item["id"] == str(attachment_id)), None)
        if row
        else None
    )
    if attachment is None:
        raise ApiError(404, "NOT_FOUND", "Attachment not found.")
    return Response(
        get_storage(settings).open(str(attachment["storage_key"])),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": 'attachment; filename="attachment"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/api/v1/platform/change-requests", response_model=list[ChangeRequestOut])
def operator_change_queue(staff: PlatformStaffDep, db: DbSession) -> list[ChangeRequestOut]:
    return [
        _out(row)
        for row in db.scalars(
            select(ChangeRequest)
            .join(Tenant)
            .where(
                Tenant.status == "active",
            )
            .order_by(ChangeRequest.created_at.desc())
            .limit(200)
        )
    ]


@router.patch("/api/v1/platform/change-requests/{request_id}", response_model=ChangeRequestOut)
def triage_change_request(
    request_id: UUID, body: TriageRequest, staff: PlatformStaffDep, db: DbSession, _: CsrfOk
) -> ChangeRequestOut:
    row = db.scalar(
        select(ChangeRequest)
        .join(Tenant)
        .where(ChangeRequest.id == request_id, Tenant.status == "active")
        .with_for_update()
    )
    if row is None:
        raise ApiError(404, "NOT_FOUND", "Request not found.")
    previous = row.status
    row.status, row.updated_at = body.status, datetime.now(UTC)
    record_audit(
        db,
        action="change_request.triaged",
        tenant_id=row.tenant_id,
        actor_user_id=staff.id,
        target_type="change_request",
        target_id=str(row.id),
        metadata={"from": previous, "to": body.status},
    )
    db.commit()
    return _out(row)
