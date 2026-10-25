"""Streamed chat turns over SSE (S.1-S.3, S.6).

Design: the buffered ``chat_answer`` pipeline stays the single source of
truth for routing, retrieval, the relevance gate, evidence assembly, reply
validation, handoff and persistence. Streaming only changes HOW the model
call is performed: ``StreamingReplyModel`` wraps the real ``ChatModel`` and,
for the one JSON-mode generation call, reads the provider stream through the
incremental parser, forwards released text as events and hands the complete
raw JSON back to ``chat_answer`` so the usual validation still runs. Nothing
in retrieval, the gate or the evidence helpers is touched.

Release guarantees (see ``json_stream``): no model text is sent before
``can_answer`` is true, at least one citation exists and every cited id is
valid evidence. Otherwise a single canned ``cannot_confirm`` event is sent
and the model text is dropped (the persisted reply is that canned text too).
Out-of-order keys, malformed JSON before release, a provider that cannot
stream: the call falls back to the buffered contract (the stream is read to
the end, nothing is released early, ``done`` carries the full text).

Events (all JSON): ``verdict`` {can_answer, released}, ``delta`` {text},
``cannot_confirm`` {text}, ``done`` {the buffered turn payload}, ``error``
{code, message}. ``done`` is authoritative: if the validated/persisted text
differs from what was streamed, the client replaces it.
"""

import asyncio
import json
import logging
import re
import threading
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.chat import prompts
from app.chat.conversations import visitor_chat_turn
from app.chat.json_stream import (
    AnswerDelta,
    IncrementalReplyParser,
    ReplyVerdict,
)
from app.chat.providers import (
    ChatModel,
    ExtractiveStubModel,
    ProviderError,
    StreamUnsupported,
)
from app.chat.service import (
    _default_answer_language,
    _support_contact,
    order_account_handoff_applies,
)
from app.core.config import Settings
from app.core.errors import ApiError
from app.db.models import Bot, Conversation, UsageEvent, VisitorSession
from app.db.session import get_engine, session_factory
from app.knowledge.language import detect_language

logger = logging.getLogger(__name__)

HEARTBEAT_SECONDS = 10.0
SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "X-Accel-Buffering": "no",
    "Connection": "keep-alive",
}

_EVIDENCE_MARKER = 'ids go into "sources"):\n'
_EVIDENCE_ID = re.compile(r"(?:\A|\n\n)\[([0-9a-f-]{36})\] ")


class StreamCancelled(Exception):
    """The client went away; stop the provider call and persist nothing."""


@dataclass
class StreamStats:
    """Private trace fields for the turn (S.6)."""

    streamed: bool = False
    # "streamed" | "canned" | "buffered" (parser fallback) | "unsupported"
    mode: str = "unsupported"
    ttft_ms: int | None = None
    invalid_reason: str | None = None

    def as_trace(self) -> dict[str, object]:
        return {
            "streamed": self.streamed,
            "stream_mode": self.mode,
            "time_to_first_token_ms": self.ttft_ms,
            "stream_invalid_reason": self.invalid_reason,
        }


def evidence_ids(system_prompt: str) -> frozenset[str]:
    """Chunk ids that the prompt offered as evidence (the valid citations).

    Read from the evidence block only (after the template's own marker). The
    authoritative validation still happens in ``chat_answer`` on the final
    text; a blank-line-plus-uuid inside a document can at worst release text
    that the validated result then replaces in ``done``."""
    _, _, region = system_prompt.partition(_EVIDENCE_MARKER)
    return frozenset(_EVIDENCE_ID.findall(region))


