"""Private per-turn model measurements. Unknown cost remains unknown."""

from decimal import Decimal
from time import perf_counter
from typing import Any

from app.chat.providers import ChatModel, ExtractiveStubModel, ProviderError


class TracedModel(ChatModel):
    def __init__(self, inner: ChatModel, trace: dict[str, Any]) -> None:
        self.inner, self.trace = inner, trace
        self.events: list[dict[str, Any]] = []
        trace["events"] = self.events

    def complete(self, messages: list[dict[str, str]], *, json_mode: bool, max_tokens: int) -> str:
        system = messages[0]["content"] if messages else ""
        kind = (
            "generation"
            if json_mode
            else ("rewrite" if "condense a visitor" in system else "translation")
        )
        before = dict(self.inner.usage_totals or {})
        started, status = perf_counter(), "ok"
        try:
            return self.inner.complete(messages, json_mode=json_mode, max_tokens=max_tokens)
        except ProviderError:
            status = "failed"
            raise
        finally:
            usage = {
                key: max(0, value - before.get(key, 0))
                for key, value in (self.inner.usage_totals or {}).items()
            }
            model = getattr(self.inner, "model_used", None) or getattr(self.inner, "model", None)
            if isinstance(self.inner, ExtractiveStubModel):
                model = "test:extractive-stub"
            cost = getattr(self.inner, "last_cost_usd", None)
            if (
                not isinstance(cost, Decimal)
                and isinstance(model, str)
                and (model.endswith(":free") or model.startswith("test:"))
            ):
                cost = Decimal(0)
            self.events.append(
                {
                    "kind": kind,
                    "model": model if isinstance(model, str) else "mock:unmeasured",
                    "tokens": usage or None,
                    "cost_usd": str(cost) if isinstance(cost, Decimal) else None,
                    "latency_ms": round((perf_counter() - started) * 1000),
                    "status": status,
                }
            )
            self.trace["model"] = self.events[-1]["model"]
            self.trace["tokens"] = dict(self.inner.usage_totals or {}) or None
            costs = [event["cost_usd"] for event in self.events]
            self.trace["cost_usd"] = (
                str(sum((Decimal(value) for value in costs), Decimal(0)))
                if all(value is not None for value in costs)
                else None
            )
