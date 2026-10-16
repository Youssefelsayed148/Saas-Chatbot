"""Shared helpers for endpoint tests: authenticated clients and seeded tenants."""

from typing import Any
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.conftest import csrf_headers  # re-exported for dependent modules

PASSWORD = "Str0ngPass!"


def register(client: TestClient, email: str) -> dict[str, Any]:
    response = client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    assert response.status_code == 201, response.text
    payload: dict[str, Any] = response.json()
    return payload


def logged_in(app: FastAPI, email: str) -> tuple[TestClient, dict[str, Any]]:
    """A fresh authenticated TestClient for one user (registers first)."""
    client = TestClient(app)
    payload = register(client, email)
    return client, payload


def token_of(client: TestClient) -> str:
    token = client.cookies.get("chatbot_csrf")
    assert isinstance(token, str)
    return token


def create_tenant(client: TestClient, name: str = "Acme", slug: str | None = None) -> UUID:
    body: dict[str, Any] = {"name": name}
    if slug:
        body["slug"] = slug
    response = client.post("/api/v1/tenants", json=body, headers=csrf_headers(client))
    assert response.status_code == 201, response.text
    tenant: dict[str, Any] = response.json()
    return UUID(tenant["id"])


class TenantUsers:
    """Three client members plus a separate staff account with no membership."""

    def __init__(
        self,
        app: FastAPI,
        tenant_id: UUID,
        roles: dict[str, str],
        prefix: str,
        existing: dict[str, tuple[TestClient, dict[str, Any]]] | None = None,
    ) -> None:
        self.clients: dict[str, TestClient] = {}
        self.users: dict[str, dict[str, Any]] = {}
        for label in roles:
            if existing and label in existing:
                self.clients[label], self.users[label] = existing[label]
                continue
            email = f"{prefix}-{label}@example.com"
            client, payload = logged_in(app, email)
            self.clients[label] = client
            self.users[label] = payload
        self.tenant_id = tenant_id
        self.roles = roles

    def as_user(self, role: str) -> TestClient:
        return self.clients[role]

    def call(self, role: str, method: str, path: str, **kwargs: Any) -> Any:
        client = self.as_user(role)
        return client.request(method, path, headers=csrf_headers(client), **kwargs)

    def cleanup(self) -> None:
        for client in self.clients.values():
            client.close()


def seeded_tenant(
    app: FastAPI, db: Any, prefix: str = "seed", plan_label: str = "business"
) -> TenantUsers:
    """Create an admin-led tenant, editor/viewer members, and independent staff."""
    admin_client, admin_payload = logged_in(app, f"{prefix}-admin@example.com")
    try:
        tenant_id = create_tenant(admin_client, name=f"Org {prefix}")
    except Exception:
        admin_client.close()
        raise
    roles = {"admin": "admin", "editor": "editor", "viewer": "viewer", "staff": "platform_staff"}
    members = TenantUsers(
        app, tenant_id, roles, prefix, existing={"admin": (admin_client, admin_payload)}
    )
    from sqlalchemy import text

    # Unrelated tests must not trip placeholder quotas; quota tests set their own plan/overrides.
    db.execute(
        text("UPDATE tenants SET plan_label = :plan WHERE id = CAST(:tid AS uuid)"),
        {"plan": plan_label, "tid": str(tenant_id)},
    )
    db.execute(
        text("UPDATE users SET is_platform_staff = true WHERE id = CAST(:uid AS uuid)"),
        {"uid": members.users["staff"]["id"]},
    )
    for role in ("editor", "viewer"):
        db.execute(
            text(
                "INSERT INTO memberships (tenant_id, user_id, role, status, created_at) "
                "VALUES (CAST(:tid AS uuid), CAST(:uid AS uuid), :role, 'active', NOW())"
            ),
            {"tid": str(tenant_id), "uid": members.users[role]["id"], "role": role},
        )
    db.commit()
    return members


def make_bot(users: TenantUsers, name: str = "Bot") -> dict[str, Any]:
    """Insert fixture bots directly; tenant members cannot create bots anymore."""
    import secrets
    from uuid import uuid4

    from sqlalchemy import insert

    from app.db.models import Bot
    from app.db.session import get_engine

    bot = Bot(
        id=uuid4(),
        tenant_id=users.tenant_id,
        name=name,
        status="draft",
        config={},
        widget_locator="w" + secrets.token_hex(16),
    )
    with get_engine().begin() as connection:
        connection.execute(
            insert(Bot).values(
                id=bot.id,
                tenant_id=bot.tenant_id,
                name=bot.name,
                status=bot.status,
                config=bot.config,
                widget_locator=bot.widget_locator,
            )
        )
    return {
        "id": str(bot.id),
        "tenant_id": str(bot.tenant_id),
        "name": bot.name,
        "status": bot.status,
        "config": bot.config,
        "widget_locator": bot.widget_locator,
    }


def make_invitation(
    users: TenantUsers, email: str, role: str = "viewer"
) -> tuple[str, dict[str, Any]]:
    """Create an invitation as admin; return (token, invitation payload)."""
    response = users.call(
        "admin",
        "POST",
        f"/api/v1/tenants/{users.tenant_id}/invitations",
        json={"email": email, "role": role},
    )
    assert response.status_code == 201, response.text
    payload: dict[str, Any] = response.json()
    link = payload["link_path"]
    assert link.startswith("/accept-invite?token=")
    token = link.split("token=", 1)[1]
    return token, payload


def accept_invitation(client: TestClient, token: str) -> Any:
    return client.post(
        "/api/v1/invitations/accept",
        json={"token": token},
        headers=csrf_headers(client),
    )


def audit_actions(db: Any, action: str, tenant_id: UUID | None = None) -> list[dict[str, Any]]:
    from sqlalchemy import text

    if tenant_id is None:
        rows = (
            db.execute(
                text("SELECT * FROM audit_events WHERE action = :action ORDER BY created_at"),
                {"action": action},
            )
            .mappings()
            .all()
        )
    else:
        rows = (
            db.execute(
                text(
                    "SELECT * FROM audit_events WHERE action = :action "
                    "AND tenant_id = CAST(:tid AS uuid) ORDER BY created_at"
                ),
                {"action": action, "tid": str(tenant_id)},
            )
            .mappings()
            .all()
        )
    return [dict(row) for row in rows]


def cleanup_clients(*groups_or_clients: Any) -> None:
    for item in groups_or_clients:
        if isinstance(item, TenantUsers):
            item.cleanup()
        elif isinstance(item, TestClient):
            item.close()


__all__ = [
    "PASSWORD",
    "csrf_headers",
    "TenantUsers",
    "accept_invitation",
    "audit_actions",
    "cleanup_clients",
    "create_tenant",
    "logged_in",
    "make_bot",
    "make_invitation",
    "register",
    "seeded_tenant",
    "token_of",
]
