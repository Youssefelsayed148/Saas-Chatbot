"""One live connection per (channel, many_channel_ref) (D11, contract v1.1).

Revision ID: 0027_channel_ref_unique
Revises: 0026_channel_health_poll
"""

import sqlalchemy as sa

from alembic import op

revision = "0027_channel_ref_unique"
down_revision = "0026_channel_health_poll"
branch_labels = None
depends_on = None


def upgrade() -> None:
    duplicates = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT count(*) FROM (SELECT 1 FROM channel_connections "
                "WHERE many_channel_ref IS NOT NULL AND status <> 'revoked' "
                "GROUP BY channel, many_channel_ref HAVING count(*) > 1) d"
            )
        )
        .scalar_one()
    )
    if duplicates:
        raise RuntimeError(
            "Cannot add the unique channel reference index: "
            f"{duplicates} duplicated live (channel, many_channel_ref) pairs need owner review."
        )
    op.create_index(
        "uq_channel_connections_live_ref",
        "channel_connections",
        ["channel", "many_channel_ref"],
        unique=True,
        postgresql_where=sa.text("many_channel_ref IS NOT NULL AND status <> 'revoked'"),
    )


def downgrade() -> None:
    op.drop_index("uq_channel_connections_live_ref", table_name="channel_connections")
