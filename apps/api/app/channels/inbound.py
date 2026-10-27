"""Idempotent storage handlers for authenticated ManyOsirisChat events."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as OrmSession

from app.channels.config import CHANNEL_ERROR_CODES
from app.channels.guard import conversation_turn_lock
from app.channels.health import apply_health, clean_text
from app.chat.conversations import channel_chat_turn
from app.core.config import Settings, get_settings
from app.db.models import (
    Bot,
    ChannelConnection,
    ChannelEvent,
    Contact,
    ContactIdentity,
    Conversation,
    Job,
    Message,
)
from app.inbox.events import add_inbox_event

_STATUS_RANK = {"pending": 0, "unconfirmed": 0, "sent": 1, "delivered": 2, "read": 3}


def _clean(value: object, limit: int) -> str | None:
    return clean_text(value, limit)


def _event_time(payload: dict[str, Any], key: str = "occurred_at") -> datetime:
    value = payload.get(key)
    if not isinstance(value, str):
        return datetime.now(UTC)
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def clamp_received_at(payload: dict[str, Any], now: datetime | None = None) -> datetime:
    """Many's ``received_at`` limited to [now-24h, now+5min]; otherwise our own clock
    (contract v1.1 A10), so a skewed or hostile clock cannot reorder a thread."""
    now = now or datetime.now(UTC)
    try:
        claimed = _event_time(payload, "received_at")
    except ValueError:
        return now
    if not now - timedelta(hours=24) <= claimed <= now + timedelta(minutes=5):
        return now
    return claimed


def _refresh_contact(contact: Contact, data: dict[str, Any]) -> None:
    """Later events refresh name, phone and handle, but never overwrite what staff
    typed: a field is replaced only if it is empty, the placeholder, or still the
    value this channel gave us last time."""
    fields = dict(contact.custom_fields or {})
    name = _clean(data.get("name"), 120)
    phone = _clean(data.get("phone"), 40)
    handle = _clean(data.get("handle"), 120)
    if name and name != fields.get("channel_name"):
        if contact.display_name in {None, "", "Channel visitor", fields.get("channel_name")} or (
            contact.display_name == fields.get("channel_handle")
        ):
            contact.display_name = name
        fields["channel_name"] = name
    if phone and phone != fields.get("channel_phone"):
        if not contact.phone or contact.phone == fields.get("channel_phone"):
            contact.phone = phone
        fields["channel_phone"] = phone
    if handle:
        fields["channel_handle"] = handle
    if fields != (contact.custom_fields or {}):
        contact.custom_fields = fields


def _identity(
    db: OrmSession, *, connection: ChannelConnection, payload: dict[str, Any]
) -> ContactIdentity:
    external_id = payload["external_contact_id"]
    identity = db.scalar(
        select(ContactIdentity).where(
            ContactIdentity.tenant_id == connection.tenant_id,
            ContactIdentity.connection_id == connection.id,
            ContactIdentity.external_id == external_id,
        )
    )
    contact_data = payload.get("contact", {})
    contact_data = contact_data if isinstance(contact_data, dict) else {}
    if identity is not None:
        contact = db.scalar(
            select(Contact).where(
                Contact.tenant_id == connection.tenant_id, Contact.id == identity.contact_id
            )
        )
        if contact is not None:
            _refresh_contact(contact, contact_data)
        return identity
    name = _clean(contact_data.get("name"), 120)
    phone = _clean(contact_data.get("phone"), 40)
    handle = _clean(contact_data.get("handle"), 120)
    contact = Contact(
        tenant_id=connection.tenant_id,
        display_name=name or handle or phone or "Channel visitor",
        phone=phone,
        source_channel=payload["channel"],
        custom_fields={
            key: value
            for key, value in (
                ("channel_handle", handle),
                ("channel_name", name),
                ("channel_phone", phone),
            )
            if value
        },
    )
    db.add(contact)
    db.flush()
    identity = ContactIdentity(
        tenant_id=connection.tenant_id,
        contact_id=contact.id,
        channel=payload["channel"],
        external_id=external_id,
        connection_id=connection.id,
    )
    db.add(identity)
    db.flush()
    return identity


def _clean_origin(origin: object) -> dict[str, object] | None:
    """Only the contract's origin fields are stored (already length-validated)."""
    if not isinstance(origin, dict):
        return None
    keep: dict[str, object] = {
        key: origin[key]
        for key in ("type", "campaign_name", "opening_message_text", "campaign_ref")
        if isinstance(origin.get(key), str)
    }
    return keep or None


