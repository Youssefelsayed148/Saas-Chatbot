"""platform admin console: provisioning_requests

Revision ID: 0006_provisioning
Revises: 0005_retention_leads
Create Date: 2026-10-13

P4-06 (docs/11, ADR-018): the durable request record behind the shared
ProvisioningService (staff onboarding now; self-service in P7-03). The
``idempotency_key`` is unique per caller scope so double-submission creates
exactly one tenant. ``payload_json`` holds only ids/configuration words,
never secrets, and file uploads are stored through the normal storage keys.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0006_provisioning"
down_revision: str | None = "0005_retention_leads"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "provisioning_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=True),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("mode", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("payload_hash", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "mode IN ('platform', 'self_service')", name="ck_provisioning_requests_mode"
        ),
        sa.CheckConstraint(
            "status IN ('requested', 'provisioning', 'ready', 'failed')",
            name="ck_provisioning_requests_status",
        ),
        # One durable row per scope+key: double submission re-reads the same row.
        sa.UniqueConstraint("mode", "idempotency_key", name="uq_provisioning_scope_key"),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_provisioning_tenant", ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["users.id"], name="fk_provisioning_actor", ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_provisioning_requests_created", "provisioning_requests", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_provisioning_requests_created", table_name="provisioning_requests")
    op.drop_table("provisioning_requests")