class StreamingReplyModel(ChatModel):
    """Wraps a ChatModel; streams the JSON-mode generation call."""

    def __init__(
        self,
        inner: ChatModel,
        *,
        emit: Callable[[str, dict[str, object]], None],
        cannot_confirm_text: str,
        cancelled: Callable[[], bool],
    ) -> None:
        self.inner = inner
        self._emit = emit
        self._cannot_confirm_text = cannot_confirm_text
        self._cancelled = cancelled
        self.stats = StreamStats()

    # -- attribute pass-through (metering/tracing read these off the model) --

    @property
    def usage_totals(self) -> dict[str, int] | None:
        return self.inner.usage_totals

    @usage_totals.setter
    def usage_totals(self, value: dict[str, int] | None) -> None:
        self.inner.usage_totals = value

    def __getattr__(self, name: str) -> Any:
        # Only called for attributes not found normally: delegate to the
        # real client (blocked, model_used, fallback_models, requests_used...).
        if name == "inner":
            raise AttributeError(name)
        return getattr(self.inner, name)

    # -- ChatModel -------------------------------------------------------

    def complete(self, messages: list[dict[str, str]], *, json_mode: bool, max_tokens: int) -> str:
        if not json_mode:
            return self.inner.complete(messages, json_mode=json_mode, max_tokens=max_tokens)
        started = perf_counter()
        parser = IncrementalReplyParser(evidence_ids(messages[0]["content"] if messages else ""))
        parts: list[str] = []
        mode = "streamed"  # "streamed" | "buffered" | "canned"
        stream = None
        try:
            stream = self.inner.stream_complete(messages, max_tokens=max_tokens)
            for fragment in stream:
                if self._cancelled():
                    raise StreamCancelled()
                parts.append(fragment)
                if mode != "streamed":
                    continue
                for event in parser.feed(fragment):
                    if isinstance(event, ReplyVerdict):
                        if not event.released:
                            mode = "canned"
                            self.stats.ttft_ms = round((perf_counter() - started) * 1000)
                            self._emit("cannot_confirm", {"text": self._cannot_confirm_text})
                            break
                        self._emit("verdict", {"can_answer": event.can_answer, "released": True})
                    elif isinstance(event, AnswerDelta):
                        if self.stats.ttft_ms is None:
                            self.stats.ttft_ms = round((perf_counter() - started) * 1000)
                        self._emit("delta", {"text": event.text})
                if mode == "streamed" and parser.invalid and not parser.released:
                    mode = "buffered"
                    self.stats.invalid_reason = parser.invalid_reason
                if mode == "canned":
                    break  # no more tokens needed: stop paying for text we drop
        except StreamUnsupported:
            if parts:
                raise ProviderError("The stream failed after it started.") from None
            self.stats.mode = "unsupported"
            return self.inner.complete(messages, json_mode=True, max_tokens=max_tokens)
        finally:
            close = getattr(stream, "close", None)
            if callable(close):
                close()
        self.stats.streamed = True
        if mode == "streamed" and parser.invalid:
            # Malformed after release: chat_answer's strict parse decides the
            # authoritative text; the client replaces what it showed.
            self.stats.invalid_reason = parser.invalid_reason
        self.stats.mode = mode
        if mode == "canned":
            return json.dumps(
                {"can_answer": False, "sources": [], "answer": self._cannot_confirm_text},
                ensure_ascii=False,
            )
        return "".join(parts)


class _StreamingStubModel(StreamingReplyModel, ExtractiveStubModel):
    """Keeps ``isinstance(model, ExtractiveStubModel)`` true so metering and
    tracing label the offline stub exactly as they do on the buffered path."""


def wrap_for_streaming(
    inner: ChatModel,
    *,
    emit: Callable[[str, dict[str, object]], None],
    cannot_confirm_text: str,
    cancelled: Callable[[], bool],
) -> StreamingReplyModel:
    cls = _StreamingStubModel if isinstance(inner, ExtractiveStubModel) else StreamingReplyModel
    return cls(
        inner,
        emit=emit,
        cannot_confirm_text=cannot_confirm_text,
        cancelled=cancelled,
    )


def cannot_confirm_for(bot: Bot, question: str, language_hint: str | None) -> str:
    """The canned text for this turn, resolved the way ``chat_answer`` does."""
    language = (
        detect_language(question)
        or (language_hint if language_hint in ("en", "ar") else None)
        or _default_answer_language(bot)
    )
    # A refusal on an order/account question ends as a handoff (chat_answer):
    # show the same text while it streams, so the final `done` does not change it.
    kind = "handoff" if order_account_handoff_applies(bot, question) else "cannot_confirm"
    return prompts.canned(kind, language, support_contact=_support_contact(bot))


