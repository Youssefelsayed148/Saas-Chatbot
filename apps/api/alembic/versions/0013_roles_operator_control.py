"""Three client roles, change requests and durable soft-deletion ledger.

Revision ID: 0013_roles_operator_control
Revises: 0012_quota_jobs
"""

from uuid import NAMESPACE_URL, uuid5

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0013_roles_operator_control"
down_revision = "0012_quota_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("memberships", "invitations"):
        op.execute(sa.text(f"UPDATE {table} SET role = 'admin' WHERE role = 'owner'"))
        op.drop_constraint(f"ck_{table}_role", table, type_="check")
        op.create_check_constraint(f"ck_{table}_role", table, "role IN ('admin','editor','viewer')")
    # Retire only the shipped former demo-owner login. Keep its identity for
    # historical content/audit FKs; demo-admin is the single administrator login.
    demo_tenant = uuid5(NAMESPACE_URL, "https://demo.example.com/demo-dental-clinic/tenant")
    demo_owner = uuid5(NAMESPACE_URL, "https://demo.example.com/demo-dental-clinic/user/owner")
    bind = op.get_bind()
    retired = bind.execute(
        sa.text(
            "SELECT u.id FROM users u JOIN memberships m ON m.user_id=u.id "
            "WHERE u.id=:uid AND u.email='demo-owner@example.com' AND m.tenant_id=:tid"
        ),
        {"uid": demo_owner, "tid": demo_tenant},
    ).scalar_one_or_none()
    if retired is not None:
        demo_admin = uuid5(NAMESPACE_URL, "https://demo.example.com/demo-dental-clinic/user/admin")
        # Reconstitute the canonical fictional admin if it was removed from the
        # demo; retiring the old login must never leave the demo without an admin.
        bind.execute(
            sa.text(
                "INSERT INTO users (id,email,password_hash,is_platform_staff,created_at) "
                "SELECT :aid,'demo-admin@example.com',password_hash,false,CURRENT_TIMESTAMP "
                "FROM users WHERE id=:uid ON CONFLICT (id) DO NOTHING"
            ),
            {"aid": demo_admin, "uid": demo_owner},
        )
        canonical = bind.execute(
            sa.text("SELECT id FROM users WHERE id=:aid AND email='demo-admin@example.com'"),
            {"aid": demo_admin},
        ).scalar_one_or_none()
        if canonical is None:
            raise RuntimeError(
                "Canonical demo identity conflict; refusing to retire its last admin."
            )
        bind.execute(
            sa.text(
                "INSERT INTO memberships (tenant_id,user_id,role,status,created_at) "
                "VALUES (:tid,:aid,'admin','active',CURRENT_TIMESTAMP) "
                "ON CONFLICT (tenant_id,user_id) DO UPDATE SET role='admin',status='active'"
            ),
            {"tid": demo_tenant, "aid": demo_admin},
        )
        bind.execute(
            sa.text(
                "UPDATE memberships SET status='revoked' WHERE user_id=:uid AND tenant_id=:tid"
            ),
            {"uid": demo_owner, "tid": demo_tenant},
        )
        bind.execute(
            sa.text("UPDATE sessions SET revoked_at=CURRENT_TIMESTAMP WHERE user_id=:uid"),
            {"uid": demo_owner},
        )
        bind.execute(
            sa.text("UPDATE users SET password_hash='!retired-demo-login' WHERE id=:uid"),
            {"uid": demo_owner},
        )
    op.create_table(
        "change_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("requester_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("attachments", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "type IN ('knowledge','text_change','domain','delete_org','other')",
            name="ck_change_requests_type",
        ),
        sa.CheckConstraint(
            "status IN ('pending','triaged','in_progress','completed','rejected')",
            name="ck_change_requests_status",
        ),
    )
    op.create_index(
        "ix_change_requests_tenant_created", "change_requests", ["tenant_id", "created_at"]
    )
    op.create_table(
        "organization_deletions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False, unique=True),
        sa.Column("organization_name", sa.Text(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("storage_keys", postgresql.JSONB(), nullable=False),
        sa.Column("counts", postgresql.JSONB(), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("purge_after", sa.DateTime(timezone=True), nullable=False),
        sa.Column("purged_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "ix_organization_deletions_purge_after", "organization_deletions", ["purge_after"]
    )


def downgrade() -> None:
    op.drop_table("organization_deletions")
    op.drop_table("change_requests")
    for table in ("memberships", "invitations"):
        op.drop_constraint(f"ck_{table}_role", table, type_="check")
        op.create_check_constraint(
            f"ck_{table}_role", table, "role IN ('owner','admin','editor','viewer')"
        )
    # Mapping is intentionally irreversible: do not guess which admin was owner.
