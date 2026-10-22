"""Merge bot names (#9): copy the legacy bots.name into config.assistant_name.

The settings UI now has one field, "Assistant name". The old `bots.name`
column stays (it names the bot in lists), so nothing is dropped; bots whose
config has no assistant name get their legacy name as the starting value.
"""

import sqlalchemy as sa

from alembic import op

revision = "0018_bot_assistant_name"
down_revision = "0017_staff_members"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE bots SET config = config || jsonb_build_object('assistant_name', name) "
            "WHERE coalesce(btrim(config ->> 'assistant_name'), '') = '' "
            "AND coalesce(btrim(name), '') <> ''"
        )
    )


def downgrade() -> None:
    # Data backfill only: the copied value is indistinguishable from an edit,
    # so downgrade keeps it (no data loss).
    pass