def stamp_stream_trace(db: OrmSession, *, bot: Bot, ai_message_id: str, stats: StreamStats) -> None:
    """Add the streamed flag and time-to-first-token to the turn's private
    trace (the usage event payload ``rag_trace``). Fail-soft."""
    try:
        event = db.execute(
            select(UsageEvent).where(
                UsageEvent.tenant_id == bot.tenant_id,
                UsageEvent.bot_id == bot.id,
                UsageEvent.external_key == f"message:{ai_message_id}",
            )
        ).scalar_one_or_none()
        if event is None:
            return
        payload: dict[str, Any] = dict(event.payload or {})
        trace: dict[str, Any] = dict(payload.get("rag_trace") or {})
        trace.update(stats.as_trace())
        payload["rag_trace"] = trace
        event.payload = payload
        db.add(event)
        db.commit()
    except Exception:  # noqa: BLE001 - tracing must never fail a delivered answer
        db.rollback()
        logger.warning("chat.stream_trace_failed")


@dataclass
class StreamTurn:
    """What the route resolved up front (ids only; the worker re-reads rows
    in its own session)."""

    tenant_id: UUID
    bot_id: UUID
    visitor_session_id: UUID | None  # None for the staff playground
    conversation_id: UUID
    text: str
    language_hint: str | None
    settings: Settings
    model: ChatModel | None  # None: no model configured (canned busy reply)
    extra: dict[str, Any] = field(default_factory=dict)
    # Staff playground draft preview only; visitor_chat_turn refuses it on any other source.
    preview_revision_id: UUID | None = None


def run_turn(
    turn: StreamTurn, emit: Callable[[str, dict[str, object]], None], cancelled: Callable[[], bool]
) -> dict[str, Any]:
    """Blocking: the whole turn in a worker thread with its own DB session."""
    with session_factory(get_engine())() as db:
        bot = db.get(Bot, turn.bot_id)
        conversation = db.get(Conversation, turn.conversation_id)
        visitor_session = (
            db.get(VisitorSession, turn.visitor_session_id)
            if turn.visitor_session_id is not None
            else None
        )
        if (
            bot is None
            or conversation is None
            or bot.tenant_id != turn.tenant_id
            or conversation.tenant_id != turn.tenant_id
            or (turn.visitor_session_id is not None and visitor_session is None)
            or (visitor_session is not None and visitor_session.tenant_id != turn.tenant_id)
        ):
            raise ApiError(404, "NOT_FOUND", "Widget not found.")
        model = (
            wrap_for_streaming(
                turn.model,
                emit=emit,
                cannot_confirm_text=cannot_confirm_for(bot, turn.text, turn.language_hint),
                cancelled=cancelled,
            )
            if turn.model is not None
            else None
        )
        result = visitor_chat_turn(
            db,
            tenant_id=turn.tenant_id,
            bot=bot,
            conversation=conversation,
            question=turn.text,
            language_hint=turn.language_hint,
            model=model,
            settings=turn.settings,
            preview_revision_id=turn.preview_revision_id,
        )
        ai_message = result.get("ai_message")
        if ai_message and model is not None:
            stamp_stream_trace(db, bot=bot, ai_message_id=str(ai_message["id"]), stats=model.stats)
        return result


def sse(event: str, data: object) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def stream_events(
    turn: StreamTurn,
    shape_done: Callable[[dict[str, Any]], dict[str, Any]],
) -> AsyncGenerator[str]:
    """The SSE body. Runs the blocking turn in a worker thread and relays its
    events. If the consumer goes away (client disconnect cancels this
    generator) the worker is told to stop: the provider stream is closed, the
    turn rolls back and no partial answer is persisted."""
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[tuple[str, object]] = asyncio.Queue()
    cancel = threading.Event()

    def emit(kind: str, data: object) -> None:
        try:
            loop.call_soon_threadsafe(queue.put_nowait, (kind, data))
        except RuntimeError:  # loop already closed: nobody is listening
            pass

    def worker() -> None:
        try:
            result = run_turn(turn, emit, cancel.is_set)
            emit("done", shape_done(result))
        except StreamCancelled:
            logger.info("chat.stream_cancelled bot=%s", turn.bot_id)
        except ApiError as error:
            emit("error", {"code": error.code, "message": error.message})
        except ProviderError:
            emit("error", {"code": "MODEL_UNAVAILABLE", "message": "The assistant is unavailable."})
        except Exception:  # noqa: BLE001 - never leak internals into the stream
            logger.exception("chat.stream_failed bot=%s", turn.bot_id)
            emit("error", {"code": "INTERNAL_ERROR", "message": "Something went wrong."})
        finally:
            emit("end", None)

    future = loop.run_in_executor(None, worker)
    try:
        yield ": stream\n\n"
        while True:
            try:
                kind, data = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SECONDS)
            except TimeoutError:
                yield ": keep-alive\n\n"
                continue
            if kind == "end":
                break
            yield sse(kind, data)
    finally:
        cancel.set()
        del future  # the worker reports through the queue and never raises


