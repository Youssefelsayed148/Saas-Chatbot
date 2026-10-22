"""Public widget endpoints (docs/05 public rows, P4-01).

- GET  /api/public/v1/widgets/{locator}/config        safe config + state
- POST /api/public/v1/widgets/{locator}/sessions      short-lived capability token
- POST /api/public/v1/sessions/{session_id}/messages  one grounded chat turn
- GET  /api/public/v1/sessions/{session_id}/messages  thread recovery (since=)
- POST /api/public/v1/sessions/{session_id}/messages/{message_id}/feedback

No dashboard cookie is involved: authentication is the per-session
capability token in ``X-Session-Token``. The tenant/bot are resolved
server-side from the locator/session; caller-supplied ids are never used as
authority (docs/06). Stable error format everywhere (docs/05).
"""

import hmac  # noqa: F401  (kept for constant-time helpers used in tests)
from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.core.ratelimit import client_ip
from app.db.models import VisitorSession
from app.db.session import get_session
from app.widget import service

router = APIRouter(prefix="/api/public/v1")

DbSession = Annotated[Any, Depends(get_session)]
CurrentSettings = Annotated[Settings, Depends(get_settings)]

SESSION_TOKEN_HEADER = "X-Session-Token"


class SessionCreateRequest(BaseModel):
    # The PAGE origin as reported by the loader script (the iframe origin is
    # ours). Defence signal only — never treated as authentication (docs/06).
    page_origin: str | None = Field(default=None, max_length=300)


class WidgetMessageRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    # Optional widget language hint (docs/14 §2: with no letters uses hint).
    language: str | None = Field(default=None, pattern="^(en|ar)$")


class CitationOut(BaseModel):
    chunk_id: str
    title: str | None = None
    heading: str | None = None
    source_url: str | None = None
    page_ref: str | None = None


class MessagePart(BaseModel):
    id: str
    sender_type: str
    text: str
    citations: list[CitationOut] | None = None
    can_answer: bool | None = None
    needs_human: bool = False
    created_at: str


class MessageTurnResponse(BaseModel):
    conversation_id: str
    visitor_message: dict[str, Any]
    ai_message: dict[str, Any] | None
    kind: str
    language: str


class SessionMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    sender_type: str
    text: str
    citations: list[dict[str, Any]] | None = None
    can_answer: bool | None = None
    needs_human: bool = False
    created_at: datetime


class SessionCreateResponse(BaseModel):
    session_id: str
    token: str
    expires_at: str
    config: dict[str, Any]


class FrameAncestorsResponse(BaseModel):
    # The compiled CSP source list for the frame page (#33). It carries only
    # what the frame HTTP header already shows any browser; it never exposes
    # other config keys.
    frame_ancestors: str


class FeedbackRequest(BaseModel):
    rating: str = Field(pattern="^(up|down)$")


class LeadRequest(BaseModel):
    """Lead form (P4-04, docs/14 §14/§16): consent is REQUIRED, name plus a
    reachable channel (email or phone). The widget renders the same consent
    text the contact records (`consent_text_version`)."""

    name: str = Field(min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=40)
    consent_accepted: bool = False
    # The language the widget displayed the consent text in (audit trail).
    consent_language: str = Field(default="en", pattern="^(en|ar)$")


def _session_or_401(
    db: Any, session_id: UUID, settings: Settings, token: str | None
) -> VisitorSession:
    if not token:
        raise ApiError(401, "SESSION_INVALID", "This chat session is no longer valid.")
    return service.bot_by_session(db, session_id, token)


@router.get("/widgets/{locator}/config")
def widget_config(
    locator: str,
    db: DbSession,
) -> dict[str, Any]:
    """Safe public config + availability (docs/09 states; paused/not-ready
    still returns the known config so the widget can show its controlled UI)."""
    bot = service.bot_by_locator(db, locator)
    availability = service.widget_availability(bot)
    return {
        "locator": locator,
        "available": availability is None,
        "reason": availability,
        "config": service.widget_config(bot),
    }


@router.get("/widgets/{locator}/frame-ancestors", response_model=FrameAncestorsResponse)
def widget_frame_ancestors(
    locator: str,
    db: DbSession,
    settings: CurrentSettings,
) -> FrameAncestorsResponse:
    """Per-bot CSP source list the web proxy sets on the frame page response
    (A2.2). Locator-addressed like the rest of the public surface; unknown
    locators 404. Falls back to Next's static permissive rule when unset."""
    bot = service.bot_by_locator(db, locator)
    return FrameAncestorsResponse(
        frame_ancestors=service.frame_ancestors(bot, settings.environment)
    )


