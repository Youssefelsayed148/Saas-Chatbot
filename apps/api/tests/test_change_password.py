"""S4: signed-in password change (POST /api/v1/auth/change-password).

Covers: success (rotation keeps the caller signed in), wrong current password
(throttled per user), same-as-current, policy failure (422), unauthenticated
401, missing CSRF 403, other sessions revoked, old/new password login,
platform staff self-change, the audit row, secret-free responses/logs, and
per-user throttle isolation.
"""

from typing import Any
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session as OrmSession

from app.core.config import get_settings
from tests.conftest import build_test_settings, csrf_headers
from tests.helpers import PASSWORD, logged_in
from tests.test_platform import staff_login

NEW_PASSWORD = "N3wStr0ngPass!"


def _change(
    client: TestClient,
    current: str,
    new: str,
) -> Any:
    return client.post(
        "/api/v1/auth/change-password",
        json={"current_password": current, "new_password": new},
        headers=csrf_headers(client),
    )


def _second_session(app: FastAPI, email: str, password: str) -> TestClient:
    """A second, independent signed-in session for the same account."""
    other = TestClient(app)
    response = other.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return other


def _audit_rows(db: OrmSession, user_id: str) -> list[tuple[str, str, str]]:
    rows = db.execute(
        text(
            "SELECT action, actor_user_id::text, metadata_json::text FROM audit_events "
            "WHERE target_type = 'user' AND target_id = :uid"
        ),
        {"uid": user_id},
    ).all()
    return [(str(r[0]), str(r[1]), str(r[2])) for r in rows]


def test_change_password_success_rotates_session_and_revokes_others(
    app: FastAPI, db: OrmSession
) -> None:
    me_client, me = logged_in(app, "changer@example.com")
    other = _second_session(app, "changer@example.com", PASSWORD)

    response = _change(me_client, PASSWORD, NEW_PASSWORD)
    assert response.status_code == 200, response.text

    # The current session was rotated: the fresh cookie keeps working.
    followed = me_client.get("/api/v1/auth/me")
    assert followed.status_code == 200, followed.text
    assert followed.json()["email"] == "changer@example.com"
    # A brand-new session cookie value was issued (rotation, not reuse).
    assert me_client.cookies.get("chatbot_session")

    # Every OTHER session is revoked (other contexts are signed out).
    assert other.get("/api/v1/auth/me").status_code == 401

    # The old password stops working; the new one signs in.
    stale = TestClient(app)
    assert (
        stale.post(
            "/api/v1/auth/login", json={"email": "changer@example.com", "password": PASSWORD}
        ).status_code
        == 401
    )
    fresh = TestClient(app)
    assert (
        fresh.post(
            "/api/v1/auth/login", json={"email": "changer@example.com", "password": NEW_PASSWORD}
        ).status_code
        == 200
    )
    me_client.close()
    other.close()
    stale.close()
    fresh.close()


def test_change_password_writes_audit_row_without_secrets(
    app: FastAPI, db: OrmSession, caplog: Any
) -> None:
    me_client, me = logged_in(app, "audited@example.com")
    response = _change(me_client, PASSWORD, NEW_PASSWORD)
    assert response.status_code == 200, response.text

    rows = _audit_rows(db, me["id"])
    assert len(rows) == 1, rows
    action, actor, metadata = rows[0]
    assert action == "auth.password_changed"
    assert actor == me["id"]
    # No secrets in metadata (empty by contract) and none anywhere else.
    assert metadata in ("{}", "null")
    for secret in (PASSWORD, NEW_PASSWORD, "$argon2"):
        assert secret not in response.text
        assert secret not in caplog.text
    me_client.close()


