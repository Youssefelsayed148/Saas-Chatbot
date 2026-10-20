"""Staff account administration. Secrets are returned only at issuance."""

import re
import secrets
from datetime import datetime
from typing import Annotated, Self
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as Db

from app.auth.cookies import require_csrf
from app.auth.schemas import PASSWORD_MIN_LENGTH
from app.auth.security import hash_password
from app.auth.service import AuthService
from app.core.audit import record_audit
from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.tenancy import TenantContext
from app.db.models import Membership, Tenant, User
from app.db.models.core import ClientRole
from app.db.session import get_session
from app.platform.staff import PlatformStaffDep
from app.quotas.service import lock_tenant, require_capacity
from app.tenants.service import TenantService


def prevent_caching(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(
    prefix="/users", tags=["platform users"], dependencies=[Depends(prevent_caching)]
)
Database = Annotated[Db, Depends(get_session)]
Csrf = Annotated[None, Depends(require_csrf)]


class PasswordInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    password: str | None = Field(default=None, min_length=PASSWORD_MIN_LENGTH, max_length=200)
    generate: bool = False

    @model_validator(mode="after")
    def exactly_one(self) -> Self:
        if (self.password is not None) == self.generate:
            raise ValueError("Provide a password or request generation.")
        return self


class CreateUser(PasswordInput):
    email: EmailStr
    phone: str | None = None
    organization_id: UUID | None = None
    role: ClientRole | None = None

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        value = re.sub(r"[\s().-]", "", value)
        if not re.fullmatch(r"\+[1-9][0-9]{1,14}", value):
            raise ValueError("Use an international phone number such as +201234567890.")
        return value

    @model_validator(mode="after")
    def organization_role_pair(self) -> Self:
        if (self.organization_id is None) != (self.role is None):
            raise ValueError("Organization and role must be supplied together.")
        return self


class AddMembership(BaseModel):
    model_config = ConfigDict(extra="forbid")
    organization_id: UUID
    role: ClientRole


class ChangeRole(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: ClientRole


class MembershipOut(BaseModel):
    organization_id: UUID
    organization_name: str
    role: ClientRole
    status: str


class UserOut(BaseModel):
    id: UUID
    email: str
    phone: str | None
    is_active: bool
    created_at: datetime
    memberships: list[MembershipOut]


class UserList(BaseModel):
    users: list[UserOut]
    total: int


class IssuedUser(BaseModel):
    user: UserOut
    generated_password: str | None = None


def editable(db: Db, user_id: UUID) -> User:
    user = db.scalar(
        select(User).where(User.id == user_id, User.is_platform_staff.is_(False)).with_for_update()
    )
    if user is None:
        raise ApiError(404, "NOT_FOUND", "User not found.")
    return user


def output(db: Db, user: User) -> UserOut:
    rows = db.execute(
        select(Membership, Tenant)
        .join(Tenant)
        .where(Membership.user_id == user.id)
        .order_by(Tenant.name)
    ).all()
    return UserOut(
        id=user.id,
        email=user.email,
        phone=user.phone,
        is_active=user.is_active,
        created_at=user.created_at,
        memberships=[
            MembershipOut(
                organization_id=t.id, organization_name=t.name, role=m.role, status=m.status
            )
            for m, t in rows
        ],
    )


def audit(db: Db, staff: User, user: User, action: str, tenant_id: UUID | None = None) -> None:
    record_audit(
        db,
        action=f"platform.user.{action}",
        actor_user_id=staff.id,
        tenant_id=tenant_id,
        target_type="user",
        target_id=str(user.id),
    )


def add_membership(db: Db, staff: User, user: User, body: AddMembership) -> None:
    tenant = lock_tenant(db, body.organization_id)
    member = db.get(Membership, (tenant.id, user.id))
    if member is not None and member.status == "active":
        raise ApiError(409, "ALREADY_MEMBER", "This user is already a member.")
    require_capacity(db, tenant, "seats")
    if member is None:
        member = Membership(tenant_id=tenant.id, user_id=user.id, role=body.role, status="active")
    else:
        member.role, member.status = body.role, "active"
    db.add(member)
    audit(db, staff, user, "membership_added", tenant.id)


@router.get("", response_model=UserList)
def list_users(
    staff: PlatformStaffDep,
    db: Database,
    q: str = Query("", max_length=254),
    organization_id: UUID | None = None,
    status: str | None = Query(None, pattern="^(active|inactive)$"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> UserList:
    statement = select(User).where(User.is_platform_staff.is_(False))
    if q.strip():
        statement = statement.where(User.email.contains(q.strip(), autoescape=True))
    if organization_id:
        statement = statement.where(
            select(Membership.user_id)
            .where(
                Membership.user_id == User.id,
                Membership.tenant_id == organization_id,
                Membership.status == "active",
            )
            .exists()
        )
    if status:
        statement = statement.where(User.is_active.is_(status == "active"))
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    users = db.scalars(statement.order_by(User.created_at, User.id).offset(offset).limit(limit))
    result = [output(db, user) for user in users]
    if organization_id:
        for user in result:
            user.memberships = [m for m in user.memberships if m.organization_id == organization_id]
    return UserList(users=result, total=total)


@router.post("", response_model=IssuedUser, status_code=201)
def create_user(body: CreateUser, staff: PlatformStaffDep, db: Database, _: Csrf) -> IssuedUser:
    if db.scalar(select(User.id).where(User.email == str(body.email))):
        raise ApiError(409, "EMAIL_TAKEN", "An account with this email already exists.")
    password = secrets.token_urlsafe(24) if body.generate else body.password
    assert password is not None
    user = User(
        id=uuid4(),
        email=str(body.email).lower(),
        phone=body.phone,
        password_hash=hash_password(password),
        is_active=True,
        is_platform_staff=False,
    )
    db.add(user)
    try:
        db.flush()
        audit(db, staff, user, "created")
        if body.organization_id is not None and body.role is not None:
            add_membership(
                db, staff, user, AddMembership(organization_id=body.organization_id, role=body.role)
            )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ApiError(409, "EMAIL_TAKEN", "An account with this email already exists.") from None
    return IssuedUser(user=output(db, user), generated_password=password if body.generate else None)


@router.get("/{user_id}", response_model=UserOut)
def get_user(user_id: UUID, staff: PlatformStaffDep, db: Database) -> UserOut:
    return output(db, editable(db, user_id))


@router.post("/{user_id}/memberships", response_model=UserOut, status_code=201)
def assign(
    user_id: UUID, body: AddMembership, staff: PlatformStaffDep, db: Database, _: Csrf
) -> UserOut:
    user = editable(db, user_id)
    add_membership(db, staff, user, body)
    db.commit()
    return output(db, user)


@router.patch("/{user_id}/memberships/{organization_id}", response_model=UserOut)
def role(
    user_id: UUID,
    organization_id: UUID,
    body: ChangeRole,
    staff: PlatformStaffDep,
    db: Database,
    _: Csrf,
) -> UserOut:
    user = editable(db, user_id)
    tenant = lock_tenant(db, organization_id)
    TenantService(db).change_role(
        TenantContext(db, staff, tenant, None),
        user.id,
        body.role,
        audit_action="platform.user.role_changed",
    )
    return output(db, user)


@router.delete("/{user_id}/memberships/{organization_id}", status_code=204)
def remove(
    user_id: UUID, organization_id: UUID, staff: PlatformStaffDep, db: Database, _: Csrf
) -> Response:
    user = editable(db, user_id)
    tenant = lock_tenant(db, organization_id)
    TenantService(db).remove_member(
        TenantContext(db, staff, tenant, None),
        user.id,
        audit_action="platform.user.membership_removed",
    )
    return Response(status_code=204)


@router.post("/{user_id}/password", response_model=IssuedUser)
def reset(
    user_id: UUID, body: PasswordInput, staff: PlatformStaffDep, db: Database, _: Csrf
) -> IssuedUser:
    user = editable(db, user_id)
    password = secrets.token_urlsafe(24) if body.generate else body.password
    assert password is not None
    user.password_hash = hash_password(password)
    AuthService(db, get_settings()).revoke_all_sessions(user)
    audit(db, staff, user, "password_reset")
    db.commit()
    return IssuedUser(user=output(db, user), generated_password=password if body.generate else None)


def set_active(db: Db, staff: User, user_id: UUID, active: bool) -> UserOut:
    user = editable(db, user_id)
    user.is_active = active
    if not active:
        AuthService(db, get_settings()).revoke_all_sessions(user)
    audit(db, staff, user, "reactivated" if active else "deactivated")
    db.commit()
    return output(db, user)


@router.post("/{user_id}/deactivate", response_model=UserOut)
def deactivate(user_id: UUID, staff: PlatformStaffDep, db: Database, _: Csrf) -> UserOut:
    return set_active(db, staff, user_id, False)


@router.post("/{user_id}/reactivate", response_model=UserOut)
def reactivate(user_id: UUID, staff: PlatformStaffDep, db: Database, _: Csrf) -> UserOut:
    return set_active(db, staff, user_id, True)
