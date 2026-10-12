"""Bots router: thin endpoints over the bot service (docs/03)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.auth import cookies
from app.bots.schemas import BotCreateRequest, BotOut, BotUpdateRequest
from app.bots.service import BotService
from app.core.tenancy import TenantContextDep

router = APIRouter(tags=["bots"])

CsrfOk = Annotated[None, Depends(cookies.require_csrf)]


@router.post("/api/v1/tenants/{tenant_id}/bots", response_model=BotOut, status_code=201)
def create_bot(bot: BotCreateRequest, context: TenantContextDep, _: CsrfOk) -> BotOut:
    """Editor+ creates a bot in draft status."""
    context.require_role("editor")
    bot_row = BotService(context.db).create_bot(context, bot)
    return BotOut.model_validate(bot_row)


@router.get("/api/v1/tenants/{tenant_id}/bots", response_model=list[BotOut])
def list_bots(context: TenantContextDep, include_archived: bool = False) -> list[BotOut]:
    rows = BotService(context.db).list_bots(context, include_archived=include_archived)
    return [BotOut.model_validate(row) for row in rows]


@router.get("/api/v1/tenants/{tenant_id}/bots/{bot_id}", response_model=BotOut)
def get_bot(bot_id: UUID, context: TenantContextDep) -> BotOut:
    bot = BotService(context.db).get_bot(context, bot_id)
    return BotOut.model_validate(bot)


@router.patch("/api/v1/tenants/{tenant_id}/bots/{bot_id}", response_model=BotOut)
def update_bot(
    bot_id: UUID, body: BotUpdateRequest, context: TenantContextDep, _: CsrfOk
) -> BotOut:
    context.require_role("editor")
    bot = BotService(context.db).update_bot(context, bot_id, body)
    return BotOut.model_validate(bot)


@router.delete(
    "/api/v1/tenants/{tenant_id}/bots/{bot_id}",
    response_model=BotOut,
    summary="Soft archive",
)
def archive_bot(bot_id: UUID, context: TenantContextDep, _: CsrfOk) -> BotOut:
    """Soft archive: the bot stays, its config stays; the default list hides it."""
    context.require_role("editor")
    bot = BotService(context.db).archive_bot(context, bot_id)
    return BotOut.model_validate(bot)
