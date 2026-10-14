"""contact stage vocabulary for light CRM

Revision ID: 0008_contacts
Revises: 0007_inbox
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008_contacts"
down_revision: str | None = "0007_inbox"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "contact_stages",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.CheckConstraint("length(name) BETWEEN 1 AND 64", name="ck_contact_stages_name"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("tenant_id", "name"),
    )
    op.execute(
        """INSERT INTO contact_stages (tenant_id, name, sort_order)
        SELECT t.id, s.name, s.ordinality - 1
        FROM tenants AS t
        CROSS JOIN unnest(ARRAY['new','qualified','customer','lost']::text[])
          WITH ORDINALITY AS s(name, ordinality)"""
    )


def downgrade() -> None:
    op.drop_table("contact_stages")
