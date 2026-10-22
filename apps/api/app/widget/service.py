"""Widget public-channel service (P4-01, docs/09, docs/14 §7).

Public surface, no dashboard cookie: every lookup resolves through the
opaque bot locator or the visitor capability token — callers NEVER supply a
tenant_id (docs/06). The allowed-domain check is a defence signal, not
authentication; rate limits are Postgres-backed fixed windows that survive
restarts (docs/14 §7); quota hooks check the daily message cap per bot from
usage_events (per-plan quotas formalised in P7).

Hidden/foreign resources return 404/401 exactly like the dashboard API.
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from app.chat.conversations import (
    get_or_create_conversation_for_session,
    record_usage_event,
    visitor_chat_turn,
)
from app.chat.models import model_from_settings
from app.core.config import Settings
from app.core.errors import ApiError
from app.core.ratelimit import rate_limit
from app.db.models import (
    Bot,
    Contact,
    ContactIdentity,
    Conversation,
    Message,
    Tenant,
    UsageEvent,
    VisitorSession,
)
from app.quotas.service import lock_tenant, require_capacity

RETIRED_WINDOW = 60  # fixed-window width used by the public counters (seconds)


# --- bot resolution ---------------------------------------------------------


def bot_by_locator(db: OrmSession, locator: str) -> Bot:
    """Resolve one bot from its public locator; unknown locators look like 404."""
    bot = db.execute(select(Bot).where(Bot.widget_locator == locator)).scalar_one_or_none()
    tenant = db.get(Tenant, bot.tenant_id) if bot is not None else None
    if bot is None or bot.status == "archived" or tenant is None or tenant.status != "active":
        raise ApiError(404, "NOT_FOUND", "Widget not found.")
    return bot


def bot_by_session(db: OrmSession, session_id: UUID, token: str) -> VisitorSession:
    """Resolve the visitor session from its capability token; a guessed id,
    another session's token (or another bot's) always produce 401 — the id
    alone reveals nothing."""
    visitor_session = db.get(VisitorSession, session_id)
    if visitor_session is None or visitor_session.token_hash != hash_session_token(token):
        raise ApiError(401, "SESSION_INVALID", "This chat session is no longer valid.")
    tenant = db.get(Tenant, visitor_session.tenant_id)
    if (
        visitor_session.expires_at <= datetime.now(UTC)
        or tenant is None
        or tenant.status != "active"
    ):
        raise ApiError(401, "SESSION_EXPIRED", "This chat session expired.")
    return visitor_session


def bot_for_session(db: OrmSession, visitor_session: VisitorSession) -> Bot:
    """The session's own bot — composite FK bound; a foreign bot 404s."""
    bot = db.get(Bot, visitor_session.bot_id)
    if bot is None or bot.tenant_id != visitor_session.tenant_id:
        raise ApiError(404, "NOT_FOUND", "Widget not found.")
    return bot


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def widget_availability(bot: Bot) -> str | None:
    """Controlled-unavailable reasons (docs/09 states): None = ready."""
    if bot.status == "paused":
        return "paused"
    if bot.status != "active":
        return "disabled"
    if bot.published_revision_id is None:
        return "not_ready"
    return None


def require_available(bot: Bot, *, session_scope: bool) -> None:
    """409 with the specific unavailability code (docs/09 states); the widget
    maps the code to a localized message."""
    del session_scope
    availability = widget_availability(bot)
    codes = {"paused": "BOT_PAUSED", "not_ready": "BOT_NOT_READY", "disabled": "BOT_DISABLED"}
    if availability is not None:
        raise ApiError(409, codes[availability], "This assistant is not available right now.")


# --- allowed domains (defence signal, NOT auth; docs/06) --------------------


def _host_of(value: str | None) -> str | None:
    """The hostname behind a PAGE origin ("https://example.com:8443/page") or
    behind a bare hostname ("example.com", "localhost" — what the loader's
    location.hostname sends). Malformed or ambiguous input (colon in the
    authority-less form) yields None so the check fails closed."""
    candidate = (value or "").strip().lower()
    if not candidate:
        return None
    try:
        parts = urlsplit(candidate)
    except ValueError:
        return None
    if parts.netloc:
        try:
            # .hostname lowercases; it also parses the port and may raise on
            # malformed input (e.g. "https://user:bad:port@example.com").
            host = parts.hostname or ""
        except ValueError:
            return None
    elif ":" in candidate or "//" in candidate:
        # Authority-less but colon/colon-slashes ("example.com:8080",
        # "example.com less://x"): ambiguous, never guess from these.
        return None
    else:
        # Bare hostname, optionally with a path ("example.com/page").
        host = parts.path.split("/", 1)[0]
    return host or None