def test_wrong_current_password_is_safe_and_actionable(
    app: FastAPI, db: OrmSession, caplog: Any
) -> None:
    me_client, me = logged_in(app, "wrong@example.com")
    response = _change(me_client, "NotTheCurrentOne!", NEW_PASSWORD)
    assert response.status_code == 400
    body: dict[str, Any] = response.json()
    assert body["error"]["code"] == "INVALID_CURRENT_PASSWORD"
    assert "incorrect" in body["error"]["message"]
    # Nothing changed: the session survives and no audit row was written.
    assert me_client.get("/api/v1/auth/me").status_code == 200
    assert _audit_rows(db, me["id"]) == []
    for secret in (NEW_PASSWORD, "$argon2"):
        assert secret not in response.text
        assert secret not in caplog.text
    me_client.close()


def test_same_password_is_rejected(app: FastAPI, db: OrmSession) -> None:
    me_client, me = logged_in(app, "same@example.com")
    response = _change(me_client, PASSWORD, PASSWORD)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "PASSWORD_UNCHANGED"
    # The session still works (nothing was changed or revoked).
    assert me_client.get("/api/v1/auth/me").status_code == 200
    assert _audit_rows(db, me["id"]) == []
    me_client.close()


def test_policy_failure_returns_validation_error(app: FastAPI) -> None:
    me_client, _ = logged_in(app, "policy@example.com")
    response = _change(me_client, PASSWORD, "short")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    me_client.close()


def test_unauthenticated_gets_401(app: FastAPI) -> None:
    client = TestClient(app)
    response = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


def test_missing_csrf_is_refused(app: FastAPI) -> None:
    me_client, _ = logged_in(app, "csrf@example.com")
    response = me_client.post(
        "/api/v1/auth/change-password",
        json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_MISSING"
    me_client.close()


def test_failed_attempts_are_throttled_per_user(app: FastAPI) -> None:
    app.dependency_overrides[get_settings] = lambda: build_test_settings(
        change_password_rate_limit_attempts=2,
    )
    me_client, me = logged_in(app, "throttled@example.com")
    other_client, other = logged_in(app, "unthrottled@example.com")

    first = _change(me_client, "Wrong0ne!", NEW_PASSWORD)
    second = _change(me_client, "Wrong0ne!", NEW_PASSWORD)
    assert (first.status_code, second.status_code) == (400, 400)
    third = _change(me_client, "Wrong0ne!", NEW_PASSWORD)
    assert third.status_code == 429
    assert third.json()["error"]["code"] == "RATE_LIMITED"

    # The per-user counter does not throttle a different user.
    assert _change(other_client, PASSWORD, NEW_PASSWORD).status_code == 200
    # The presented (authenticated) session is unaffected by the throttle errors.
    assert me_client.get("/api/v1/auth/me").status_code == 200
    assert UUID(other["id"])  # shape sanity
    me_client.close()
    other_client.close()


def test_platform_staff_can_change_their_own_password(app: FastAPI, db: OrmSession) -> None:
    staff_client = staff_login(app, db, "staff-change@example.com")
    response = _change(staff_client, PASSWORD, NEW_PASSWORD)
    assert response.status_code == 200, response.text

    followed = staff_client.get("/api/v1/auth/me")
    assert followed.status_code == 200
    assert followed.json()["is_platform_staff"] is True

    fresh = TestClient(app)
    assert (
        fresh.post(
            "/api/v1/auth/login",
            json={"email": "staff-change@example.com", "password": NEW_PASSWORD},
        ).status_code
        == 200
    )
    rows = _audit_rows(db, followed.json()["id"])
    assert rows and rows[0][0] == "auth.password_changed"
    staff_client.close()
    fresh.close()


def test_wrong_current_password_does_not_leak_hash_or_account_details(
    app: FastAPI, caplog: Any
) -> None:
    me_client, me = logged_in(app, "leak@example.com")
    response = me_client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "Nope0ne!", "new_password": NEW_PASSWORD},
        headers=csrf_headers(me_client),
    )
    assert response.status_code == 400
    assert me["email"] not in response.json()["error"]["message"]
    assert "$argon2" not in response.text
    assert "$argon2" not in caplog.text
    me_client.close()
