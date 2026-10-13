"""widget public channel: bots.widget_locator, visitor_sessions,
rate_limit_counters, conversations.session_id

Revision ID: 0004_widget_public
Revises: 0003_conversation_core
Create Date: 2026-10-13

P4-01 (docs/09, docs/14 §7, docs/04): the website channel's public surface.

- ``bots.widget_locator``: the opaque PUBLIC locator (docs/05: the locator is
  NOT a secret); resolved server-side to a tenant+bot, callers never pass
  tenant_id.
- ``visitor_sessions``: short-lived capability tokens bound to one bot
  (composite FKs, docs/09). Only the token hash is stored.
- ``conversations.session_id``: ties a website conversation to its visitor
  session (composite FK — a conversation can never cross tenants).
- ``rate_limit_counters``: fixed-window abuse counters in Postgres so limits
  survive restarts and several processes (docs/14 §7). Also backs the login
  limiter (P1 carry-over into P4-01).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_widget_public"
down_revision: str | None = "0003_conversation_core"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("bots", sa.Column("widget_locator", sa.Text(), nullable=True))
    # Backfill one opaque locator per existing bot (gen_random_uuid is core
    # since PG13); random() is volatile so every row gets a distinct value,
    # and the unique index below guards this for good.
    op.execute(
        "UPDATE bots SET widget_locator = 'w' || replace("
        "gen_random_uuid()::text, '-', '') WHERE widget_locator IS NULL"
    )
    op.create_index("uq_bots_widget_locator", "bots", ["widget_locator"], unique=True)

    op.create_table(
        "visitor_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("bot_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "bot_id"],
            ["bots.tenant_id", "bots.id"],
            name="fk_visitor_sessions_tenant_bot",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_visitor_sessions_tenant_anchor",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_visitor_sessions_token"),
    )
    op.create_index(
        "uq_visitor_sessions_tenant_id_id",
        "visitor_sessions",
        ["tenant_id", "id"],
        unique=True,
    )
    op.create_index(
        "uq_visitor_sessions_tenant_bot_id",
        "visitor_sessions",
        ["tenant_id", "bot_id", "id"],
        unique=True,
    )
    op.create_index(
        "ix_visitor_sessions_bot_created",
        "visitor_sessions",
        ["tenant_id", "bot_id", "created_at"],
    )

    op.add_column("conversations", sa.Column("session_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_conversations_session",
        "conversations",
        "visitor_sessions",
        ["tenant_id", "session_id"],
        ["tenant_id", "id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "rate_limit_counters",
        sa.Column("bucket_key", sa.Text(), nullable=False),
        sa.Column("window_start", sa.Integer(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("count >= 0", name="ck_rate_limit_counters_count"),
        sa.CheckConstraint("window_start >= 0", name="ck_rate_limit_counters_window"),
        sa.PrimaryKeyConstraint("bucket_key"),
    )
    op.create_index("ix_rate_limit_counters_window", "rate_limit_counters", ["window_start"])


def downgrade() -> None:
    op.drop_index("ix_rate_limit_counters_window", table_name="rate_limit_counters")
    op.drop_table("rate_limit_counters")
    op.drop_constraint("fk_conversations_session", "conversations", type_="foreignkey")
    op.drop_column("conversations", "session_id")
    op.drop_table("visitor_sessions")
    op.drop_index("uq_bots_widget_locator", table_name="bots")
    op.drop_column("bots", "widget_locator")