def origin_allowed(bot: Bot, page_origin: str | None) -> bool:
    """Configured domains vs the PAGE origin the loader script sends (not the
    iframe origin). Empty/absent configuration keeps the check inactive; the
    session capability and rate limits still bound abuse (docs/09)."""
    allowed = bot.config.get("allowed_domains") if isinstance(bot.config, dict) else None
    if not isinstance(allowed, list) or not allowed:
        return True
    origin = (page_origin or "").strip().lower()
    if not origin:
        return False
    host = _host_of(origin)
    if host is None:
        return False
    return any(host == str(entry) or host.endswith("." + str(entry)) for entry in allowed)


# --- widget config (safe fields only, docs/09) ------------------------------


def widget_config(bot: Bot) -> dict[str, Any]:
    """Safe public fields only: branding, greeting, opening questions,
    appearance, language. Internal config stays internal: support contact,
    always-include ids, allowed domains are never exposed."""
    config = bot.config if isinstance(bot.config, dict) else {}
    welcome_raw = config.get("welcome_message")
    welcome = welcome_raw if isinstance(welcome_raw, dict) else {}
    questions = config.get("opening_questions")
    language = (
        config.get("default_language") if config.get("default_language") in ("en", "ar") else "en"
    )
    name = str(config.get("assistant_name") or bot.name)[:100]
    return {
        "bot_name": name,
        "business_name": str(config.get("business_name") or "")[:100],
        "assistant_name": name,
        "welcome_message": {
            "en": str(welcome.get("en") or ""),
            "ar": str(welcome.get("ar") or ""),
        },
        "opening_questions": [str(question)[:120] for question in questions[:10]]
        if isinstance(questions, list)
        else [],
        "colour": str(config.get("colour") or "#1f7a5c"),
        "position": config.get("position")
        if config.get("position") in ("left", "right")
        else "right",
        "avatar": str(config.get("avatar") or "")[:500],
        "default_language": language,
        "dir": "rtl" if language == "ar" else "ltr",
    }


# --- visitor sessions --------------------------------------------------------


def _session_creation_abuse(db: OrmSession, *, ip: str, settings: Settings) -> None:
    count, _ = rate_limit(
        db,
        key=f"widget:sess:{ip}",
        limit=settings.widget_sessions_per_minute_per_ip,
        window_seconds=RETIRED_WINDOW,
    )
    if count > settings.widget_sessions_per_minute_per_ip:
        raise ApiError(429, "RATE_LIMITED", "Too many requests. Please slow down.")


def create_visitor_session(
    db: OrmSession,
    *,
    bot: Bot,
    settings: Settings,
    page_origin: str | None,
    ip: str,
) -> dict[str, Any]:
    require_available(bot, session_scope=False)
    if not origin_allowed(bot, page_origin):
        raise ApiError(
            403, "DOMAIN_NOT_ALLOWED", "This site is not allowed to embed the assistant."
        )
    _session_creation_abuse(db, ip=ip, settings=settings)

    token = secrets.token_urlsafe(24)
    visitor_session = VisitorSession(
        id=uuid4(),
        tenant_id=bot.tenant_id,
        bot_id=bot.id,
        token_hash=hash_session_token(token),
        expires_at=datetime.now(UTC) + timedelta(seconds=settings.widget_session_ttl_seconds),
    )
    db.add(visitor_session)
    db.flush()
    # widget_open usage event (docs/14 §9 — measured "sessions started")
    record_usage_event(
        db,
        tenant_id=bot.tenant_id,
        bot_id=bot.id,
        kind="widget_open",
        external_key=f"session:{visitor_session.id}",
    )
    db.commit()
    return {
        "session_id": str(visitor_session.id),
        "token": token,  # shown once; only the SHA-256 hash is stored (docs/06)
        "expires_at": visitor_session.expires_at.isoformat(),
        "config": widget_config(bot),
    }