@router.post("/widgets/{locator}/sessions", response_model=SessionCreateResponse, status_code=201)
def create_session(
    locator: str,
    body: SessionCreateRequest,
    db: DbSession,
    request: Request,
    settings: CurrentSettings,
) -> SessionCreateResponse:
    """Visitor session: short-lived capability token bound to the bot (docs/09)."""
    bot = service.bot_by_locator(db, locator)
    payload = service.create_visitor_session(
        db,
        bot=bot,
        settings=settings,
        page_origin=body.page_origin,
        ip=client_ip(request),
    )
    return SessionCreateResponse(
        session_id=payload["session_id"],
        token=payload["token"],
        expires_at=payload["expires_at"],
        config=payload["config"],
    )


@router.post("/sessions/{session_id}/messages", response_model=MessageTurnResponse, status_code=201)
def send_message(
    session_id: UUID,
    body: WidgetMessageRequest,
    request: Request,
    db: DbSession,
    settings: CurrentSettings,
    x_session_token: Annotated[str | None, Header()] = None,
) -> MessageTurnResponse:
    """One grounded turn through the P3 pipeline (citations, needs_human)."""
    visitor_session = _session_or_401(db, session_id, settings, x_session_token)
    bot = service.bot_for_session(db, visitor_session)
    payload = service.widget_message_turn(
        db,
        visitor_session=visitor_session,
        bot=bot,
        text=body.text,
        ip=client_ip(request),
        settings=settings,
        language_hint=body.language,
    )
    return MessageTurnResponse(
        conversation_id=payload["conversation_id"],
        visitor_message=payload["visitor_message"],
        ai_message=(
            {**payload["ai_message"], "citations": []} if payload["ai_message"] else None
        ),
        kind=payload["kind"],
        language=payload["language"],
    )


@router.get("/sessions/{session_id}/messages", response_model=list[SessionMessageOut])
def session_messages(
    session_id: UUID,
    db: DbSession,
    settings: CurrentSettings,
    x_session_token: Annotated[str | None, Header()] = None,
    since: Annotated[datetime | None, Query()] = None,
) -> list[SessionMessageOut]:
    """Thread recovery/history for the visitor's own session (docs/09)."""
    visitor_session = _session_or_401(db, session_id, settings, x_session_token)
    rows = service.session_history(
        db, visitor_session=visitor_session, settings=settings, since=since
    )
    return [
        SessionMessageOut(
            id=row.id,
            sender_type=row.sender_type,
            text=row.text,
            citations=[],
            can_answer=row.can_answer,
            needs_human=row.needs_human,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.post("/sessions/{session_id}/messages/{message_id}/feedback", status_code=200)
def session_feedback(
    session_id: UUID,
    message_id: UUID,
    body: FeedbackRequest,
    db: DbSession,
    settings: CurrentSettings,
    x_session_token: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    """Thumbs up/down from the widget; idempotent per message+session."""
    visitor_session = _session_or_401(db, session_id, settings, x_session_token)
    service.widget_feedback(
        db,
        visitor_session=visitor_session,
        message_id=message_id,
        rating=body.rating,
    )
    return {"status": "ok"}


@router.post("/sessions/{session_id}/lead", status_code=201)
def session_lead(
    session_id: UUID,
    body: LeadRequest,
    db: DbSession,
    settings: CurrentSettings,
    x_session_token: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Lead capture: explicit consent REQUIRED before any contact write."""
    visitor_session = _session_or_401(db, session_id, settings, x_session_token)
    email = (body.email or "").strip() or None
    phone = (body.phone or "").strip() or None
    if not email and not phone:
        raise ApiError(422, "VALIDATION_ERROR", "Provide an email address or a phone number.")
    if email and ("@" not in email):
        raise ApiError(422, "VALIDATION_ERROR", "Provide a valid email address.")
    if not body.consent_accepted:
        raise ApiError(422, "CONSENT_REQUIRED", "Lead details can only be saved with consent.")
    return service.capture_lead(
        db,
        visitor_session=visitor_session,
        name=body.name.strip(),
        email=email,
        phone=phone,
    )
