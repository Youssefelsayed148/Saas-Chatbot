"""Idempotent storage handlers for authenticated ManyOsirisChat events."""

import unicodedata
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

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

_STATUS_RANK = {"pending": 0, "sent": 1, "delivered": 2, "read": 3}
_HEALTH = {
    "connected": "healthy",
    "token_expiring": "degraded",
    "webhook_unhealthy": "degraded",
    "token_expired": "unhealthy",
    "disconnected": "unhealthy",
}


def _clean(value: object, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = "".join(char for char in value if not unicodedata.category(char).startswith("C"))
    cleaned = " ".join(cleaned.split()).strip()[:limit]
    return cleaned or None


def _event_time(payload: dict[str, Any], key: str = "occurred_at") -> datetime:
    value = payload.get(key)
    if not isinstance(value, str):
        return datetime.now(UTC)
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


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
    if identity is not None:
        return identity
    contact_data = payload.get("contact", {})
    contact_data = contact_data if isinstance(contact_data, dict) else {}
    name = _clean(contact_data.get("name"), 120)
    phone = _clean(contact_data.get("phone"), 40)
    handle = _clean(contact_data.get("handle"), 120)
    contact = Contact(
        tenant_id=connection.tenant_id,
        display_name=name or handle or phone or "Channel visitor",
        phone=phone,
        source_channel=payload["channel"],
        custom_fields={"channel_handle": handle} if handle else {},
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
            origin=origin if isinstance(origin, dict) else None,
            mode="ai",
            status="open",
            source="channel",
        )
        db.add(conversation)
        db.flush()
    elif conversation.origin is None and isinstance(payload.get("origin"), dict):
        # First available origin sticks; later messages cannot rewrite it.
        conversation.origin = payload["origin"]
    return conversation


def _received(
    db: OrmSession, connection: ChannelConnection, payload: dict[str, Any]
) -> tuple[Conversation, Message | None, bool]:
    identity = _identity(db, connection=connection, payload=payload)
    conversation = _conversation(
        db, connection=connection, identity=identity, payload=payload
    )
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
        text = (
            "تعذر عرض هذه الرسالة."
            if payload["channel"] in {"whatsapp", "messenger", "instagram"}
            else "Unsupported message type."
        )
        conversation.status = "waiting_human"
    elif connection.status == "paused":
        conversation.status = "waiting_human"
    message = Message(
        tenant_id=connection.tenant_id,
        bot_id=connection.bot_id,
        conversation_id=conversation.id,
        sender_type="visitor",
        text=text,
        channel_message_id=external_message_id,
        created_at=_event_time(payload, "received_at"),
    )
    db.add(message)
    now = datetime.now(UTC)
    conversation.last_message_at = now
    conversation.updated_at = now
    db.add(conversation)
    db.flush()
    return conversation, message, True


def _message_status(db: OrmSession, connection: ChannelConnection, payload: dict[str, Any]) -> None:
    message_id = payload.get("message_id")
    statement = select(Message).join(
        Conversation,
        (Conversation.tenant_id == Message.tenant_id)
        & (Conversation.id == Message.conversation_id),
    ).where(
        Message.tenant_id == connection.tenant_id,
        Conversation.connection_id == connection.id,
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
    incoming = str(payload["status"])
    current = message.delivery_status or "pending"
    if incoming == "failed":
        if _STATUS_RANK.get(current, 0) < _STATUS_RANK["delivered"]:
            message.delivery_status = "failed"
            message.error_code = _clean(payload.get("error_code"), 64)
    elif current != "failed" and _STATUS_RANK[incoming] > _STATUS_RANK.get(current, 0):
        message.delivery_status = incoming


def _channel_status(connection: ChannelConnection, payload: dict[str, Any]) -> None:
    occurred_at = _event_time(payload)
    if connection.health_updated_at is not None and occurred_at < connection.health_updated_at:
        return
    status = payload["status"]
    connection.health_status = _HEALTH[status]
    connection.health_reason = status
    connection.health_detail = _clean(payload.get("detail"), 200)
    connection.health_updated_at = occurred_at
    connection.updated_at = datetime.now(UTC)


def run_channel_inbound(
    db: OrmSession, job: Job, settings: Settings | None = None
) -> str | None:
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
    payload = event.payload
    if event.event_type == "message.received":
        conversation, visitor_message, is_new = _received(db, connection, payload)
        if is_new and visitor_message is not None:
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
    elif event.event_type == "message.status":
        _message_status(db, connection, payload)
    elif event.event_type == "channel.status":
        _channel_status(connection, payload)
    else:
        event.status = "ignored"
        event.processed_at = datetime.now(UTC)
        return None
    event.status = "processed"
    event.processed_at = datetime.now(UTC)
    return None