# --- messages ---------------------------------------------------------------


def check_daily_message_quota(db: OrmSession, bot: Bot, settings: Settings) -> None:
    """Quota hook (docs/14 §7): the daily message cap per bot measured from
    real usage events. 429 QUOTA_EXCEEDED; per-plan quotas formalise in P7."""
    start_of_day = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    today = (
        db.execute(
            select(func.count())
            .select_from(UsageEvent)
            .where(
                UsageEvent.tenant_id == bot.tenant_id,
                UsageEvent.bot_id == bot.id,
                UsageEvent.kind == "message",
                UsageEvent.created_at >= start_of_day,
            )
        )
        .scalars()
        .one()
    )
    if int(today) >= settings.widget_daily_message_cap:
        raise ApiError(429, "QUOTA_EXCEEDED", "The assistant reached today's message limit.")


def widget_message_turn(
    db: OrmSession,
    *,
    visitor_session: VisitorSession,
    bot: Bot,
    text: str,
    ip: str,
    settings: Settings,
    language_hint: str | None = None,
) -> dict[str, Any]:
    """One visitor turn on the public channel. The SAME chat pipeline as the
    dashboard playground produces grounded answers with citations and
    needs_human routing (docs/09; docs/14 §6)."""
    require_available(bot, session_scope=False)  # paused mid-session → controlled 409
    # Fixed window per (IP, session); defaults per docs/14 §7: 20/min.
    count, _ = rate_limit(
        db,
        key=f"widget:msg:{ip}:{visitor_session.id}",
        limit=settings.widget_messages_per_minute,
        window_seconds=RETIRED_WINDOW,
    )
    if count > settings.widget_messages_per_minute:
        raise ApiError(429, "RATE_LIMITED", "Too many messages. Please slow down.")
    tenant = lock_tenant(db, visitor_session.tenant_id)
    require_capacity(db, tenant, "monthly_messages")
    check_daily_message_quota(db, bot, settings)

    conversation = get_or_create_conversation_for_session(
        db, bot=bot, visitor_session=visitor_session
    )
    model = model_from_settings(settings, bot)
    if model is None:
        raise ApiError(
            503, "MODEL_NOT_CONFIGURED", "The assistant is not configured for this deployment yet."
        )
    return visitor_chat_turn(
        db,
        tenant_id=visitor_session.tenant_id,
        bot=bot,
        conversation=conversation,
        question=text,
        language_hint=language_hint,
        model=model,
        settings=settings,
    )


def session_history(
    db: OrmSession,
    *,
    visitor_session: VisitorSession,
    settings: Settings,
    since: datetime | None = None,
    limit: int = 100,
) -> list[Message]:
    """Recovery/polling view of the session's thread. Retention applies like
    the dashboard thread view (docs/14 §7)."""
    conversation = (
        db.execute(
            select(Conversation).where(
                Conversation.tenant_id == visitor_session.tenant_id,
                Conversation.session_id == visitor_session.id,
            )
        )
        .scalars()
        .first()
    )
    if conversation is None:
        return []
    from app.followups.service import deliver_ready_follow_ups

    if deliver_ready_follow_ups(db, conversation=conversation, visitor_session=visitor_session):
        db.commit()
    since_retention = datetime.now(UTC) - timedelta(seconds=settings.retention_days * 86400)
    statement = select(Message).where(
        Message.conversation_id == conversation.id,
        Message.created_at > since_retention,
        # Internal state changes and notes are never exposed to visitors.
        Message.sender_type != "system",
    )
    if since is not None:
        statement = statement.where(Message.created_at > since)
    return list(
        db.execute(statement.order_by(Message.created_at.asc(), Message.id).limit(limit)).scalars()
    )


CONSENT_TEXT_VERSION = "widget-lead/v1 2026-10"

CONSENT_TEXT = {
    "en": (
        "I agree that this business may store my name and contact details to "
        "follow up on this chat."
    ),
    "ar": ("أوافق على أن تحفظ هذه الشركة اسمي وبيانات التواصل لمتابعة هذه المحادثة."),
}


