"""Per-bot staff tone and rules (#15): nullable text, capped at 2000 characters."""

import sqlalchemy as sa

from alembic import op

revision = "0019_bot_tone_and_rules"
down_revision = "0018_bot_assistant_name"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("bots", sa.Column("tone_and_rules", sa.Text(), nullable=True))
    op.create_check_constraint(
        "ck_bots_tone_and_rules_length",
        "bots",
        "tone_and_rules IS NULL OR char_length(tone_and_rules) <= 2000",
    )


def downgrade() -> None:
    op.drop_constraint("ck_bots_tone_and_rules_length", "bots", type_="check")
    op.drop_column("bots", "tone_and_rules")
