"""P1-03: members — role matrix, last-owner protection, escalation, audit."""

from typing import Any

from sqlalchemy.orm import Session as OrmSession

from tests.helpers import (
    audit_actions,
    seeded_tenant,
)


def test_member_removal_by_admin(app: Any, db: OrmSession) -> None:
    users = seeded_tenant(app, db)
    try:
        editor_id = users.users["editor"]["id"]
        from uuid import UUID

        from app.db.models import Conversation, Membership, Message
        from tests.helpers import make_bot

        bot = make_bot(users)
        conversation = Conversation(
            tenant_id=users.tenant_id,
            bot_id=UUID(bot["id"]),
            assigned_user_id=UUID(editor_id),
            mode="human",
        )
        db.add(conversation)
        db.flush()
        message = Message(
            tenant_id=users.tenant_id,
            bot_id=UUID(bot["id"]),
            conversation_id=conversation.id,
            sender_type="agent",
            sender_user_id=UUID(editor_id),
            text="Historical agent reply",
        )
        db.add(message)
        db.commit()
        url = f"/api/v1/tenants/{users.tenant_id}/members/{editor_id}"
        assert users.call("admin", "DELETE", url).status_code == 204
        members = users.call("admin", "GET", f"/api/v1/tenants/{users.tenant_id}/members").json()
        assert editor_id not in [row["user_id"] for row in members]
        # Removing again is 404 (member gone).
        assert users.call("admin", "DELETE", url).status_code == 404
        audit = audit_actions(db, "member.removed", users.tenant_id)
        assert len(audit) == 1
        db.expire_all()
        assert db.get(Membership, (users.tenant_id, UUID(editor_id))).status == "revoked"
        assert db.get(Message, message.id).tenant_id == users.tenant_id
        assert db.get(Conversation, conversation.id).assigned_user_id == UUID(editor_id)
        assert (
            users.call("editor", "GET", f"/api/v1/tenants/{users.tenant_id}/bots").status_code
            == 404
        )
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


def test_last_admin_is_protected(app: Any, db: OrmSession) -> None:
    users = seeded_tenant(app, db)
    try:
        path = f"/api/v1/tenants/{users.tenant_id}/members/{users.users['admin']['id']}"
        for role in ("admin", "staff"):
            response = users.call(role, "PATCH", path, json={"role": "editor"})
            assert response.status_code == 403
            assert response.json()["error"]["code"] == "LAST_ADMIN"
            response = users.call(role, "DELETE", path)
            assert response.status_code == 403
            assert response.json()["error"]["code"] == "LAST_ADMIN"
        assert users.call("viewer", "PATCH", path, json={"role": "admin"}).status_code == 403
    finally:
        users.cleanup()


def test_admin_can_promote_then_step_down(app: Any, db: OrmSession) -> None:
    users = seeded_tenant(app, db)
    try:
        base = f"/api/v1/tenants/{users.tenant_id}/members"
        promoted = users.call(
            "admin", "PATCH", f"{base}/{users.users['editor']['id']}", json={"role": "admin"}
        )
        assert promoted.status_code == 200
        demoted = users.call(
            "admin", "PATCH", f"{base}/{users.users['admin']['id']}", json={"role": "viewer"}
        )
        assert demoted.status_code == 200
        assert len(audit_actions(db, "member.role_changed", users.tenant_id)) == 2
    finally:
        users.cleanup()


def test_owner_role_and_transfer_removed(app: Any, db: OrmSession) -> None:
    users = seeded_tenant(app, db)
    try:
        target = f"/api/v1/tenants/{users.tenant_id}/members/{users.users['editor']['id']}"
        assert users.call("admin", "PATCH", target, json={"role": "owner"}).status_code == 422
        assert users.call("admin", "POST", f"{target}/transfer-ownership").status_code == 404
    finally:
        users.cleanup()
