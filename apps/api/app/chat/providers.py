"""Chat providers (docs/14 §6): a small ChatModel interface and an
OpenAI-compatible client (OpenRouter free chain by default; OpenAI option
per plan in config). Keys/env only — never logged; the client never prints
request bodies.

`complete(messages, json_mode, max_tokens)` returns the raw completion text.
Model/chain errors raise `ProviderError` so the chat service can fall back
or emit the localized busy message (never a stack trace).
"""

import json
import os
import re
import time
from abc import ABC, abstractmethod
from collections.abc import Generator, Iterator
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

import httpx

from app.core.errors import ApiError


class ChatModel(ABC):
    """Interface for the answering provider (P3-05 swaps in fakes)."""

    usage_totals: dict[str, int] | None = None

    @abstractmethod
    def complete(self, messages: list[dict[str, str]], *, json_mode: bool, max_tokens: int) -> str:
        """One synchronous completion."""

    def stream_complete(self, messages: list[dict[str, str]], *, max_tokens: int) -> Iterator[str]:
        """Yield the JSON-mode completion as text fragments (S.1).

        Same model/fallback/blocked rules as ``complete``. Providers that
        cannot stream raise ``StreamUnsupported`` before yielding anything so
        the caller falls back to the buffered ``complete``. Closing the
        iterator releases the provider connection (client disconnect)."""
        raise StreamUnsupported("This provider cannot stream.")


class ProviderError(Exception):
    """The provider chain failed for this turn (timeout/rate limit/network/HTTP)."""


class StreamUnsupported(Exception):
    """The model cannot stream; use the buffered ``complete`` path instead."""


@dataclass
class ProviderChainAttempt:
    model: str
    error: str


# Models whose API rejected ``temperature`` / ``max_tokens`` and then accepted the
# compat profile (no temperature, ``max_completion_tokens``). In-process memory:
# later requests skip the attempt that is known to fail.
_COMPAT_PROFILE: set[str] = set()
_PARAMETER_HINTS = (
    "temperature",
    "max_tokens",
    "max_completion_tokens",
    "unsupported parameter",
    "unsupported_parameter",
    "unsupported value",
    "unsupported_value",
)


def _names_parameter(response: httpx.Response) -> bool:
    """A 400 whose error text blames a sampling/length parameter."""
    try:
        text = response.text.lower()
    except httpx.HTTPError:
        return False
    return any(hint in text for hint in _PARAMETER_HINTS)


