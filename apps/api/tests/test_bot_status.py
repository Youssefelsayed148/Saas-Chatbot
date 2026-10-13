"""P4-01 addendum: bot status lifecycle transitions (docs/04 statuses).

The widget channel needs draft→active, active↔paused; archiving stays
DELETE-only (the P1 soft-archive contract). Role rules follow docs/06
(viewer cannot mutate) and transitions are audited."""

from typing import Any

import tests.retrieval_helpers as _rh  # noqa: F401 — registers the corpus fixture
from tests.helpers import audit_actions, make_bot

corpus = _rh.corpus


def _path(corpus: dict[str, Any], bot_id: str) -> str:
    return f"/api/v1/tenants/{corpus['users_a'].tenant_id}/bots/{bot_id}"


def test_draft_bot_activates(corpus: dict[str, Any], db: Any) -> None:
    users = corpus["users_a"]
    bot = make_bot(users, "To Activate")
    bot_id = str(bot["id"])
    response = users.call("owner", "PATCH", _path(corpus, bot_id), json={"status": "active"})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "active"
    transitions = audit_actions(db, "bot.updated", users.tenant_id)
    assert any(
        row["metadata_json"].get("fields") == ["status"] and row["target_id"] == bot_id
        for row in transitions
    )


def test_active_bot_pauses_and_resumes(corpus: dict[str, Any]) -> None:
    users = corpus["users_a"]
    bot = make_bot(users, "Pausable")
    bot_id = str(bot["id"])
    users.call("owner", "PATCH", _path(corpus, bot_id), json={"status": "active"})
    paused = users.call("owner", "PATCH", _path(corpus, bot_id), json={"status": "paused"})
    assert paused.json()["status"] == "paused"
    resumed = users.call("owner", "PATCH", _path(corpus, bot_id), json={"status": "active"})
    assert resumed.json()["status"] == "active"


def test_invalid_transitions_are_rejected(corpus: dict[str, Any]) -> None:
    users = corpus["users_a"]
    bot = make_bot(users, "No State Jumps")
    bot_id = str(bot["id"])
    draft_pause = users.call("owner", "PATCH", _path(corpus, bot_id), json={"status": "paused"})
    assert draft_pause.status_code == 422
    users.call("owner", "PATCH", _path(corpus, bot_id), json={"status": "active"})
    to_archived = users.call("owner", "PATCH", _path(corpus, bot_id), json={"status": "archived"})
    assert to_archived.status_code == 422  # archiving stays DELETE-only
    unknown = users.call("owner", "PATCH", _path(corpus, bot_id), json={"status": "flying"})
    assert unknown.status_code == 422
    # archived bots cannot be revived through PATCH
    users.call("editor", "DELETE", _path(corpus, bot_id))
    revive = users.call("owner", "PATCH", _path(corpus, bot_id), json={"status": "active"})
    assert revive.status_code == 409
    assert revive.json()["error"]["code"] == "BOT_ARCHIVED"


def test_viewer_cannot_transition_and_editor_admin_owner_can(corpus: dict[str, Any]) -> None:
    users = corpus["users_a"]
    bot = make_bot(users, "Role Gated")
    bot_id = str(bot["id"])
    denied = users.as_user("viewer").patch(
        _path(corpus, bot_id),
        json={"status": "active"},
        headers={"X-CSRF-Token": users.as_user("viewer").cookies.get("chatbot_csrf") or ""},
    )
    assert denied.status_code == 403
    viewer_activate = users.as_user("owner").patch(
        _path(corpus, bot_id),
        json={"status": "active"},
        headers={"X-CSRF-Token": users.as_user("owner").cookies.get("chatbot_csrf") or ""},
    )
    assert viewer_activate.status_code == 200
    for role in ("editor", "admin", "owner"):
        client = users.as_user(role)
        target = "paused" if role == "editor" else "active"
        response = client.patch(
            _path(corpus, bot_id),
            json={"status": target},
            headers={"X-CSRF-Token": client.cookies.get("chatbot_csrf") or ""},
        )
        assert response.status_code == 200, response.text


def test_tenant_b_cannot_transition_tenant_a_bot(corpus: dict[str, Any]) -> None:
    users = corpus["users_a"]
    bot = make_bot(users, "Isolated")
    bot_id = str(bot["id"])
    foreign = corpus["users_b"]
    response = foreign.call("owner", "PATCH", _path(corpus, bot_id), json={"status": "active"})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
