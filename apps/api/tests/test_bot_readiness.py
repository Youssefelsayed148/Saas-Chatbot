"""#26: the readiness checklist reflects the bot's real state (staff only, tenant scoped)."""

from typing import Any
from uuid import UUID

from fastapi import FastAPI
from sqlalchemy.orm import Session as OrmSession

from app.bots.service import readiness_items
from app.core.config import Settings
from app.db.models import Bot
from tests.helpers import make_bot, seeded_tenant


def _bot(config: dict[str, Any], *, published: bool = False, tier: str = "standard") -> Bot:
    return Bot(
        name="B",
        config=config,
        tier=tier,
        published_revision_id=UUID(int=1) if published else None,
    )


STUB = Settings.model_construct(chat_stub_model=True)  # a model is configured


def _status(bot: Bot) -> dict[str, str]:
    return {item.id: item.status for item in readiness_items(bot, STUB)}


def test_checklist_states_follow_the_config() -> None:
    empty = _status(_bot({}))
    assert empty == {
        "support_contact": "todo",
        "welcome_message": "todo",
        "allowed_domains": "warning",
        "knowledge_published": "todo",
        "tier": "ok",
        "model_provider": "ok",
    }
    full = _status(
        _bot(
            {
                "support_phone": " +201000000000 ",
                "welcome_message": {"en": "Hi", "ar": ""},
                "allowed_domains": ["example.com"],
            },
            published=True,
            tier="premium",
        )
    )
    assert set(full.values()) == {"ok"}
    blank = _status(_bot({"support_email": "  ", "welcome_message": {"en": " "}}))
    assert blank["support_contact"] == "todo" and blank["welcome_message"] == "todo"


def test_endpoint_is_staff_only_and_tenant_scoped(app: FastAPI, db: OrmSession) -> None:
    a = seeded_tenant(app, db, prefix="ready-a")
    b = seeded_tenant(app, db, prefix="ready-b")
    try:
        bot_id = str(make_bot(a)["id"])
        path = f"/api/v1/tenants/{a.tenant_id}/bots/{bot_id}/readiness"
        for role in ("admin", "editor", "viewer"):
            assert a.call(role, "GET", path).status_code == 403
        assert b.call("admin", "GET", path).status_code == 404
        own_path = f"/api/v1/tenants/{b.tenant_id}/bots/{bot_id}/readiness"
        assert b.call("staff", "GET", own_path).status_code == 404
        before = a.call("staff", "GET", path)
        assert before.status_code == 200, before.text
        assert before.json()["ready"] is False
        patched = a.call(
            "staff",
            "PATCH",
            f"/api/v1/tenants/{a.tenant_id}/bots/{bot_id}",
            json={
                "config": {
                    "support_email": "help@example.com",
                    "welcome_message": {"en": "Hello"},
                    "allowed_domains": ["example.com"],
                }
            },
        )
        assert patched.status_code == 200
        after = {i["id"]: i["status"] for i in a.call("staff", "GET", path).json()["items"]}
        assert after["knowledge_published"] == "todo"
        assert after["support_contact"] == after["welcome_message"] == "ok"
        assert after["allowed_domains"] == "ok"
    finally:
        a.cleanup()
        b.cleanup()
