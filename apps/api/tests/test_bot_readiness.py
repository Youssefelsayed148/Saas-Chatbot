"""#26: the readiness checklist reflects the bot's real state (staff only, tenant scoped)."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from fastapi import FastAPI
from sqlalchemy.orm import Session as OrmSession

from app.bots.service import model_reachability, readiness_items
from app.core.config import Settings
from app.db.models import Bot, UsageEvent
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


# --- "Model reachable" (R3c-5): read from recorded traces, never a live call ---------


def failed_turn(code: str | None, model: str = "gpt-gone") -> dict[str, Any]:
    attempt = {"attempt": 1, "model": model, "outcome": "failed", "error_code": code}
    return {
        "model": model,
        "provider_error": {"status": "failed", "model": model, "attempts": [attempt]},
    }


GOOD_TURN: dict[str, Any] = {"model": "gpt-5.4-nano"}


def test_model_reachable_warns_on_a_setup_error_and_names_it() -> None:
    item = model_reachability([failed_turn("model_not_found"), GOOD_TURN])
    assert item.id == "model_reachable" and item.status == "warning"
    assert "model_not_found" in item.detail and "gpt-gone" in item.detail
    for code in ("invalid_api_key", "insufficient_quota", "payment_required"):
        assert model_reachability([failed_turn(code)]).status == "warning"


def test_model_reachable_warns_when_every_recent_call_failed() -> None:
    item = model_reachability([failed_turn(None), failed_turn("rate_limited")])
    assert item.status == "warning" and "all failed" in item.detail


def test_model_reachable_is_ok_after_a_clean_call_and_without_history() -> None:
    # The newest call is clean: the older failure has been fixed since.
    assert model_reachability([GOOD_TURN, failed_turn("model_not_found")]).status == "ok"
    assert model_reachability([]).status == "ok"
    # Turns that never called a model (routing, no evidence) are not evidence either way.
    assert model_reachability([{"model": None}, {"model": None}]).status == "ok"
    # A turn answered by a later model in the chain still shows the dead head model.
    masked: dict[str, object] = {
        "model": "b:free",
        "provider_attempts": [
            {"attempt": 1, "model": "a:free", "outcome": "failed", "error_code": "model_not_found"},
            {"attempt": 2, "model": "b:free", "outcome": "ok", "error_code": None},
        ],
    }
    assert model_reachability([masked]).status == "warning"
    # Not-configured is the other item's job.
    unavailable: dict[str, object] = {"provider_error": {"status": "not_configured", "model": None}}
    assert model_reachability([unavailable]).status == "ok"


def test_only_the_last_five_model_calls_count() -> None:
    old_failure = failed_turn("model_not_found")
    five_failures = [failed_turn(None)] * 5
    assert "model_not_found" not in model_reachability([*five_failures, old_failure]).detail


def test_endpoint_item_reads_recorded_traces_for_this_bot_only(
    app: FastAPI, db: OrmSession
) -> None:
    a = seeded_tenant(app, db, prefix="reach-a")
    b = seeded_tenant(app, db, prefix="reach-b")
    try:
        bot_id = str(make_bot(a)["id"])
        other_id = str(make_bot(b)["id"])
        path = f"/api/v1/tenants/{a.tenant_id}/bots/{bot_id}/readiness"

        def item() -> dict[str, str]:
            body = a.call("staff", "GET", path).json()
            return next(i for i in body["items"] if i["id"] == "model_reachable")

        assert item()["status"] == "ok"  # nothing recorded yet
        now = datetime.now(UTC)
        for tenant, bot, trace in (
            (a.tenant_id, bot_id, failed_turn("model_not_found")),
            (b.tenant_id, other_id, GOOD_TURN),
        ):
            db.add(
                UsageEvent(
                    id=uuid4(),
                    tenant_id=tenant,
                    bot_id=UUID(bot),
                    kind="message",
                    external_key=f"message:{uuid4()}",
                    payload={"rag_trace": trace},
                    created_at=now - timedelta(seconds=1),
                )
            )
        db.commit()
        assert item()["status"] == "warning"
        assert "model_not_found" in item()["detail"]
        # The other tenant's clean call never hides this bot's failure.
        assert (
            next(
                i
                for i in b.call(
                    "staff", "GET", f"/api/v1/tenants/{b.tenant_id}/bots/{other_id}/readiness"
                ).json()["items"]
                if i["id"] == "model_reachable"
            )["status"]
            == "ok"
        )
    finally:
        a.cleanup()
        b.cleanup()
