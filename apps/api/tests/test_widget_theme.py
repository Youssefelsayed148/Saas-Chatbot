"""#14: widget theme slots are server-validated, round-trip and reach widget_config."""

import re
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.orm import Session as OrmSession

from app.bots.schemas import THEME_PRESET_IDS, THEME_SLOTS, BotConfig, WidgetTheme
from app.db.models import Bot
from app.widget.service import widget_config
from tests.helpers import make_bot, seeded_tenant

WEB_THEME = Path(__file__).resolve().parents[2] / "web" / "lib" / "widget-theme.ts"


def test_slots_accept_hex_and_normalize() -> None:
    theme = WidgetTheme(header="#ABC", send_button="#1F7A5C", text="#ffffff")
    assert theme.header == "#aabbcc"
    assert theme.send_button == "#1f7a5c"
    assert theme.bot_bubble is None


@pytest.mark.parametrize(
    "bad", ["red", "#12", "#12345", "#1234567", "rgb(1,2,3)", "url(x)", "#ggg", "", "#fff; x:y"]
)
def test_slots_reject_non_hex(bad: str) -> None:
    for slot in THEME_SLOTS:
        with pytest.raises(ValidationError):
            WidgetTheme(**{slot: bad})


def test_unknown_preset_and_extra_keys_rejected() -> None:
    with pytest.raises(ValidationError):
        WidgetTheme(preset="neon")
    with pytest.raises(ValidationError):
        WidgetTheme(**{"header": "#fff", "background": "#000"})
    assert WidgetTheme(preset="midnight-glass").preset == "midnight-glass"


def test_preset_ids_match_the_web_presets() -> None:
    source = WEB_THEME.read_text(encoding="utf-8")
    block = source[source.index("export const THEME_PRESETS") : source.index("PALETTE")]
    web_ids = set(re.findall(r'^\s{4}id: "([a-z-]+)",', block, flags=re.MULTILINE))
    assert web_ids == set(THEME_PRESET_IDS) - {"custom"}


def test_widget_config_default_payload_has_no_theme() -> None:
    bot = Bot(name="B", config={"colour": "#1f7a5c"})
    assert "theme" not in widget_config(bot)


def test_widget_config_returns_only_valid_theme_values() -> None:
    bot = Bot(
        name="B",
        config={
            "theme": {
                "preset": "ocean",
                "header": "#0B5EA8",
                "text": "not-a-colour",
                "bot_bubble": "#eaf3fb",
                "unknown": "#000000",
            }
        },
    )
    assert widget_config(bot)["theme"] == {
        "preset": "ocean",
        "header": "#0b5ea8",
        "bot_bubble": "#eaf3fb",
    }


def test_bot_config_accepts_nested_theme() -> None:
    config = BotConfig.model_validate({"theme": {"preset": "classic"}})
    assert config.theme is not None and config.theme.preset == "classic"


def test_theme_round_trips_through_the_api_and_one_422_saves_nothing(
    app: FastAPI, db: OrmSession
) -> None:
    users = seeded_tenant(app, db)
    try:
        made = make_bot(users, "Themed")
        base = f"/api/v1/tenants/{users.tenant_id}/bots/{made['id']}"
        theme = {
            "preset": "midnight-glass",
            "header": "#1e1b4b",
            "send_button": "#818cf8",
            "user_bubble": "#4f46e5",
            "bot_bubble": "#1e293b",
            "text": "#f1f5f9",
            "launcher": "#4f46e5",
        }
        saved = users.call("staff", "PATCH", base, json={"config": {"theme": theme}})
        assert saved.status_code == 200, saved.text
        assert saved.json()["config"]["theme"] == theme
        public = TestClient(app).get(f"/api/public/v1/widgets/{made['widget_locator']}/config")
        assert public.json()["config"]["theme"] == theme

        # Resetting to the default look replaces the whole theme (no stale slots).
        reset = users.call(
            "staff", "PATCH", base, json={"config": {"theme": {"preset": "classic"}}}
        )
        assert reset.json()["config"]["theme"] == {"preset": "classic"}

        # One invalid slot is a 422 with a field path and nothing else is saved.
        bad = users.call(
            "staff",
            "PATCH",
            base,
            json={
                "name": "Renamed",
                "config": {"assistant_name": "Changed", "theme": {"header": "red"}},
            },
        )
        assert bad.status_code == 422
        fields = bad.json()["error"]["details"]["fields"]
        assert fields[0]["field"] == "config.theme.header"
        assert '"red"' not in bad.text
        after = users.call("staff", "GET", base).json()
        assert after["name"] == "Themed"
        assert after["config"]["theme"] == {"preset": "classic"}
        assert "assistant_name" not in after["config"]

        # Members cannot write a theme (staff-only PATCH).
        denied = users.call("admin", "PATCH", base, json={"config": {"theme": theme}})
        assert denied.status_code == 403
    finally:
        users.cleanup()
