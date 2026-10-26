"""Staff account lifecycle, authorization, privacy and organization isolation."""

from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.models import AuditEvent, Tenant, User
from tests.helpers import PASSWORD, csrf_headers, seeded_tenant
from tests.test_platform import platform_call, staff_login


def create(staff: TestClient, **overrides: Any) -> Any:
    return platform_call(
        staff,
        "POST",
        "/users",
        json={"email": "Test.Owner@Example.com", "password": PASSWORD, **overrides},
    )


@pytest.mark.parametrize("generated", [False, True])
def test_create_login_normalization_uniqueness_privacy(app: Any, db: Any, generated: bool) -> None:
    org = seeded_tenant(app, db, prefix="members")
    staff = org.as_user("staff")
    body = {"generate": True, "password": None} if generated else {}
    result = create(
        staff, phone="+20 (123) 456-7890", organization_id=str(org.tenant_id), role="editor", **body
    )
    assert result.status_code == 201, result.text
    user = result.json()["user"]
    assert user["email"] == "test.owner@example.com"
    assert user["phone"] == "+201234567890"
    assert "password_hash" not in result.text
    password = result.json()["generated_password"] if generated else PASSWORD
    assert bool(result.json()["generated_password"]) == generated
    client = TestClient(app)
    assert (
        client.post(
            "/api/v1/auth/login", json={"email": user["email"], "password": password}
        ).status_code
        == 200
    )
    assert "phone" not in client.get("/api/v1/auth/me").text
    for path in ("members", "invitations"):
        response = org.call("admin", "GET", f"/api/v1/tenants/{org.tenant_id}/{path}")
        assert response.status_code == 200
        assert "phone" not in response.text
    assert create(staff, email="TEST.OWNER@example.com").status_code == 409
    assert create(staff, email="bad-phone@example.com", phone="123").status_code == 422
    assert password not in platform_call(staff, "GET", f"/users/{user['id']}").text
    events = list(db.scalars(select(AuditEvent).where(AuditEvent.target_id == user["id"])))
    assert {e.action for e in events} == {"platform.user.created", "platform.user.membership_added"}
    assert all(str(e.actor_user_id) == org.users["staff"]["id"] for e in events)
    assert all(
        password not in str(e.metadata_json) and "hash" not in str(e.metadata_json) for e in events
    )


def test_reset_deactivation_reactivation_revoke_all_sessions(app: Any, db: Any) -> None:
    staff = staff_login(app, db)
    result = create(staff)
    uid = result.json()["user"]["id"]
    clients = [TestClient(app), TestClient(app)]
    for client in clients:
        assert (
            client.post(
                "/api/v1/auth/login", json={"email": "test.owner@example.com", "password": PASSWORD}
            ).status_code
            == 200
        )
    reset = platform_call(staff, "POST", f"/users/{uid}/password", json={"generate": True})
    assert reset.status_code == 200
    password = reset.json()["generated_password"]
    assert all(c.get("/api/v1/auth/me").status_code == 401 for c in clients)
    client = clients[0]
    assert (
        client.post(
            "/api/v1/auth/login", json={"email": "test.owner@example.com", "password": password}
        ).status_code
        == 200
    )
    assert platform_call(staff, "POST", f"/users/{uid}/deactivate").status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401
    assert (
        client.post(
            "/api/v1/auth/login", json={"email": "test.owner@example.com", "password": password}
        ).status_code
        == 401
    )
    assert platform_call(staff, "POST", f"/users/{uid}/reactivate").status_code == 200
    assert (
        client.post(
            "/api/v1/auth/login", json={"email": "test.owner@example.com", "password": password}
        ).status_code
        == 200
    )
    assert {
        e.action for e in db.scalars(select(AuditEvent).where(AuditEvent.target_id == uid))
    } >= {"platform.user.password_reset", "platform.user.deactivated", "platform.user.reactivated"}


