"""Pydantic contracts for tenants, memberships and invitations (docs/05, docs/14 s19)."""

import re
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SLUG_MAX_LENGTH = 63
NAME_MAX_LENGTH = 100

DEFAULT_INVITATION_EXPIRY_DAYS = 7  # docs/14 s19
MAX_INVITATION_EXPIRY_DAYS = 30


class TenantCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=NAME_MAX_LENGTH)
    slug: str | None = Field(default=None, max_length=SLUG_MAX_LENGTH)

    @field_validator("slug")
    @classmethod
    def slug_shape(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not SLUG_RE.fullmatch(value):
            raise ValueError("Slug must be lowercase letters, digits and dashes.")
        return value


class TenantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    slug: str
    status: str
    # Message retention override (P4-04); NULL falls back to the deployment default.
    retention_days: int | None = None
    created_at: datetime


class TenantUpdateRequest(BaseModel):
    """Tenant-level settings (P4-04): retention only for now; admin only."""

    model_config = ConfigDict(extra="forbid")
    retention_days: int | None = Field(default=None, ge=1, le=365)


class MemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    user_id: UUID
    email: str
    role: Literal["admin", "editor", "viewer"]
    status: str
    joined_at: datetime


class MemberRoleUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["admin", "editor", "viewer"]


class InvitationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    role: Literal["admin", "editor", "viewer"] = "viewer"
    expiry_days: int = Field(
        default=DEFAULT_INVITATION_EXPIRY_DAYS, ge=1, le=MAX_INVITATION_EXPIRY_DAYS
    )


class InvitationOut(BaseModel):
    """Pending invitations expose no tokens; `expires_at` flags expiry client-side."""

    model_config = ConfigDict(from_attributes=True)
    id: UUID
    email: str
    role: Literal["admin", "editor", "viewer"]
    expires_at: datetime
    created_at: datetime
    expired: bool


class InvitationCreatedOut(InvitationOut):
    """Create responses carry the one-time link once; the raw token is never stored."""

    link_path: str


class AcceptInvitationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=16, max_length=200)


class MembershipResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    tenant_id: UUID
    tenant_name: str
    tenant_slug: str
    role: Literal["admin", "editor", "viewer"]
