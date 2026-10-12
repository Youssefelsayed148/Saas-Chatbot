"""initial schema: users, sessions, tenants, memberships, bots, invitations, audit_events

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-12

Designed with docs/04 and the P1-02 ticket: UUID PKs, citext emails,
tenant_id indexes, and (tenant_id, id) unique keys that anchor the
composite foreign keys later phases add (ADR-010).
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from sqlalchemy import text

from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


class CITEXT(sa.types.UserDefinedType[Any]):
    """Case-insensitive text type; requires the citext extension (created below)."""

    cache_ok = True

    def get_col_spec(self, **kw: Any) -> str:
        return "CITEXT"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")

    op.create_table(
        "users",
        sa.Column("id", sa.types.Uuid(), nullable=False),
        sa.Column("email", CITEXT(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("is_platform_staff", sa.Boolean(), nullable=False, server_default=text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )

    op.create_table(
        "sessions",
        sa.Column("id", sa.types.Uuid(), nullable=False),
        # SHA-256 hex of the opaque cookie token; only hashes are stored (docs/06).
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("user_id", sa.types.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_sessions_token_hash"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_sessions_user_id", ondelete="CASCADE"
        ),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])

    op.create_table(
        "tenants",
        sa.Column("id", sa.types.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=text("'active'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_tenants_slug"),
        sa.CheckConstraint("status IN ('active', 'archived')", name="ck_tenants_status"),
    )

    op.create_table(
        "memberships",
        sa.Column("tenant_id", sa.types.Uuid(), nullable=False),
        sa.Column("user_id", sa.types.Uuid(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False, server_default=text("'viewer'")),
        sa.Column("status", sa.Text(), nullable=False, server_default=text("'active'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("tenant_id", "user_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_memberships_tenant_id", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_memberships_user_id", ondelete="CASCADE"
        ),
        sa.CheckConstraint(
            "role IN ('owner', 'admin', 'editor', 'viewer')", name="ck_memberships_role"
        ),
        sa.CheckConstraint("status IN ('active', 'revoked')", name="ck_memberships_status"),
    )
    op.create_index("ix_memberships_tenant_id", "memberships", ["tenant_id"])
    op.create_index("ix_memberships_user_id", "memberships", ["user_id"])

    op.create_table(
        "bots",
        sa.Column("id", sa.types.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.types.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=text("'draft'")),
        sa.Column(
            "config",
            sa.dialects.postgresql.JSONB(),
            nullable=False,
            server_default=text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_bots_tenant_id", ondelete="CASCADE"
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'active', 'paused', 'archived')", name="ck_bots_status"
        ),
    )
    # Anchors composite FKs of later child tables (tenant_id, bot_id) -> bots (ADR-010).
    op.create_index("uq_bots_tenant_id_id", "bots", ["tenant_id", "id"], unique=True)
    op.create_index("ix_bots_tenant_id", "bots", ["tenant_id"])

    op.create_table(
        "invitations",
        sa.Column("id", sa.types.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.types.Uuid(), nullable=False),
        sa.Column("email", CITEXT(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False, server_default=text("'viewer'")),
        # SHA-256 hash of the one-time link token; the raw token is never stored or logged.
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.types.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_invitations_token_hash"),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_invitations_tenant_id", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name="fk_invitations_created_by", ondelete="RESTRICT"
        ),
        sa.CheckConstraint(
            "role IN ('owner', 'admin', 'editor', 'viewer')", name="ck_invitations_role"
        ),
    )
    op.create_index("ix_invitations_tenant_id", "invitations", ["tenant_id"])
    op.create_index("ix_invitations_email", "invitations", ["email"])

    op.create_table(
        "audit_events",
        sa.Column("id", sa.types.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.types.Uuid(), nullable=True),
        sa.Column("actor_user_id", sa.types.Uuid(), nullable=True),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("target_type", sa.Text(), nullable=True),
        sa.Column("target_id", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_audit_events_tenant_id", ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name="fk_audit_events_actor_user_id",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_audit_events_tenant_id", "audit_events", ["tenant_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_events_tenant_id", "audit_events")
    op.drop_table("audit_events")
    op.drop_index("ix_invitations_email", "invitations")
    op.drop_index("ix_invitations_tenant_id", "invitations")
    op.drop_table("invitations")
    op.drop_index("ix_bots_tenant_id", "bots")
    op.drop_index("uq_bots_tenant_id_id", "bots")
    op.drop_table("bots")
    op.drop_index("ix_memberships_user_id", "memberships")
    op.drop_index("ix_memberships_tenant_id", "memberships")
    op.drop_table("memberships")
    op.drop_table("tenants")
    op.drop_index("ix_sessions_user_id", "sessions")
    op.drop_table("sessions")
    op.drop_table("users")
    op.execute("DROP EXTENSION IF EXISTS citext")
