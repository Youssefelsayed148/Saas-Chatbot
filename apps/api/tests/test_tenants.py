"""P1-03: tenants — create/get, slug validation, hidden-resource 404s."""

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session as OrmSession

from tests.conftest import csrf_headers
from tests.helpers import audit_actions, create_tenant, logged_in, make_bot


def test_create_tenant_makes_creator_owner(app: Any, db: OrmSession) -> None:
    client, payload = logged_in(app, "owner-acme@example.com")
    try:
        response = client.post(
            "/api/v1/tenants", json={"name": "Acme Ltd"}, headers=csrf_headers(client)
        )
        assert response.status_code == 201
        body: dict[str, Any] = response.json()
        assert body["name"] == "Acme Ltd"
        assert body["status"] == "active"
        assert body["slug"] == "acme-ltd"
        tenant_id = body["id"]

        me = client.get("/api/v1/auth/me").json()
        roles = {m["tenant_id"]: m["role"] for m in me["memberships"]}
        assert roles[tenant_id] == "owner"

        # Exactly one membership row for this user and it is the owner.
        rows = (
            db.execute(
                __import__("sqlalchemy").text(
                    "SELECT role FROM memberships WHERE user_id = CAST(:uid AS uuid)"
                ),
                {"uid": payload["id"]},
            )
            .scalars()
            .all()
        )
        assert rows == ["owner"]

        audits = audit_actions(db, "tenant.created")
        assert len(audits) == 1
        assert audits[0]["tenant_id"] == __import__("uuid").UUID(tenant_id)
    finally:
        client.close()


def test_slug_conflicts_get_a_unique_suffix(app: Any) -> None:
    first_client, _ = logged_in(app, "slug-first@example.com")
    second_client, _ = logged_in(app, "slug-second@example.com")
    try:
        first_id = create_tenant(first_client, name="Super Org")
        second_id = create_tenant(second_client, name="Super Org")
        assert first_id != second_id
        first = first_client.get(f"/api/v1/tenants/{first_id}").json()
        second = second_client.get(f"/api/v1/tenants/{second_id}").json()
        assert first["slug"] != second["slug"]
    finally:
        cleanup(first_client, second_client)


def cleanup(*clients: TestClient) -> None:
    for client in clients:
        client.close()


def test_slug_field_validation(app: Any) -> None:
    client, _ = logged_in(app, "slug-bad@example.com")
    try:
        bad_shapes = ["Has Spaces", "UPPER", "double--dash?", "trailing-"]
        for slug in bad_shapes:
            assert (
                client.post(
                    "/api/v1/tenants",
                    json={"name": "Acme", "slug": slug},
                    headers=csrf_headers(client),
                ).status_code
                == 422
            )
        assert (
            client.post(
                "/api/v1/tenants", json={"name": "", "slug": None}, headers=csrf_headers(client)
            ).status_code
            == 422
        )
    finally:
        client.close()


def test_get_tenant_member_only(app: Any, db: OrmSession) -> None:
    member, _ = logged_in(app, "member-get@example.com")
    outsider, _ = logged_in(app, "outsider-get@example.com")
    try:
        tenant_id = create_tenant(member, name="Hidden Org")
        assert member.get(f"/api/v1/tenants/{tenant_id}").status_code == 200

        hidden = outsider.get(f"/api/v1/tenants/{tenant_id}")
        assert hidden.status_code == 404
        assert hidden.json()["error"]["code"] == "NOT_FOUND"

        unknown = outsider.get("/api/v1/tenants/00000000-0000-0000-0000-000000000001")
        assert unknown.status_code == 404
    finally:
        cleanup(member, outsider)


def test_create_tenant_requires_session_and_csrf(app: Any) -> None:
    with TestClient(app) as anonymous:
        response = anonymous.post("/api/v1/tenants", json={"name": "Nope"})
        assert response.status_code == 401

    client, _ = logged_in(app, "csrf-tenant@example.com")
    try:
        response = client.post("/api/v1/tenants", json={"name": "Nope"})  # no CSRF header
        assert response.status_code == 403
    finally:
        client.close()


def test_bots_of_other_tenant_are_hidden_on_every_endpoint(app: Any, db: OrmSession) -> None:
    member, _ = logged_in(app, "member-hide@example.com")
    outsider, _ = logged_in(app, "outsider-hide@example.com")
    try:
        tenant_a = create_tenant(member, name="Tenant A")
        bot = make_bot(
            type(
                "U",
                (),
                {
                    "clients": {"owner": member},
                    "users": {},
                    "tenant_id": tenant_a,
                    "roles": {},
                    "as_user": lambda self, r: self.clients[r],
                    "call": lambda self, r, m, p, **kw: member.request(
                        m, p, headers=csrf_headers(member), **kw
                    ),
                },
            )(),
            name="A Bot",
        )
        bot_id = bot["id"]

        guessed = f"/api/v1/tenants/{tenant_a}/bots"
        assert outsider.get(guessed).status_code == 404
        assert (
            outsider.post(guessed, json={"name": "X"}, headers=csrf_headers(outsider)).status_code
            == 404
        )
        single = f"{guessed}/{bot_id}"
        assert outsider.get(single).status_code == 404
        assert (
            outsider.patch(single, json={"name": "Y"}, headers=csrf_headers(outsider)).status_code
            == 404
        )
        assert outsider.delete(single, headers=csrf_headers(outsider)).status_code == 404
        assert outsider.get(f"/api/v1/tenants/{tenant_a}").status_code == 404

        # Team-management endpoints of a foreign tenant are hidden the same way.
        tenant_url = f"/api/v1/tenants/{tenant_a}"
        assert outsider.get(tenant_url + "/invitations").status_code == 404
        assert (
            outsider.post(
                tenant_url + "/invitations",
                json={"email": "spy@example.com", "role": "viewer"},
                headers=csrf_headers(outsider),
            ).status_code
            == 404
        )
        assert outsider.get(tenant_url + "/members").status_code == 404
        assert (
            outsider.post(
                tenant_url + "/invitations/00000000-0000-0000-0000-000000000002/resend",
                headers=csrf_headers(outsider),
            ).status_code
            == 404
        )
        assert (
            outsider.delete(
                tenant_url + "/invitations/00000000-0000-0000-0000-000000000002",
                headers=csrf_headers(outsider),
            ).status_code
            == 404
        )
        assert (
            outsider.delete(
                tenant_url + "/members/00000000-0000-0000-0000-000000000003",
                headers=csrf_headers(outsider),
            ).status_code
            == 404
        )

        # Member still sees the bot; nothing leaked through the 404s.
        assert member.get(single).status_code == 200
    finally:
        cleanup(member, outsider)