@pytest.mark.parametrize(
    "method,suffix,payload",
    [
        ("GET", "", None),
        ("POST", "", {}),
        ("GET", "/{user}", None),
        ("POST", "/{user}/memberships", {}),
        ("PATCH", "/{user}/memberships/{org}", {}),
        ("DELETE", "/{user}/memberships/{org}", None),
        ("POST", "/{user}/password", {}),
        ("POST", "/{user}/deactivate", None),
        ("POST", "/{user}/reactivate", None),
    ],
)
def test_every_endpoint_requires_staff(
    app: Any, db: Any, method: str, suffix: str, payload: Any
) -> None:
    users = seeded_tenant(app, db)
    path = "/api/v1/platform/users" + suffix.format(user=uuid4(), org=users.tenant_id)
    for role in ("admin", "editor"):
        assert users.call(role, method, path, json=payload).status_code == 403
    assert TestClient(app).request(method, path, json=payload).status_code == 401


def test_membership_rules_staff_exclusion_and_filtered_lists(app: Any, db: Any) -> None:
    a = seeded_tenant(app, db, prefix="staff-a")
    b = seeded_tenant(app, db, prefix="staff-b")
    staff = a.as_user("staff")
    uid = create(staff).json()["user"]["id"]
    for org in (a, b):
        added = platform_call(
            staff,
            "POST",
            f"/users/{uid}/memberships",
            json={"organization_id": str(org.tenant_id), "role": "editor"},
        )
        assert added.status_code == 201, added.text
    filtered = platform_call(staff, "GET", f"/users?organization_id={a.tenant_id}&q=owner").json()
    assert filtered["total"] == 1
    assert {m["organization_id"] for m in filtered["users"][0]["memberships"]} == {str(a.tenant_id)}
    assert (
        platform_call(
            staff, "PATCH", f"/users/{uid}/memberships/{a.tenant_id}", json={"role": "viewer"}
        ).status_code
        == 200
    )
    assert (
        platform_call(staff, "DELETE", f"/users/{uid}/memberships/{a.tenant_id}").status_code == 204
    )
    admin_id = a.users["admin"]["id"]
    for method, payload in (("PATCH", {"role": "viewer"}), ("DELETE", None)):
        response = platform_call(
            staff, method, f"/users/{admin_id}/memberships/{a.tenant_id}", json=payload
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "LAST_ADMIN"
    staff_id = a.users["staff"]["id"]
    assert staff_id not in {u["id"] for u in platform_call(staff, "GET", "/users").json()["users"]}
    for suffix in ("", "/password", "/deactivate", "/reactivate", "/memberships"):
        response = platform_call(
            staff,
            "GET" if not suffix else "POST",
            f"/users/{staff_id}{suffix}",
            json={"generate": True}
            if suffix == "/password"
            else {"organization_id": str(a.tenant_id), "role": "viewer"}
            if suffix == "/memberships"
            else None,
        )
        assert response.status_code == 404
    tenant = db.get(Tenant, b.tenant_id)
    tenant.quota_overrides = {"seats": 0}
    db.commit()
    other = create(staff, email="quota@example.com").json()["user"]["id"]
    assert (
        platform_call(
            staff,
            "POST",
            f"/users/{other}/memberships",
            json={"organization_id": str(b.tenant_id), "role": "viewer"},
        ).status_code
        == 429
    )


def test_invitation_existing_user_mixed_case(app: Any, db: Any) -> None:
    org = seeded_tenant(app, db)
    assert create(org.as_user("staff")).status_code == 201
    path = f"/api/v1/tenants/{org.tenant_id}/invitations"
    assert (
        org.call(
            "admin", "POST", path, json={"email": "unknown@example.com", "role": "viewer"}
        ).json()["error"]["code"]
        == "USER_NOT_FOUND"
    )
    invitation = org.call(
        "admin", "POST", path, json={"email": "TeSt.Owner@Example.com", "role": "viewer"}
    )
    assert invitation.status_code == 201, invitation.text
    client = TestClient(app)
    assert (
        client.post(
            "/api/v1/auth/login", json={"email": "TEST.OWNER@example.com", "password": PASSWORD}
        ).status_code
        == 200
    )
    token = invitation.json()["link_path"].split("token=")[1]
    accepted = client.post(
        "/api/v1/invitations/accept", json={"token": token}, headers=csrf_headers(client)
    )
    assert accepted.status_code == 200, accepted.text
    assert (
        db.get(
            User, UUID(create(org.as_user("staff"), email="other@example.com").json()["user"]["id"])
        ).email
        == "other@example.com"
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"email": 123},
        {"email": "invalid"},
        {"password": "short"},
        {"generate": True},
        {"password": None},
        {"phone": "++1234"},
        {"phone": "+0123456789"},
        {"phone": "+1234567890123456"},
        {"role": "admin"},
        {"organization_id": str(uuid4())},
        {"is_platform_staff": True},
    ],
)
def test_create_validation_is_safe_and_atomic(app: Any, db: Any, payload: dict[str, Any]) -> None:
    staff = staff_login(app, db)
    result = create(staff, **payload)
    assert result.status_code == 422, result.text
    # Field names may be reported (A1.2); submitted values must never be echoed.
    for value in payload.values():
        if isinstance(value, str) and value:
            assert value not in result.text
    assert PASSWORD not in result.text
    assert db.scalar(select(User).where(User.email == "test.owner@example.com")) is None


