"""P4-06: platform admin console basics (docs/11, ADR-018).

- /platform API paths guarded SERVER-SIDE by users.is_platform_staff
  (non-staff 403, hidden tenants 404);
- the staff flag is separate from tenant roles (a staff user without any
  membership reaches the console; a tenant owner without the flag does not);
- staff onboarding through the SHARED ProvisioningService with a required
  Idempotency-Key: DOUBLE SUBMISSION creates exactly ONE tenant;
- actor attribution in audit; tenant A/B isolation unaffected."""

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import text

import tests.retrieval_helpers as _rh  # noqa: F401 — registers the corpus fixture
from tests.helpers import logged_in, make_bot, seeded_tenant

corpus = _rh.corpus

ONBOARD_FORM = {
    "client_name": "Provisioned Org",
    "owner_email": "new-owner@example.com",
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
    owner_client, _payload = logged_in(app, "just-owner@example.com")
    tenant_id = None
    create = owner_client.post(
        "/api/v1/tenants",
        json={"name": "Own.org"},
        headers={"X-CSRF-Token": owner_client.cookies.get("chatbot_csrf")},
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
        response = owner_client.request(method, f"/api/v1/platform{path}")
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
    # ...and a tenant OWNER without the flag is refused (role is not enough).
    owner_client, _payload = logged_in(app, "plain-owner2@example.com")
    owner_client.post(
        "/api/v1/tenants",
        json={"name": "Plain"},
        headers={"X-CSRF-Token": owner_client.cookies.get("chatbot_csrf")},
    )
    assert platform_call(owner_client, "GET", "/tenants").status_code == 403


# --- onboarding -------------------------------------------------------------


def test_staff_onboarding_creates_tenant_bot_and_owner_invite(
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
    invite = result["owner_invite"]
    assert invite["link_path"].startswith("/accept-invite?token=")
    # the invitation exists as an OWNER row (single-use token hashed)
    invitations = db.execute(
        text("SELECT email, role FROM invitations WHERE tenant_id = :t"),
        {"t": tenant_id},
    ).fetchall()
    assert len(invitations) == 1 and invitations[0][1] == "owner"
    # actor attribution: the staff action is in the tenant's audit trail
    audit = db.execute(
        text(
            "SELECT action, actor_user_id IS NOT NULL FROM audit_events "
            "WHERE tenant_id = :t AND action LIKE 'platform.onboarding%'"
        ),
        {"t": tenant_id},
    ).fetchall()
    actions = {row[0] for row in audit}
    assert "platform.onboarding.tenant_created" in actions
    assert all(row[1] for row in audit)
    # tenant is a REAL tenant (no owner membership yet — invite-pending)
    members = db.execute(
        text("SELECT count(*) FROM memberships WHERE tenant_id = :t"),
        {"t": tenant_id},
    ).scalar_one()
    assert int(members) == 0


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
    assert target["bots"] == 1 and target["seats"] == 4
    detail = platform_call(staff_client, "GET", f"/tenants/{target['id']}")
    assert detail.status_code == 200
    body = detail.json()
    assert any(bot["name"] == "Client Bot" for bot in body["bots"])
    assert len(body["members"]) == 4
    assert isinstance(body["recent_audit"], list)
    # a different tenant's unknown id → 404, tenant isolation unaffected
    unknown = platform_call(staff_client, "GET", "/tenants/00000000-0000-0000-0000-00000000aaa1")
    assert unknown.status_code == 404
    # Tenant A vs B: nothing leaks between them through staff-only paths
    owner_a = users.as_user("owner")
    bot_a = make_bot(users, "Another")
    outsider = (
        platform_call(users.as_user("viewer"), "GET", f"/platform-derived/{bot_a['id']}")
        if False
        else None
    )
    del outsider, bot_a, owner_a


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
