"""tenant retention setting, leads

Revision ID: 0005_retention_leads
Revises: 0004_widget_public
Create Date: 2026-10-13

P4-04 (docs/14 §7/§16): the configurable retention window moves to the tenant
level (default 30 days, 1–365; NULL = deployment default) and the widget lead
capture reuses the EXISTING conversation-core tables (contacts + consent JSON
+ contact_identities) — no new table needed; `tenants.retention_days` is the
only schema change. Purge applies each tenant's own window.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_retention_leads"
down_revision: str | None = "0004_widget_public"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("retention_days", sa.Integer(), nullable=True))
    op.create_check_constraint(
        "ck_tenants_retention_days",
        "tenants",
        "retention_days IS NULL OR (retention_days >= 1 AND retention_days <= 365)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_tenants_retention_days", "tenants", type_="check")
    op.drop_column("tenants", "retention_days")
