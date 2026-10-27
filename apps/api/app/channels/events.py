"""Authenticated server-to-server event ingestion for ManyOsirisChat."""

import json
import logging
import time
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as OrmSession

from app.channels.secrets import signing_secrets
from app.channels.signing import verify
from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.core.ratelimit import rate_limit
from app.db.models import ChannelConnection, ChannelEvent
from app.db.session import get_session
from app.jobs.queue import enqueue_job

logger = logging.getLogger(__name__)
router = APIRouter(tags=["channel-events"])
DbSession = Annotated[OrmSession, Depends(get_session)]
CurrentSettings = Annotated[Settings, Depends(get_settings)]
MAX_BODY_BYTES = 64 * 1024
EVENTS_PER_MINUTE = 300


def _unauthorized(reason: str) -> ApiError:
    # The reason is an internal enum only; never log request content or secrets.
    logger.info("ManyOsirisChat event authentication rejected (%s)", reason)
    return ApiError(401, "UNAUTHORIZED", "Invalid channel request.")


async def _raw_body(request: Request) -> bytes:
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_BODY_BYTES:
                raise _unauthorized("body_too_large")
        except ValueError:
            raise _unauthorized("invalid_content_length") from None
    parts: list[bytes] = []
    size = 0
    async for part in request.stream():
        size += len(part)
        if size > MAX_BODY_BYTES:
            raise _unauthorized("body_too_large")
        parts.append(part)
    return b"".join(parts)


