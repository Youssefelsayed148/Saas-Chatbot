"""Bots router: thin endpoints over the bot service (docs/03)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.auth import cookies
from app.bots.schemas import BotCreateRequest, BotOut, BotUpdateRequest, ReadinessOut, ToneOut
from app.bots.service import BotService, readiness_items
from app.core.tenancy import TenantContext, TenantContextDep

router = APIRouter(tags=["bots"])

CsrfOk = Annotated[None, Depends(cookies.require_csrf)]


def _client_bot_out(context: TenantContext, bot: object) -> BotOut:
    out = BotOut.model_validate(bot)
    if not context.user.is_platform_staff:
        out.widget_locator = None
        out.config = {}
        out.tone_and_rules = None
    return out


@router.post("/api/v1/tenants/{tenant_id}/bots", response_model=BotOut, status_code=201)
def create_bot(bot: BotCreateRequest, context: TenantContextDep, _: CsrfOk) -> BotOut:
    """Only platform staff create bots; the platform Bots section uses the shared factory."""
    context.require_operator()
    return BotOut.model_validate(BotService(context.db).create_bot(context, bot))


@router.get("/api/v1/tenants/{tenant_id}/bots", response_model=list[BotOut])
def list_bots(context: TenantContextDep, include_archived: bool = False) -> list[BotOut]:
    rows = BotService(context.db).list_bots(context, include_archived=include_archived)
    return [_client_bot_out(context, row) for row in rows]


@router.get("/api/v1/tenants/{tenant_id}/bots/{bot_id}", response_model=BotOut)
def get_bot(bot_id: UUID, context: TenantContextDep) -> BotOut:
    bot = BotService(context.db).get_bot(context, bot_id)
    return _client_bot_out(context, bot)


@router.get("/api/v1/tenants/{tenant_id}/bots/{bot_id}/tone-and-rules", response_model=ToneOut)
def get_tone_and_rules(bot_id: UUID, context: TenantContextDep) -> ToneOut:
    """Staff-only read of the tone field: members get 403 (not a hidden UI)."""
    context.require_operator()
    bot = BotService(context.db).get_bot(context, bot_id)
    return ToneOut(tone_and_rules=bot.tone_and_rules)


@router.get("/api/v1/tenants/{tenant_id}/bots/{bot_id}/readiness", response_model=ReadinessOut)
def get_readiness(bot_id: UUID, context: TenantContextDep) -> ReadinessOut:
    """Staff-only, read-only launch checklist computed from the bot's real state."""
    context.require_operator()
    bot = BotService(context.db).get_bot(context, bot_id)
    items = readiness_items(bot)
    return ReadinessOut(ready=all(item.status != "todo" for item in items), items=items)


@router.patch("/api/v1/tenants/{tenant_id}/bots/{bot_id}", response_model=BotOut)
def update_bot(
    bot_id: UUID, body: BotUpdateRequest, context: TenantContextDep, _: CsrfOk
) -> BotOut:
    context.require_operator()
    bot = BotService(context.db).update_bot(context, bot_id, body)
    return _client_bot_out(context, bot)


@router.delete(
    "/api/v1/tenants/{tenant_id}/bots/{bot_id}",
    response_model=BotOut,
    summary="Soft archive",
)
def archive_bot(bot_id: UUID, context: TenantContextDep, _: CsrfOk) -> BotOut:
    """Soft archive: the bot stays, its config stays; the default list hides it."""
    context.require_operator()
    return BotOut.model_validate(BotService(context.db).archive_bot(context, bot_id))
