"""Embedding providers. No retries or implicit fallback to another model.

Ollama is the development default. Paid adapters must be explicitly configured;
their real-call behavior is not verified by the agent. Tests use mocked HTTP or
the guarded deterministic test embedder, never a silent production substitute.
"""

import hashlib
import math
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

import httpx

from app.core.config import Settings

DIMENSION = 1024
OPENAI_LARGE_USD_PER_MILLION = Decimal("0.13")


class EmbeddingError(Exception):
    """Safe failure; never includes provider bodies or credentials.

    ambiguous=True means the provider may have processed (and billed) the request.
    """

    def __init__(self, message: str = "", *, ambiguous: bool = False) -> None:
        super().__init__(message)
        self.ambiguous = ambiguous


@dataclass
class EmbeddingBatch:
    vectors: list[list[float]]
    tokens: int = 0
    cost_usd: Decimal | None = None


class Embedder(Protocol):
    identity: str

    def embed(self, texts: list[str]) -> EmbeddingBatch: ...


def validate_vector(raw: object) -> list[float]:
    if not isinstance(raw, list) or len(raw) != DIMENSION:
        raise EmbeddingError("Embedding dimension does not match this deployment.")
    if any(isinstance(value, bool) or not isinstance(value, (float, int)) for value in raw):
        raise EmbeddingError("Embedding contains invalid values.")
    vector = [float(value) for value in raw]
    if not all(math.isfinite(value) for value in vector) or not any(vector):
        raise EmbeddingError("Embedding must be finite and non-zero.")
    return vector


def configured_identity(settings: Settings) -> str:
    default = {"ollama": "bge-m3", "openai": "text-embedding-3-large", "openrouter": ""}
    model = settings.embedding_model or default[settings.embedding_provider]
    if not model:
        raise EmbeddingError("An embedding model must be explicitly configured for this provider.")
    return f"{settings.embedding_provider}:{model}"


class HTTPEmbedder:
    def __init__(
        self,
        *,
        identity: str,
        base_url: str,
        api_key: str = "",
        timeout: float = 25,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.identity = identity
        self.provider, self.model = identity.split(":", 1)
        if self.provider not in ("ollama", "openai", "openrouter"):
            raise EmbeddingError("Unsupported embedding provider.")
        if self.provider != "ollama" and not api_key:
            raise EmbeddingError("Embedding credentials are not configured.")
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self.timeout = timeout
        self.transport = transport

    def embed(self, texts: list[str]) -> EmbeddingBatch:
        if not texts or any(not text.strip() for text in texts):
            raise EmbeddingError("Embedding input must be non-empty.")
        body: dict[str, object] = {"model": self.model, "input": texts}
        if self.provider == "ollama":
            body["truncate"] = False
            endpoint = "/api/embed"
        else:
            endpoint = "/embeddings"
            body.update(dimensions=DIMENSION, encoding_format="float")
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        received = False
        try:
            with httpx.Client(
                timeout=self.timeout, transport=self.transport, follow_redirects=False
            ) as client:
                response = client.post(self.base_url + endpoint, headers=headers, json=body)
            if response.status_code != 200:
                raise EmbeddingError("Embedding provider is unavailable.")
            received = True
            payload = response.json()
            if self.provider == "ollama":
                raw_vectors = payload["embeddings"]
                tokens = payload.get("prompt_eval_count")
            else:
                rows = sorted(payload["data"], key=lambda row: row["index"])
                if [row["index"] for row in rows] != list(range(len(texts))):
                    raise EmbeddingError("Embedding response indexes are invalid.")
                raw_vectors = [row["embedding"] for row in rows]
                usage = payload.get("usage")
                tokens = usage.get("total_tokens") if isinstance(usage, dict) else None
            if not isinstance(raw_vectors, list) or len(raw_vectors) != len(texts):
                raise EmbeddingError("Embedding batch size mismatch.")
            vectors = [validate_vector(raw) for raw in raw_vectors]
            measured = isinstance(tokens, int) and not isinstance(tokens, bool) and tokens >= 0
            tokens = tokens if measured else 0
            cost = Decimal(0) if self.provider == "ollama" else None
            if self.identity == "openai:text-embedding-3-large" and measured:
                cost = Decimal(tokens) * OPENAI_LARGE_USD_PER_MILLION / 1_000_000
            return EmbeddingBatch(vectors, tokens, cost)
        except EmbeddingError as exc:
            if received:
                exc.ambiguous = True
            raise
        except (httpx.ConnectError, httpx.ConnectTimeout):
            raise EmbeddingError("Embedding provider is unavailable.") from None
        except (httpx.HTTPError, ValueError, KeyError, TypeError, IndexError):
            # A response (or a mid-flight timeout) may already have been billed.
            raise EmbeddingError(
                "Embedding response could not be processed.", ambiguous=True
            ) from None


class TestHashEmbedder:
    """Non-semantic deterministic vectors, explicitly enabled only for test runs."""

    def __init__(self, identity: str) -> None:
        self.identity = identity

    def embed(self, texts: list[str]) -> EmbeddingBatch:
        vectors = []
        for text in texts:
            values = [0.0] * DIMENSION
            for token in re.findall(r"\w+", text.casefold()):
                slot = (
                    int.from_bytes(hashlib.sha256(token.encode()).digest()[:4], "big") % DIMENSION
                )
                values[slot] += 1
            norm = math.sqrt(sum(value * value for value in values))
            if norm == 0:
                values[0], norm = 1, 1
            vectors.append([value / norm for value in values])
        return EmbeddingBatch(vectors, cost_usd=Decimal(0))


def from_settings(settings: Settings, identity: str | None = None) -> Embedder:
    identity = identity or configured_identity(settings)
    if settings.embedding_test_stub:
        if settings.environment != "test":
            raise EmbeddingError("Test embeddings cannot serve a non-test environment.")
        return TestHashEmbedder(identity)
    provider = identity.split(":", 1)[0]
    if provider == "ollama":
        base_url, key = settings.embedding_ollama_base_url, ""
    elif provider == "openai":
        base_url = settings.chat_openai_base_url
        key = (
            settings.chat_openai_api_key.get_secret_value() if settings.chat_openai_api_key else ""
        )
    elif provider == "openrouter":
        base_url = settings.chat_openrouter_base_url
        key = (
            settings.chat_openrouter_api_key.get_secret_value()
            if settings.chat_openrouter_api_key
            else ""
        )
    else:
        raise EmbeddingError("Unsupported embedding model identity.")
    return HTTPEmbedder(
        identity=identity,
        base_url=base_url,
        api_key=key,
        timeout=settings.embedding_timeout_seconds,
    )
