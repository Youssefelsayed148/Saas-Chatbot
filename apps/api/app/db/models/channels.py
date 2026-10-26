"""ManyOsirisChat delegated channel records (ADR-017, docs/17)."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utcnow

CHANNEL_CONNECTION_STATUSES = ("active", "paused", "revoked")
CHANNEL_HEALTH_STATUSES = ("healthy", "degraded", "unhealthy", "unknown")
CHANNEL_EVENT_STATUSES = ("received", "processed", "failed", "ignored")


class ChannelConnection(Base):
    __tablename__ = "channel_connections"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(nullable=False)
    bot_id: Mapped[UUID] = mapped_column(nullable=False)
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    many_base_url: Mapped[str] = mapped_column(Text, nullable=False)
    many_channel_ref: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active")
    ai_enabled: Mapped[bool] = mapped_column(nullable=False, default=True)
    secret_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    secret_key_version: Mapped[int] = mapped_column(nullable=False, default=1)
    secret_rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    prev_secret_ciphertext: Mapped[str | None] = mapped_column(Text)
    prev_secret_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    health_status: Mapped[str] = mapped_column(Text, nullable=False, default="unknown")
    health_reason: Mapped[str | None] = mapped_column(Text)
    health_detail: Mapped[str | None] = mapped_column(Text)
    health_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    __table_args__ = (
        CheckConstraint(
            "channel IN ('whatsapp', 'messenger', 'instagram')",
            name="ck_channel_connections_channel",
        ),
        CheckConstraint(
            "status IN ('active', 'paused', 'revoked')", name="ck_channel_connections_status"
        ),
        CheckConstraint(
            "health_status IN ('healthy', 'degraded', 'unhealthy', 'unknown')",
            name="ck_channel_connections_health_status",
        ),
        CheckConstraint("secret_key_version > 0", name="ck_channel_connections_key_version"),
        ForeignKeyConstraint(
            ["tenant_id", "bot_id"],
            ["bots.tenant_id", "bots.id"],
            name="fk_channel_connections_tenant_bot",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_channel_connections_tenant", ondelete="CASCADE"
        ),
        Index("uq_channel_connections_tenant_id", "tenant_id", "id", unique=True),
        Index(
            "uq_channel_connections_live_ref",
            "channel",
            "many_channel_ref",
            unique=True,
            postgresql_where=text("many_channel_ref IS NOT NULL AND status <> 'revoked'"),
        ),
        Index(
            "ix_channel_connections_tenant_status",
            "tenant_id",
            "status",
            "created_at",
        ),
    )


class ChannelEvent(Base):
    __tablename__ = "channel_events"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(nullable=False)
    connection_id: Mapped[UUID] = mapped_column(nullable=False)
    event_id: Mapped[str] = mapped_column(Text, nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="received")
    error_code: Mapped[str | None] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "status IN ('received', 'processed', 'failed', 'ignored')",
            name="ck_channel_events_status",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "connection_id"],
            ["channel_connections.tenant_id", "channel_connections.id"],
            name="fk_channel_events_connection",
            ondelete="CASCADE",
        ),
        Index("uq_channel_events_connection_event", "connection_id", "event_id", unique=True),
        Index("ix_channel_events_tenant_received", "tenant_id", "received_at"),
    )


__all__ = ["ChannelConnection", "ChannelEvent"]