def prepare_widget_stream(
    db: OrmSession,
    *,
    visitor_session: VisitorSession,
    bot: Bot,
    text: str,
    ip: str,
    settings: Settings,
    language_hint: str | None,
) -> StreamTurn:
    """Everything the buffered ``widget_message_turn`` checks BEFORE the model
    call, so a refusal is still a normal HTTP error (401/404/409/429/503)
    rather than an in-stream event. Mirrors that function step by step; the
    session capability, bot availability, per-session rate limit, tenant
    capacity and daily message cap all apply identically."""
    from app.chat.conversations import get_or_create_conversation_for_session
    from app.chat.models import model_from_settings
    from app.core.ratelimit import rate_limit
    from app.quotas.service import lock_tenant, require_capacity
    from app.widget import service

    service.require_available(bot, session_scope=False)
    count, _ = rate_limit(
        db,
        key=f"widget:msg:{ip}:{visitor_session.id}",
        limit=settings.widget_messages_per_minute,
        window_seconds=service.RETIRED_WINDOW,
    )
    if count > settings.widget_messages_per_minute:
        db.commit()  # the counter must persist even though the request is refused
        raise ApiError(429, "RATE_LIMITED", "Too many messages. Please slow down.")
    tenant = lock_tenant(db, visitor_session.tenant_id)
    require_capacity(db, tenant, "monthly_messages")
    service.check_daily_message_quota(db, bot, settings)
    conversation = get_or_create_conversation_for_session(
        db, bot=bot, visitor_session=visitor_session
    )
    model = model_from_settings(settings, bot)  # None: the turn answers with the busy reply
    # Persist the rate-limit counter and the lazily created conversation, and
    # release the tenant row lock before the (long) streamed turn begins.
    db.commit()
    return StreamTurn(
        tenant_id=visitor_session.tenant_id,
        bot_id=bot.id,
        visitor_session_id=visitor_session.id,
        conversation_id=conversation.id,
        text=text,
        language_hint=language_hint,
        settings=settings,
        model=model,
    )


def prepare_playground_stream(
    db: OrmSession,
    *,
    tenant_id: UUID,
    bot: Bot,
    user_id: UUID,
    text: str,
    settings: Settings,
    knowledge: str = "published",
) -> StreamTurn:
    """The staff playground's twin of ``prepare_widget_stream``: same worker,
    wrapper model and reconciliation, with the conversation scoped to
    (bot, user). Failures before the stream opens are ordinary HTTP errors."""
    from app.chat.conversations import (
        get_or_create_playground_conversation,
        resolve_preview_revision,
    )
    from app.chat.models import model_from_settings

    preview_revision_id = resolve_preview_revision(
        db, tenant_id=tenant_id, bot_id=bot.id, knowledge=knowledge
    )
    model = model_from_settings(settings, bot)
    if model is None:
        raise ApiError(
            503, "MODEL_NOT_CONFIGURED", "No chat model is configured for this deployment."
        )
    conversation = get_or_create_playground_conversation(
        db, tenant_id=tenant_id, bot_id=bot.id, user_id=user_id
    )
    db.commit()
    return StreamTurn(
        tenant_id=tenant_id,
        bot_id=bot.id,
        visitor_session_id=None,
        conversation_id=conversation.id,
        text=text,
        language_hint=None,
        settings=settings,
        model=model,
        preview_revision_id=preview_revision_id,
    )
