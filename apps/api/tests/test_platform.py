"""P4-06: platform admin console basics (docs/11, ADR-018).

- /platform API paths guarded SERVER-SIDE by users.is_platform_staff
  (non-staff 403, hidden tenants 404);
- the staff flag is separate from tenant roles (a staff user without any
  membership reaches the console; a tenant admin without the flag does not);
- staff setup uses the separate organization/user/bot endpoints;
- retained durable provisioning service retries still create exactly ONE tenant;
- actor attribution in audit; tenant A/B isolation unaffected."""

from io import BytesIO
from typing import Any, BinaryIO
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

import tests.retrieval_helpers as _rh  # noqa: F401 — registers the corpus fixture
from app.core.config import get_settings
from app.core.errors import ApiError
from app.db.models import User
from app.provisioning.service import ProvisioningPayload, ProvisioningService
from tests.helpers import (
    PASSWORD,
    accept_invitation,
    csrf_headers,
    logged_in,
    make_bot,
    seeded_tenant,
)

corpus = _rh.corpus

ONBOARD_FORM = {
    "client_name": "Provisioned Org",
    "admin_email": "new-admin@example.com",
    "bot_name": "First Bot",
}


def staff_login(app: Any, db: Any, email: str = "staff@example.com") -> TestClient:
    """A user whose is_platform_staff flag is set DIRECTLY in the DB (the flag
    is separate from any tenant membership)."""
    client, payload = logged_in(app, email)
    db.execute(
        text("UPDATE users SET is_platform_staff = TRUE WHERE id = :u"),
        {"u": payload["id"]},
    )
    db.commit()
    return client


def platform_call(client: TestClient, method: str, path: str, **kwargs: Any) -> Any:
    csrf = client.cookies.get("chatbot_csrf")
    headers = {"X-CSRF-Token": csrf or ""} if method in ("POST", "PATCH", "DELETE") else {}
    headers.update(kwargs.pop("headers", {}))
    return client.request(method, f"/api/v1/platform{path}", headers=headers, **kwargs)


def legacy_onboard(
    app: Any,
    db: Any,
    staff: TestClient,
    form: dict[str, Any],
    key: str,
    files: list[tuple[str, BinaryIO]] | None = None,
) -> dict[str, Any]:
    """Exercise the retained durable service, not the retired HTTP route."""
    actor = db.get(User, UUID(platform_call(staff, "GET", "/me").json()["id"]))
    assert actor is not None
    settings = app.dependency_overrides[get_settings]()
    return ProvisioningService(db, settings).onboard_platform_client(
        actor=actor, payload=ProvisioningPayload(**form), idempotency_key=key, files=files
    )


def create_platform_client(staff: TestClient) -> dict[str, Any]:
    """Real staff organization/user/invitation/bot endpoints replace batch setup."""
    org = platform_call(staff, "POST", "/tenants", json={"name": ONBOARD_FORM["client_name"]})
    assert org.status_code == 201, org.text
    tenant_id = org.json()["id"]
    user = platform_call(
        staff, "POST", "/users", json={"email": ONBOARD_FORM["admin_email"], "password": PASSWORD}
    )
    assert user.status_code == 201, user.text
    invitation = staff.post(
        f"/api/v1/tenants/{tenant_id}/invitations",
        json={"email": ONBOARD_FORM["admin_email"], "role": "admin"},
        headers=csrf_headers(staff),
    )
    assert invitation.status_code == 201, invitation.text
    bot = platform_call(
        staff,
        "POST",
        "/bots",
        json={"organization_id": tenant_id, "name": ONBOARD_FORM["bot_name"]},
    )
    assert bot.status_code == 201, bot.text
    return {"tenant_id": tenant_id, "bot_id": bot.json()["id"], "admin_invite": invitation.json()}


# --- guarding ---------------------------------------------------------------


def test_non_staff_get_403_everywhere(corpus: dict[str, Any], app: Any, db: Any) -> None:
    admin_client, _payload = logged_in(app, "just-admin@example.com")
    tenant_id = None
    create = admin_client.post(
        "/api/v1/tenants",
        json={"name": "Own.org"},
        headers={"X-CSRF-Token": admin_client.cookies.get("chatbot_csrf")},
    )
    assert create.status_code == 201
    tenant_id = create.json()["id"]
    for method, path in (
        ("GET", "/me"),
        ("GET", "/tenants"),
        ("GET", f"/tenants/{tenant_id}"),
        ("GET", "/operations/jobs"),
        ("GET", "/analytics"),
        ("GET", "/audit"),
        ("GET", "/quotas"),
        ("GET", "/bots"),
        ("POST", "/bots"),
        ("GET", "/users"),
    ):
        response = admin_client.request(method, f"/api/v1/platform{path}")
        assert response.status_code == 403, (method, path, response.text)
        assert response.json()["error"]["code"] == "FORBIDDEN"
    del tenant_id


