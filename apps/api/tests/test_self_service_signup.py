"""P7-03 registration provisions one free tenant and bot idempotently."""

from concurrent.futures import ThreadPoolExecutor
from typing import Any
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import select
from app.core.config import get_settings

from app.db.models import Bot, Membership, ProvisioningRequest, Tenant
from tests.helpers import PASSWORD, csrf_headers, logged_in
from tests.conftest import build_test_settings


def test_self_service_signup_retries_create_one_tenant_and_bot(app: Any, db: Any) -> None:
    email = "p7-signup@example.com"
    client_a, user = logged_in(app, email)
    client_b = TestClient(app)
    login = client_b.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    )
    assert login.status_code == 200, login.text
    body = {"client_name": "Example Co", "bot_name": "Website bot"}

    def signup(client: TestClient) -> Any:
        return client.post(
            "/api/v1/provisioning/self-service",
            json=body,
            headers=csrf_headers(client),
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(signup, (client_a, client_b)))
    assert [response.status_code for response in responses] == [201, 201]
    results = [response.json()["result"] for response in responses]
    assert results[0]["tenant_id"] == results[1]["tenant_id"]
    assert results[0]["bot_id"] == results[1]["bot_id"]
    assert results[0]["owner_invite"] is None
    db.expire_all()
    tenant_id = results[0]["tenant_id"]
    parsed_tenant_id = UUID(tenant_id)
    parsed_user_id = UUID(user["id"])
    assert db.execute(select(Tenant).where(Tenant.id == parsed_tenant_id)).scalar_one().plan_label == "free"
    assert len(db.execute(select(Bot).where(Bot.tenant_id == parsed_tenant_id)).scalars().all()) == 1
    assert len(
        db.execute(
            select(ProvisioningRequest).where(
                ProvisioningRequest.mode == "self_service",
                ProvisioningRequest.actor_user_id == parsed_user_id,
            )
        ).scalars().all()
    ) == 1
    assert db.execute(
        select(Membership).where(
            Membership.tenant_id == parsed_tenant_id, Membership.user_id == parsed_user_id
        )
    ).scalar_one().role == "owner"

    mismatch = client_a.post(
        "/api/v1/provisioning/self-service",
        json={"client_name": "Different name", "bot_name": "Website bot"},
        headers=csrf_headers(client_a),
    )
    assert mismatch.status_code == 409
    client_a.close()
    client_b.close()


def test_self_service_bot_has_widget_locator_and_public_config_is_reachable(
    app: Any, db: Any
) -> None:
    client, _ = logged_in(app, "p7-locator@example.com")
    response = client.post(
        "/api/v1/provisioning/self-service",
        json={"client_name": "Locator Co", "bot_name": "Website bot"},
        headers=csrf_headers(client),
    )
    assert response.status_code == 201, response.text
    bot_id = UUID(response.json()["result"]["bot_id"])
    db.expire_all()
    locator = db.execute(select(Bot.widget_locator).where(Bot.id == bot_id)).scalar_one()
    assert locator
    public = TestClient(app).get(f"/api/public/v1/widgets/{locator}/config")
    assert public.status_code == 200, public.text
    client.close()


def test_signup_disabled_blocks_org_and_provisioning_without_creating_data(app: Any, db: Any) -> None:
    client, user = logged_in(app, "signup-disabled@example.com")
    app.dependency_overrides[get_settings] = lambda: build_test_settings(self_serve_signup=False)
    try:
        assert client.get("/api/v1/auth/config").json() == {"self_serve_signup": False}
        org = client.post(
            "/api/v1/tenants", json={"name": "Forbidden"}, headers=csrf_headers(client)
        )
        provision = client.post(
            "/api/v1/provisioning/self-service",
            json={"client_name": "Forbidden", "bot_name": "Forbidden"},
            headers=csrf_headers(client),
        )
        assert org.status_code == 403
        assert provision.status_code == 403
        assert db.execute(select(Tenant)).scalars().all() == []
        assert db.execute(select(Bot)).scalars().all() == []
        assert user["memberships"] == []
    finally:
        client.close()
