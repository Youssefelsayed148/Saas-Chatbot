"""Scoped RAG caps and a durable reserve-before-I/O AI usage ledger."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Integer, cast, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ApiError
from app.db.models import Bot, Chunk, Document, Source, Tenant, UsageEvent
from app.quotas.rag_contracts import RagLimits


def scope(
    db: Session, tenant_id: UUID, bot_id: UUID, settings: Settings, *, lock: bool = False
) -> tuple[Bot, RagLimits]:
    query = (
        select(Bot, Tenant.plan_label)
        .join(Tenant, Tenant.id == Bot.tenant_id)
        .where(
            Bot.tenant_id == tenant_id,
            Bot.id == bot_id,
            Tenant.status == "active",
            Bot.status != "archived",
        )
    )
    if lock:
        query = query.with_for_update(of=Bot)
    row = db.execute(query.execution_options(populate_existing=True)).one_or_none()
    if row is None:
        raise ApiError(404, "NOT_FOUND", "Resource not found.")
    bot, plan = row
    base = settings.rag_plan_limits.get(plan, RagLimits()).model_dump()
    base.update(bot.rag_limits or {})
    return bot, RagLimits.model_validate(base)


def month_scope(tenant_id: UUID, bot_id: UUID) -> tuple[Any, ...]:
    start = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return (
        UsageEvent.tenant_id == tenant_id,
        UsageEvent.bot_id == bot_id,
        UsageEvent.created_at >= start,
    )


def monthly_usage(db: Session, tenant_id: UUID, bot_id: UUID) -> dict[str, int]:
    filters = month_scope(tenant_id, bot_id)
    payload = UsageEvent.payload
    totals = db.execute(
        select(
            func.coalesce(func.sum(cast(payload["accounted_tokens"].as_string(), Integer)), 0),
            func.coalesce(func.sum(cast(payload["embedding_tokens"].as_string(), Integer)), 0),
            func.coalesce(func.sum(cast(payload["ocr_pages"].as_string(), Integer)), 0),
        ).where(*filters, UsageEvent.kind == "ai_usage")
    ).one()
    messages = int(
        db.scalar(
            select(func.count())
            .select_from(UsageEvent)
            .where(
                *filters,
                UsageEvent.kind == "message",
            )
        )
        or 0
    )
    reserved = int(
        db.scalar(
            select(func.count())
            .select_from(UsageEvent)
            .where(
                *filters,
                UsageEvent.kind == "ai_usage",
                payload["event_type"].as_string() == "message",
                payload["status"].as_string() == "reserved",
            )
        )
        or 0
    )
    legacy_tokens = int(
        db.scalar(
            select(
                func.coalesce(
                    func.sum(cast(payload["provider_usage"]["total_tokens"].as_string(), Integer)),
                    0,
                )
            ).where(
                *filters,
                UsageEvent.kind == "message",
                payload["ai_metered"].as_boolean().is_not(True),
            )
        )
        or 0
    )
    return {
        "monthly_tokens": int(totals[0]) + legacy_tokens,
        "monthly_embedding_tokens": int(totals[1]),
        "monthly_ocr_pages": int(totals[2]),
        "monthly_messages": messages + reserved,
    }


def quota(counter: str) -> ApiError:
    return ApiError(
        429,
        "QUOTA_EXCEEDED",
        "The bot's usage limit has been reached. Contact us.",
        details={"counter": counter},
    )


def check_resources(
    db: Session,
    tenant_id: UUID,
    bot_id: UUID,
    settings: Settings,
    *,
    additions: dict[str, int] | None = None,
    absolute: dict[str, int] | None = None,
) -> None:
    _, limits = scope(db, tenant_id, bot_id, settings, lock=True)
    for counter, amount in (additions or {}).items():
        limit = getattr(limits, counter)
        if limit is None:
            continue
        if counter != "storage_bytes":
            raise ValueError("Only storage byte additions are supported.")
        used = int(
            db.scalar(
                select(func.coalesce(func.sum(Source.size_bytes), 0)).where(
                    Source.tenant_id == tenant_id,
                    Source.bot_id == bot_id,
                )
            )
            or 0
        )
        if used + amount > limit:
            raise quota(counter)
    for counter, total in (absolute or {}).items():
        limit = getattr(limits, counter)
        if limit is not None and total > limit:
            raise quota(counter)


def resource_usage(db: Session, tenant_id: UUID, bot_id: UUID) -> dict[str, int]:
    result = {}
    for name, model in (("documents", Document), ("chunks", Chunk)):
        per_revision = (
            select(func.count().label("n"))
            .select_from(model)
            .where(
                model.tenant_id == tenant_id,
                model.bot_id == bot_id,
            )
            .group_by(model.revision_id)
            .subquery()
        )
        result[name] = int(db.scalar(select(func.coalesce(func.max(per_revision.c.n), 0))) or 0)
    result["storage_bytes"] = int(
        db.scalar(
            select(func.coalesce(func.sum(Source.size_bytes), 0)).where(
                Source.tenant_id == tenant_id,
                Source.bot_id == bot_id,
            )
        )
        or 0
    )
    return result


def reserve(
    db: Session,
    tenant_id: UUID,
    bot_id: UUID,
    settings: Settings,
    *,
    event_type: str,
    model: str | None,
    channel: str,
    token_bound: int = 0,
    ocr_pages: int = 0,
) -> UUID:
    if token_bound < 0 or ocr_pages < 0:
        raise ValueError("Usage reservations cannot be negative.")
    _, limits = scope(db, tenant_id, bot_id, settings, lock=True)
    used = monthly_usage(db, tenant_id, bot_id)
    embedding = token_bound if event_type.startswith("embed_") else 0
    amounts = {
        "monthly_tokens": token_bound,
        "monthly_embedding_tokens": embedding,
        "monthly_ocr_pages": ocr_pages,
        "monthly_messages": 1 if event_type == "message" else 0,
    }
    for counter, amount in amounts.items():
        limit = getattr(limits, counter)
        if amount and limit is not None and used[counter] + amount > limit:
            raise quota(counter)
    event = UsageEvent(
        tenant_id=tenant_id,
        bot_id=bot_id,
        kind="ai_usage",
        external_key=f"ai:{uuid4()}",
        payload={
            "event_type": event_type,
            "model": model,
            "channel": channel,
            "status": "reserved",
            "reserved_tokens": token_bound,
            "accounted_tokens": token_bound,
            "embedding_tokens": embedding,
            "ocr_pages": ocr_pages,
            "measured_tokens": None,
            "cost_usd": None,
        },
    )
    db.add(event)
    db.commit()  # Durable reservation releases the bot lock before provider I/O.
    return event.id


def settle(
    db: Session,
    tenant_id: UUID,
    bot_id: UUID,
    event_id: UUID,
    settings: Settings,
    *,
    tokens: int | None,
    cost_usd: Decimal | None,
    model: str | None = None,
    commit: bool = True,
) -> None:
    scope(db, tenant_id, bot_id, settings, lock=True)
    event = db.scalar(
        select(UsageEvent)
        .where(
            UsageEvent.tenant_id == tenant_id,
            UsageEvent.bot_id == bot_id,
            UsageEvent.id == event_id,
            UsageEvent.kind == "ai_usage",
        )
        .with_for_update()
    )
    if event is None or event.payload.get("status") != "reserved":
        return
    payload = dict(event.payload)
    measured = (
        tokens if isinstance(tokens, int) and not isinstance(tokens, bool) and tokens >= 0 else None
    )
    accounted = measured if measured is not None else payload["reserved_tokens"]
    payload.update(
        status="settled" if measured is not None else "usage_unreported",
        measured_tokens=measured,
        accounted_tokens=accounted,
        embedding_tokens=accounted if str(payload["event_type"]).startswith("embed_") else 0,
        cost_usd=str(cost_usd)
        if cost_usd is not None and cost_usd.is_finite() and cost_usd >= 0
        else None,
    )
    if model is not None:
        payload["model"] = model
    event.payload = payload
    if commit:
        db.commit()


def release(
    db: Session,
    tenant_id: UUID,
    bot_id: UUID,
    event_id: UUID,
    settings: Settings,
    *,
    commit: bool = True,
) -> None:
    """Return a reservation when no provider output was produced (definite failure).

    Ambiguous outcomes (timeout after send, 200 with unusable body) must use
    settle(tokens=None) so the conservative hold stays.
    """
    scope(db, tenant_id, bot_id, settings, lock=True)
    event = db.scalar(
        select(UsageEvent)
        .where(
            UsageEvent.tenant_id == tenant_id,
            UsageEvent.bot_id == bot_id,
            UsageEvent.id == event_id,
            UsageEvent.kind == "ai_usage",
        )
        .with_for_update()
    )
    if event is None or event.payload.get("status") != "reserved":
        return
    event.payload = {
        **event.payload,
        "status": "released",
        "measured_tokens": 0,
        "accounted_tokens": 0,
        "embedding_tokens": 0,
        "ocr_pages": 0,
        "cost_usd": "0",
    }
    if commit:
        db.commit()


def cost_summary(db: Session, tenant_id: UUID, bot_id: UUID) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(UsageEvent).where(
            *month_scope(tenant_id, bot_id),
            UsageEvent.kind == "ai_usage",
            UsageEvent.payload["event_type"].as_string() != "message",
        )
    )
    groups: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        p = row.payload
        key = tuple(str(p.get(name) or "unknown") for name in ("channel", "model", "event_type"))
        channel, model, event_type = key
        group = groups.setdefault(
            (channel, model, event_type),
            {
                "channel": channel,
                "model": model,
                "event_type": event_type,
                "events": 0,
                "measured_tokens": 0,
                "reserved_or_accounted_tokens": 0,
                "cost_usd": Decimal(0),
                "unmeasured_events": 0,
            },
        )
        group["events"] += 1
        measured = p.get("measured_tokens")
        accounted = p.get("accounted_tokens")
        group["measured_tokens"] += measured if isinstance(measured, int) else 0
        group["reserved_or_accounted_tokens"] += accounted if isinstance(accounted, int) else 0
        if p.get("cost_usd") is None:
            group["unmeasured_events"] += 1
        else:
            group["cost_usd"] += Decimal(str(p["cost_usd"]))
    return [{**group, "cost_usd": str(group["cost_usd"])} for group in groups.values()]