def _conversation(
    db: OrmSession,
    *,
    connection: ChannelConnection,
    identity: ContactIdentity,
    payload: dict[str, Any],
) -> Conversation:
    external_id = payload["external_conversation_id"]
    conversation = db.scalar(
        select(Conversation).where(
            Conversation.tenant_id == connection.tenant_id,
            Conversation.connection_id == connection.id,
            Conversation.external_conversation_id == external_id,
        )
    )
    if conversation is None:
        origin = payload.get("origin")
        conversation = Conversation(
            tenant_id=connection.tenant_id,
            bot_id=connection.bot_id,
            contact_id=identity.contact_id,
            channel=payload["channel"],
            connection_id=connection.id,
            external_conversation_id=external_id,
            origin=_clean_origin(origin),
            mode="ai",
            status="open",
            source="channel",
        )
        try:
            with db.begin_nested():
                db.add(conversation)
                db.flush()
        except IntegrityError:
            # Lost a creation race (the turn lock normally prevents it): reuse the winner.
            conversation = db.scalar(
                select(Conversation).where(
                    Conversation.tenant_id == connection.tenant_id,
                    Conversation.connection_id == connection.id,
                    Conversation.external_conversation_id == external_id,
                )
            )
            assert conversation is not None
    elif conversation.origin is None and _clean_origin(payload.get("origin")) is not None:
        # First available origin sticks; later messages cannot rewrite it.
        conversation.origin = _clean_origin(payload["origin"])
    return conversation


_UNSUPPORTED_PLACEHOLDER = {
    "en": "Unsupported message type.",
    "ar": "تعذر عرض هذه الرسالة.",
}


def _received(
    db: OrmSession,
    connection: ChannelConnection,
    payload: dict[str, Any],
    bot_language: str = "en",
) -> tuple[Conversation, Message | None, bool]:
    identity = _identity(db, connection=connection, payload=payload)
    conversation = _conversation(db, connection=connection, identity=identity, payload=payload)
    external_message_id = payload["external_message_id"]
    exists = db.scalar(
        select(Message.id).where(
            Message.tenant_id == connection.tenant_id,
            Message.conversation_id == conversation.id,
            Message.sender_type == "visitor",
            Message.channel_message_id == external_message_id,
        )
    )
    if exists is not None:
        message = db.get(Message, exists)
        return conversation, message, False
    text = payload.get("text", "")
    if payload.get("type") == "unsupported":
        # Localized by the bot language; gating and handoff happen in the turn.
        text = _UNSUPPORTED_PLACEHOLDER.get(bot_language, _UNSUPPORTED_PLACEHOLDER["en"])
    message = Message(
        tenant_id=connection.tenant_id,
        bot_id=connection.bot_id,
        conversation_id=conversation.id,
        sender_type="visitor",
        text=text,
        channel_message_id=external_message_id,
        created_at=clamp_received_at(payload),
    )
    db.add(message)
    now = datetime.now(UTC)
    conversation.last_message_at = now
    conversation.updated_at = now
    db.add(conversation)
    db.flush()
    # Publish on the shared inbox SSE cursor like every other message.append;
    # without it a waiting-human inbound is invisible to open inboxes (P6-05b).
    add_inbox_event(
        db,
        tenant_id=connection.tenant_id,
        conversation_id=conversation.id,
        message_id=message.id,
        event_type="message.created",
    )
    return conversation, message, True


