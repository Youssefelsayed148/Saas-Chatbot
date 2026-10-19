"""Transactional channel outbox and signed, DNS-pinned delivery to Many."""

import ipaddress
import json
import random
import re
import socket
import time
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Literal
from uuid import UUID

import httpx
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.channels.config import (
    REPLY_CHAR_LIMITS,
    SEND_BACKOFF_SECONDS,
    SEND_CONNECT_SECONDS,
    SEND_MAX_ATTEMPTS,
    SEND_READ_SECONDS,
    SEND_RESPONSE_BYTES,
)
from app.channels.router import _validate_base_url
from app.channels.secrets import decrypt_secret
from app.channels.signing import sign
from app.core.config import Settings
from app.core.errors import ApiError
from app.db.models import ChannelConnection, ContactIdentity, Conversation, Job, Message
from app.inbox.events import add_inbox_event
from app.jobs.queue import enqueue_job


class OutboundPayload(BaseModel):
    message_id: UUID
    connection_id: UUID
    external_contact_id: str = Field(min_length=1, max_length=64 * 1024)
    external_conversation_id: str = Field(min_length=1, max_length=64 * 1024)
    text: str = Field(min_length=1)
    kind: Literal["reply", "agent", "handoff"]


PERMANENT_CODES = {"window_closed", "template_required", "recipient_unreachable"}


class SendRetry(Exception):
    """A sanitized retry outcome; never carry request/response content."""

    def __init__(self, delay: float) -> None:
        super().__init__("Many is temporarily unavailable.")
        self.delay = delay


class UnsafeTarget(Exception):
    pass


def split_reply(text: str, channel: str) -> list[str]:
    limit = REPLY_CHAR_LIMITS[channel]
    parts: list[str] = []
    while len(text) > limit:
        prefix = text[: limit + 1]
        boundaries = list(re.finditer(r"[.!?؟。！]\s+|\n+", prefix))
        cut = boundaries[-1].end() if boundaries else prefix.rfind(" ") + 1
        if cut <= 0 or cut > limit:
            cut = limit
        parts.append(text[:cut])
        text = text[cut:]
    if text or not parts:
        parts.append(text)
    return parts


