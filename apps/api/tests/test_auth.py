"""P1-02: register/login/logout/me, sessions, CSRF, rate limiting, error format."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import FastAPI, Response
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session as OrmSession

from app.auth.cookies import CSRF_HEADER_NAME, SESSION_COOKIE_NAME, set_session_cookie
from app.core.config import Settings, get_settings
from tests.conftest import csrf_headers


def _set_small_limiter(app: FastAPI, attempts: int = 2, window_seconds: int = 60) -> None:
    """Login limiter settings (Postgres-backed since P4-01): the settings
    dependency carries the smaller window for a deterministic test."""
    app.dependency_overrides[get_settings] = lambda: Settings.model_construct(
        database_url=None,
        cookie_secure=False,
        login_rate_limit_attempts=attempts,
        login_rate_limit_window_seconds=window_seconds,
    )


def _register(client: TestClient, email: str = "owner@example.com") -> dict[str, Any]:
    response = client.post(
        "/api/v1/auth/register", json={"email": email, "password": "Str0ngPass!"}
    )
    assert response.status_code == 201
    payload: dict[str, Any] = response.json()
    return payload


def _login(
    client: TestClient, email: str = "owner@example.com", password: str = "Str0ngPass!"
) -> dict[str, Any]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    payload: dict[str, Any] = response.json()
    return payload


def _error_code(response: Any) -> str:
    return str(response.json()["error"]["code"])


# --- register --------------------------------------------------------------


def test_register_sets_session_and_csrf_cookies(client: TestClient) -> None:
    client.cookies.clear()
    response = client.post(
        "/api/v1/auth/register", json={"email": "owner@example.com", "password": "Str0ngPass!"}
    )
    assert response.status_code == 201
    payload: dict[str, Any] = response.json()
    assert payload["email"] == "owner@example.com"
    assert payload["is_platform_staff"] is False
    assert payload["memberships"] == []

    session_cookie = client.cookies.get(SESSION_COOKIE_NAME)
    csrf_cookie = client.cookies.get("chatbot_csrf")
    assert session_cookie and csrf_cookie

    # The register response sets the session cookie HttpOnly + SameSite=lax (no Secure
    # under plain HTTP; the secure variant is asserted separately in production config).
    set_cookie_headers = response.headers.get_list("set-cookie")
    session_headers = [h for h in set_cookie_headers if SESSION_COOKIE_NAME in h]
    assert session_headers, set_cookie_headers
    header = session_headers[0].lower()
    assert "httponly" in header
    assert "samesite=lax" in header
    assert "secure" not in header

    # The second register sets a session for the new user (independent rows).
    _register(client, "flags@example.com")


def test_register_duplicate_email_case_insensitive(client: TestClient) -> None:
    _register(client, "first@example.com")
    response = client.post(
        "/api/v1/auth/register", json={"email": "FIRST@example.com", "password": "Str0ngPass!"}
    )
    assert response.status_code == 409
    assert _error_code(response) == "EMAIL_TAKEN"


def test_register_validation_rejected(client: TestClient) -> None:
    short_password = client.post(
        "/api/v1/auth/register", json={"email": "a@example.com", "password": "short"}
    )
    assert short_password.status_code == 422
    invalid_email = client.post(
        "/api/v1/auth/register", json={"email": "not-an-email", "password": "Str0ngPass!"}
    )
    assert invalid_email.status_code == 422
    # Input values (including the secret) are never echoed back.
    assert "not-an-email" not in invalid_email.text


def test_unknown_email_and_wrong_password_fail_identically(client: TestClient) -> None:
    unknown_email = client.post(
        "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "Str0ngPass!"}
    )
    assert unknown_email.status_code == 401
    assert _error_code(unknown_email) == "INVALID_CREDENTIALS"
    assert "nobody@example.com" not in unknown_email.text

    _register(client)
    wrong_password = client.post(
        "/api/v1/auth/login", json={"email": "owner@example.com", "password": "Wr0ngPass!"}
    )
    assert wrong_password.status_code == 401
    # Same code and message as unknown email: no account-existence oracle.
    detail_unknown = unknown_email.json()["error"]
    detail_wrong = wrong_password.json()["error"]
    assert detail_unknown["code"] == detail_wrong["code"]
    assert detail_unknown["message"] == detail_wrong["message"]


# --- sessions --------------------------------------------------------------


def test_sessions_valid_invalid_expired_revoked(client: TestClient, db: OrmSession) -> None:
    client.cookies.clear()
    _register(client)
    assert client.get("/api/v1/auth/me").status_code == 200

    # Invalid token value (jar cleared, then a wrong value set directly).
    client.cookies.clear()
    client.cookies.set(SESSION_COOKIE_NAME, "not-a-real-token", domain="testserver.local")
    invalid = client.get("/api/v1/auth/me")
    assert invalid.status_code == 401
    assert _error_code(invalid) == "SESSION_INVALID"

    # Valid session again, then expired server-side.
    client.post(
        "/api/v1/auth/register", json={"email": "second@example.com", "password": "Str0ngPass!"}
    )
    assert client.get("/api/v1/auth/me").status_code == 200
    db.execute(
        text("UPDATE sessions SET expires_at = CAST(:at AS timestamptz)"),
        {"at": (datetime.now(UTC) - timedelta(seconds=1)).isoformat()},
    )
    db.commit()
    expired = client.get("/api/v1/auth/me")
    assert expired.status_code == 401
    assert _error_code(expired) == "SESSION_INVALID"

    # A fresh session, then revoked server-side.
    revoked_user = client.post(
        "/api/v1/auth/register", json={"email": "third@example.com", "password": "Str0ngPass!"}
    )
    assert revoked_user.status_code == 201
    assert client.get("/api/v1/auth/me").status_code == 200
    db.execute(text("UPDATE sessions SET revoked_at = NOW()"))
    db.commit()
    revoked = client.get("/api/v1/auth/me")
    assert revoked.status_code == 401
    assert _error_code(revoked) == "SESSION_INVALID"


def test_without_cookie_me_is_unauthenticated(client: TestClient) -> None:
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert _error_code(response) == "UNAUTHENTICATED"


def test_me_includes_memberships_once_tenants_exist(client: TestClient, db: OrmSession) -> None:
    _register(client)
    user_id = str(client.get("/api/v1/auth/me").json()["id"])
    db.execute(
        text(
            "INSERT INTO tenants (id, name, slug, status, created_at) "
            "VALUES (CAST(:tid AS uuid), 'Acme', 'acme', 'active', NOW())"
        ),
        {"tid": str(uuid.uuid4())},
    )
    db.execute(
        text(
            "INSERT INTO memberships (tenant_id, user_id, role, status, created_at) "
            "VALUES ("
            "(SELECT id FROM tenants WHERE slug='acme'), CAST(:uid AS uuid), 'owner', 'active',"
            "NOW()"
            ")"
        ),
        {"uid": user_id},
    )
    db.commit()
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    memberships = me.json()["memberships"]
    assert len(memberships) == 1
    assert memberships[0]["tenant_name"] == "Acme"
    assert memberships[0]["role"] == "owner"


def test_login_rotates_session(client: TestClient) -> None:
    """Rotation: each login issues a NEW session; the old value no longer authenticates."""
    client.cookies.clear()
    _register(client)
    first_token = client.cookies.get(SESSION_COOKIE_NAME)
    assert first_token

    logged_out = client.post("/api/v1/auth/logout", headers=csrf_headers(client))
    assert logged_out.status_code == 200
    # Login with the revoked token presented: a fresh session is issued regardless.
    client.cookies.clear()
    client.cookies.set(SESSION_COOKIE_NAME, first_token, domain="testserver.local")
    login_response = client.post(
        "/api/v1/auth/login", json={"email": "owner@example.com", "password": "Str0ngPass!"}
    )
    assert login_response.status_code == 200
    second_token = client.cookies.get(SESSION_COOKIE_NAME)
    assert second_token and second_token != first_token
    assert client.get("/api/v1/auth/me").status_code == 200

    # A further login rotates again; only the latest token remains valid.
    _login(client)
    third_token = client.cookies.get(SESSION_COOKIE_NAME)
    assert third_token and third_token != second_token
    assert client.get("/api/v1/auth/me").status_code == 200
    client.cookies.clear()
    client.cookies.set(SESSION_COOKIE_NAME, second_token, domain="testserver.local")
    stale = client.get("/api/v1/auth/me")
    assert stale.status_code == 401
    assert _error_code(stale) == "SESSION_INVALID"


# --- logout ----------------------------------------------------------------


def test_logout_requires_csrf_and_revokes_session(client: TestClient) -> None:
    _register(client)
    without_csrf = client.post("/api/v1/auth/logout")
    assert without_csrf.status_code == 403
    assert _error_code(without_csrf) == "CSRF_MISSING"

    with_csrf = client.post("/api/v1/auth/logout", headers=csrf_headers(client))
    assert with_csrf.status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401


def test_csrf_rejects_wrong_token(client: TestClient) -> None:
    _register(client)
    response = client.post("/api/v1/auth/logout", headers={CSRF_HEADER_NAME: "wrong-value"})
    assert response.status_code == 403
    assert _error_code(response) == "CSRF_INVALID"


# --- rate limiting ---------------------------------------------------------


def test_login_rate_limited(client: TestClient, app: FastAPI) -> None:
    """The P4-01 Postgres-backed login limiter: same 429 contract, counts
    failed attempts, resets when the window ages out (docs/14 §7)."""
    _register(client)
    _set_small_limiter(app, attempts=2)
    first = client.post(
        "/api/v1/auth/login", json={"email": "owner@example.com", "password": "Wr0ngPass!"}
    )
    assert first.status_code == 401
    second = client.post(
        "/api/v1/auth/login", json={"email": "owner@example.com", "password": "Wr0ngPass!"}
    )
    assert second.status_code == 401
    third = client.post(
        "/api/v1/auth/login", json={"email": "owner@example.com", "password": "Str0ngPass!"}
    )
    assert third.status_code == 429
    assert _error_code(third) == "RATE_LIMITED"


def test_rate_limiter_window_allows_again(db: OrmSession) -> None:
    """Postgres counter: the window start is stamped on the row; past the
    window the count resets to 1 (extends the P1 in-process limiter)."""
    from datetime import UTC, datetime

    from app.core.ratelimit import rate_limit

    t0 = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
    first, _ = rate_limit(db, key="unit:window", limit=1, window_seconds=1, now=t0)
    assert first == 1
    # Still inside the window: the count grows past the limit (the caller
    # turns count > limit into the standard 429).
    second, _ = rate_limit(db, key="unit:window", limit=1, window_seconds=1, now=t0)
    assert second == 2
    db.commit()
    # Window passes -> allowed again (fresh window count).
    later, _ = rate_limit(
        db,
        key="unit:window",
        limit=1,
        window_seconds=1,
        now=datetime(2026, 1, 1, 0, 0, 5, tzinfo=UTC),
    )
    assert later == 1


# --- error format & cookie flags -------------------------------------------


def test_error_responses_use_stable_format(client: TestClient) -> None:
    response = client.get("/api/v1/auth/me")
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "request_id"}
    assert body["error"]["request_id"] == response.headers.get("X-Request-ID")
    request_id = body["error"]["request_id"]
    assert isinstance(request_id, str) and len(request_id) > 0


def test_error_messages_do_not_leak_secrets(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register", json={"email": "x@example.com", "password": "SL3cret$Value"}
    )
    assert "SL3cret$Value" not in response.text


def test_secure_cookie_flags_in_production_config() -> None:
    settings = Settings.model_construct(cookie_secure=True)
    response = Response()
    set_session_cookie(response, settings, token="token-value", max_age_seconds=60)
    header = response.headers["set-cookie"]
    assert "HttpOnly" in header
    assert "SameSite=lax" in header
    assert "Secure" in header