class OpenAICompatibleModel(ChatModel):
    """A simple sync client for OpenAI-compatible chat endpoints.

    `free_only` guards the default OpenRouter configuration: model ids must
    end with ':free'. For OpenAI-hosted plans, `free_only=False`.
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        fallback_models: list[str] | None = None,
        free_only: bool = True,
        timeout_seconds: float = 25.0,
        retries: int = 0,
        transport: httpx.BaseTransport | None = None,
        temperature: float = 0.2,
    ) -> None:
        if not api_key:
            raise ApiError(503, "MODEL_NOT_CONFIGURED", "No model is configured for this bot.")
        if free_only:
            model_names = [model, *(fallback_models or [])]
            broken = [name for name in model_names if not name.endswith(":free")]
            if broken:
                raise ApiError(500, "MODEL_NOT_FREE", "Free plans may only use :free model ids.")
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key  # never logged
        self.model = model
        self.fallback_models = list(fallback_models or [])
        self.free_only = free_only
        self.timeout_seconds = timeout_seconds
        del retries  # compatibility only: retries are forbidden for all callers
        self.transport = transport
        self.blocked = False
        # Real HTTP status of the most recent provider response (None: no response).
        self.last_http_status: int | None = None
        self.requests_used = 0
        # Attempts that may have been processed and billed without usable output.
        self.ambiguous_attempts = 0
        self.model_used: str | None = None
        self.last_cost_usd: Decimal | None = None
        self.temperature = temperature
        self.usage_totals = None

    def _blocks(self, status: int) -> bool:
        """401/402 block the turn. 403/429 only block when no next model exists."""
        if status in (401, 402):
            return True
        return status in (403, 429) and not self.fallback_models

    def complete(self, messages: list[dict[str, str]], *, json_mode: bool, max_tokens: int) -> str:
        if self.blocked:
            raise ProviderError("Provider unavailable for this turn.")
        self.last_cost_usd = None
        # One attempt per model; at most the immediate next model as fallback.
        # An auth/payment response (401/402) blocks all subsequent calls on this
        # turn's model instance, including preprocessing followed by generation.
        # A rate limit / forbidden / 5xx on one model moves on to the next one.
        self.last_http_status = None
        with httpx.Client(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self._api_key}"},
            timeout=self.timeout_seconds,
            transport=self.transport,
            follow_redirects=False,
        ) as client:
            for model in [self.model, *self.fallback_models[:1]]:
                response = self._post(client, model, messages, json_mode, max_tokens)
                if response is None:
                    continue
                if self._blocks(response.status_code):
                    self.blocked = True
                    raise ProviderError("Provider unavailable for this turn.")
                if response.status_code != 200:
                    continue
                try:
                    payload = response.json()
                    content = payload["choices"][0]["message"]["content"]
                except (KeyError, IndexError, ValueError, TypeError):
                    self.ambiguous_attempts += 1
                    continue
                if not isinstance(content, str) or not content.strip():
                    self.ambiguous_attempts += 1
                    continue
                usage = payload.get("usage")
                if isinstance(usage, dict):
                    try:
                        cost = Decimal(str(usage.get("cost")))
                        if cost.is_finite() and cost >= 0:
                            self.last_cost_usd = cost
                    except InvalidOperation:
                        pass
                    measured = {
                        key: value
                        for key, value in usage.items()
                        if key in ("prompt_tokens", "completion_tokens", "total_tokens")
                        and isinstance(value, int)
                        and not isinstance(value, bool)
                        and value >= 0
                    }
                    if measured:
                        totals = self.usage_totals or {}
                        self.usage_totals = {
                            key: totals.get(key, 0) + value for key, value in measured.items()
                        }
                self.model_used = model
                return content
        raise ProviderError("All configured models failed.")

    def _body(
        self,
        model: str,
        messages: list[dict[str, str]],
        max_tokens: int,
        *,
        json_mode: bool,
        compat: bool,
    ) -> dict[str, object]:
        body: dict[str, object] = {"model": model, "messages": messages}
        if compat:
            # Models that reject the classic parameters (reasoning models).
            body["max_completion_tokens"] = max_tokens
        else:
            body["temperature"] = self.temperature
            body["max_tokens"] = max_tokens
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        return body

    def _post(
        self,
        client: httpx.Client,
        model: str,
        messages: list[dict[str, str]],
        json_mode: bool,
        max_tokens: int,
    ) -> httpx.Response | None:
        """One request for ``model``; None when the transport failed.

        A 400 that blames temperature / max_tokens / an unsupported parameter is
        retried ONCE with the compat profile, and a profile that works is
        remembered for this model name."""
        compat = model in _COMPAT_PROFILE
        for attempt in (0, 1):
            body = self._body(model, messages, max_tokens, json_mode=json_mode, compat=compat)
            self.requests_used += 1
            try:
                response = client.post("chat/completions", json=body)
            except (httpx.ConnectError, httpx.ConnectTimeout):
                return None
            except httpx.HTTPError:
                self.ambiguous_attempts += 1
                return None
            self.last_http_status = response.status_code
            if (
                response.status_code == 400
                and attempt == 0
                and not compat
                and _names_parameter(response)
            ):
                compat = True
                continue
            if response.status_code == 200 and compat:
                _COMPAT_PROFILE.add(model)
            return response
        return None  # unreachable: the second attempt always returns

    def stream_complete(self, messages: list[dict[str, str]], *, max_tokens: int) -> Iterator[str]:
        """Streamed JSON-mode completion (OpenAI-compatible SSE).

        Mirrors ``complete``: one attempt per model, at most the next model as
        fallback, auth/quota responses block the instance. A model is only
        abandoned for the next one while NO text was yielded yet; a failure
        after text started raises ``ProviderError`` (the caller must not
        replay a different model's text on top of released output)."""
        if self.blocked:
            raise ProviderError("Provider unavailable for this turn.")
        self.last_cost_usd = None
        self.last_http_status = None
        with httpx.Client(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self._api_key}"},
            timeout=self.timeout_seconds,
            transport=self.transport,
            follow_redirects=False,
        ) as client:
            for model in [self.model, *self.fallback_models[:1]]:
                produced = yield from self._stream_one(client, model, messages, max_tokens)
                if produced:
                    return
        raise ProviderError("All configured models failed.")

    def _stream_one(
        self,
        client: httpx.Client,
        model: str,
        messages: list[dict[str, str]],
        max_tokens: int,
    ) -> Generator[str, None, bool]:
        """Stream one model; the return value says whether it produced text
        (True: done) or the next model should be tried (False). Same one-shot
        compat retry as ``_post``; a 400 arrives before any text."""
        compat = model in _COMPAT_PROFILE
        for attempt in (0, 1):
            body = self._body(model, messages, max_tokens, json_mode=True, compat=compat)
            body["stream"] = True
            body["stream_options"] = {"include_usage": True}
            self.requests_used += 1
            yielded = False
            try:
                with client.stream("POST", "chat/completions", json=body) as response:
                    self.last_http_status = response.status_code
                    if self._blocks(response.status_code):
                        self.blocked = True
                        raise ProviderError("Provider unavailable for this turn.")
                    if response.status_code == 400 and attempt == 0 and not compat:
                        response.read()
                        if _names_parameter(response):
                            compat = True
                            continue
                    if response.status_code != 200:
                        return False
                    if compat:
                        _COMPAT_PROFILE.add(model)
                    for line in response.iter_lines():
                        fragment = self._stream_line(line)
                        if fragment is None:
                            continue
                        yielded = True
                        self.model_used = model
                        yield fragment
                    if yielded:
                        return True
                    self.ambiguous_attempts += 1
                    return False
            except (httpx.ConnectError, httpx.ConnectTimeout):
                return False
            except httpx.HTTPError as error:
                self.ambiguous_attempts += 1
                if yielded:
                    raise ProviderError("The stream was interrupted.") from error
                return False
        return False

    def _stream_line(self, line: str) -> str | None:
        """One SSE line -> a content fragment, or None (comments, usage, done)."""
        if not line.startswith("data:"):
            return None
        data = line[5:].strip()
        if not data or data == "[DONE]":
            return None
        try:
            payload = json.loads(data)
        except ValueError:
            return None
        if not isinstance(payload, dict):
            return None
        usage = payload.get("usage")
        if isinstance(usage, dict):
            self._record_usage(usage)
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            return None
        delta = choices[0].get("delta")
        content = delta.get("content") if isinstance(delta, dict) else None
        return content if isinstance(content, str) and content else None

    def _record_usage(self, usage: dict[str, object]) -> None:
        try:
            cost = Decimal(str(usage.get("cost")))
            if cost.is_finite() and cost >= 0:
                self.last_cost_usd = cost
        except InvalidOperation:
            pass
        measured = {
            key: value
            for key, value in usage.items()
            if key in ("prompt_tokens", "completion_tokens", "total_tokens")
            and isinstance(value, int)
            and not isinstance(value, bool)
            and value >= 0
        }
        if measured:
            totals = self.usage_totals or {}
            self.usage_totals = {key: totals.get(key, 0) + value for key, value in measured.items()}


