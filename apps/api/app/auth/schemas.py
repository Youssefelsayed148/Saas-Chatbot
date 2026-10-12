"""Pydantic request/response schemas for auth (typed contracts, docs/05)."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

PASSWORD_MIN_LENGTH = 8


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=200)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class MembershipOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    tenant_id: UUID
    tenant_name: str
    tenant_slug: str
    role: str


class MeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    email: str
    is_platform_staff: bool
    memberships: list[MembershipOut]


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    email: str
    is_platform_staff: bool


class OkResponse(BaseModel):
    ok: bool = True
