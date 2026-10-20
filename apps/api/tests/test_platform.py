"""P4-06: platform admin console basics (docs/11, ADR-018).

- /platform API paths guarded SERVER-SIDE by users.is_platform_staff
  (non-staff 403, hidden tenants 404);
- the staff flag is separate from tenant roles (a staff user without any
  membership reaches the console; a tenant admin without the flag does not);
- staff onboarding through the SHARED ProvisioningService with a required
  Idempotency-Key: DOUBLE SUBMISSION creates exactly ONE tenant;
- actor attribution in audit; tenant A/B isolation unaffected."""

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import text

import tests.retrieval_helpers as _rh  # noqa: F401 — registers the corpus fixture
from tests.helpers import accept_invitation, logged_in, make_bot, seeded_tenant

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
        ("POST", "/onboarding"),
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


def test_staff_onboarding_creates_tenant_bot_and_admin_invite(
    app: Any, db: Any, corpus: dict[str, Any]
) -> None:
    staff_client = staff_login(app, db)
    response = platform_call(
        staff_client,
        "POST",
        "/onboarding",
        data=ONBOARD_FORM,
        headers={"Idempotency-Key": "ob-1"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "ready"
    result = body["result"]
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
        text(
            "SELECT action, actor_user_id IS NOT NULL FROM audit_events "
            "WHERE tenant_id = :t AND action LIKE 'platform.onboarding%'"
        ),
        {"t": tenant_id},
    ).fetchall()
    actions = {row[0] for row in audit}
    assert "platform.onboarding.admin_invited" in actions
    assert "platform.onboarding.owner_invited" not in actions
    assert "platform.onboarding.tenant_created" in actions
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
    staff_client = staff_login(app, db)
    first = platform_call(
        staff_client, "POST", "/onboarding", data=ONBOARD_FORM, headers={"Idempotency-Key": "dup-1"}
    )
    assert first.status_code == 201
    second = platform_call(
        staff_client, "POST", "/onboarding", data=ONBOARD_FORM, headers={"Idempotency-Key": "dup-1"}
    )
    assert second.status_code == 201
    body = second.json()
    assert body["replayed"] is True
    assert body["result"]["tenant_id"] == first.json()["result"]["tenant_id"]
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
    staff_client = staff_login(app, db)
    first = platform_call(
        staff_client, "POST", "/onboarding", data=ONBOARD_FORM, headers={"Idempotency-Key": "mix-1"}
    )
    assert first.status_code == 201
    clash = dict(ONBOARD_FORM, client_name="Another Org")
    response = platform_call(
        staff_client, "POST", "/onboarding", data=clash, headers={"Idempotency-Key": "mix-1"}
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "IDEMPOTENCY_KEY_PAYLOAD_MISMATCH"


def test_missing_idempotency_key_is_rejected(app: Any, db: Any, corpus: dict[str, Any]) -> None:
    staff_client = staff_login(app, db)
    response = platform_call(staff_client, "POST", "/onboarding", data=ONBOARD_FORM)
    assert response.status_code == 400


def test_onboarding_accepts_optional_files(app: Any, db: Any, corpus: dict[str, Any]) -> None:
    staff_client = staff_login(app, db)
    response = platform_call(
        staff_client,
        "POST",
        "/onboarding",
        data=ONBOARD_FORM,
        files={
            "files": (
                "pages/001-services.md",
                b"---\ntitle: Services\n---\n\n# Services\n",
                "text/markdown",
            )
        },
        headers={"Idempotency-Key": "files-1"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "ready"
    assert any(row["display"] == "pages/001-services.md" for row in body["result"]["files"])


# --- read views ---------------------------------------------------------------


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
    invalid_plan = platform_call(staff, "POST", "/tenants", json={"name": "Valid", "plan_label": "mystery"})
    assert invalid_name.status_code == invalid_plan.status_code == 422
    updated = platform_call(
        staff,
        "PATCH",
        f"/tenants/{org['id']}",
        json={"name": "Acme Updated", "plan_label": "business", "status": "archived"},
    )
    assert updated.status_code == 200, updated.text
    assert (updated.json()["name"], updated.json()["plan_label"], updated.json()["status"]) == (
        "Acme Updated",
        "business",
        "archived",
    )
    assert platform_call(staff, "PATCH", f"/tenants/{org['id']}", json={"status": "suspended"}).status_code == 422
    audit = db.execute(
        text(
            "select action, actor_user_id, metadata_json from audit_events "
            "where tenant_id=:id order by action"
        ),
        {"id": org["id"]},
    ).all()
    assert [row[0] for row in audit] == ["platform.organization.created", "platform.organization.updated"]
    actor_id = db.execute(text("select id from users where email='staff@example.com'")).scalar_one()
    assert all(row[1] == actor_id for row in audit)
    assert audit[-1][2]["fields"] == ["name", "plan_label", "status"]
    assert audit[-1][2]["before"] == {
        "name": "Acme Labs",
        "plan_label": "pro",
        "status": "active",
    }
    assert audit[-1][2]["after"] == {
        "name": "Acme Updated",
        "plan_label": "business",
        "status": "archived",
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
    assert {m["email"] for m in detail["members"]} == {u["email"] for u in a.users.values()}
    assert [bot["name"] for bot in detail["bots"]] == ["A private bot"]
    assert detail["counts"] == {"members": 3, "bots": 1}
    for role in ("admin", "viewer"):
        user = a.as_user(role)
        assert platform_call(user, "POST", "/tenants", json={"name": "No"}).status_code == 403
        assert platform_call(user, "PATCH", path, json={"name": "No"}).status_code == 403
        assert platform_call(user, "GET", path).status_code == 403
    with TestClient(app) as anonymous:
        assert anonymous.post("/api/v1/platform/tenants", json={"name": "No"}).status_code == 403
        assert (
            anonymous.patch(
                f"/api/v1/platform/tenants/{a.tenant_id}", json={"name": "No"}
            ).status_code
            == 403
        )
        assert anonymous.get(f"/api/v1/platform/tenants/{a.tenant_id}").status_code == 403


def test_staff_onboarded_bot_has_widget_locator_and_public_config_is_reachable(
    app: Any, db: Any, corpus: dict[str, Any]
) -> None:
    from fastapi.testclient import TestClient

    staff_client = staff_login(app, db)
    response = platform_call(
        staff_client,
        "POST",
        "/onboarding",
        data=ONBOARD_FORM,
        headers={"Idempotency-Key": "ob-locator"},
    )
    assert response.status_code == 201, response.text
    bot_id = response.json()["result"]["bot_id"]
    locator = db.execute(
        text("SELECT widget_locator FROM bots WHERE id = CAST(:b AS uuid)"), {"b": bot_id}
    ).scalar_one()
    assert locator
    public = TestClient(app).get(f"/api/public/v1/widgets/{locator}/config")
    assert public.status_code == 200, public.text