def _message_status(db: OrmSession, connection: ChannelConnection, payload: dict[str, Any]) -> None:
    message_id = payload.get("message_id")
    statement = (
        select(Message)
        .join(
            Conversation,
            (Conversation.tenant_id == Message.tenant_id)
            & (Conversation.id == Message.conversation_id),
        )
        .where(
            Message.tenant_id == connection.tenant_id,
            Conversation.connection_id == connection.id,
            Message.sender_type.in_(("ai", "agent")),
        )
        .with_for_update(of=Message)
        .execution_options(populate_existing=True)
    )
    if message_id:
        try:
            message_uuid = UUID(str(message_id))
        except ValueError:
            return
        statement = statement.where(Message.id == message_uuid)
    else:
        statement = statement.where(
            Message.channel_message_id == payload.get("external_message_id")
        )
    message = db.scalar(statement)
    if message is None:
        return
    previous_state = (message.delivery_status, message.error_code)
    incoming = str(payload["status"])
    current = message.delivery_status or "pending"
    if incoming == "failed":
        if _STATUS_RANK.get(current, 0) < _STATUS_RANK["delivered"]:
            message.delivery_status = "failed"
            code = _clean(payload.get("error_code"), 64)
            message.error_code = code if code in CHANNEL_ERROR_CODES else "unknown"
    elif current != "failed" and _STATUS_RANK[incoming] > _STATUS_RANK.get(current, 0):
        message.delivery_status = incoming
    if previous_state != (message.delivery_status, message.error_code):
        add_inbox_event(
            db,
            tenant_id=message.tenant_id,
            conversation_id=message.conversation_id,
            message_id=message.id,
            event_type="message.delivery",
        )


def _channel_status(db: OrmSession, connection: ChannelConnection, payload: dict[str, Any]) -> None:
    """Pushed ``channel.status`` (docs/17 §4.3): newest wins, audited."""
    # A future ``occurred_at`` (skewed Many clock) must not shadow later genuine signals,
    # the same clamp the pull path applies in health.parse_health_body.
    occurred_at = min(_event_time(payload), datetime.now(UTC))
    apply_health(
        db,
        connection,
        status=payload["status"],
        detail=clean_text(payload.get("detail"), 200),
        occurred_at=occurred_at,
        source="event",
    )


def _earlier_pending(db: OrmSession, event: ChannelEvent) -> list[ChannelEvent]:
    """Unprocessed ``message.received`` events of the same conversation that arrived
    before ``event`` (receipt time, then id), oldest first."""
    return list(
        db.scalars(
            select(ChannelEvent)
            .where(
                ChannelEvent.tenant_id == event.tenant_id,
                ChannelEvent.connection_id == event.connection_id,
                ChannelEvent.event_type == "message.received",
                ChannelEvent.status == "received",
                ChannelEvent.id != event.id,
                ChannelEvent.payload["external_conversation_id"].as_string()
                == str((event.payload or {}).get("external_conversation_id")),
                (ChannelEvent.received_at < event.received_at)
                | ((ChannelEvent.received_at == event.received_at) & (ChannelEvent.id < event.id)),
            )
            .order_by(ChannelEvent.received_at, ChannelEvent.id)
            .with_for_update()
        )
    )


def _unanswered(db: OrmSession, visitor_message: Message) -> bool:
    """True when nothing (AI, staff or system) followed the stored visitor message."""
    later = db.scalar(
        select(Message.id)
        .where(
            Message.tenant_id == visitor_message.tenant_id,
            Message.conversation_id == visitor_message.conversation_id,
            Message.sender_type != "visitor",
            Message.created_at >= visitor_message.created_at,
        )
        .limit(1)
    )
    return later is None