def capture_lead(
    db: OrmSession,
    *,
    visitor_session: VisitorSession,
    name: str,
    email: str | None,
    phone: str | None,
) -> dict[str, Any]:
    """Lead capture with explicit consent (P4-04, docs/14 §14/§16).

    Requires consent BEFORE any contact write (checked by the router). Creates
    OR updates one contact per tenant (matched by email, else by phone); the
    conversation gets bound to the contact; consent is recorded as JSON on
    the contact (channel + version + timestamp). Attach the session as a
    website identity (unique per tenant+channel+external id)."""
    now = datetime.now(UTC)
    # 1) match an existing reachable contact of this tenant (never another).
    contact: Contact | None = None
    if email:
        contact = (
            db.execute(
                select(Contact).where(
                    Contact.tenant_id == visitor_session.tenant_id,
                    Contact.email == email,  # citext: case-insensitive match
                )
            )
            .scalars()
            .first()
        )
    if contact is None and phone:
        contact = (
            db.execute(
                select(Contact).where(
                    Contact.tenant_id == visitor_session.tenant_id,
                    Contact.phone == phone,
                )
            )
            .scalars()
            .first()
        )
    created = contact is None
    if contact is None:
        contact = Contact(
            id=uuid4(),
            tenant_id=visitor_session.tenant_id,
            display_name="",
            email=email,
            phone=phone,
            stage="new",
            source_channel="website",
        )
        db.add(contact)
    if name and (not contact.display_name or contact.source_channel == "website"):
        # Website-sourced contacts get their name refreshed by a later lead;
        # CRM-owned names (P5) are never overwritten.
        contact.display_name = name
    consent = dict(contact.consent) if isinstance(contact.consent, dict) else {}
    consent.setdefault(
        "website",
        {"granted_at": now.isoformat(), "text_version": CONSENT_TEXT_VERSION},
    )
    contact.consent = consent
    contact.updated_at = now
    db.add(contact)
    db.flush()

    # Website identity for the session (idempotent).
    identity = (
        db.execute(
            select(ContactIdentity).where(
                ContactIdentity.tenant_id == visitor_session.tenant_id,
                ContactIdentity.channel == "website",
                ContactIdentity.external_id == str(visitor_session.id),
            )
        )
        .scalars()
        .first()
    )
    if identity is None:
        db.add(
            ContactIdentity(
                tenant_id=visitor_session.tenant_id,
                contact_id=contact.id,
                channel="website",
                external_id=str(visitor_session.id),
            )
        )
    db.flush()

    # Bind the conversation to the contact (composite FK stays tenant-scoped).
    conversation = (
        db.execute(
            select(Conversation).where(
                Conversation.tenant_id == visitor_session.tenant_id,
                Conversation.session_id == visitor_session.id,
            )
        )
        .scalars()
        .first()
    )
    if conversation is not None:
        conversation.contact_id = contact.id
        db.add(conversation)

    record_usage_event(
        db,
        tenant_id=visitor_session.tenant_id,
        bot_id=visitor_session.bot_id,
        kind="lead",
        external_key=f"lead:{visitor_session.id}",
        conversation_id=conversation.id if conversation is not None else None,
    )
    db.commit()
    return {
        "contact_id": str(contact.id),
        "created": created,
        "display_name": contact.display_name,
        "email": str(contact.email) if contact.email else None,
        "phone": contact.phone,
    }


def widget_feedback(
    db: OrmSession,
    *,
    visitor_session: VisitorSession,
    message_id: UUID,
    rating: str,
) -> None:
    """Thumbs up/down from the widget (docs/09 / docs/14 §11): idempotent per
    message + session through the same usage-event mechanism."""
    if rating not in ("up", "down"):
        raise ApiError(422, "VALIDATION_ERROR", "Rating must be up or down.")
    message = (
        db.execute(
            select(Message).where(
                Message.id == message_id,
                Message.tenant_id == visitor_session.tenant_id,
                Message.bot_id == visitor_session.bot_id,
                Message.sender_type == "ai",
            )
        )
        .scalars()
        .one_or_none()
    )
    if message is None:
        raise ApiError(404, "NOT_FOUND", "Resource not found.")
    record_usage_event(
        db,
        tenant_id=visitor_session.tenant_id,
        bot_id=visitor_session.bot_id,
        kind="feedback_up" if rating == "up" else "feedback_down",
        external_key=f"feedback:{rating}:{message_id}:{visitor_session.id}",
        message_id=message.id,
        conversation_id=message.conversation_id,
    )
    db.commit()