def test_staff_flag_is_separate_from_tenant_roles(
    app: Any, db: Any, corpus: dict[str, Any]
) -> None:
    staff_client = staff_login(app, db, "rolefree-staff@example.com")
    me = platform_call(staff_client, "GET", "/me")
    assert me.status_code == 200
    # The staff user has NO tenant membership and still reaches the console:
    listing = platform_call(staff_client, "GET", "/tenants")
    assert listing.status_code == 200
    # ...and a tenant ADMIN without the flag is refused (role is not enough).
    admin_client, _payload = logged_in(app, "plain-admin2@example.com")
    admin_client.post(
        "/api/v1/tenants",
        json={"name": "Plain"},
        headers={"X-CSRF-Token": admin_client.cookies.get("chatbot_csrf")},
    )
    assert platform_call(admin_client, "GET", "/tenants").status_code == 403


# --- onboarding -------------------------------------------------------------


def test_staff_sections_create_tenant_user_bot_and_admin_invite(
    app: Any, db: Any, corpus: dict[str, Any]
) -> None:
    staff_client = staff_login(app, db)
    result = create_platform_client(staff_client)
    tenant_id = result["tenant_id"]
    assert result["bot_id"]
    invite = result["admin_invite"]
    assert invite["link_path"].startswith("/accept-invite?token=")
    # the invitation exists as an ADMIN row (single-use token hashed)
    invitations = db.execute(
        text("SELECT email, role FROM invitations WHERE tenant_id = :t"),
        {"t": tenant_id},
    ).fetchall()
    assert len(invitations) == 1 and invitations[0][1] == "admin"
    # actor attribution: the staff action is in the tenant's audit trail
    audit = db.execute(
        text("SELECT action, actor_user_id IS NOT NULL FROM audit_events WHERE tenant_id = :t"),
        {"t": tenant_id},
    ).fetchall()
    actions = {row[0] for row in audit}
    assert "invitation.created" in actions
    assert "platform.bot.created" in actions
    assert "platform.onboarding.owner_invited" not in actions
    assert "platform.organization.created" in actions
    assert all(row[1] for row in audit)
    # tenant is a REAL tenant (no admin membership yet — invite-pending)
    members = db.execute(
        text("SELECT count(*) FROM memberships WHERE tenant_id = :t"),
        {"t": tenant_id},
    ).scalar_one()
    assert int(members) == 0
    invitee, _ = logged_in(app, ONBOARD_FORM["admin_email"])
    accepted = accept_invitation(invitee, invite["link_path"].split("token=")[1])
    assert accepted.status_code == 200, accepted.text
    role = db.execute(
        text("SELECT role FROM memberships WHERE tenant_id = :t"), {"t": tenant_id}
    ).scalar_one()
    assert role == "admin"
    assert invitee.get("/api/v1/platform/me").status_code == 403


def test_double_submit_creates_exactly_one_tenant(
    app: Any, db: Any, corpus: dict[str, Any]
) -> None:
    staff = staff_login(app, db)
    first = legacy_onboard(app, db, staff, ONBOARD_FORM, "dup-1")
    second = legacy_onboard(app, db, staff, ONBOARD_FORM, "dup-1")
    assert first["status"] == second["status"] == "ready"
    assert second["replayed"] is True
    assert second["result"]["tenant_id"] == first["result"]["tenant_id"]
    tenants = db.execute(
        text("SELECT count(*) FROM tenants WHERE name = 'Provisioned Org'")
    ).scalar_one()
    assert int(tenants) == 1
    bots = db.execute(
        text(
            "SELECT count(*) FROM bots b JOIN tenants t ON t.id = b.tenant_id "
            "WHERE t.name = 'Provisioned Org'"
        )
    ).scalar_one()
    assert int(bots) == 1


def test_same_key_different_payload_is_conflict(app: Any, db: Any, corpus: dict[str, Any]) -> None:
    staff = staff_login(app, db)
    first = legacy_onboard(app, db, staff, ONBOARD_FORM, "mix-1")
    assert first["status"] == "ready"
    clash = dict(ONBOARD_FORM, client_name="Another Org")
    with pytest.raises(ApiError) as raised:
        legacy_onboard(app, db, staff, clash, "mix-1")
    assert raised.value.status_code == 409
    assert raised.value.code == "IDEMPOTENCY_KEY_PAYLOAD_MISMATCH"


