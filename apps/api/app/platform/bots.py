"""Staff bot directory and creation, sharing tenant-safe summary fields."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.cookies import require_csrf
from app.bots.factory import create_bot_record
from app.bots.schemas import BotOut
from app.db.models import Bot, Job, Tenant
from app.db.models.knowledge import KnowledgeRevision, Source
from app.db.session import get_session
from app.platform.staff import PlatformStaffDep

router = APIRouter(prefix="/api/v1/platform/bots", tags=["platform bots"])
Database = Annotated[Session, Depends(get_session)]
Csrf = Annotated[None, Depends(require_csrf)]


class CreateBot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    organization_id: UUID
    name: str = Field(min_length=1, max_length=100)

    @field_validator("name", mode="before")
    @classmethod
    def trimmed_name(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class Organization(BaseModel):
    id: UUID
    name: str


class BotRow(BaseModel):
    id: UUID
    name: str
    organization: Organization
    status: str
    widget_state: str
    source_count: int
    last_ingestion_job_status: str | None
    published_revision_id: UUID | None


class BotList(BaseModel):
    bots: list[BotRow]
    total: int


def bot_summary(db: Session, bot: Bot) -> dict[str, Any]:
    sources = (
        db.scalar(
            select(func.count())
            .select_from(Source)
            .where(Source.tenant_id == bot.tenant_id, Source.bot_id == bot.id)
        )
        or 0
    )
    latest = db.scalar(
        select(Job)
        .where(Job.tenant_id == bot.tenant_id, Job.bot_id == bot.id, Job.type == "ingest_batch")
        .order_by(Job.created_at.desc(), Job.id)
        .limit(1)
    )
    revision = (
        db.scalar(
            select(KnowledgeRevision).where(
                KnowledgeRevision.id == bot.published_revision_id,
                KnowledgeRevision.tenant_id == bot.tenant_id,
                KnowledgeRevision.bot_id == bot.id,
            )
        )
        if bot.published_revision_id
        else None
    )
    return {
        "id": str(bot.id),
        "name": bot.name,
        "status": bot.status,
        "published": bot.published_revision_id is not None,
        "widget_state": "configured" if bot.widget_locator else "not_configured",
        "source_count": int(sources),
        "last_ingestion_job_status": latest.status if latest else None,
        "published_revision_id": str(bot.published_revision_id)
        if bot.published_revision_id
        else None,
        "published_at": revision.published_at.isoformat()
        if revision and revision.published_at
        else None,
    }


@router.get("", response_model=BotList)
def list_bots(
    staff: PlatformStaffDep,
    db: Database,
    q: str = Query("", max_length=100),
    organization_id: UUID | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> BotList:
    statement = select(Bot, Tenant).join(Tenant, Tenant.id == Bot.tenant_id)
    if q.strip():
        statement = statement.where(
            func.lower(Bot.name).contains(q.strip().lower(), autoescape=True)
        )
    if organization_id:
        statement = statement.where(Bot.tenant_id == organization_id)
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    rows = db.execute(statement.order_by(Bot.created_at.desc(), Bot.id).offset(offset).limit(limit))
    return BotList(
        total=total,
        bots=[
            BotRow.model_validate(
                {**bot_summary(db, bot), "organization": {"id": tenant.id, "name": tenant.name}}
            )
            for bot, tenant in rows
        ],
    )


@router.post("", response_model=BotOut, status_code=201)
def create_bot(body: CreateBot, staff: PlatformStaffDep, db: Database, _: Csrf) -> BotOut:
    bot = create_bot_record(
        db,
        tenant_id=body.organization_id,
        name=body.name,
        actor=staff,
        audit_action="platform.bot.created",
    )
    db.commit()
    return BotOut.model_validate(bot)