def _handle_received(
    db: OrmSession,
    event: ChannelEvent,
    connection: ChannelConnection,
    bot: Bot,
    settings: Settings,
) -> None:
    payload = event.payload
    if payload is None:  # purged by retention before it was processed
        event.status = "ignored"
        event.error_code = "payload_purged"
        event.processed_at = datetime.now(UTC)
        return
    bot_language = (
        str(bot.config.get("default_language", "en")) if isinstance(bot.config, dict) else "en"
    )
    conversation, visitor_message, is_new = _received(db, connection, payload, bot_language)
    # reserve() commits the visitor message mid-turn, so a crashed turn leaves it stored
    # with no reply. The queue retry finds it (is_new is False) and must run the turn
    # again; a genuine duplicate already has its reply (or handoff notice) and does not.
    if visitor_message is not None and (is_new or _unanswered(db, visitor_message)):
        channel_chat_turn(
            db,
            tenant_id=connection.tenant_id,
            bot=bot,
            conversation=conversation,
            connection=connection,
            visitor_message=visitor_message,
            question=str(payload.get("text", "")),
            supported=payload.get("type") == "text",
            settings=settings,
        )
    event.status = "processed"
    event.processed_at = datetime.now(UTC)
    # Make the turn visible before the next waiting event takes the lock.
    db.commit()


def run_channel_inbound(db: OrmSession, job: Job, settings: Settings | None = None) -> str | None:
    """Process a channel event with tenant/bot authority taken only from its connection."""
    settings = settings or get_settings()
    raw_event_id = job.payload.get("channel_event_id")
    try:
        event_id = UUID(str(raw_event_id))
    except (ValueError, TypeError):
        return "Invalid channel event reference."
    event = db.scalar(
        select(ChannelEvent).where(
            ChannelEvent.id == event_id,
            ChannelEvent.tenant_id == job.tenant_id,
        )
    )
    if event is None:
        return None
    if event.status in {"processed", "ignored"}:
        return None
    connection = db.scalar(
        select(ChannelConnection).where(
            ChannelConnection.id == event.connection_id,
            ChannelConnection.tenant_id == event.tenant_id,
        )
    )
    if connection is None or connection.status == "revoked":
        event.status = "ignored"
        event.error_code = "connection_unavailable"
        event.processed_at = datetime.now(UTC)
        return None
    bot = db.scalar(
        select(Bot).where(Bot.id == connection.bot_id, Bot.tenant_id == connection.tenant_id)
    )
    if bot is None:
        event.status = "ignored"
        event.error_code = "connection_bot_unavailable"
        event.processed_at = datetime.now(UTC)
        return None
    if event.payload is None:
        # Purged by retention before it was processed: nothing left to act on.
        event.status = "ignored"
        event.error_code = "payload_purged"
        event.processed_at = datetime.now(UTC)
        return None
    payload = event.payload
    if event.event_type == "message.received":
        # One event at a time per conversation, held for the whole turn (several
        # workers, commits inside the turn): see conversation_turn_lock.
        with conversation_turn_lock(db, connection.id, str(payload["external_conversation_id"])):
            # Order of receipt (A7): events of this conversation that arrived earlier
            # and are still unprocessed (their job lost the race for the lock, or is
            # waiting for a retry) run first. Their own jobs then find them processed.
            db.refresh(event)
            if event.status not in {"processed", "ignored"}:
                for earlier in _earlier_pending(db, event):
                    _handle_received(db, earlier, connection, bot, settings)
                _handle_received(db, event, connection, bot, settings)
        return None
    elif event.event_type == "message.status":
        _message_status(db, connection, payload)
    elif event.event_type == "channel.status":
        _channel_status(db, connection, payload)
    else:
        event.status = "ignored"
        event.processed_at = datetime.now(UTC)
        return None
    event.status = "processed"
    event.processed_at = datetime.now(UTC)
    return None
