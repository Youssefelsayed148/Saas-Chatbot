"""Tenants, members and invitations routers (docs/05 phase-1 frozen contract).

`GET /api/v1/me` lives in the auth router; this module adds tenants,
memberships and the one-time-link invitation flow of docs/14 s19.
"""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session as OrmSession

from app.auth import cookies
from app.auth.schemas import MembershipOut, MeResponse
from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.core.tenancy import CurrentUserDep, TenantContextDep
from app.db.models import User
from app.db.session import get_session
from app.tenants.payloads import invitation_payload
from app.tenants.schemas import (
    AcceptInvitationRequest,
    InvitationCreatedOut,
    InvitationCreateRequest,
    InvitationOut,
    MemberOut,
    MemberRoleUpdateRequest,
    TenantCreateRequest,
    TenantOut,
    TenantUpdateRequest,
)
from app.tenants.service import TenantService

router = APIRouter(tags=["tenants"])

DbSession = Annotated[OrmSession, Depends(get_session)]
CsrfOk = Annotated[None, Depends(cookies.require_csrf)]
CurrentSettingsDep = Annotated[Settings, Depends(get_settings)]


@router.post("/api/v1/tenants", response_model=TenantOut, status_code=201)
def create_tenant(
    body: TenantCreateRequest, db: DbSession, user: CurrentUserDep, _: CsrfOk
) -> TenantOut:
    """Create an organization; the creator becomes its owner (docs/06)."""
    service = TenantService(db)
    tenant = service.create_tenant(user, body.name, body.slug)
    return TenantOut.model_validate(tenant)


@router.get("/api/v1/tenants/{tenant_id}", response_model=TenantOut)
def get_tenant(context: TenantContextDep) -> TenantOut:
    return TenantOut.model_validate(context.tenant)


@router.patch("/api/v1/tenants/{tenant_id}", response_model=TenantOut, status_code=200)
def update_tenant(
    body: TenantUpdateRequest,
    context: TenantContextDep,
    _: CsrfOk,
) -> TenantOut:
    """Tenant settings (P4-04): retention window (owner/admin only, audited)."""
    context.require_role("admin")
    service = TenantService(context.db)
    tenant = service.update_tenant(context, body.retention_days)
    return TenantOut.model_validate(tenant)


# --- members (admin+) -------------------------------------------------------


@router.get("/api/v1/tenants/{tenant_id}/members", response_model=list[MemberOut])
def list_members(context: TenantContextDep) -> list[MemberOut]:
    context.require_role("admin")
    service = TenantService(context.db)
    return [
        MemberOut(
            user_id=member.id,
            email=member.email,
            role=membership.role,
            status=membership.status,
            joined_at=membership.created_at,
        )
        for membership, member in service.members_of(context.tenant_id)
    ]


@router.patch("/api/v1/tenants/{tenant_id}/members/{user_id}", response_model=MemberOut)
def change_member_role(
    user_id: UUID, body: MemberRoleUpdateRequest, context: TenantContextDep, _: CsrfOk
) -> MemberOut:
    context.require_role("admin")
    service = TenantService(context.db)
    membership = service.change_role(context, user_id, body.role)
    member = context.db.get(User, membership.user_id)
    if member is None:  # pragma: no cover - FK guarantees presence
        raise ApiError(404, "NOT_FOUND", "Member not found.")
    return MemberOut(
        user_id=member.id,
        email=member.email,
        role=membership.role,
        status=membership.status,
        joined_at=membership.created_at,
    )


@router.delete("/api/v1/tenants/{tenant_id}/members/{user_id}", status_code=204)
def remove_member(user_id: UUID, context: TenantContextDep, _: CsrfOk) -> Response:
    context.require_role("admin")
    TenantService(context.db).remove_member(context, user_id)
    return Response(status_code=204)


# --- invitations (owner/admin) ----------------------------------------------


@router.post(
    "/api/v1/tenants/{tenant_id}/invitations",
    response_model=InvitationCreatedOut,
    status_code=201,
)
def create_invitation(
    body: InvitationCreateRequest, context: TenantContextDep, _: CsrfOk
) -> InvitationOut:
    """Returns the one-time link once; only its SHA-256 hash is stored."""
    context.require_role("admin")
    service = TenantService(context.db)
    invitation, token = service.create_invitation(context, body.email, body.role, body.expiry_days)
    return invitation_payload(invitation, token)


@router.get("/api/v1/tenants/{tenant_id}/invitations", response_model=list[InvitationOut])
def list_invitations(context: TenantContextDep) -> list[InvitationOut]:
    context.require_role("admin")
    service = TenantService(context.db)
    now = datetime.now(UTC)
    return [
        InvitationOut(
            id=invitation.id,
            email=invitation.email,
            role=invitation.role,
            expires_at=invitation.expires_at,
            created_at=invitation.created_at,
            expired=invitation.expires_at <= now,
        )
        for invitation in service.pending_invitations(context)
    ]


@router.post(
    "/api/v1/tenants/{tenant_id}/invitations/{invitation_id}/resend",
    response_model=InvitationCreatedOut,
)
def resend_invitation(invitation_id: UUID, context: TenantContextDep, _: CsrfOk) -> InvitationOut:
    context.require_role("admin")
    service = TenantService(context.db)
    invitation, token = service.resend_invitation(context, invitation_id, 7)
    return invitation_payload(invitation, token)


@router.delete("/api/v1/tenants/{tenant_id}/invitations/{invitation_id}", status_code=204)
def revoke_invitation(invitation_id: UUID, context: TenantContextDep, _: CsrfOk) -> Response:
    context.require_role("admin")
    TenantService(context.db).revoke_invitation(context, invitation_id)
    return Response(status_code=204)


@router.post("/api/v1/invitations/accept", response_model=MeResponse)
def accept_invitation(
    body: AcceptInvitationRequest,
    response: Response,
    request: Request,
    db: DbSession,
    settings: CurrentSettingsDep,
    user: CurrentUserDep,
    _: CsrfOk,
) -> MeResponse:
    """Join with the invited role; the session email must match the invitation."""
    cookies.ensure_csrf_cookie(request, response, settings)
    service = TenantService(db)
    service.accept_invitation(db, user, body.token)
    memberships = [
        MembershipOut(
            tenant_id=tenant.id,
            tenant_name=tenant.name,
            tenant_slug=tenant.slug,
            role=membership.role,
        )
        for membership, tenant in service.memberships_of(user.id)
    ]
    return MeResponse(
        id=user.id,
        email=user.email,
        is_platform_staff=user.is_platform_staff,
        memberships=memberships,
    )