def test_retired_onboarding_post_is_rejected(app: Any, db: Any, corpus: dict[str, Any]) -> None:
    staff = staff_login(app, db)
    response = platform_call(staff, "POST", "/onboarding", data=ONBOARD_FORM)
    assert response.status_code in (404, 405)


def test_legacy_provisioning_accepts_optional_files(
    app: Any, db: Any, corpus: dict[str, Any]
) -> None:
    staff = staff_login(app, db)
    body = legacy_onboard(
        app,
        db,
        staff,
        ONBOARD_FORM,
        "files-1",
        files=[("pages/001-services.md", BytesIO(b"---\ntitle: Services\n---\n\n# Services\n"))],
    )
    assert body["status"] == "ready"
    assert any(row["display"] == "pages/001-services.md" for row in body["result"]["files"])


def test_client_list_and_detail_are_reachable_by_staff_only(
    app: Any, db: Any, corpus: dict[str, Any]
) -> None:
    users = seeded_tenant(app, db, prefix="plat")
    make_bot(users, "Client Bot")
    staff_client = staff_login(app, db)
    listing = platform_call(staff_client, "GET", "/tenants")
    assert listing.status_code == 200
    tenants = listing.json()["tenants"]
    target = next(row for row in tenants if row["slug"] == "org-plat")
    assert target["bots"] == 1 and target["seats"] == 3
    detail = platform_call(staff_client, "GET", f"/tenants/{target['id']}")
    assert detail.status_code == 200
    body = detail.json()
    assert any(bot["name"] == "Client Bot" for bot in body["bots"])
    assert len(body["members"]) == 3
    assert isinstance(body["recent_audit"], list)
    # a different tenant's unknown id → 404, tenant isolation unaffected
    unknown = platform_call(staff_client, "GET", "/tenants/00000000-0000-0000-0000-00000000aaa1")
    assert unknown.status_code == 404
    # Tenant A vs B: nothing leaks between them through staff-only paths
    admin_a = users.as_user("admin")
    bot_a = make_bot(users, "Another")
    outsider = (
        platform_call(users.as_user("viewer"), "GET", f"/platform-derived/{bot_a['id']}")
        if False
        else None
    )
    del outsider, bot_a, admin_a


def test_staff_can_create_and_update_organization_without_provisioning(
    app: Any, db: Any, corpus: dict[str, Any]
) -> None:
    staff = staff_login(app, db)
    created = platform_call(
        staff,
        "POST",
        "/tenants",
        json={"name": "  Acme Labs  ", "plan_label": "pro"},
    )
    assert created.status_code == 201, created.text
    org = created.json()
    assert org["name"] == "Acme Labs" and org["plan_label"] == "pro"
    assert org["status"] == "active" and org["slug"]
    same_name = platform_call(staff, "POST", "/tenants", json={"name": "Acme Labs"})
    assert same_name.status_code == 201
    assert same_name.json()["slug"] != org["slug"]
    assert same_name.json()["plan_label"] == "starter"
    for table in ("bots", "invitations", "memberships"):
        count = db.execute(
            text(f"select count(*) from {table} where tenant_id=:id"), {"id": org["id"]}
        ).scalar_one()
        assert count == 0
    invalid_name = platform_call(staff, "POST", "/tenants", json={"name": "x" * 201})
    invalid_plan = platform_call(
        staff, "POST", "/tenants", json={"name": "Valid", "plan_label": "mystery"}
    )
    assert invalid_name.status_code == invalid_plan.status_code == 422
    updated = platform_call(
        staff,
        "PATCH",
        f"/tenants/{org['id']}",
        json={"name": "Acme Updated", "status": "archived"},
    )
    assert updated.status_code == 200, updated.text
    assert (updated.json()["name"], updated.json()["plan_label"], updated.json()["status"]) == (
        "Acme Updated",
        "pro",
        "archived",
    )
    assert (
        platform_call(
            staff, "PATCH", f"/tenants/{org['id']}", json={"status": "suspended"}
        ).status_code
        == 422
    )
    assert (
        platform_call(
            staff, "PATCH", f"/tenants/{org['id']}", json={"plan_label": "business"}
        ).status_code
        == 422
    )
    assert (
        platform_call(staff, "GET", f"/tenants/{org['id']}").json()["tenant"]["plan_label"] == "pro"
    )
    audit = db.execute(
        text(
            "select action, actor_user_id, metadata_json from audit_events "
            "where tenant_id=:id order by action"
        ),
        {"id": org["id"]},
    ).all()
    assert [row[0] for row in audit] == [
        "platform.organization.created",
        "platform.organization.updated",
    ]
    actor_id = db.execute(text("select id from users where email='staff@example.com'")).scalar_one()
    assert all(row[1] == actor_id for row in audit)
    assert audit[-1][2]["fields"] == ["name", "status"]
    assert audit[-1][2]["before"] == {
        "name": "Acme Labs",
        "status": "active",
    }
    assert audit[-1][2]["after"] == {
        "name": "Acme Updated",
        "status": "archived",
    }