def _parse_time(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp")
    return parsed.astimezone(UTC)


ORIGIN_FIELD_LIMITS = {
    "campaign_name": 120,
    "opening_message_text": 2000,
    "campaign_ref": 128,
}


def _validate_payload(
    payload: object, connection_id: UUID, connection_channel: str
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("object")
    if payload.get("version") != 1:
        raise ValueError("version")
    event_id = payload.get("event_id")
    event_type = payload.get("event_type")
    if not isinstance(event_id, str) or not 1 <= len(event_id) <= 128:
        raise ValueError("event_id")
    if not isinstance(event_type, str) or not 1 <= len(event_type) <= 100:
        raise ValueError("event_type")
    if payload.get("connection_id") != str(connection_id):
        raise ValueError("connection_id")
    _parse_time(payload.get("occurred_at"))
    if event_type == "message.received":
        contact = payload.get("contact", {})
        if not isinstance(contact, dict):
            raise ValueError("contact")
        required = (
            "channel",
            "external_contact_id",
            "external_conversation_id",
            "external_message_id",
        )
        if any(not isinstance(payload.get(key), str) or not payload[key] for key in required):
            raise ValueError("message identifiers")
        if payload["channel"] not in {"whatsapp", "messenger", "instagram"}:
            raise ValueError("channel")
        # Tenant, bot and channel all come from the connection (contract v1.1 A1).
        if payload["channel"] != connection_channel:
            raise ValueError("channel mismatch")
        if payload.get("type") not in {"text", "unsupported"}:
            raise ValueError("message type")
        text = payload.get("text", "")
        if not isinstance(text, str) or len(text) > 4000:
            raise ValueError("message text")
        if payload.get("type") == "text" and not text:
            raise ValueError("message text")
        for key, maximum in (("name", 200), ("phone", 100), ("handle", 200)):
            value = contact.get(key)
            if value is not None and not isinstance(value, str):
                raise ValueError("contact field")
            if isinstance(value, str) and len(value) > maximum:
                raise ValueError("contact field")
        _parse_time(payload.get("received_at"))
        origin = payload.get("origin")
        if origin is not None:
            if not isinstance(origin, dict):
                raise ValueError("origin")
            if not isinstance(origin.get("type", "campaign"), str):
                raise ValueError("origin")
            for key, maximum in ORIGIN_FIELD_LIMITS.items():
                value = origin.get(key)
                if value is not None and (not isinstance(value, str) or len(value) > maximum):
                    raise ValueError("origin")
    elif event_type == "message.status":
        if not isinstance(payload.get("status"), str) or payload["status"] not in {
            "sent",
            "delivered",
            "read",
            "failed",
        }:
            raise ValueError("status")
        if not isinstance(payload.get("message_id") or payload.get("external_message_id"), str):
            raise ValueError("message identifier")
        if payload.get("error_code") is not None and not isinstance(payload["error_code"], str):
            raise ValueError("error_code")
        if payload.get("error_detail") is not None and (
            not isinstance(payload["error_detail"], str) or len(payload["error_detail"]) > 200
        ):
            raise ValueError("error_detail")
    elif event_type == "channel.status":
        if payload.get("status") not in {
            "connected",
            "token_expiring",
            "webhook_unhealthy",
            "token_expired",
            "disconnected",
        }:
            raise ValueError("status")
        if payload.get("detail") is not None and (
            not isinstance(payload["detail"], str) or len(payload["detail"]) > 200
        ):
            raise ValueError("detail")
    return payload


def _remove_jsonb_nul(value: Any) -> Any:
    """PostgreSQL JSONB cannot represent U+0000 in strings."""
    if isinstance(value, str):
        return value.replace("\x00", "")
    if isinstance(value, list):
        return [_remove_jsonb_nul(item) for item in value]
    if isinstance(value, dict):
        return {key: _remove_jsonb_nul(item) for key, item in value.items()}
    return value


@router.post("/api/channels/manyosiris/events", status_code=202)
async def receive_channel_event(
    request: Request, db: DbSession, settings: CurrentSettings
) -> JSONResponse:
    connection_header = request.headers.get("x-osiris-connection", "")
    timestamp = request.headers.get("x-osiris-timestamp", "")
    signature = request.headers.get("x-osiris-signature", "")
    try:
        connection_id = UUID(connection_header)
    except (ValueError, AttributeError):
        raise _unauthorized("unknown_connection") from None
    connection = db.scalar(select(ChannelConnection).where(ChannelConnection.id == connection_id))
    if connection is None or connection.status == "revoked":
        raise _unauthorized("unknown_or_revoked_connection")
    raw = await _raw_body(request)
    try:
        secrets = signing_secrets(connection, settings)
    except ValueError:
        secrets = ()
    if not secrets or not any(verify(secret, timestamp, raw, signature) for secret in secrets):
        raise _unauthorized("signature_or_timestamp")
    try:
        decoded = json.loads(raw.decode("utf-8"))
        payload = _remove_jsonb_nul(_validate_payload(decoded, connection_id, connection.channel))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError):
        raise ApiError(422, "VALIDATION_ERROR", "Signed event body failed validation.") from None
    if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
        raise ApiError(422, "VALIDATION_ERROR", "Signed event body failed validation.")

    now = datetime.now(UTC)
    count, _remaining = rate_limit(
        db,
        key=f"manyosiris-events:{connection_id}",
        limit=EVENTS_PER_MINUTE,
        window_seconds=60,
        now=now,
    )
    if count > EVENTS_PER_MINUTE:
        db.commit()
        retry_after = max(1, 60 - int(time.time()) % 60)
        return JSONResponse(
            status_code=429,
            headers={"Retry-After": str(retry_after)},
            content={"error": {"code": "RATE_LIMITED", "message": "Too many channel events."}},
        )

    existing = db.scalar(
        select(ChannelEvent).where(
            ChannelEvent.connection_id == connection_id,
            ChannelEvent.event_id == payload["event_id"],
        )
    )
    if existing is not None:
        db.commit()
        return JSONResponse(status_code=202, content={"status": "duplicate"})

    event = ChannelEvent(
        tenant_id=connection.tenant_id,
        connection_id=connection.id,
        event_id=payload["event_id"],
        event_type=payload["event_type"],
        payload=payload,
        status="received",
    )
    try:
        with db.begin_nested():
            db.add(event)
            db.flush()
            enqueue_job(
                db,
                tenant_id=connection.tenant_id,
                bot_id=connection.bot_id,
                job_type="channel_inbound",
                payload={"channel_event_id": str(event.id)},
                created_by=None,
                settings=settings,
            )
    except IntegrityError:
        existing = db.scalar(
            select(ChannelEvent).where(
                ChannelEvent.connection_id == connection_id,
                ChannelEvent.event_id == payload["event_id"],
            )
        )
        if existing is None:
            raise
        db.commit()
        return JSONResponse(status_code=202, content={"status": "duplicate"})
    connection.last_event_at = now
    db.commit()
    return JSONResponse(status_code=202, content={"status": "accepted"})
