"""platform operations plan labels

Revision ID: 0010_platform_ops
Revises: 0009_follow_ups
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010_platform_ops"
down_revision: str | None = "0009_follow_ups"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("plan_label", sa.Text(), server_default="starter", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("tenants", "plan_label")