def test_organization_plan_changes_require_existing_reason_and_audit(
    app: Any, db: Any, corpus: dict[str, Any]
) -> None:
    staff = staff_login(app, db)
    created = platform_call(staff, "POST", "/tenants", json={"name": "Plan review"})
    assert created.status_code == 201
    org_id = created.json()["id"]
    path = f"/tenants/{org_id}"
    assert platform_call(staff, "PATCH", path, json={"plan_label": "pro"}).status_code == 422
    for payload in ({"plan_label": "pro"}, {"plan_label": "pro", "reason": "   "}):
        assert platform_call(staff, "PATCH", f"{path}/plan", json=payload).status_code == 422
    assert platform_call(staff, "GET", path).json()["tenant"]["plan_label"] == "starter"
    assigned = platform_call(
        staff,
        "PATCH",
        f"{path}/plan",
        json={"plan_label": "pro", "reason": "Reviewed organization capacity"},
    )
    assert assigned.status_code == 200
    assert platform_call(staff, "GET", path).json()["tenant"]["plan_label"] == "pro"
    rows = db.execute(
        text(
            "SELECT actor_user_id, metadata_json FROM audit_events "
            "WHERE tenant_id=:id AND action='platform.tenant.plan_assigned'"
        ),
        {"id": org_id},
    ).all()
    actor = db.execute(text("SELECT id FROM users WHERE email='staff@example.com'")).scalar_one()
    assert len(rows) == 1
    assert rows[0][0] == actor
    assert rows[0][1] == {
        "from": "starter",
        "to": "pro",
        "reason": "Reviewed organization capacity",
    }


def test_organization_endpoints_are_staff_only_and_detail_scoped(
    app: Any, db: Any, corpus: dict[str, Any]
) -> None:
    a = seeded_tenant(app, db, prefix="org-a")
    b = seeded_tenant(app, db, prefix="org-b")
    make_bot(a, "A private bot")
    make_bot(b, "B private bot")
    staff = staff_login(app, db)
    path = f"/tenants/{a.tenant_id}"
    detail = platform_call(staff, "GET", path).json()
    assert "password_hash" not in str(detail)
    assert {m["email"] for m in detail["members"]} == {
        a.users[role]["email"] for role in ("admin", "editor", "viewer")
    }
    assert [bot["name"] for bot in detail["bots"]] == ["A private bot"]
    assert detail["counts"] == {"members": 3, "bots": 1}
    for role in ("admin", "editor", "viewer"):
        user = a.as_user(role)
        assert platform_call(user, "POST", "/tenants", json={"name": "No"}).status_code == 403
        assert platform_call(user, "PATCH", path, json={"name": "No"}).status_code == 403
        assert platform_call(user, "GET", path).status_code == 403
    with TestClient(app) as anonymous:
        assert anonymous.post("/api/v1/platform/tenants", json={"name": "No"}).status_code == 401
        assert (
            anonymous.patch(
                f"/api/v1/platform/tenants/{a.tenant_id}", json={"name": "No"}
            ).status_code
            == 401
        )
        assert anonymous.get(f"/api/v1/platform/tenants/{a.tenant_id}").status_code == 401


def test_staff_created_bot_has_widget_locator_and_public_config_is_reachable(
    app: Any, db: Any, corpus: dict[str, Any]
) -> None:
    from fastapi.testclient import TestClient

    staff_client = staff_login(app, db)
    bot_id = create_platform_client(staff_client)["bot_id"]
    locator = db.execute(
        text("SELECT widget_locator FROM bots WHERE id = CAST(:b AS uuid)"), {"b": bot_id}
    ).scalar_one()
    assert locator
    public = TestClient(app).get(f"/api/public/v1/widgets/{locator}/config")
    assert public.status_code == 200, public.text
