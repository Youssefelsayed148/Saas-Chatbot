"""Foundation schema tables (P1-02, docs/04, ADR-009/010).

Tenant-owned tables carry ``tenant_id``; composite uniqueness on
``(tenant_id, id)`` lets later child tables reference them without
cross-tenant joins. RLS is not used (ADR-010) — isolation is enforced
by app-layer tenant scoping plus these composite keys.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, utcnow
from app.db.models.types import CITEXT

ROLE_VALUES = ("owner", "admin", "editor", "viewer")
BOT_STATUS_VALUES = ("draft", "active", "paused", "archived")
TENANT_STATUS_VALUES = ("active", "archived")
PROVISIONING_MODE_VALUES = ("platform", "self_service")
PROVISIONING_STATUS_VALUES = ("requested", "provisioning", "ready", "failed")


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(CITEXT, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    is_platform_staff: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    memberships: Mapped[list["Membership"]] = relationship(back_populates="user")


class Session(Base):
    """Server-side session; ``token_hash`` is the SHA-256 of the opaque cookie value."""

    __tablename__ = "sessions"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    user: Mapped[User] = relationship()


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    # Message retention override (P4-04, docs/14 §7): NULL = deployment default.
    retention_days: Mapped[int | None] = mapped_column()
    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="active",
        server_default=text("'active'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    __table_args__ = (
        CheckConstraint("status IN ('active', 'archived')", name="ck_tenants_status"),
    )

    memberships: Mapped[list["Membership"]] = relationship(back_populates="tenant")


class Membership(Base):
    __tablename__ = "memberships"

    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, primary_key=True
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, primary_key=True
    )
    # ADR-009: owner / admin / editor / viewer.
    role: Mapped[str] = mapped_column(Text, nullable=False, default="viewer")
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="active", server_default=text("'active'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    __table_args__ = (
        CheckConstraint(
            "role IN ('owner', 'admin', 'editor', 'viewer')", name="ck_memberships_role"
        ),
        CheckConstraint("status IN ('active', 'revoked')", name="ck_memberships_status"),
        Index("ix_memberships_tenant_id", "tenant_id"),
        Index("ix_memberships_user_id", "user_id"),
    )

    tenant: Mapped[Tenant] = relationship(back_populates="memberships")
    user: Mapped[User] = relationship(back_populates="memberships")


class Bot(Base):
    __tablename__ = "bots"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="draft", server_default=text("'draft'")
    )
    # Validated by a Pydantic settings schema when bot settings endpoints land (docs/04).
    config: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    # Opaque public widget locator (P4-01, docs/04/05): NOT a secret — the
    # public widget endpoints resolve the bot ONLY through it and never accept
    # a caller-supplied tenant_id (docs/06). Assigned at creation.
    widget_locator: Mapped[str | None] = mapped_column(Text, unique=True)
    # Set on knowledge publish (P2-03); NULL until the bot has published knowledge.
    published_revision_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("knowledge_revisions.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'active', 'paused', 'archived')", name="ck_bots_status"
        ),
        # unique(tenant_id, id): anchor for later composite FKs (docs/03, ADR-010).
        Index("uq_bots_tenant_id_id", "tenant_id", "id", unique=True),
        Index("ix_bots_tenant_id", "tenant_id"),
    )


class Invitation(Base):
    __tablename__ = "invitations"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str] = mapped_column(CITEXT, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False, default="viewer")
    # Only the SHA-256 hash of the one-time link token is stored (docs/14 s19).
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    __table_args__ = (
        CheckConstraint(
            "role IN ('owner', 'admin', 'editor', 'viewer')", name="ck_invitations_role"
        ),
        Index("ix_invitations_tenant_id", "tenant_id"),
        Index("ix_invitations_email", "email"),
    )


class ProvisioningRequest(Base):
    """Durable onboarding record (P4-06, docs/04: provisioning_requests).

    One row per (mode, idempotency_key); retried submissions RE-READ the same
    row instead of creating a second tenant/bot. The payload holds
    configuration words only; no secrets and no raw file content (uploads go
    through the standard generated storage keys)."""

    __tablename__ = "provisioning_requests"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID | None] = mapped_column(ForeignKey("tenants.id", ondelete="SET NULL"))
    actor_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    mode: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="requested")
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    payload_hash: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    result: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    __table_args__ = (
        CheckConstraint(
            "mode IN ('platform', 'self_service')", name="ck_provisioning_requests_mode"
        ),
        CheckConstraint(
            "status IN ('requested', 'provisioning', 'ready', 'failed')",
            name="ck_provisioning_requests_status",
        ),
        Index("uq_provisioning_scope_key", "mode", "idempotency_key", unique=True),
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[UUID | None] = mapped_column(ForeignKey("tenants.id", ondelete="SET NULL"))
    actor_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(Text, nullable=False)
    target_type: Mapped[str | None] = mapped_column(Text)
    target_id: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    __table_args__ = (Index("ix_audit_events_tenant_id", "tenant_id", "created_at"),)


__all__ = [
    "AuditEvent",
    "Bot",
    "Invitation",
    "Membership",
    "ProvisioningRequest",
    "Session",
    "Tenant",
    "User",
]
