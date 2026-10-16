"""Auth router: register / login / logout / me (docs/05 phase-1 frozen contract)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session as OrmSession

from app.auth import cookies
from app.auth.schemas import (
    LoginRequest,
    MembershipOut,
    MeResponse,
    OkResponse,
    RegisterRequest,
)
from app.auth.service import AuthService
from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.core.ratelimit import client_ip, rate_limit
from app.db.models import User
from app.db.session import get_session

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

DbSession = Annotated[OrmSession, Depends(get_session)]
CurrentSettings = Annotated[Settings, Depends(get_settings)]
CurrentUser = Annotated[User, Depends(cookies.get_current_user)]
CsrfOk = Annotated[None, Depends(cookies.require_csrf)]


@router.get("/config")
def auth_config(settings: CurrentSettings) -> dict[str, bool]:
    return {"self_serve_signup": settings.self_serve_signup}


def _login_rate_limited(db: OrmSession, request: Request, settings: Settings) -> None:
    """Fixed-window login limiter (P1 carry-over, now Postgres-backed so it
    survives restarts and works across processes — P4-01, docs/14 §7).

    The increment commits in its own transaction so FAILED attempts are
    counted, not silently rolled back by a later 401."""
    ip = client_ip(request)
    count, _remaining = rate_limit(
        db,
        key=f"login:{ip}",
        limit=settings.login_rate_limit_attempts,
        window_seconds=settings.login_rate_limit_window_seconds,
    )
    db.commit()
    if count > settings.login_rate_limit_attempts:
        raise ApiError(429, "RATE_LIMITED", "Too many login attempts. Try again later.")


@router.post("/register", response_model=MeResponse, status_code=201)
def register(
    body: RegisterRequest,
    response: Response,
    request: Request,
    db: DbSession,
    settings: CurrentSettings,
) -> MeResponse:
    service = AuthService(db, settings)
    user, token = service.register(body.email, body.password)
    cookies.set_session_cookie(
        response, settings, token=token, max_age_seconds=settings.session_lifetime_seconds
    )
    cookies.ensure_csrf_cookie(request, response, settings)
    return _me_response(service, user)


@router.post("/login", response_model=MeResponse)
def login(
    body: LoginRequest,
    response: Response,
    request: Request,
    db: DbSession,
    settings: CurrentSettings,
) -> MeResponse:
    """Rate-limited login with session rotation (the presented token is revoked)."""
    _login_rate_limited(db, request, settings)
    service = AuthService(db, settings)
    presented = cookies.read_session_token(request, settings)
    user, token = service.login(body.email, body.password, rotate_token=presented)
    cookies.set_session_cookie(
        response, settings, token=token, max_age_seconds=settings.session_lifetime_seconds
    )
    cookies.ensure_csrf_cookie(request, response, settings)
    return _me_response(service, user)


@router.post("/logout", response_model=OkResponse)
def logout(
    response: Response,
    request: Request,
    db: DbSession,
    settings: CurrentSettings,
    _: CsrfOk,
) -> OkResponse:
    """Cookie-authenticated write ⇒ CSRF-checked. Revokes the presented session."""
    service = AuthService(db, settings)
    service.logout(token=cookies.read_session_token(request, settings))
    cookies.clear_session_cookie(response, settings)
    return OkResponse()


@router.get("/me", response_model=MeResponse)
def me(
    response: Response,
    request: Request,
    db: DbSession,
    settings: CurrentSettings,
    user: CurrentUser,
) -> MeResponse:
    cookies.ensure_csrf_cookie(request, response, settings)
    service = AuthService(db, settings)
    return _me_response(service, user)


def _me_response(service: AuthService, user: User) -> MeResponse:
    memberships = [
        MembershipOut(
            tenant_id=tenant.id,
            tenant_name=tenant.name,
            tenant_slug=tenant.slug,
            role=membership.role,
        )
        for membership, tenant in service.memberships_of(user.id)
    ]
    return MeResponse(
        id=user.id,
        email=user.email,
        is_platform_staff=user.is_platform_staff,
        memberships=memberships,
    )