class FakeChatModel(ChatModel):
    """Deterministic model for unit tests and the evaluation suite."""

    def __init__(
        self,
        responses: list[str] | None = None,
        *,
        raises: bool = False,
        stream_chunks: list[list[str]] | None = None,
    ) -> None:
        self.responses = list(responses or [])
        self.calls: list[tuple[list[dict[str, str]], bool, int]] = []
        self._raises = raises
        # Streaming scripts, consumed one per stream_complete call. The
        # fragment "!error" raises ProviderError at that point of the stream.
        self.stream_chunks = list(stream_chunks or [])
        self.stream_closed = False

    def stream_complete(self, messages: list[dict[str, str]], *, max_tokens: int) -> Iterator[str]:
        self.calls.append((messages, True, max_tokens))
        if not self.stream_chunks:
            raise StreamUnsupported("fake model without a stream script")
        script = self.stream_chunks.pop(0)
        try:
            for fragment in script:
                if fragment == "!error":
                    raise ProviderError("stream failed (fake)")
                yield fragment
        finally:
            self.stream_closed = True

    def complete(self, messages: list[dict[str, str]], *, json_mode: bool, max_tokens: int) -> str:
        self.calls.append((messages, json_mode, max_tokens))
        if self._raises:
            raise ProviderError("model unavailable (fake)")
        if not self.responses:
            raise ProviderError("no canned response")
        return self.responses.pop(0)


__all__ = [
    "ChatModel",
    "ExtractiveStubModel",
    "FakeChatModel",
    "OpenAICompatibleModel",
    "ProviderChainAttempt",
    "ProviderError",
    "StreamUnsupported",
]


