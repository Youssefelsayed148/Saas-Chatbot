"""Website follow-up scheduling; delivery is queued and never pushed."""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.auth import cookies
from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.core.tenancy import TenantContext, TenantContextDep
from app.db.models import Conversation, FollowUp, Job
from app.followups.schemas import FollowUpCreate, FollowUpOut
from app.jobs.queue import enqueue_job

router = APIRouter(prefix="/api/v1/tenants/{tenant_id}/follow-ups", tags=["follow-ups"])
CsrfOk = Annotated[None, Depends(cookies.require_csrf)]
CurrentSettings = Annotated[Settings, Depends(get_settings)]


def _follow_up(context: TenantContext, follow_up_id: UUID) -> FollowUp:
    row: FollowUp | None = context.db.execute(
        select(FollowUp).where(
            FollowUp.tenant_id == context.tenant_id,
            FollowUp.id == follow_up_id,
        )
    ).scalar_one_or_none()
    if row is None:
        raise ApiError(404, "NOT_FOUND", "Resource not found.")
    return row


@router.get("")
def list_follow_ups(context: TenantContextDep) -> dict[str, object]:
    context.require_role("viewer")
    rows = (
        context.db.execute(
            select(FollowUp)
            .where(FollowUp.tenant_id == context.tenant_id)
            .order_by(FollowUp.send_at.desc(), FollowUp.id)
            .limit(500)
        )
        .scalars()
        .all()
    )
    return {"follow_ups": [FollowUpOut.model_validate(row).model_dump(mode="json") for row in rows]}


@router.post("", status_code=201)
def create_follow_up(
    body: FollowUpCreate,
    context: TenantContextDep,
    settings: CurrentSettings,
    _: CsrfOk,
) -> FollowUpOut:
    context.require_role("editor")
    conversation = context.db.execute(
        select(Conversation).where(
            Conversation.tenant_id == context.tenant_id,
            Conversation.id == body.conversation_id,
        )
    ).scalar_one_or_none()
    if conversation is None:
        raise ApiError(404, "NOT_FOUND", "Resource not found.")
    if (
        conversation.channel != "website"
        or conversation.source != "website"
        or conversation.session_id is None
    ):
        raise ApiError(
            422,
            "CHANNEL_NOT_SUPPORTED",
            "Only website conversations can receive follow-ups in this phase.",
        )
    if body.contact_id is not None and conversation.contact_id != body.contact_id:
        raise ApiError(404, "NOT_FOUND", "Resource not found.")

    row = FollowUp(
        id=uuid4(),
        tenant_id=context.tenant_id,
        bot_id=conversation.bot_id,
        conversation_id=conversation.id,
        contact_id=conversation.contact_id,
        text=body.text.strip(),
        send_at=body.send_at.astimezone(UTC),
        status="scheduled",
        created_by=context.user.id,
    )
    context.db.add(row)
    job = enqueue_job(
        context.db,
        tenant_id=context.tenant_id,
        bot_id=conversation.bot_id,
        job_type="follow_up_delivery",
        payload={"follow_up_id": str(row.id)},
        created_by=context.user.id,
        settings=settings,
    )
    job.run_at = row.send_at
    context.db.commit()
    return FollowUpOut.model_validate(row)


@router.delete("/{follow_up_id}", status_code=204)
def cancel_follow_up(follow_up_id: UUID, context: TenantContextDep, _: CsrfOk) -> None:
    context.require_role("editor")
    row = _follow_up(context, follow_up_id)
    if row.status in ("delivered", "cancelled"):
        raise ApiError(409, "FOLLOW_UP_FINISHED", "This follow-up cannot be cancelled.")
    row.status = "cancelled"
    job = context.db.execute(
        select(Job)
        .where(
            Job.tenant_id == context.tenant_id,
            Job.bot_id == row.bot_id,
            Job.type == "follow_up_delivery",
            Job.payload["follow_up_id"].astext == str(row.id),
        )
        .with_for_update()
    ).scalar_one_or_none()
    if job is not None:
        if job.status == "pending":
            job.status = "cancelled"
            job.finished_at = datetime.now(UTC)
        elif job.status == "running":
            job.cancel_requested = True
        job.updated_at = datetime.now(UTC)
    context.db.commit()