def test_failed_assignment_does_not_leave_partial_user(app: Any, db: Any) -> None:
    staff = staff_login(app, db)
    result = create(staff, organization_id=str(uuid4()), role="viewer")
    assert result.status_code == 404
    assert db.scalar(select(User).where(User.email == "test.owner@example.com")) is None
    assert not list(
        db.scalars(select(AuditEvent).where(AuditEvent.action == "platform.user.created"))
    )


def test_list_pagination_status_search_and_password_never_reissued(app: Any, db: Any) -> None:
    staff = staff_login(app, db)
    result = create(staff, password=None, generate=True)
    assert result.headers["cache-control"] == "no-store"
    user = result.json()["user"]
    password = result.json()["generated_password"]
    assert len(password) >= 24
    assert platform_call(staff, "POST", f"/users/{user['id']}/deactivate").status_code == 200
    assert platform_call(staff, "GET", "/users?status=active&q=owner").json()["total"] == 0
    response = platform_call(staff, "GET", "/users?status=inactive&q=TEST.OWNER&limit=1")
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert password not in response.text
    assert "generated_password" not in response.text
    assert platform_call(staff, "GET", "/users?status=inactive&offset=1").json()["users"] == []
    assert platform_call(staff, "GET", "/users?q=%25").json()["total"] == 0


def test_typed_password_reset_enforces_policy_and_revokes_session(app: Any, db: Any) -> None:
    staff = staff_login(app, db)
    user_id = create(staff).json()["user"]["id"]
    client = TestClient(app)
    assert (
        client.post(
            "/api/v1/auth/login", json={"email": "test.owner@example.com", "password": PASSWORD}
        ).status_code
        == 200
    )
    assert (
        platform_call(
            staff, "POST", f"/users/{user_id}/password", json={"password": "short"}
        ).status_code
        == 422
    )
    assert client.get("/api/v1/auth/me").status_code == 200
    password = "New-Staff-Password-123"
    result = platform_call(staff, "POST", f"/users/{user_id}/password", json={"password": password})
    assert result.status_code == 200
    assert result.json()["generated_password"] is None
    assert password not in result.text
    assert client.get("/api/v1/auth/me").status_code == 401
    assert (
        client.post(
            "/api/v1/auth/login", json={"email": "test.owner@example.com", "password": PASSWORD}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/v1/auth/login", json={"email": "test.owner@example.com", "password": password}
        ).status_code
        == 200
    )
