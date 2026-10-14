"""Chat providers (docs/14 §6): a small ChatModel interface and an
OpenAI-compatible client (OpenRouter free chain by default; OpenAI option
per plan in config). Keys/env only — never logged; the client never prints
request bodies.

`complete(messages, json_mode, max_tokens)` returns the raw completion text.
Model/chain errors raise `ProviderError` so the chat service can fall back
or emit the localized busy message (never a stack trace).
"""

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.core.errors import ApiError


class ChatModel(ABC):
    """Interface for the answering provider (P3-05 swaps in fakes)."""

    usage_totals: dict[str, int] | None = None

    @abstractmethod
    def complete(self, messages: list[dict[str, str]], *, json_mode: bool, max_tokens: int) -> str:
        """One synchronous completion."""


class ProviderError(Exception):
    """The provider chain failed for this turn (timeout/rate limit/network/HTTP)."""


@dataclass
class ProviderChainAttempt:
    model: str
    error: str


RETRYABLE_HTTP_STATUS = {408, 409, 425, 429}


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
        retries: int = 2,
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
        self.retries = retries
        self.temperature = temperature
        self.usage_totals = None

    def complete(self, messages: list[dict[str, str]], *, json_mode: bool, max_tokens: int) -> str:
        from httpx import Client, HTTPError

        body: dict[str, object] = {
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}

        chain: list[ProviderChainAttempt] = []
        for model in [self.model, *self.fallback_models]:
            body["model"] = model
            last_error: Exception | None = None
            for _attempt in range(self.retries + 1):
                try:
                    response = Client(
                        base_url=self.base_url,
                        headers={"Authorization": f"Bearer {self._api_key}"},
                        timeout=self.timeout_seconds,
                    ).post("/chat/completions", json=body)
                except HTTPError as http_error:
                    # Network error or timeout: retry this model, then next.
                    last_error = ProviderError(f"model {model}: {type(http_error).__name__}")
                    continue
                if response.status_code in RETRYABLE_HTTP_STATUS:
                    last_error = ProviderError(f"model {model}: HTTP {response.status_code}")
                    continue
                if response.status_code >= 500:
                    last_error = ProviderError(f"model {model}: HTTP {response.status_code}")
                    continue
                if response.status_code != 200:
                    last_error = ProviderError(f"model {model}: HTTP {response.status_code}")
                    break  # non-retryable: try the next model immediately
                try:
                    payload = response.json()
                    content = payload["choices"][0]["message"]["content"]
                except (KeyError, IndexError, ValueError) as parse_error:
                    last_error = ProviderError(f"model {model}: malformed response ({parse_error})")
                    break
                if not isinstance(content, str) or not content.strip():
                    last_error = ProviderError(f"model {model}: empty completion")
                    continue
                usage = payload.get("usage")
                if isinstance(usage, dict):
                    measured = {
                        key: value
                        for key, value in usage.items()
                        if key in ("prompt_tokens", "completion_tokens", "total_tokens")
                        and isinstance(value, int)
                        and value >= 0
                    }
                    if measured:
                        totals = self.usage_totals or {}
                        self.usage_totals = {
                            key: totals.get(key, 0) + value
                            for key, value in measured.items()
                        }
                return content
            if last_error is not None:
                chain.append(ProviderChainAttempt(model=model, error=str(last_error)))
        raise ProviderError("All configured models failed.")


class FakeChatModel(ChatModel):
    """Deterministic model for unit tests and the evaluation suite."""

    def __init__(self, responses: list[str] | None = None, *, raises: bool = False) -> None:
        self.responses = list(responses or [])
        self.calls: list[tuple[list[dict[str, str]], bool, int]] = []
        self._raises = raises

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
                    "answer": "I have no data configured for this yet.",
                    "can_answer": False,
                    "sources": [],
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
                    "answer": "I cannot confirm that from the information I have.",
                    "can_answer": False,
                    "sources": [],
                }
            )

        # Choose the chunk with the most question-token overlap (extractive pick).
        def score(item: tuple[str, str]) -> int:
            lowered = item[1].casefold()
            return sum(1 for token in question_tokens if token in lowered)

        best = max(blocks, key=score)
        chunk_id, chunk_text = best
        answer = chunk_text.strip().split("\n")[0][:300]
        return json.dumps({"answer": answer, "can_answer": True, "sources": [chunk_id]})


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
