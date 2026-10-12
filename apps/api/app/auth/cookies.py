"""Cookie mechanics for server-side sessions and the CSRF double-submit token."""

import hmac
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.auth.security import generate_session_token, hash_token
from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.db.models import Session, User
from app.db.session import get_session

CSRF_HEADER_NAME = "X-CSRF-Token"
SESSION_COOKIE_NAME = "chatbot_session"  # keep in sync with Settings.session_cookie_name default
CSRF_COOKIE_NAME = "chatbot_csrf"  # keep in sync with Settings.csrf_cookie_name default
CSRF_COOKIE_MAX_AGE_SECONDS = 14 * 24 * 3600


def set_session_cookie(
    response: Response,
    settings: Settings,
    *,
    token: str,
    max_age_seconds: int,
) -> None:
    # HttpOnly: not readable by JS. SameSite=Lax: normal navigation allowed, cross-site
    # form posts without a token blocked. Secure is set unless running plain HTTP (tests/dev).
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=max_age_seconds,
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )


def clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=settings.session_cookie_name, path="/", secure=settings.cookie_secure, httponly=True
    )


def read_session_token(request: Request, settings: Settings) -> str | None:
    return request.cookies.get(settings.session_cookie_name) or None


def ensure_csrf_cookie(request: Request, response: Response, settings: Settings) -> str:
    """Issue a CSRF token cookie if absent so JS clients can send X-CSRF-Token on writes."""
    token = request.cookies.get(settings.csrf_cookie_name)
    if token:
        return token
    token = generate_session_token()
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=token,
        max_age=CSRF_COOKIE_MAX_AGE_SECONDS,
        path="/",
        secure=settings.cookie_secure,
        httponly=False,  # The token must be readable by the SPA to send it as a header.
        samesite="lax",
    )
    return token


def require_csrf(request: Request, settings: Annotated[Settings, Depends(get_settings)]) -> None:
    """Double-submit check for cookie-authenticated writes (docs/06)."""
    cookie_token = request.cookies.get(settings.csrf_cookie_name) or ""
    header_token = request.headers.get(CSRF_HEADER_NAME) or ""
    if not cookie_token or not header_token:
        # A missing token fails closed: HttpOnly session cookies cannot be used by
        # cross-site scripts, and the CSRF token is compared against the header only.
        raise ApiError(403, "CSRF_MISSING", "Missing CSRF token for this request.")
    if not hmac.compare_digest(cookie_token.encode("utf-8"), header_token.encode("utf-8")):
        raise ApiError(403, "CSRF_INVALID", "Invalid CSRF token for this request.")


def get_current_user(
    request: Request,
    db: Annotated[OrmSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> User:
    """Resolve the user from the server-side session cookie or fail with 401."""
    token = read_session_token(request, settings)
    if token is None:
        raise ApiError(401, "UNAUTHENTICATED", "Authentication required.")
    now = datetime.now(UTC)
    row = db.execute(
        select(Session).where(
            Session.token_hash == hash_token(token),
            Session.revoked_at.is_(None),
            Session.expires_at > now,
        )
    ).scalar_one_or_none()
    if row is None:
        raise ApiError(401, "SESSION_INVALID", "Session is invalid, expired or revoked.")
    user = db.get(User, row.user_id)
    if user is None:
        raise ApiError(401, "SESSION_INVALID", "Session user no longer exists.")
    return user
