"""P1-03: members — role matrix, last-owner protection, escalation, audit."""

from typing import Any
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy.orm import Session as OrmSession

from tests.helpers import (
    audit_actions,
    make_bot,
    seeded_tenant,
)


def test_full_role_matrix(app: Any, db: OrmSession) -> None:
    users = seeded_tenant(app, db)
    try:
        tenant_id = users.tenant_id
        bot = make_bot(users, name="Matrix")
        bot_url = f"/api/v1/tenants/{tenant_id}/bots/{bot['id']}"
        admin_dummy = users.users["admin"]["id"]  # target of member PATCH/DELETE checks
        members_url = f"/api/v1/tenants/{tenant_id}/members"
        member_url = f"{members_url}/{admin_dummy}"
        invitations_url = f"/api/v1/tenants/{tenant_id}/invitations"
        ghost_bot = f"/api/v1/tenants/{tenant_id}/bots/{uuid4()}"

        cases = [
            ("owner", "GET", f"/api/v1/tenants/{tenant_id}", 200),
            ("admin", "GET", f"/api/v1/tenants/{tenant_id}", 200),
            ("editor", "GET", f"/api/v1/tenants/{tenant_id}", 200),
            ("viewer", "GET", f"/api/v1/tenants/{tenant_id}", 200),
            ("owner", "GET", f"/api/v1/tenants/{tenant_id}/bots", 200),
            ("viewer", "GET", f"/api/v1/tenants/{tenant_id}/bots", 200),
            ("owner", "POST", f"/api/v1/tenants/{tenant_id}/bots", 403),
            ("admin", "POST", f"/api/v1/tenants/{tenant_id}/bots", 403),
            ("editor", "POST", f"/api/v1/tenants/{tenant_id}/bots", 403),
            ("viewer", "POST", f"/api/v1/tenants/{tenant_id}/bots", 403),
            ("owner", "GET", bot_url, 200),
            ("viewer", "GET", bot_url, 200),
            ("owner", "PATCH", bot_url, 200),
            ("editor", "PATCH", bot_url, 403),
            ("admin", "PATCH", bot_url, 200),
            ("viewer", "PATCH", bot_url, 403),
            ("owner", "DELETE", bot_url, 403),
            ("admin", "DELETE", bot_url, 403),
            ("editor", "DELETE", bot_url, 403),
            ("viewer", "DELETE", bot_url, 403),
            ("owner", "GET", invitations_url, 200),
            ("admin", "GET", invitations_url, 200),
            ("editor", "GET", invitations_url, 403),
            ("viewer", "GET", invitations_url, 403),
            ("owner", "POST", invitations_url, 201),
            ("admin", "POST", invitations_url, 201),
            ("editor", "POST", invitations_url, 403),
            ("viewer", "POST", invitations_url, 403),
            ("owner", "GET", members_url, 200),
            ("admin", "GET", members_url, 200),
            ("editor", "GET", members_url, 403),
            ("viewer", "GET", members_url, 403),
            ("owner", "PATCH", member_url, 200),  # same-role no-op for the admin target
            ("admin", "PATCH", member_url, 200),  # admin no-op on their own role
            ("editor", "PATCH", member_url, 403),
            ("viewer", "PATCH", member_url, 403),
            ("owner", "DELETE", f"{members_url}/{uuid4()}", 404),
            ("editor", "DELETE", f"{members_url}/{uuid4()}", 403),
            ("viewer", "DELETE", f"{members_url}/{uuid4()}", 403),
        ]
        # Give the owner a second bot name to avoid name-noop PATCH (still fine 200).
        for role, method, url, expected in cases:
            if method == "POST" and url.endswith("/bots"):
                payload = {"name": "Matrix Bot"}
            elif method == "PATCH" and url == bot_url:
                payload = {"name": f"Matrix {role}"}
            elif method == "PATCH" and url == member_url:
                payload = {"role": "admin"} if role == "owner" else {"role": "admin"}
            elif method == "POST" and url == invitations_url:
                payload = {"email": f"{role}-matrix@example.com", "role": "viewer"}
            elif method == "DELETE" and url == bot_url:
                payload = None
            else:
                payload = None
            response = users.call(role, method, url, json=payload)
            status = response.status_code
            assert status == expected, (role, method, url, status, expected, response.text)
    finally:
        users.cleanup()


def test_admin_cannot_escalate_to_owner(app: Any, db: OrmSession) -> None:
    users = seeded_tenant(app, db)
    try:
        editor_id = users.users["editor"]["id"]
        admin_grant = users.call(
            "admin",
            "PATCH",
            f"/api/v1/tenants/{users.tenant_id}/members/{editor_id}",
            json={"role": "owner"},
        )
        assert admin_grant.status_code == 403
        assert admin_grant.json()["error"]["code"] == "FORBIDDEN"

        # Admin also cannot change an owner's role.
        owner_id = users.users["owner"]["id"]
        attack = users.call(
            "admin",
            "PATCH",
            f"/api/v1/tenants/{users.tenant_id}/members/{owner_id}",
            json={"role": "viewer"},
        )
        assert attack.status_code == 403
        assert attack.json()["error"]["code"] == "FORBIDDEN"

        # Admin cannot remove an owner.
        remove = users.call(
            "admin", "DELETE", f"/api/v1/tenants/{users.tenant_id}/members/{owner_id}"
        )
        assert remove.status_code == 403
    finally:
        users.cleanup()


