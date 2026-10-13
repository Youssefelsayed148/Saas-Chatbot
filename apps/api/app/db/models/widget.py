"""Widget public-channel tables (P4-01, docs/09, docs/14 §7, docs/04).

``visitor_sessions`` carry the short-lived capability token for one bot
(only the SHA-256 hash is stored — docs/06 session discipline, same as the
dashboard sessions). ``rate_limit_counters`` are Postgres-backed fixed-window
counters: they survive restarts and work across API processes (docs/14 §7;
they also replace the P1 in-process login limiter).

Both tables are tenant-scoped with the same anchor pattern as every other
tenant-owned table (ADR-010); no row is ever reachable by ID guessing
because the public API resolves everything through the opaque locator or
the capability token.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKeyConstraint, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utcnow


class VisitorSession(Base):
    """One widget visitor session bound to one bot (docs/04: short-lived)."""

    __tablename__ = "visitor_sessions"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(nullable=False)
    bot_id: Mapped[UUID] = mapped_column(nullable=False)
    # SHA-256 of the opaque capability token; the raw value is shown ONCE.
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    __table_args__ = (
        # Composite FKs: a session can never point at another tenant's bot/anchor.
        ForeignKeyConstraint(
            ["tenant_id", "bot_id"],
            ["bots.tenant_id", "bots.id"],
            name="fk_visitor_sessions_tenant_bot",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_visitor_sessions_tenant_anchor",
            ondelete="CASCADE",
        ),
        Index("uq_visitor_sessions_tenant_id_id", "tenant_id", "id", unique=True),
        Index("uq_visitor_sessions_tenant_bot_id", "tenant_id", "bot_id", "id", unique=True),
        Index("ix_visitor_sessions_bot_created", "tenant_id", "bot_id", "created_at"),
    )


class RateLimitCounter(Base):
    """Fixed-window abuse counter (docs/14 §7 defaults; Postgres-backed).

    ``window_start`` is the truncated window epoch (UTC seconds); the key
    encodes scope+window, e.g. ``widget:sess:{session_id}:60`` or
    ``login:{ip}``. Cleanup happens with the retention purge job.
    """

    __tablename__ = "rate_limit_counters"

    bucket_key: Mapped[str] = mapped_column(Text, primary_key=True)
    window_start: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    __table_args__ = (
        CheckConstraint("count >= 0", name="ck_rate_limit_counters_count"),
        CheckConstraint("window_start >= 0", name="ck_rate_limit_counters_window"),
        Index("ix_rate_limit_counters_window", "window_start"),
    )


__all__ = ["RateLimitCounter", "VisitorSession"]
