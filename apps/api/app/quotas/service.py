"""Tenant scoped placeholder entitlement checks (ADR-010)."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from app.core.errors import ApiError
from app.db.models import (
    Bot,
    Contact,
    Invitation,
    Membership,
    SourcePage,
    Tenant,
    UsageEvent,
)
from app.quotas.plans import PLACEHOLDER_PLAN_LIMITS, PLAN_LABELS, PlanLimits
from app.quotas.rag import counts_toward_message_quota

COUNTERS = (
    "bots",
    "seats",
    "pages_per_bot",
    "upload_file_mb",
    "monthly_messages",
    "contacts",
    "channel_connections",
    "sentiment_runs",
)


def limits_for(tenant: Tenant) -> PlanLimits:
    base = PLACEHOLDER_PLAN_LIMITS.get(tenant.plan_label.lower())
    unknown_plan = base is None
    if base is None:
        base = PLACEHOLDER_PLAN_LIMITS["starter"]
    values = {name: getattr(base, name) for name in COUNTERS}
    if unknown_plan:
        values["bots"] = 1
    for name, value in (tenant.quota_overrides or {}).items():
        if name in values and isinstance(value, int) and value >= 0:
            values[name] = value
    return PlanLimits(**values)


def _count(db: OrmSession, statement: Any) -> int:
    return int(db.execute(statement).scalar_one())


def _measured_total_tokens(payload: object) -> int:
    if not isinstance(payload, dict):
        return 0
    provider_usage = payload.get("provider_usage")
    if not isinstance(provider_usage, dict):
        return 0
    total_tokens = provider_usage.get("total_tokens")
    if isinstance(total_tokens, bool) or not isinstance(total_tokens, int):
        return 0
    return total_tokens


def usage_snapshot(db: OrmSession, tenant: Tenant, *, bot_id: UUID | None = None) -> dict[str, Any]:
    now = datetime.now(UTC)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    bot_count = _count(
        db,
        select(func.count())
        .select_from(Bot)
        .where(Bot.tenant_id == tenant.id, Bot.status != "archived"),
    )
    seat_count = _count(
        db,
        select(func.count())
        .select_from(Membership)
        .where(Membership.tenant_id == tenant.id, Membership.status == "active"),
    ) + _count(
        db,
        select(func.count())
        .select_from(Invitation)
        .where(
            Invitation.tenant_id == tenant.id,
            Invitation.accepted_at.is_(None),
            Invitation.revoked_at.is_(None),
            Invitation.expires_at > now,
        ),
    )
    pages_query = (
        select(func.count()).select_from(SourcePage).where(SourcePage.tenant_id == tenant.id)
    )
    if bot_id is not None:
        pages_query = pages_query.where(SourcePage.bot_id == bot_id)
        pages_count = _count(db, pages_query)
    else:
        per_bot = (
            select(func.count().label("page_count"))
            .select_from(SourcePage)
            .where(SourcePage.tenant_id == tenant.id)
            .group_by(SourcePage.bot_id)
            .subquery()
        )
        pages_count = int(
            db.execute(select(func.coalesce(func.max(per_bot.c.page_count), 0))).scalar_one()
        )
    message_count = _count(
        db,
        select(func.count())
        .select_from(UsageEvent)
        .where(
            UsageEvent.tenant_id == tenant.id,
            UsageEvent.kind == "message",
            UsageEvent.created_at >= month_start,
            counts_toward_message_quota(),
        ),
    )
    # Tokens stay measured for every turn (playground included): they are real spend.
    measured_token_payloads = db.execute(
        select(UsageEvent.payload).where(
            UsageEvent.tenant_id == tenant.id,
            UsageEvent.kind == "message",
            UsageEvent.created_at >= month_start,
        )
    ).scalars()
    measured_tokens = sum(_measured_total_tokens(payload) for payload in measured_token_payloads)
    contacts_count = _count(
        db, select(func.count()).select_from(Contact).where(Contact.tenant_id == tenant.id)
    )
    sentiment_count = _count(
        db,
        select(func.count())
        .select_from(UsageEvent)
        .where(
            UsageEvent.tenant_id == tenant.id,
            UsageEvent.kind == "sentiment_run",
            UsageEvent.created_at >= month_start,
        ),
    )
    # Channel connection rows belong to P6; no such connections exist before it.
    usage = {
        "bots": bot_count,
        "seats": seat_count,
        "pages_per_bot": pages_count,
        "upload_file_mb": 0,
        "monthly_messages": message_count,
        "contacts": contacts_count,
        # Website widget availability maps 1:1 to a non-archived bot until
        # Many connections become available in P6.
        "channel_connections": bot_count,
        "sentiment_runs": sentiment_count,
    }
    limits = limits_for(tenant)
    result: dict[str, Any] = {
        "placeholder": True,
        "plan": tenant.plan_label,
        "usage": {},
        "limits": {},
    }
    # Tenant-wide, provider-reported chat tokens only (message events). It is NOT the per-bot
    # `monthly_tokens` AI limit counter in quotas/rag.py, which also holds embeddings and
    # conservative reservations for unreported usage (see docs/05).
    result["measured_tokens_this_month"] = measured_tokens
    for name in COUNTERS:
        used = usage[name]
        limit = getattr(limits, name)
        result["usage"][name] = used
        result["limits"][name] = limit
    result["warnings"] = [
        name
        for name in COUNTERS
        if getattr(limits, name) > 0 and result["usage"][name] >= getattr(limits, name) * 0.8
    ]
    # Subset of `warnings` that has reached the limit (used >= limit); the rest are approaching.
    result["at_limit"] = [
        name
        for name in COUNTERS
        if getattr(limits, name) > 0 and result["usage"][name] >= getattr(limits, name)
    ]
    return result


def lock_tenant(db: OrmSession, tenant_id: UUID) -> Tenant:
    tenant = db.execute(
        select(Tenant).where(Tenant.id == tenant_id).with_for_update()
    ).scalar_one_or_none()
    if tenant is None or tenant.status != "active":
        raise ApiError(404, "NOT_FOUND", "Resource not found.")
    return tenant


def require_capacity(
    db: OrmSession, tenant: Tenant, counter: str, *, bot_id: UUID | None = None, amount: int = 1
) -> None:
    limits = limits_for(tenant)
    limit = getattr(limits, counter)
    snapshot = usage_snapshot(db, tenant, bot_id=bot_id)
    used = snapshot["usage"][counter]
    if used + amount > limit:
        raise ApiError(
            429,
            "QUOTA_EXCEEDED",
            (
                f"Your plan allows {limit} bot(s). Contact us to add another bot."
                if counter == "bots"
                else (
                    f"The {counter.replace('_', ' ')} limit for the "
                    f"{tenant.plan_label} plan is {limit}."
                )
            ),
            details={
                "counter": counter,
                "limit": limit,
                "used": used,
                "plan": tenant.plan_label,
                "placeholder": True,
            },
        )


__all__ = [
    "COUNTERS",
    "PLAN_LABELS",
    "PLACEHOLDER_PLAN_LIMITS",
    "lock_tenant",
    "limits_for",
    "require_capacity",
    "usage_snapshot",
]
