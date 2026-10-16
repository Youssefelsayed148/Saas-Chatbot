"""P1-03: members — role matrix, last-admin protection, escalation, audit."""

from typing import Any

import pytest
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
        membership = db.get(Membership, (users.tenant_id, UUID(editor_id)))
        saved_message = db.get(Message, message.id)
        saved_conversation = db.get(Conversation, conversation.id)
        assert membership is not None and membership.status == "revoked"
        assert saved_message is not None and saved_message.tenant_id == users.tenant_id
        assert saved_conversation is not None
        assert saved_conversation.assigned_user_id == UUID(editor_id)
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


@pytest.mark.parametrize("methods", [("DELETE", "DELETE"), ("PATCH", "PATCH"), ("DELETE", "PATCH")])
def test_concurrent_last_admin_changes_keep_one_admin(
    app: Any, db: OrmSession, monkeypatch: Any, methods: tuple[str, str]
) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from uuid import UUID

    from fastapi.testclient import TestClient
    from sqlalchemy import func, select

    from app.db.models import Membership
    from app.quotas.service import lock_tenant
    from tests.conftest import csrf_headers

    users = seeded_tenant(app, db, prefix="concurrent-admin")
    try:
        base = f"/api/v1/tenants/{users.tenant_id}/members"
        second_id = users.users["editor"]["id"]
        assert (
            users.call("admin", "PATCH", f"{base}/{second_id}", json={"role": "admin"}).status_code
            == 200
        )
        barrier = Barrier(2)

        def simultaneous_lock(session: Any, tenant_id: Any) -> Any:
            barrier.wait(timeout=10)
            return lock_tenant(session, tenant_id)

        monkeypatch.setattr("app.tenants.service.lock_tenant", simultaneous_lock)

        def request(method: str, user_id: str) -> Any:
            with TestClient(app) as client:
                client.cookies.update(users.as_user("staff").cookies)
                return client.request(
                    method,
                    f"{base}/{user_id}",
                    headers=csrf_headers(client),
                    **({"json": {"role": "viewer"}} if method == "PATCH" else {}),
                )

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(request, method, user_id)
                for method, user_id in zip(
                    methods, [users.users["admin"]["id"], second_id], strict=True
                )
            ]
            responses = [future.result(timeout=20) for future in futures]
        assert sorted(response.status_code for response in responses) in ([200, 403], [204, 403])
        denied = next(response for response in responses if response.status_code == 403)
        assert denied.json()["error"]["code"] == "LAST_ADMIN"
        db.expire_all()
        assert (
            db.scalar(
                select(func.count())
                .select_from(Membership)
                .where(
                    Membership.tenant_id == users.tenant_id,
                    Membership.role == "admin",
                    Membership.status == "active",
                )
            )
            == 1
        )
        assert db.get(Membership, (users.tenant_id, UUID(second_id))) is not None
    finally:
        users.cleanup()
