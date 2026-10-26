"""Staff member phone and account eligibility."""

import sqlalchemy as sa

from alembic import op

revision = "0017_staff_members"
down_revision = "0016_arabic_fts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("phone", sa.Text(), nullable=True))
    op.add_column(
        "users", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true())
    )


def downgrade() -> None:
    op.drop_column("users", "is_active")
    op.drop_column("users", "phone")
