"""Client change requests and independent organization deletion ledger."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utcnow


class ChangeRequest(Base):
    __tablename__ = "change_requests"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    requester_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    type: Mapped[str] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    attachments: Mapped[list[dict[str, object]]] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(Text, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        CheckConstraint(
            "type IN ('knowledge','text_change','domain','delete_org','other')",
            name="ck_change_requests_type",
        ),
        CheckConstraint(
            "status IN ('pending','triaged','in_progress','completed','rejected')",
            name="ck_change_requests_status",
        ),
        Index("ix_change_requests_tenant_created", "tenant_id", "created_at"),
    )


class OrganizationDeletion(Base):
    # No tenant FK: this record and its storage manifest must survive a purge.
    __tablename__ = "organization_deletions"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(unique=True)
    organization_name: Mapped[str] = mapped_column(Text)
    actor_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reason: Mapped[str] = mapped_column(Text)
    storage_keys: Mapped[list[str]] = mapped_column(JSONB, default=list)
    counts: Mapped[dict[str, int]] = mapped_column(JSONB, default=dict)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    purge_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
