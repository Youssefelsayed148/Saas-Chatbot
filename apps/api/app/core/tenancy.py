"""Reusable tenant-scoping dependency (ADR-010).

Resolves the tenant from the path, verifies active membership, and hands
services a ``TenantContext``. Hidden resources return 404 — never 403 —
so a guessed tenant id reveals nothing.
"""

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy.orm import Session as OrmSession

from app.auth.cookies import get_current_user
from app.core.errors import ApiError
from app.db.models import Membership, Tenant, User
from app.db.session import get_session

ROLE_LEVELS: dict[str, int] = {"viewer": 1, "editor": 2, "admin": 3}
ROLES = tuple(ROLE_LEVELS)


def role_at_least(role: str, minimum: str) -> bool:
    if role not in ROLE_LEVELS or minimum not in ROLE_LEVELS:
        raise ApiError(500, "INTERNAL_ERROR", "Unknown role referenced.")
    return ROLE_LEVELS[role] >= ROLE_LEVELS[minimum]


@dataclass
class TenantContext:
    """Validated caller context for one tenant-scoped request."""

    db: OrmSession
    user: User
    tenant: Tenant
    membership: Membership | None

    @property
    def role(self) -> str:
        return self.membership.role if self.membership else "platform_staff"

    def require_role(self, minimum: str) -> None:
        """Raise 403 unless the caller holds at least `minimum` (docs/06 matrix)."""
        if not self.user.is_platform_staff and not role_at_least(self.role, minimum):
            raise ApiError(
                403,
                "FORBIDDEN",
                f"This action requires the {minimum} role or higher.",
            )

    def require_operator(self) -> None:
        if not self.user.is_platform_staff:
            raise ApiError(403, "FORBIDDEN", "Only platform staff can control the bot.")

    # Convenience for services that need ids as primitives.
    @property
    def tenant_id(self) -> UUID:
        return self.tenant.id


def get_tenant_context(
    tenant_id: UUID,
    request: Request,
    db: Annotated[OrmSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> TenantContext:
    tenant = db.get(Tenant, tenant_id)
    if tenant is None or tenant.status != "active":
        raise ApiError(404, "NOT_FOUND", "Resource not found.")
    membership = (
        db.query(Membership)
        .filter(
            Membership.tenant_id == tenant_id,
            Membership.user_id == user.id,
            Membership.status == "active",
        )
        .one_or_none()
    )
    if membership is None and not user.is_platform_staff:
        # Do not reveal the tenant exists: a hidden resource looks like a 404.
        raise ApiError(404, "NOT_FOUND", "Resource not found.")
    context = TenantContext(db=db, user=user, tenant=tenant, membership=membership)
    minimum = request.scope["route"].openapi_extra["x-minimum-role"]
    route = request.scope["route"]
    inbox_action = request.method != "GET" and (
        "/inbox/" in route.path
        or route.path.startswith("/api/v1/tenants/{tenant_id}/conversations/")
    )
    if minimum == "editor" and membership is None and inbox_action:
        raise ApiError(403, "FORBIDDEN", "Inbox actions require an active tenant membership.")
    if minimum == "platform_staff_only":
        context.require_operator()
    else:
        context.require_role(minimum)
    return context


TenantContextDep = Annotated[TenantContext, Depends(get_tenant_context)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]
