"""P7-03 registration provisions one free tenant and bot idempotently."""

from concurrent.futures import ThreadPoolExecutor
from typing import Any
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import AuditEvent, Bot, Membership, ProvisioningRequest, Tenant
from tests.conftest import build_test_settings
from tests.helpers import PASSWORD, csrf_headers, logged_in


def test_self_service_signup_retries_create_one_tenant_and_bot(app: Any, db: Any) -> None:
    email = "p7-signup@example.com"
    client_a, user = logged_in(app, email)
    client_b = TestClient(app)
    login = client_b.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
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
    assert results[0]["admin_invite"] is None
    db.expire_all()
    tenant_id = results[0]["tenant_id"]
    parsed_tenant_id = UUID(tenant_id)
    parsed_user_id = UUID(user["id"])
    assert (
        db.execute(select(Tenant).where(Tenant.id == parsed_tenant_id)).scalar_one().plan_label
        == "free"
    )
    assert (
        len(db.execute(select(Bot).where(Bot.tenant_id == parsed_tenant_id)).scalars().all()) == 1
    )
    assert (
        len(
            db.execute(
                select(ProvisioningRequest).where(
                    ProvisioningRequest.mode == "self_service",
                    ProvisioningRequest.actor_user_id == parsed_user_id,
                )
            )
            .scalars()
            .all()
        )
        == 1
    )
    assert (
        db.execute(
            select(Membership).where(
                Membership.tenant_id == parsed_tenant_id, Membership.user_id == parsed_user_id
            )
        )
        .scalar_one()
        .role
        == "admin"
    )

    actions = db.scalars(
        select(AuditEvent.action).where(AuditEvent.tenant_id == parsed_tenant_id)
    ).all()
    assert "self_service.admin_assigned" in actions
    assert "self_service.owner_assigned" not in actions

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


def test_signup_disabled_blocks_org_and_provisioning_without_creating_data(
    app: Any, db: Any
) -> None:
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


def test_registration_when_signup_off_requires_valid_matching_active_invite(
    app: Any, db: Any
) -> None:
    from datetime import UTC, datetime, timedelta

    from app.db.models import Invitation, User
    from tests.helpers import make_invitation, seeded_tenant

    users = seeded_tenant(app, db, prefix="signup-invite")
    token, invitation = make_invitation(users, "invited@example.com", "admin")
    # Preserve the legacy pre-S2 invitation registration contract. New invites
    # require existing users; this fixture represents an outstanding old invite.
    from sqlalchemy import delete

    db.execute(delete(User).where(User.email == "invited@example.com"))
    db.commit()
    app.dependency_overrides[get_settings] = lambda: build_test_settings(self_serve_signup=False)
    guest = TestClient(app)
    try:
        body = {"email": "invited@example.com", "password": PASSWORD}
        for extra in [{}, {"invite_token": "invalid-token-123456"}]:
            assert guest.post("/api/v1/auth/register", json={**body, **extra}).status_code == 403
        assert (
            guest.post(
                "/api/v1/auth/register",
                json={**body, "email": "other@example.com", "invite_token": token},
            ).status_code
            == 403
        )
        row = db.get(Invitation, UUID(invitation["id"]))
        row.revoked_at = datetime.now(UTC)
        db.commit()
        assert (
            guest.post("/api/v1/auth/register", json={**body, "invite_token": token}).status_code
            == 403
        )
        row.revoked_at = None
        row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
        assert (
            guest.post("/api/v1/auth/register", json={**body, "invite_token": token}).status_code
            == 403
        )
        assert db.scalar(select(User).where(User.email == body["email"])) is None
        row.expires_at = datetime.now(UTC) + timedelta(days=1)
        db.commit()
        registered = guest.post("/api/v1/auth/register", json={**body, "invite_token": token})
        assert registered.status_code == 201, registered.text
        accepted = guest.post(
            "/api/v1/invitations/accept", json={"token": token}, headers=csrf_headers(guest)
        )
        assert accepted.status_code == 200
        assert accepted.json()["memberships"][0]["role"] == "admin"
        assert (
            guest.post("/api/v1/auth/register", json={**body, "invite_token": token}).status_code
            == 403
        )
    finally:
        guest.close()
        users.cleanup()


def test_register_without_invite_token_is_invitation_required_when_signup_off(
    app: Any, db: Any
) -> None:
    """S6 contract check: with self-service signup OFF, POST /auth/register
    without a valid invite token returns 403 INVITATION_REQUIRED and creates
    no account (the message must stay safe, with no internals)."""
    from app.db.models import User

    app.dependency_overrides[get_settings] = lambda: build_test_settings(self_serve_signup=False)
    guest = TestClient(app)
    try:
        response = guest.post(
            "/api/v1/auth/register",
            json={"email": "ghost@example.com", "password": PASSWORD},
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "INVITATION_REQUIRED"
        assert db.execute(select(User)).scalars().all() == []
    finally:
        guest.close()


def test_default_config_keeps_registration_closed(app: Any, db: Any, monkeypatch: Any) -> None:
    """ADR-021 / ADR-022 default-config guard: with NO override of
    ``self_serve_signup`` (the shipped default), registration is closed.

    Unlike the tests above, the flag is not forced off by hand: the settings are
    built from the real ``Settings`` defaults, ignoring any developer ``.env``
    file and any ``SELF_SERVE_SIGNUP`` environment variable.
    """
    from app.core.config import Settings
    from app.db.models import User

    monkeypatch.delenv("SELF_SERVE_SIGNUP", raising=False)
    default_settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert default_settings.self_serve_signup is False

    app.dependency_overrides[get_settings] = lambda: default_settings
    guest = TestClient(app)
    try:
        config = guest.get("/api/v1/auth/config")
        assert config.status_code == 200
        assert config.json() == {"self_serve_signup": False}
        response = guest.post(
            "/api/v1/auth/register",
            json={"email": "default-closed@example.com", "password": PASSWORD},
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "INVITATION_REQUIRED"
        assert db.execute(select(User)).scalars().all() == []
    finally:
        guest.close()
