"""#15: tone_and_rules is staff-only on the API (members get 403) and tenant scoped."""

from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session as OrmSession

from tests.helpers import make_bot, seeded_tenant


def _paths(users: Any, bot_id: str) -> tuple[str, str]:
    base = f"/api/v1/tenants/{users.tenant_id}/bots/{bot_id}"
    return base, base + "/tone-and-rules"


def test_staff_round_trip_and_clear(app: FastAPI, db: OrmSession) -> None:
    users = seeded_tenant(app, db)
    try:
        bot_id = str(make_bot(users, "Toned")["id"])
        base, tone_path = _paths(users, bot_id)
        saved = users.call("staff", "PATCH", base, json={"tone_and_rules": "  Warm and brief.  "})
        assert saved.status_code == 200, saved.text
        assert saved.json()["tone_and_rules"] == "Warm and brief."
        assert users.call("staff", "GET", tone_path).json() == {"tone_and_rules": "Warm and brief."}
        assert users.call("staff", "GET", base).json()["tone_and_rules"] == "Warm and brief."
        cleared = users.call("staff", "PATCH", base, json={"tone_and_rules": ""})
        assert cleared.status_code == 200
        assert cleared.json()["tone_and_rules"] is None
    finally:
        users.cleanup()


def test_length_cap_is_enforced(app: FastAPI, db: OrmSession) -> None:
    users = seeded_tenant(app, db)
    try:
        bot_id = str(make_bot(users)["id"])
        base, _ = _paths(users, bot_id)
        ok = users.call("staff", "PATCH", base, json={"tone_and_rules": "x" * 2000})
        assert ok.status_code == 200, ok.text
        too_long = users.call("staff", "PATCH", base, json={"tone_and_rules": "x" * 2001})
        assert too_long.status_code == 422
        fields = too_long.json()["error"]["details"]["fields"]
        assert fields[0]["field"] == "tone_and_rules"
    finally:
        users.cleanup()


def test_members_get_403_on_read_and_write_and_never_see_the_text(
    app: FastAPI, db: OrmSession
) -> None:
    users = seeded_tenant(app, db)
    try:
        bot_id = str(make_bot(users)["id"])
        base, tone_path = _paths(users, bot_id)
        assert (
            users.call("staff", "PATCH", base, json={"tone_and_rules": "Secret tone"}).status_code
            == 200
        )
        for role in ("admin", "editor", "viewer"):
            assert users.call(role, "GET", tone_path).status_code == 403
            assert users.call(role, "PATCH", base, json={"tone_and_rules": "x"}).status_code == 403
            seen = users.call(role, "GET", base)
            assert seen.status_code == 200
            assert seen.json()["tone_and_rules"] is None
            assert "Secret tone" not in seen.text
            listed = users.call(role, "GET", f"/api/v1/tenants/{users.tenant_id}/bots")
            assert "Secret tone" not in listed.text
        # The text did not change.
        assert users.call("staff", "GET", tone_path).json()["tone_and_rules"] == "Secret tone"
    finally:
        users.cleanup()


def test_tenant_b_cannot_reach_tenant_a_tone(app: FastAPI, db: OrmSession) -> None:
    a = seeded_tenant(app, db, prefix="tone-a")
    b = seeded_tenant(app, db, prefix="tone-b")
    try:
        bot_id = str(make_bot(a)["id"])
        # Tenant B's own members: 404 on A's tenant path (hidden resource).
        cross = f"/api/v1/tenants/{a.tenant_id}/bots/{bot_id}/tone-and-rules"
        assert b.call("admin", "GET", cross).status_code == 404
        # B's tenant path with A's bot id: not found.
        wrong = f"/api/v1/tenants/{b.tenant_id}/bots/{bot_id}/tone-and-rules"
        assert b.call("staff", "GET", wrong).status_code == 404
        assert (
            b.call(
                "staff",
                "PATCH",
                wrong.removesuffix("/tone-and-rules"),
                json={"tone_and_rules": "x"},
            ).status_code
            == 404
        )
    finally:
        a.cleanup()
        b.cleanup()


def test_public_widget_config_never_exposes_tone(app: FastAPI, db: OrmSession) -> None:
    users = seeded_tenant(app, db)
    try:
        made = make_bot(users)
        base, _ = _paths(users, str(made["id"]))
        users.call("staff", "PATCH", base, json={"tone_and_rules": "Hidden tone text"})
        response = TestClient(app).get(f"/api/public/v1/widgets/{made['widget_locator']}/config")
        assert response.status_code == 200
        assert "Hidden tone text" not in response.text
        assert "tone" not in response.text
    finally:
        users.cleanup()
