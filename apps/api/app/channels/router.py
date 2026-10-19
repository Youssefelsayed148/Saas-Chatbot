"""Staff lifecycle and client-safe read routes for delegated channels."""

import ipaddress
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal, cast
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from app.auth import cookies
from app.channels.health import check_health, effective_health
from app.channels.secrets import encrypt_secret
from app.core.audit import record_audit
from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.core.tenancy import TenantContextDep
from app.db.models import Bot, ChannelConnection, User
from app.db.session import get_session
from app.platform.staff import PlatformStaffDep
from app.quotas.service import limits_for, lock_tenant

router = APIRouter(tags=["channels"])
DbSession = Annotated[OrmSession, Depends(get_session)]
CurrentSettings = Annotated[Settings, Depends(get_settings)]
CsrfOk = Annotated[None, Depends(cookies.require_csrf)]

ChannelName = Literal["whatsapp", "messenger", "instagram"]
ConnectionStatus = Literal["active", "paused", "revoked"]
HealthStatus = Literal["healthy", "degraded", "unhealthy", "unknown"]


class ChannelConnectionCreate(BaseModel):
    tenant_id: UUID
    bot_id: UUID
    channel: ChannelName
    display_name: str = Field(min_length=1, max_length=120)
    many_base_url: str = Field(min_length=8, max_length=500)
    many_channel_ref: str | None = Field(default=None, max_length=128)

    @field_validator("display_name")
    @classmethod
    def clean_display_name(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("A display name is required.")
        return value

    @field_validator("many_channel_ref")
    @classmethod
    def clean_channel_ref(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class ChannelConnectionUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    many_base_url: str | None = Field(default=None, min_length=8, max_length=500)
    many_channel_ref: str | None = Field(default=None, max_length=128)
    ai_enabled: bool | None = None

    @field_validator("display_name")
    @classmethod
    def clean_display_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = " ".join(value.split())
        if not value:
            raise ValueError("A display name is required.")
        return value


class StaffConnectionOut(BaseModel):
    id: UUID
    tenant_id: UUID
    bot_id: UUID
    channel: ChannelName
    display_name: str
    many_base_url: str
    many_channel_ref: str | None
    status: ConnectionStatus
    ai_enabled: bool
    secret_key_version: int
    secret_rotated_at: datetime | None
    prev_secret_expires_at: datetime | None
    health_status: HealthStatus
    health_reason: str | None
    health_detail: str | None
    health_updated_at: datetime | None
    last_event_at: datetime | None
    created_by: UUID | None
    created_at: datetime
    updated_at: datetime


class CreatedConnectionOut(StaffConnectionOut):
    secret: str


class ConnectionListOut(BaseModel):
    items: list[StaffConnectionOut]


class ClientChannelOut(BaseModel):
    channel: ChannelName
    display_name: str
    status: ConnectionStatus
    health_status: HealthStatus
    last_event_at: datetime | None


class ClientChannelListOut(BaseModel):
    items: list[ClientChannelOut]


def _validate_base_url(value: str, settings: Settings) -> str:
    parsed = urlsplit(value.strip())
    if parsed.scheme not in {"https", "http"} or not parsed.hostname:
        raise ApiError(422, "INVALID_MANY_URL", "Many base URL must use HTTP or HTTPS.")
    hostname = parsed.hostname.rstrip(".").lower()
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
        if hostname == "localhost" or hostname.endswith(
            (".localhost", ".local", ".internal", ".lan", ".home.arpa")
        ):
            raise ApiError(
                422, "INVALID_MANY_URL", "Many base URL must use a public host."
            ) from None
        numeric_labels = hostname.split(".")
        if all(
            label.isdecimal()
            or (
                label.startswith("0x")
                and len(label) > 2
                and all(character in "0123456789abcdef" for character in label[2:])
            )
            for label in numeric_labels
        ):
            raise ApiError(422, "INVALID_MANY_URL", "Many base URL has an invalid host.") from None
    if address is not None and not address.is_global:
        raise ApiError(422, "INVALID_MANY_URL", "Many base URL must use a public host.")
    if (
        parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ApiError(
            422, "INVALID_MANY_URL", "Many base URL must not include credentials or query data."
        )
    if settings.environment == "production" and parsed.scheme != "https":
        raise ApiError(422, "INVALID_MANY_URL", "Many base URL must use HTTPS in production.")
    try:
        if parsed.port is not None and not 1 <= parsed.port <= 65535:
            raise ValueError("port out of range")
    except ValueError as exc:
        raise ApiError(422, "INVALID_MANY_URL", "Many base URL has an invalid port.") from exc
    path = parsed.path.rstrip("/")
    return f"{parsed.scheme}://{parsed.netloc}{path}"


def _staff_out(connection: ChannelConnection) -> StaffConnectionOut:
    output = StaffConnectionOut.model_validate(connection, from_attributes=True)
    # Read-only staleness (docs/17 §4.3): an old signal shows unknown/stale.
    status, reason = effective_health(connection)
    output.health_status = cast(HealthStatus, status)
    if reason is not None:
        output.health_reason = reason
    return output


def _require_connection(db: OrmSession, connection_id: UUID, *, lock: bool) -> ChannelConnection:
    statement = select(ChannelConnection).where(ChannelConnection.id == connection_id)
    if lock:
        statement = statement.with_for_update()
    connection = db.scalar(statement)
    if connection is None:
        raise ApiError(404, "NOT_FOUND", "Resource not found.")
    return connection


def _audit(
    db: OrmSession,
    *,
    connection: ChannelConnection,
    actor: User,
    action: str,
    metadata: dict[str, object] | None = None,
) -> None:
    record_audit(
        db,
        action=f"channel_connection.{action}",
        tenant_id=connection.tenant_id,
        actor_user_id=actor.id,
        target_type="channel_connection",
        target_id=str(connection.id),
        metadata={"channel": connection.channel, **(metadata or {})},
    )


@router.get(
    "/api/v1/platform/channel-connections",
    response_model=ConnectionListOut,
)
def list_channel_connections(
    staff: PlatformStaffDep,
    db: DbSession,
    tenant_id: Annotated[UUID | None, Query()] = None,
) -> ConnectionListOut:
    del staff
    statement = select(ChannelConnection).order_by(
        ChannelConnection.created_at.desc(), ChannelConnection.id
    )
    if tenant_id is not None:
        statement = statement.where(ChannelConnection.tenant_id == tenant_id)
    return ConnectionListOut(items=[_staff_out(row) for row in db.scalars(statement)])


@router.post(
    "/api/v1/platform/channel-connections",
    response_model=CreatedConnectionOut,
    status_code=status.HTTP_201_CREATED,
)
def create_channel_connection(
    payload: ChannelConnectionCreate,
    _csrf: CsrfOk,
    staff: PlatformStaffDep,
    db: DbSession,
    settings: CurrentSettings,
) -> CreatedConnectionOut:
    tenant = lock_tenant(db, payload.tenant_id)
    bot = db.scalar(select(Bot).where(Bot.tenant_id == tenant.id, Bot.id == payload.bot_id))
    if bot is None:
        raise ApiError(404, "NOT_FOUND", "Resource not found.")
    limit = limits_for(tenant).channel_connections
    used = int(
        db.scalar(
            select(func.count())
            .select_from(ChannelConnection)
            .where(
                ChannelConnection.tenant_id == tenant.id,
                ChannelConnection.status != "revoked",
            )
        )
        or 0
    )
    if used >= limit:
        raise ApiError(429, "QUOTA_EXCEEDED", "The channel connection limit has been reached.")
    try:
        many_base_url = _validate_base_url(payload.many_base_url, settings)
        # Validate configuration before inserting anything; plaintext is returned once only.
        encryption_key = settings.channel_secret_encryption_keys
        secret = secrets.token_urlsafe(32)
        ciphertext = encrypt_secret(secret, encryption_key)
    except ValueError as exc:
        raise ApiError(
            503, "CHANNEL_ENCRYPTION_UNAVAILABLE", "Channel secret encryption is unavailable."
        ) from exc
    connection = ChannelConnection(
        id=uuid4(),
        tenant_id=tenant.id,
        bot_id=bot.id,
        channel=payload.channel,
        display_name=payload.display_name,
        many_base_url=many_base_url,
        many_channel_ref=payload.many_channel_ref,
        status="active",
        ai_enabled=True,
        secret_ciphertext=ciphertext,
        secret_key_version=1,
        health_status="unknown",
        created_by=staff.id,
    )
    db.add(connection)
    _audit(db, connection=connection, actor=staff, action="created")
    db.commit()
    db.refresh(connection)
    return CreatedConnectionOut(**_staff_out(connection).model_dump(), secret=secret)


@router.get(
    "/api/v1/platform/channel-connections/{connection_id}",
    response_model=StaffConnectionOut,
)
def get_channel_connection(
    connection_id: UUID, staff: PlatformStaffDep, db: DbSession
) -> StaffConnectionOut:
    del staff
    return _staff_out(_require_connection(db, connection_id, lock=False))


@router.patch(
    "/api/v1/platform/channel-connections/{connection_id}",
    response_model=StaffConnectionOut,
)
def update_channel_connection(
    connection_id: UUID,
    payload: ChannelConnectionUpdate,
    _csrf: CsrfOk,
    staff: PlatformStaffDep,
    db: DbSession,
    settings: CurrentSettings,
) -> StaffConnectionOut:
    connection = _require_connection(db, connection_id, lock=True)
    if connection.status == "revoked":
        raise ApiError(409, "CONNECTION_REVOKED", "A revoked connection cannot be changed.")
    values = payload.model_dump(exclude_unset=True)
    if "many_base_url" in values and values["many_base_url"] is not None:
        values["many_base_url"] = _validate_base_url(values["many_base_url"], settings)
    for name, value in values.items():
        setattr(connection, name, value)
    connection.updated_at = datetime.now(UTC)
    _audit(
        db,
        connection=connection,
        actor=staff,
        action="updated",
        metadata={"fields": sorted(values)},
    )
    db.commit()
    db.refresh(connection)
    return _staff_out(connection)


def _change_status(
    connection_id: UUID,
    *,
    target_status: Literal["active", "paused", "revoked"],
    staff: User,
    db: OrmSession,
) -> StaffConnectionOut:
    connection = _require_connection(db, connection_id, lock=True)
    if connection.status == "revoked" and target_status != "revoked":
        raise ApiError(409, "CONNECTION_REVOKED", "A revoked connection cannot be resumed.")
    if target_status == "active" and connection.status == "active":
        return _staff_out(connection)
    if target_status == "paused" and connection.status == "paused":
        return _staff_out(connection)
    connection.status = target_status
    if target_status == "revoked":
        connection.ai_enabled = False
    connection.updated_at = datetime.now(UTC)
    _audit(db, connection=connection, actor=staff, action=target_status)
    db.commit()
    db.refresh(connection)
    return _staff_out(connection)


@router.post(
    "/api/v1/platform/channel-connections/{connection_id}/pause",
    response_model=StaffConnectionOut,
)
def pause_channel_connection(
    connection_id: UUID, _csrf: CsrfOk, staff: PlatformStaffDep, db: DbSession
) -> StaffConnectionOut:
    return _change_status(connection_id, target_status="paused", staff=staff, db=db)


@router.post(
    "/api/v1/platform/channel-connections/{connection_id}/resume",
    response_model=StaffConnectionOut,
)
def resume_channel_connection(
    connection_id: UUID, _csrf: CsrfOk, staff: PlatformStaffDep, db: DbSession
) -> StaffConnectionOut:
    return _change_status(connection_id, target_status="active", staff=staff, db=db)


@router.post(
    "/api/v1/platform/channel-connections/{connection_id}/revoke",
    response_model=StaffConnectionOut,
)
def revoke_channel_connection(
    connection_id: UUID, _csrf: CsrfOk, staff: PlatformStaffDep, db: DbSession
) -> StaffConnectionOut:
    return _change_status(connection_id, target_status="revoked", staff=staff, db=db)


@router.post(
    "/api/v1/platform/channel-connections/{connection_id}/check-health",
    response_model=StaffConnectionOut,
)
def check_channel_connection_health(
    connection_id: UUID,
    _csrf: CsrfOk,
    staff: PlatformStaffDep,
    db: DbSession,
    settings: CurrentSettings,
) -> StaffConnectionOut:
    """Staff "Check now": one signed health pull, applied with an audit row."""
    connection = _require_connection(db, connection_id, lock=True)
    if connection.status == "revoked":
        raise ApiError(409, "CONNECTION_REVOKED", "A revoked connection has no health to check.")
    check_health(db, connection, settings, actor=staff)
    db.commit()
    db.refresh(connection)
    return _staff_out(connection)


@router.post(
    "/api/v1/platform/channel-connections/{connection_id}/rotate-secret",
    response_model=CreatedConnectionOut,
)
def rotate_channel_secret(
    connection_id: UUID,
    _csrf: CsrfOk,
    staff: PlatformStaffDep,
    db: DbSession,
    settings: CurrentSettings,
) -> CreatedConnectionOut:
    connection = _require_connection(db, connection_id, lock=True)
    if connection.status == "revoked":
        raise ApiError(409, "CONNECTION_REVOKED", "A revoked connection cannot rotate its secret.")
    secret = secrets.token_urlsafe(32)
    try:
        ciphertext = encrypt_secret(secret, settings.channel_secret_encryption_keys)
    except ValueError as exc:
        raise ApiError(
            503, "CHANNEL_ENCRYPTION_UNAVAILABLE", "Channel secret encryption is unavailable."
        ) from exc
    now = datetime.now(UTC)
    connection.prev_secret_ciphertext = connection.secret_ciphertext
    connection.prev_secret_expires_at = now + timedelta(hours=24)
    connection.secret_ciphertext = ciphertext
    connection.secret_key_version += 1
    connection.secret_rotated_at = now
    connection.updated_at = now
    _audit(
        db,
        connection=connection,
        actor=staff,
        action="secret_rotated",
        metadata={"secret_key_version": connection.secret_key_version},
    )
    db.commit()
    db.refresh(connection)
    return CreatedConnectionOut(**_staff_out(connection).model_dump(), secret=secret)


@router.get(
    "/api/v1/tenants/{tenant_id}/channels",
    response_model=ClientChannelListOut,
)
def list_client_channels(context: TenantContextDep) -> ClientChannelListOut:
    connections = context.db.scalars(
        select(ChannelConnection)
        .where(ChannelConnection.tenant_id == context.tenant_id)
        .order_by(ChannelConnection.created_at, ChannelConnection.id)
    )
    # The client contract intentionally omits Many URLs, channel refs, and secrets.
    items: list[ClientChannelOut] = []
    for row in connections:
        health_status, _reason = effective_health(row)
        items.append(
            ClientChannelOut(
                channel=cast(ChannelName, row.channel),
                display_name=row.display_name,
                status=cast(ConnectionStatus, row.status),
                health_status=cast(HealthStatus, health_status),
                last_event_at=row.last_event_at,
            )
        )
    return ClientChannelListOut(items=items)