def test_last_owner_is_protected(app: Any, db: OrmSession) -> None:
    users = seeded_tenant(app, db)
    try:
        owner_id = users.users["owner"]["id"]
        url = f"/api/v1/tenants/{users.tenant_id}/members/{owner_id}"

        self_demote = users.call("owner", "PATCH", url, json={"role": "editor"})
        assert self_demote.status_code == 403
        assert self_demote.json()["error"]["code"] == "LAST_OWNER"

        leave_tenant = users.call("owner", "DELETE", url)
        assert leave_tenant.status_code == 403
        assert leave_tenant.json()["error"]["code"] == "LAST_OWNER"

        # External role change of the sole owner is meaningless for non-owners; owner-only.
        viewer_attack = users.call("viewer", "PATCH", url, json={"role": "viewer"})
        assert viewer_attack.status_code == 403
    finally:
        users.cleanup()


def test_owner_transfer_allowed_with_second_owner(app: Any, db: OrmSession) -> None:
    users = seeded_tenant(app, db)
    try:
        admin_id = users.users["admin"]["id"]
        url = f"/api/v1/tenants/{users.tenant_id}/members/{admin_id}"
        grant = users.call("owner", "PATCH", url, json={"role": "owner"})
        assert grant.status_code == 200
        assert grant.json()["role"] == "owner"

        # Now two owners: the original can step down.
        owner_id = users.users["owner"]["id"]
        step_down = users.call(
            "owner",
            "PATCH",
            f"/api/v1/tenants/{users.tenant_id}/members/{owner_id}",
            json={"role": "admin"},
        )
        assert step_down.status_code == 200
        assert step_down.json()["role"] == "admin"

        audit = audit_actions(db, "member.role_changed", users.tenant_id)
        assert len(audit) == 2
    finally:
        users.cleanup()


def test_dedicated_ownership_transfer_changes_both_roles(app: Any, db: OrmSession) -> None:
    users = seeded_tenant(app, db, prefix="dedicated-transfer")
    try:
        admin_id = users.users["admin"]["id"]
        transfer = users.call(
            "owner", "POST",
            f"/api/v1/tenants/{users.tenant_id}/members/{admin_id}/transfer-ownership",
        )
        assert transfer.status_code == 204
        members = users.call("owner", "GET", f"/api/v1/tenants/{users.tenant_id}/members").json()
        by_id = {row["user_id"]: row["role"] for row in members}
        assert by_id[users.users["owner"]["id"]] == "admin"
        assert by_id[admin_id] == "owner"
        assert users.call(
            "viewer", "POST",
            f"/api/v1/tenants/{users.tenant_id}/members/{users.users['editor']['id']}/transfer-ownership",
        ).status_code == 403
    finally:
        users.cleanup()


def test_concurrent_last_owner_demotions_leave_one_owner(app: Any, db: OrmSession) -> None:
    users = seeded_tenant(app, db, prefix="last-owner-race")
    try:
        second_owner = users.users["admin"]["id"]
        grant = users.call(
            "owner", "PATCH", f"/api/v1/tenants/{users.tenant_id}/members/{second_owner}",
            json={"role": "owner"},
        )
        assert grant.status_code == 200

        def demote(role: str) -> int:
            member_id = users.users[role]["id"]
            return users.call(
                role, "PATCH", f"/api/v1/tenants/{users.tenant_id}/members/{member_id}",
                json={"role": "admin"},
            ).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(demote, "owner"), pool.submit(demote, "admin")]
            statuses = sorted(future.result() for future in futures)
        assert statuses == [200, 403]
        owners = users.call("owner", "GET", f"/api/v1/tenants/{users.tenant_id}/members").json()
        assert sum(row["role"] == "owner" for row in owners) == 1
    finally:
        users.cleanup()


def test_member_removal_by_admin(app: Any, db: OrmSession) -> None:
    users = seeded_tenant(app, db)
    try:
        editor_id = users.users["editor"]["id"]
        url = f"/api/v1/tenants/{users.tenant_id}/members/{editor_id}"
        assert users.call("admin", "DELETE", url).status_code == 204
        members = users.call("admin", "GET", f"/api/v1/tenants/{users.tenant_id}/members").json()
        assert editor_id not in [row["user_id"] for row in members]
        # Removing again is 404 (member gone).
        assert users.call("admin", "DELETE", url).status_code == 404
        audit = audit_actions(db, "member.removed", users.tenant_id)
        assert len(audit) == 1
    finally:
        users.cleanup()


def test_role_change_validation(app: Any, db: OrmSession) -> None:
    users = seeded_tenant(app, db)
    try:
        editor_id = users.users["editor"]["id"]
        url = f"/api/v1/tenants/{users.tenant_id}/members/{editor_id}"
        bad_role = users.call("admin", "PATCH", url, json={"role": "godmode"})
        assert bad_role.status_code == 422
    finally:
        users.cleanup()
