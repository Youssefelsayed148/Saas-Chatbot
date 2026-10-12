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
        evidence_pattern = re.compile(
            r"\[([0-9a-f-]{36})\] ([^\n]*)\n(.*?)(?=\n\n\[|\Z)", re.DOTALL
        )
        blocks = evidence_pattern.findall(messages[0]["content"])
        if not blocks:
            return json.dumps(
                {
                    "answer": "I have no data configured for this yet.",
                    "can_answer": False,
                    "sources": [],
                }
            )
        chunk_id, _provenance, first_text = blocks[0]
        answer_source = first_text.strip()
        if "\n" in answer_source:  # drop the trailing summary wiggle only
            answer_source = answer_source.split("\n", 1)[0].strip()
        answer = answer_source[:300]
        return json.dumps({"answer": answer, "can_answer": True, "sources": [chunk_id]})
