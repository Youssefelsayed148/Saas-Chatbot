"""Operator organizations, member visibility and revoked access regressions."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.security import hash_token
from app.db.models import Invitation, Membership, Tenant, User
from tests.helpers import PASSWORD, accept_invitation, make_invitation, seeded_tenant


def test_staff_lists_all_organizations_with_pagination(app: FastAPI, db: Session) -> None:
    users = seeded_tenant(app, db, "pagination")
    try:
        # More than both the default and maximum page sizes; no staff memberships.
        db.add_all(
            [
                Tenant(
                    id=uuid4(),
                    name=f"Client {i}",
                    slug=f"client-{i}",
                    status="archived" if i == 200 else "active",
                )
                for i in range(201)
            ]
        )
        db.commit()
        staff = users.as_user("staff")
        assert staff.get("/api/v1/auth/me").json()["memberships"] == []
        first = staff.get("/api/v1/platform/tenants?limit=200&offset=0").json()
        second = staff.get("/api/v1/platform/tenants?limit=200&offset=200").json()
        assert first["total"] == second["total"] == 202
        rows = first["tenants"] + second["tenants"]
        assert len({row["id"] for row in rows}) == 202
        assert str(users.tenant_id) in {row["id"] for row in rows}
        assert {"name", "plan_label", "status", "bots", "last_activity"} <= rows[0].keys()
        assert users.as_user("admin").get("/api/v1/platform/tenants").status_code == 403
    finally:
        users.cleanup()


def test_revoked_members_hidden_from_platform_and_team(app: FastAPI, db: Session) -> None:
    a = seeded_tenant(app, db, "a")
    b = seeded_tenant(app, db, "b")
    try:
        revoked_id = a.users["editor"]["id"]
        removed = a.call("admin", "DELETE", f"/api/v1/tenants/{a.tenant_id}/members/{revoked_id}")
        assert removed.status_code == 204
        _, revoked_invite = make_invitation(a, "revoked-invite@example.com")
        assert (
            a.call(
                "admin",
                "DELETE",
                f"/api/v1/tenants/{a.tenant_id}/invitations/{revoked_invite['id']}",
            ).status_code
            == 204
        )
        _, pending = make_invitation(a, "pending@example.com")
        for reader in (a.as_user("admin"), a.as_user("staff")):
            members = reader.get(f"/api/v1/tenants/{a.tenant_id}/members").json()
            assert {row["email"] for row in members} == {
                a.users["admin"]["email"],
                a.users["viewer"]["email"],
            }
            assert all(row["status"] == "active" for row in members)
            invites = reader.get(f"/api/v1/tenants/{a.tenant_id}/invitations").json()
            assert [row["id"] for row in invites] == [pending["id"]]
        detail = a.as_user("staff").get(f"/api/v1/platform/tenants/{a.tenant_id}").json()
        assert [row["id"] for row in detail["pending_invitations"]] == [pending["id"]]
        assert {row["email"] for row in detail["members"]} == {
            a.users["admin"]["email"],
            a.users["viewer"]["email"],
        }
        for surface in ("members", "invitations"):
            assert (
                b.as_user("admin").get(f"/api/v1/tenants/{a.tenant_id}/{surface}").status_code
                == 404
            )
    finally:
        a.cleanup()
        b.cleanup()


@pytest.mark.parametrize("role", ["admin", "editor", "viewer"])
def test_revoked_only_user_cannot_login_or_restore_access(
    app: FastAPI, db: Session, role: str
) -> None:
    users = seeded_tenant(app, db, "revoke")
    try:
        if role == "admin":
            replacement = db.get(Membership, (users.tenant_id, UUID(users.users["viewer"]["id"])))
            assert replacement is not None
            replacement.role = "admin"
        user_id = UUID(users.users[role]["id"])
        email = users.users[role]["email"]
        token = "fixture-outstanding-invitation"
        # An older invitation predating membership removal must be invalidated.
        db.add(
            Invitation(
                id=uuid4(),
                tenant_id=users.tenant_id,
                email=email,
                role="editor",
                token_hash=hash_token(token),
                expires_at=datetime.now(UTC) + timedelta(days=1),
                created_by=UUID(users.users["admin"]["id"]),
            )
        )
        db.commit()
        assert (
            users.call(
                "admin", "DELETE", f"/api/v1/tenants/{users.tenant_id}/members/{user_id}"
            ).status_code
            == 204
        )
        revoked = users.as_user(role)
        assert revoked.get(f"/api/v1/tenants/{users.tenant_id}").status_code == 404
        accepted = accept_invitation(revoked, token)
        assert accepted.status_code == 409
        assert accepted.json()["error"]["code"] == "INVITATION_REVOKED"
        revoked.cookies.clear()
        login = revoked.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
        assert login.status_code == 401
        assert login.json()["error"]["code"] == "INVALID_CREDENTIALS"
        assert revoked.get("/api/v1/auth/me").status_code == 401
        membership = db.scalar(select(Membership).where(Membership.user_id == user_id))
        assert membership is not None and membership.status == "revoked"
    finally:
        users.cleanup()


def test_revocation_preserves_other_org_and_staff_login(app: FastAPI, db: Session) -> None:
    a = seeded_tenant(app, db, "login-a")
    b = seeded_tenant(app, db, "login-b")
    try:
        user_id = UUID(a.users["editor"]["id"])
        db.add(Membership(tenant_id=b.tenant_id, user_id=user_id, role="editor", status="active"))
        db.commit()
        assert (
            a.call(
                "admin", "DELETE", f"/api/v1/tenants/{a.tenant_id}/members/{user_id}"
            ).status_code
            == 204
        )
        member = a.as_user("editor")
        login = member.post(
            "/api/v1/auth/login", json={"email": a.users["editor"]["email"], "password": PASSWORD}
        )
        assert login.status_code == 200
        assert [row["tenant_id"] for row in login.json()["memberships"]] == [str(b.tenant_id)]
        assert member.get(f"/api/v1/tenants/{a.tenant_id}").status_code == 404
        assert member.get(f"/api/v1/tenants/{b.tenant_id}").status_code == 200
        staff_id = UUID(a.users["staff"]["id"])
        db.add(Membership(tenant_id=a.tenant_id, user_id=staff_id, role="viewer", status="revoked"))
        db.commit()
        staff_login = a.as_user("staff").post(
            "/api/v1/auth/login", json={"email": a.users["staff"]["email"], "password": PASSWORD}
        )
        assert staff_login.status_code == 200
        assert db.get(User, staff_id) is not None
    finally:
        a.cleanup()
        b.cleanup()
