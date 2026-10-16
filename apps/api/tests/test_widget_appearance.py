"""P4-03: appearance settings — avatar (public http(s) URL) validated at the
contract layer and exposed in the SAFE public widget config (status
transitions live in test_bot_status, settings UI in the E2E)."""

from typing import Any
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session as OrmSession

import tests.retrieval_helpers as _rh  # noqa: F401 — registers the corpus fixture
from app.core.errors import ApiError
from app.db.models import Bot
from tests.helpers import make_bot

corpus = _rh.corpus


def test_avatar_http_url_saved_and_publicly_exposed(
    app: FastAPI,
    corpus: dict[str, Any],
) -> None:
    users = corpus["users_a"]
    bot = make_bot(users, "Styled")
    bot_id = str(bot["id"])
    saved = users.call(
        "staff",
        "PATCH",
        f"/api/v1/tenants/{users.tenant_id}/bots/{bot_id}",
        json={
            "config": {
                "avatar": "https://cdn.example.com/avatar.png",
                "colour": "#1f7a5c",
                "position": "left",
            }
        },
    )
    assert saved.status_code == 200, saved.text
    payload = saved.json()
    assert payload["config"]["avatar"] == "https://cdn.example.com/avatar.png"
    locator = payload["widget_locator"]
    assert locator

    client = TestClient(app)
    public_config = client.get(f"/api/public/v1/widgets/{locator}/config")
    assert public_config.status_code == 200
    config = public_config.json()["config"]
    assert config["avatar"] == "https://cdn.example.com/avatar.png"
    assert config["position"] == "left"
    assert config["colour"] == "#1f7a5c"


def test_avatar_rejects_non_http_values(corpus: dict[str, Any]) -> None:
    users = corpus["users_a"]
    bot = make_bot(users, "Avatar Guard")
    bot_id = str(bot["id"])
    for bad in ("data:text/html,<script>", "javascript:alert(1)", "not-a-url"):
        response = users.call(
            "staff",
            "PATCH",
            f"/api/v1/tenants/{users.tenant_id}/bots/{bot_id}",
            json={"config": {"avatar": bad}},
        )
        assert response.status_code == 422, (bad, response.text)


def test_bot_lookup_by_widget_locator(db: OrmSession, corpus: dict[str, Any]) -> None:
    """The locator resolves exactly one bot (uniqueness at the DB level)."""
    users = corpus["users_a"]
    bot = make_bot(users, "Locatable")
    row = db.get(Bot, UUID(str(bot["id"])))
    assert row is not None and row.widget_locator
    from app.widget.service import bot_by_locator

    resolved = bot_by_locator(db, str(row.widget_locator))
    assert resolved.id == row.id
    with pytest.raises(ApiError):
        bot_by_locator(db, "no-such-locator-value")
