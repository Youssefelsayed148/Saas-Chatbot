"""Meter provider work without holding row locks across network calls."""

from collections.abc import Callable
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.chat.providers import ChatModel, ExtractiveStubModel, ProviderError
from app.core.config import Settings
from app.embeddings.providers import EmbeddingBatch
from app.quotas.rag import reserve, settle


def label(model: ChatModel) -> str:
    if isinstance(model, ExtractiveStubModel):
        return "test:extractive-stub"
    name = getattr(model, "model_used", None) or getattr(model, "model", None)
    if not isinstance(name, str):
        return "mock:unmeasured"
    provider = "openrouter" if getattr(model, "free_only", False) else "openai"
    return f"{provider}:{name}"


class MeteredChatModel(ChatModel):
    def __init__(
        self,
        inner: ChatModel,
        db: Session,
        tenant_id: UUID,
        bot_id: UUID,
        settings: Settings,
        channel: str,
    ) -> None:
        self.inner, self.db = inner, db
        self.tenant_id, self.bot_id, self.settings, self.channel = (
            tenant_id,
            bot_id,
            settings,
            channel,
        )
        self.model = label(inner)
        self.model_used: str | None = None
        self.last_cost_usd: Decimal | None = None
        self.usage_totals = inner.usage_totals

    def complete(self, messages: list[dict[str, str]], *, json_mode: bool, max_tokens: int) -> str:
        if getattr(self.inner, "blocked", False):
            raise ProviderError("Provider unavailable for this turn.")
        system = messages[0]["content"] if messages else ""
        kind = (
            "generation"
            if json_mode
            else ("rewrite" if "condense a visitor" in system else "translation")
        )
        attempts = 2 if getattr(self.inner, "fallback_models", []) else 1
        # Conservative UTF-8 input bound plus protocol allowance and maximum
        # output, reserved for every allowed fallback attempt. Missing usage
        # keeps this reservation rather than silently treating work as free.
        bound = (
            sum(len(item["content"].encode()) + 128 for item in messages) + max_tokens
        ) * attempts
        event = reserve(
            self.db,
            self.tenant_id,
            self.bot_id,
            self.settings,
            event_type=kind,
            model=self.model,
            channel=self.channel,
            token_bound=bound,
        )
        before = dict(self.inner.usage_totals or {})
        before_requests = getattr(self.inner, "requests_used", 0)
        completed = False
        try:
            answer = self.inner.complete(messages, json_mode=json_mode, max_tokens=max_tokens)
            completed = True
            return answer
        finally:
            self.usage_totals = self.inner.usage_totals
            measured = (self.usage_totals or {}).get("total_tokens")
            tokens = (
                max(0, measured - before.get("total_tokens", 0)) if measured is not None else None
            )
            if not completed:
                tokens = None
            self.model_used = label(self.inner)
            cost = getattr(self.inner, "last_cost_usd", None)
            if not isinstance(cost, Decimal) and (
                self.model_used.endswith(":free") or self.model_used.startswith("test:")
            ):
                cost = Decimal(0)
            self.last_cost_usd = cost if isinstance(cost, Decimal) else None
            if getattr(self.inner, "requests_used", 0) - before_requests > 1:
                # Successful-call usage does not prove a failed fallback attempt
                # was unbilled. Retain the conservative token reservation.
                tokens = None
                if not self.model_used.endswith(":free"):
                    self.last_cost_usd = None
            settle(
                self.db,
                self.tenant_id,
                self.bot_id,
                event,
                self.settings,
                tokens=tokens,
                cost_usd=self.last_cost_usd,
                model=self.model_used,
            )


def metered_embed(
    db: Session,
    tenant_id: UUID,
    bot_id: UUID,
    settings: Settings,
    *,
    identity: str,
    texts: list[str],
    embed: Callable[[list[str]], EmbeddingBatch],
    event_type: str,
    channel: str,
) -> EmbeddingBatch:
    event = reserve(
        db,
        tenant_id,
        bot_id,
        settings,
        event_type=event_type,
        model=identity,
        channel=channel,
        token_bound=sum(len(value.encode()) + 128 for value in texts),
    )
    batch = None
    try:
        batch = embed(texts)
        return batch
    finally:
        settle(
            db,
            tenant_id,
            bot_id,
            event,
            settings,
            tokens=batch.tokens if batch is not None and batch.tokens > 0 else None,
            cost_usd=batch.cost_usd if batch is not None else None,
        )
