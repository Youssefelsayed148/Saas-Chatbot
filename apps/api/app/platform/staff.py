"""Platform-staff authorization (P4-06, docs/11, ADR-018/009).

The ``users.is_platform_staff`` flag is SEPARATE from tenant roles: it grants
access to the /platform operations area only. It never reuses the tenant
context; no impersonation exists — staff actions run as the staff user with
actor attribution.

Server-side only: the dependency resolves the session user again; the UI
takes no shortcuts (its guard is the same API check per request).
"""

from typing import Annotated

from fastapi import Depends

from app.auth.cookies import get_current_user
from app.core.errors import ApiError
from app.db.models import User


def get_platform_staff(user: Annotated[User, Depends(get_current_user)]) -> User:
    if not user.is_platform_staff:
        # Non-staff get the normal tenant-area error format; hidden resources
        # 404 — here the AREA exists, so the refusal is explicit (docs/11:
        # non-staff get 403/404).
        raise ApiError(403, "FORBIDDEN", "Platform staff access required.")
    return user


PlatformStaffDep = Annotated[User, Depends(get_platform_staff)]


def staff_tenant_scope(user: User) -> None:
    """Staff actions do not borrow tenant roles: callers never receive a
    TenantContext via this module (kept for explicit documentation)."""
    del user


def verify_platform_staff(user: User) -> None:
    if not user.is_platform_staff:
        raise ApiError(403, "FORBIDDEN", "Platform staff access required.")