class ExtractiveStubModel(ChatModel):
    """Deterministic offline stub (DEV/TEST/EVAL only — never configured for
    production): answers extractively from the evidence in the prompt so the
    grounded pipeline can be exercised without any paid API.

    - json_mode: builds the answer from the first evidence chunk and cites its
      id (DATA only — never invents facts).
    - non-json (condensation): returns the standalone query line unchanged.
    """

    calls: list[tuple[list[dict[str, str]], bool, int]]  # populated in complete

    def __init__(self) -> None:
        self.calls = []

    def stream_complete(self, messages: list[dict[str, str]], *, max_tokens: int) -> Iterator[str]:
        """Streams the deterministic JSON in small fragments (DEV/TEST only),
        so the streaming pipeline runs offline without any paid provider."""
        raw = self.complete(messages, json_mode=True, max_tokens=max_tokens)
        # DEV/TEST knob: STUB_STREAM_DELAY_MS slows the stub so browser tests
        # can observe progressive rendering through the real proxy.
        try:
            delay = max(0.0, float(os.environ.get("STUB_STREAM_DELAY_MS", "0"))) / 1000
        except ValueError:
            delay = 0.0
        step = 7
        for start in range(0, len(raw), step):
            if delay:
                time.sleep(delay)
            yield raw[start : start + step]

    def complete(self, messages: list[dict[str, str]], *, json_mode: bool, max_tokens: int) -> str:
        self.calls.append((messages, json_mode, max_tokens))
        if not json_mode:
            # Condensation pass-through: echo the standalone query.
            for message in messages:
                if message["role"] == "user" and "Follow-up:" in message["content"]:
                    return message["content"].split("Follow-up:", 1)[1].strip()
            return "query"
        blocks = _parse_evidence(messages[0]["content"])
        if not blocks:
            return json.dumps(
                {
                    "can_answer": False,
                    "sources": [],
                    "answer": "I have no data configured for this yet.",
                }
            )
        question_tokens = _question_token_set(messages)
        # Content-coverage gate: if the visitor asks for something no evidence
        # chunk even mentions, the honest extractive behaviour is to abstain —
        # never quote an unrelated chunk as an answer (docs/14 §1/§6).
        covered_text = " ".join(coverage for _, coverage in blocks).casefold()
        # Script check: a deterministic stub cannot translate; a token whose
        # script differs from the evidence's script cannot be verified by
        # coverage (the cross-language fallback path relies on real models to
        # answer in the visitor's language; the eval checks citations only).
        evidence_ascii_letters = sum(1 for ch in covered_text if ch.isascii() and ch.isalpha())
        evidence_arabic_letters = sum(1 for ch in covered_text if "\u0600" <= ch <= "\u06ff")
        evidence_script = "latin" if evidence_ascii_letters >= evidence_arabic_letters else "arabic"
        evidence_ascii_letters = sum(1 for ch in covered_text if ch.isascii() and ch.isalpha())
        evidence_arabic_letters = sum(1 for ch in covered_text if "\u0600" <= ch <= "\u06ff")
        evidence_script = "latin" if evidence_ascii_letters >= evidence_arabic_letters else "arabic"
        uncovered = [
            token
            for token in question_tokens
            if token not in covered_text
            and ("latin" if token.isascii() else "arabic") == evidence_script
        ]
        all_uncovered = bool(question_tokens) and len(uncovered) == len(question_tokens)
        weekday_gap = any(token in _WEEKDAY_TOKENS for token in uncovered)
        if all_uncovered or weekday_gap:
            return json.dumps(
                {
                    "can_answer": False,
                    "sources": [],
                    "answer": "I cannot confirm that from the information I have.",
                }
            )

        # Choose the chunk with the most question-token overlap (extractive pick).
        def score(item: tuple[str, str]) -> int:
            lowered = item[1].casefold()
            return sum(1 for token in question_tokens if token in lowered)

        best = max(blocks, key=score)
        chunk_id, chunk_text = best
        answer = chunk_text.strip().split("\n")[0][:300]
        return json.dumps({"can_answer": True, "sources": [chunk_id], "answer": answer})


_WEEKDAY_TOKENS = frozenset(
    {
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
        "saturdays",
        "sundays",
        "الاثنين",
        "الثلاثاء",
        "الاربعاء",
        "الخميس",
        "الجمعة",
        "السبت",
        "الاحد",
        "الهائمات",
    }
)


def _parse_evidence(system_content: str) -> list[tuple[str, str]]:
    """(chunk_id, coverage_text): provenance + body; the coverage check needs
    the title + heading too (docs/14 §4 indexed text)."""
    pattern = re.compile(r"\[([0-9a-f-]{36})\] ([^\n]*)\n(.*?)(?=\n\n\[|\Z)", re.DOTALL)
    return [(block[0], f"{block[1]} {block[2]}") for block in pattern.findall(system_content)]


def _question_token_set(messages: list[dict[str, str]]) -> set[str]:
    """Content tokens of the visitor question (last user message)."""
    from app.retrieval.query import ARABIC_STOP_WORDS, ENGLISH_STOP_WORDS, TOKEN_RE

    for message in reversed(messages):
        if message.get("role") == "user":
            lowered = message["content"].lower()
            return {
                token
                for token in (match.group(0) for match in TOKEN_RE.finditer(lowered))
                if len(token) >= 2
                and token not in ENGLISH_STOP_WORDS
                and token not in ARABIC_STOP_WORDS
            }
    return set()
