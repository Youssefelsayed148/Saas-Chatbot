"""Staff-only RAG configuration and backfill controls; no credentials returned."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.auth import cookies
from app.chat.models import tier_targets
from app.core.audit import record_audit
from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.core.tenancy import TenantContextDep
from app.db.models import Job, UsageEvent
from app.embeddings.backfill import queue_backfill, scoped_bot
from app.quotas.rag import cost_summary, monthly_usage, resource_usage, scope
from app.quotas.rag_contracts import RagLimits

BASE = "/api/v1/tenants/{tenant_id}/bots/{bot_id}/rag"
router = APIRouter(tags=["staff-rag"])
CsrfOk = Annotated[None, Depends(cookies.require_csrf)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


class RagPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    retrieval_mode: Literal["hybrid", "fts_only"] | None = None
    tier: Literal["standard", "premium"] | None = None
    generation_provider: Literal["openrouter", "openai"] | None = None
    generation_model: str | None = Field(default=None, min_length=1, max_length=200)
    limits: RagLimits | None = None


class BackfillRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    embedding_model: str | None = Field(default=None, min_length=3, max_length=200)


@router.get(BASE + "/traces")
def get_traces(bot_id: UUID, context: TenantContextDep) -> dict[str, object]:
    context.require_operator()
    scoped_bot(context.db, context.tenant_id, bot_id)
    rows = context.db.scalars(
        select(UsageEvent)
        .where(
            UsageEvent.tenant_id == context.tenant_id,
            UsageEvent.bot_id == bot_id,
            UsageEvent.kind.in_(("message", "unavailable")),
            UsageEvent.payload["rag_trace"].is_not(None),
        )
        .order_by(UsageEvent.created_at.desc(), UsageEvent.id.desc())
        .limit(50)
    )
    return {
        "traces": [
            {
                "message_id": str(row.message_id),
                "created_at": row.created_at.isoformat(),
                "trace": row.payload["rag_trace"],
            }
            for row in rows
        ]
    }


@router.get(BASE)
def get_rag(bot_id: UUID, context: TenantContextDep, settings: SettingsDep) -> dict[str, object]:
    context.require_operator()
    bot = scoped_bot(context.db, context.tenant_id, bot_id)
    _, effective = scope(context.db, context.tenant_id, bot_id, settings)
    job = context.db.scalar(
        select(Job)
        .where(
            Job.tenant_id == context.tenant_id,
            Job.bot_id == bot_id,
            Job.type == "reembed_backfill",
        )
        .order_by(Job.created_at.desc(), Job.id.desc())
        .limit(1)
    )
    return {
        "retrieval_mode": bot.retrieval_mode,
        "tier": bot.tier,
        "generation_provider": bot.generation_provider,
        "generation_model": bot.generation_model,
        # Provider/model each tier maps to (staff display; ADR-013).
        "tier_targets": tier_targets(settings),
        "active_embedding_model": bot.active_embedding_model,
        "embedding_dim": 1024,
        "embedding_ready": bot.embedding_ready,
        "limits": bot.rag_limits or {},
        "effective_limits": effective.model_dump(),
        "usage": {
            **resource_usage(context.db, context.tenant_id, bot_id),
            **monthly_usage(context.db, context.tenant_id, bot_id),
        },
        "backfill": {"id": str(job.id), "status": job.status, **job.payload} if job else None,
    }


@router.patch(BASE)
def patch_rag(
    bot_id: UUID, body: RagPatch, context: TenantContextDep, _: CsrfOk, settings: SettingsDep
) -> dict[str, object]:
    context.require_operator()
    bot = scoped_bot(context.db, context.tenant_id, bot_id, lock=True)
    values = body.model_dump(exclude_none=True, exclude={"limits"})
    if "limits" in body.model_fields_set:
        bot.rag_limits = (
            body.limits.model_dump(exclude_unset=True) if body.limits is not None else None
        )
    if body.tier is not None:
        bot.tier = body.tier
        bot.generation_provider = "openai" if body.tier == "premium" else "openrouter"
        bot.generation_model = None
    for name, value in values.items():
        setattr(bot, name, value)
    if (
        bot.generation_provider == "openrouter"
        and bot.generation_model
        and not bot.generation_model.endswith(":free")
    ):
        raise ApiError(422, "VALIDATION_ERROR", "OpenRouter generation requires a free model.")
    record_audit(
        context.db,
        action="rag.settings_updated",
        tenant_id=context.tenant_id,
        actor_user_id=context.user.id,
        target_type="bot",
        target_id=str(bot.id),
        metadata={"fields": sorted(body.model_fields_set)},
    )
    context.db.commit()
    return get_rag(bot_id, context, settings)


@router.get(BASE + "/costs")
def get_costs(bot_id: UUID, context: TenantContextDep) -> dict[str, object]:
    context.require_operator()
    scoped_bot(context.db, context.tenant_id, bot_id)
    return {
        "period": "current_calendar_month_utc",
        "costs": cost_summary(context.db, context.tenant_id, bot_id),
    }


@router.post(BASE + "/backfill", status_code=202)
def start_backfill(
    bot_id: UUID,
    body: BackfillRequest,
    context: TenantContextDep,
    _: CsrfOk,
    settings: SettingsDep,
) -> dict[str, str]:
    context.require_operator()
    job = queue_backfill(
        context.db,
        context.tenant_id,
        bot_id,
        settings,
        created_by=context.user.id,
        model=body.embedding_model,
    )
    record_audit(
        context.db,
        action="rag.backfill_requested",
        tenant_id=context.tenant_id,
        actor_user_id=context.user.id,
        target_type="bot",
        target_id=str(bot_id),
    )
    context.db.commit()
    return {"job_id": str(job.id), "status": job.status}
