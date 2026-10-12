"""P1-03: bots CRUD, validation and soft-archive behaviour."""

from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session as OrmSession

from tests.helpers import create_tenant, logged_in, seeded_tenant


def test_bot_create_list_get_update_archive(app: Any, db: OrmSession) -> None:
    users = seeded_tenant(app, db)
    try:
        tenant_id = users.tenant_id
        create = users.call(
            "owner", "POST", f"/api/v1/tenants/{tenant_id}/bots", json={"name": "First"}
        )
        assert create.status_code == 201
        bot: dict[str, Any] = create.json()
        assert bot["status"] == "draft"
        assert bot["config"] == {}

        listing = users.call("viewer", "GET", f"/api/v1/tenants/{tenant_id}/bots")
        assert listing.status_code == 200
        assert [row["id"] for row in listing.json()] == [bot["id"]]

        single = users.call("editor", "GET", f"/api/v1/tenants/{tenant_id}/bots/{bot['id']}")
        assert single.status_code == 200
        assert single.json()["name"] == "First"

        patch = users.call(
            "editor",
            "PATCH",
            f"/api/v1/tenants/{tenant_id}/bots/{bot['id']}",
            json={"name": "First Renamed", "config": {"default_language": "ar"}},
        )
        assert patch.status_code == 200
        assert patch.json()["name"] == "First Renamed"
        assert patch.json()["config"]["default_language"] == "ar"

        archive = users.call("owner", "DELETE", f"/api/v1/tenants/{tenant_id}/bots/{bot['id']}")
        assert archive.status_code == 200
        assert archive.json()["status"] == "archived"

        # Soft archive: config and row survive; default list hides the bot.
        assert users.call("viewer", "GET", f"/api/v1/tenants/{tenant_id}/bots").json() == []
        with_archived = users.call(
            "viewer",
            "GET",
            f"/api/v1/tenants/{tenant_id}/bots",
            params={"include_archived": "true"},
        )
        assert [row["id"] for row in with_archived.json()] == [bot["id"]]
        direct = users.call("editor", "GET", f"/api/v1/tenants/{tenant_id}/bots/{bot['id']}")
        assert direct.status_code == 200
        assert direct.json()["config"]["default_language"] == "ar"

        # Editing an archived bot is a conflict.
        assert (
            users.call(
                "editor",
                "PATCH",
                f"/api/v1/tenants/{tenant_id}/bots/{bot['id']}",
                json={"name": "No"},
            ).status_code
            == 409
        )

        # Archiving twice is idempotent.
        assert (
            users.call(
                "owner", "DELETE", f"/api/v1/tenants/{tenant_id}/bots/{bot['id']}"
            ).status_code
            == 200
        )
    finally:
        users.cleanup()


def test_bot_config_validation(app: Any, db: OrmSession) -> None:
    users = seeded_tenant(app, db)
    try:
        bot = users.call(
            "owner",
            "POST",
            f"/api/v1/tenants/{users.tenant_id}/bots",
            json={"name": "Cfg"},
        ).json()
        url = f"/api/v1/tenants/{users.tenant_id}/bots/{bot['id']}"

        assert (
            users.call("owner", "PATCH", url, json={"config": {"colour": "red"}}).status_code == 422
        )
        assert (
            users.call(
                "owner", "PATCH", url, json={"config": {"default_language": "fr"}}
            ).status_code
            == 422
        )
        assert (
            users.call(
                "owner", "PATCH", url, json={"config": {"allowed_domains": ["not a domain"]}}
            ).status_code
            == 422
        )
        assert (
            users.call(
                "owner",
                "PATCH",
                url,
                json={"config": {"welcome_message": {"de": "hi"}}},
            ).status_code
            == 422
        )
        assert users.call("owner", "PATCH", url, json={"unknown_field": 1}).status_code == 422

        valid = users.call(
            "owner",
            "PATCH",
            url,
            json={
                "config": {
                    "assistant_name": "Mib",
                    "colour": "#1a2b3c",
                    "allowed_domains": ["Example.COM", "support.example.com"],
                }
            },
        )
        assert valid.status_code == 200
        config = valid.json()["config"]
        assert config["colour"] == "#1a2b3c"
        assert config["allowed_domains"] == ["example.com", "support.example.com"]

        # Empty name cannot be saved.
        assert (
            users.call(
                "owner", "POST", f"/api/v1/tenants/{users.tenant_id}/bots", json={"name": ""}
            ).status_code
            == 422
        )
    finally:
        users.cleanup()


def test_unknown_bot_id_is_404(app: Any, db: OrmSession) -> None:
    users = seeded_tenant(app, db)
    try:
        ghost = uuid4()
        url = f"/api/v1/tenants/{users.tenant_id}/bots/{ghost}"
        assert users.call("owner", "GET", url).status_code == 404
        assert users.call("owner", "PATCH", url, json={"name": "x"}).status_code == 404
        assert users.call("owner", "DELETE", url).status_code == 404
    finally:
        users.cleanup()


def test_bot_write_requires_csrf(app: Any, db: OrmSession) -> None:
    client, _ = logged_in(app, "bot-csrf@example.com")
    try:
        tenant_id = create_tenant(client)
        response = client.post(f"/api/v1/tenants/{tenant_id}/bots", json={"name": "X"})
        assert response.status_code == 403
    finally:
        if isinstance(client, TestClient):
            client.close()