def enqueue_message(
    db: Session, conversation: Conversation, message: Message, settings: Settings
) -> None:
    """Split stored text and enqueue exactly one job per part; caller commits."""
    if conversation.source != "channel" or message.sender_type not in {"ai", "agent"}:
        return
    # Serialize on the conversation, also preventing repeated enqueues of this message.
    db.execute(
        select(Conversation.id)
        .where(
            Conversation.tenant_id == conversation.tenant_id,
            Conversation.id == conversation.id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    existing = db.scalar(
        select(Job.id).where(
            Job.tenant_id == message.tenant_id,
            Job.type == "channel_send",
            Job.payload["message_id"].astext == str(message.id),
        )
    )
    if existing is not None:
        return
    parts = split_reply(message.text, conversation.channel)
    message.text = parts[0]
    previous_id: UUID | None = None
    for index, text in enumerate(parts):
        part = message
        if index:
            part = Message(
                tenant_id=message.tenant_id,
                bot_id=message.bot_id,
                conversation_id=message.conversation_id,
                sender_type=message.sender_type,
                sender_user_id=message.sender_user_id,
                text=text,
                citations=message.citations,
                can_answer=message.can_answer,
                needs_human=message.needs_human,
                created_at=message.created_at + timedelta(microseconds=index),
            )
            db.add(part)
            db.flush()
        part.delivery_status = "pending"
        payload = {"message_id": str(part.id)}
        if previous_id is not None:
            payload["previous_message_id"] = str(previous_id)
        job = enqueue_job(
            db,
            tenant_id=part.tenant_id,
            bot_id=part.bot_id,
            job_type="channel_send",
            payload=payload,
            created_by=part.sender_user_id,
            settings=settings,
        )
        job.max_attempts = SEND_MAX_ATTEMPTS
        previous_id = part.id


def resolve_target(base_url: str, settings: Settings) -> tuple[httpx.URL, str]:
    """Resolve once, reject every non-global answer and pin TCP to that IP.

    Host and TLS SNI still use the original host; TLS certificate verification
    remains enabled. No second hostname resolution, proxies, or redirects.
    """
    try:
        url = httpx.URL(_validate_base_url(base_url, settings) + "/api/saas/messages")
        addresses = socket.getaddrinfo(
            url.host, url.port or (443 if url.scheme == "https" else 80), type=socket.SOCK_STREAM
        )
        ips = [str(answer[4][0]) for answer in addresses]
        if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):
            raise UnsafeTarget
        return url.copy_with(host=ips[0]), url.host
    except (ApiError, ValueError, httpx.InvalidURL) as exc:
        raise UnsafeTarget from exc


def _client() -> httpx.Client:
    return httpx.Client(
        follow_redirects=False,
        trust_env=False,
        timeout=httpx.Timeout(SEND_READ_SECONDS, connect=SEND_CONNECT_SECONDS),
    )


def post_message(
    url: httpx.URL, hostname: str, body: bytes, headers: dict[str, str]
) -> tuple[int, str | None, bytes]:
    # Preserve the original authority (including a non-default port) for Host.
    authority = f"[{hostname}]" if ":" in hostname else hostname
    if url.port is not None:
        authority += f":{url.port}"
    with (
        _client() as client,
        client.stream(
            "POST",
            url,
            content=body,
            headers={**headers, "Host": authority},
            extensions={"sni_hostname": hostname},
        ) as response,
    ):
        raw = bytearray()
        for chunk in response.iter_raw(chunk_size=4096):
            raw.extend(chunk)
            if len(raw) > SEND_RESPONSE_BYTES:
                raise ValueError("Many response exceeds the size limit.")
        return response.status_code, response.headers.get("Retry-After"), bytes(raw)


def retry_delay(attempt: int, retry_after: str | None = None) -> float:
    backoff = SEND_BACKOFF_SECONDS * 2 ** max(0, attempt - 1) * random.uniform(0.8, 1.2)
    if retry_after:
        try:
            delay = float(retry_after)
        except ValueError:
            try:
                delay = (parsedate_to_datetime(retry_after) - datetime.now(UTC)).total_seconds()
            except (ValueError, TypeError, OverflowError):
                delay = 0
        if 0 <= delay < float("inf"):
            backoff = max(backoff, delay)
    return float(backoff)


def _changed(db: Session, message: Message) -> None:
    add_inbox_event(
        db,
        tenant_id=message.tenant_id,
        conversation_id=message.conversation_id,
        message_id=message.id,
        event_type="message.delivery",
    )


def _fail(db: Session, message: Message, code: str) -> None:
    message.delivery_status = "failed"
    message.error_code = code
    _changed(db, message)


def run_channel_send(db: Session, job: Job, settings: Settings) -> str | None:
    try:
        message_id = UUID(str(job.payload.get("message_id")))
    except ValueError:
        return None
    message = db.scalar(
        select(Message)
        .where(
            Message.tenant_id == job.tenant_id,
            Message.bot_id == job.bot_id,
            Message.id == message_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (
        message is None
        or message.sender_type not in {"ai", "agent"}
        or message.channel_message_id
        or message.delivery_status in {"failed", "sent", "delivered", "read"}
    ):
        return None
    conversation = db.scalar(
        select(Conversation).where(
            Conversation.tenant_id == job.tenant_id,
            Conversation.bot_id == job.bot_id,
            Conversation.id == message.conversation_id,
            Conversation.source == "channel",
        )
    )
    if conversation is None:
        return None
    connection = db.scalar(
        select(ChannelConnection)
        .where(
            ChannelConnection.tenant_id == job.tenant_id,
            ChannelConnection.bot_id == job.bot_id,
            ChannelConnection.id == conversation.connection_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if connection is None or connection.status != "active":
        _fail(db, message, "connection_paused")
        return None
    previous_id = job.payload.get("previous_message_id")
    if previous_id:
        previous = db.scalar(
            select(Message).where(
                Message.tenant_id == job.tenant_id,
                Message.conversation_id == conversation.id,
                Message.id == UUID(str(previous_id)),
            )
        )
        if previous is None or previous.delivery_status == "failed":
            _fail(db, message, "previous_part_failed")
            return None
        if previous.channel_message_id is None:
            # Ordering wait is not a delivery attempt and consumes no retry budget.
            job.attempts = max(0, job.attempts - 1)
            raise SendRetry(5)
    identity = db.scalar(
        select(ContactIdentity).where(
            ContactIdentity.tenant_id == job.tenant_id,
            ContactIdentity.connection_id == connection.id,
            ContactIdentity.contact_id == conversation.contact_id,
        )
    )
    if identity is None or not conversation.external_conversation_id:
        _fail(db, message, "channel_recipient_missing")
        return None
    retry_after = None
    try:
        url, hostname = resolve_target(connection.many_base_url, settings)
        body = (
            OutboundPayload(
                message_id=message.id,
                connection_id=connection.id,
                external_contact_id=identity.external_id,
                external_conversation_id=conversation.external_conversation_id,
                text=message.text,
                kind="agent"
                if message.sender_type == "agent"
                else ("handoff" if message.needs_human else "reply"),
            )
            .model_dump_json()
            .encode("utf-8")
        )
        timestamp = int(time.time())
        secret = decrypt_secret(
            connection.secret_ciphertext, settings.channel_secret_encryption_keys
        )
        status, retry_after, raw = post_message(
            url,
            hostname,
            body,
            {
                "Content-Type": "application/json",
                "X-Osiris-Connection": str(connection.id),
                "X-Osiris-Timestamp": str(timestamp),
                "X-Osiris-Signature": sign(secret, timestamp, body),
            },
        )
        if status == 202:
            data = json.loads(raw)
            many_id = data.get("id") if isinstance(data, dict) else None
            if not isinstance(many_id, str) or not many_id.strip() or len(many_id) > 512:
                raise ValueError("Invalid Many acknowledgement.")
            message.channel_message_id = many_id
            # The callback alone advances the delivery state.
            return None
        if 400 <= status < 500 and status != 429:
            try:
                data = json.loads(raw)
                code = data.get("error_code") if isinstance(data, dict) else None
            except ValueError:
                code = None
            _fail(
                db,
                message,
                code
                if isinstance(code, str) and code in PERMANENT_CODES
                else f"many_http_{status}",
            )
            return None
        if 300 <= status < 400 or 200 <= status < 300:
            _fail(db, message, "many_invalid_response")
            return None
    except UnsafeTarget:
        _fail(db, message, "invalid_many_target")
        return None
    except (httpx.HTTPError, OSError, ValueError):
        # Never persist/log exception strings (they can contain text or secrets).
        pass
    if job.attempts >= job.max_attempts:
        _fail(db, message, "many_unreachable")
        connection.health_status = "degraded"
        connection.health_reason = "many_unreachable"
        connection.health_updated_at = datetime.now(UTC)
        return "Many could not be reached within the delivery retry budget."
    raise SendRetry(retry_delay(job.attempts, retry_after))
