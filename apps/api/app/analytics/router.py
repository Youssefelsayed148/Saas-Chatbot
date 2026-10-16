"""Analytics endpoints (P4-05, docs/05: /analytics/{summary,volume,
top-questions,unanswered,leads} and CSV exports).

Member reads only (viewers included per docs/06); measured data only (real
conversations and usage events — playground threads never count). Date range
via `from`/`to` (inclusive ISO dates). Hidden bots → 404 as everywhere.
"""

import csv
import io
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response

from app.analytics import service
from app.core.errors import ApiError
from app.core.tenancy import TenantContextDep
from app.knowledge.service import get_bot

router = APIRouter(prefix="/api/v1/tenants/{tenant_id}/bots/{bot_id}/analytics")


def _window(from_date: str | None, to_date: str | None) -> tuple[datetime, datetime]:
    try:
        return service._range_window(from_date, to_date)
    except ValueError as exc:
        raise ApiError(422, "VALIDATION_ERROR", str(exc)) from exc


@router.get("/summary")
def analytics_summary(
    bot_id: UUID,
    context: TenantContextDep,
    from_date: Annotated[str | None, Query(alias="from")] = None,
    to_date: Annotated[str | None, Query(alias="to")] = None,
) -> dict[str, object]:
    get_bot(context, bot_id)
    start, end = _window(from_date, to_date)
    return service.summary(
        context.db, tenant_id=context.tenant_id, bot_id=bot_id, start=start, end=end
    )


@router.get("/volume")
def analytics_volume(
    bot_id: UUID,
    context: TenantContextDep,
    from_date: Annotated[str | None, Query(alias="from")] = None,
    to_date: Annotated[str | None, Query(alias="to")] = None,
) -> dict[str, object]:
    get_bot(context, bot_id)
    start, end = _window(from_date, to_date)
    days = service.volume_per_day(
        context.db, tenant_id=context.tenant_id, bot_id=bot_id, start=start, end=end
    )
    return {"days": days}


@router.get("/top-questions")
def analytics_top_questions(
    bot_id: UUID,
    context: TenantContextDep,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
    from_date: Annotated[str | None, Query(alias="from")] = None,
    to_date: Annotated[str | None, Query(alias="to")] = None,
) -> dict[str, object]:
    get_bot(context, bot_id)
    start, end = _window(from_date, to_date)
    rows = service.top_questions(
        context.db,
        tenant_id=context.tenant_id,
        bot_id=bot_id,
        start=start,
        end=end,
        limit=limit,
    )
    return {"questions": rows}


@router.get("/unanswered")
def analytics_unanswered(
    bot_id: UUID,
    context: TenantContextDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    from_date: Annotated[str | None, Query(alias="from")] = None,
    to_date: Annotated[str | None, Query(alias="to")] = None,
) -> dict[str, object]:
    get_bot(context, bot_id)
    start, end = _window(from_date, to_date)
    rows = service.unanswered_questions(
        context.db,
        tenant_id=context.tenant_id,
        bot_id=bot_id,
        start=start,
        end=end,
        limit=limit,
    )
    return {"questions": rows}


@router.get("/leads")
def analytics_leads(
    bot_id: UUID,
    context: TenantContextDep,
    from_date: Annotated[str | None, Query(alias="from")] = None,
    to_date: Annotated[str | None, Query(alias="to")] = None,
) -> dict[str, object]:
    get_bot(context, bot_id)
    start, end = _window(from_date, to_date)
    trend = service.leads_trend(
        context.db, tenant_id=context.tenant_id, bot_id=bot_id, start=start, end=end
    )
    contacts = service.lead_contacts(
        context.db, tenant_id=context.tenant_id, bot_id=bot_id, start=start, end=end
    )
    return {"trend": trend, "contacts": contacts}


def _csv_response(filename: str, fieldnames: list[str], rows: list[dict[str, object]]) -> Response:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return Response(
        content=buffer.getvalue().encode("utf-8"),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/conversations.csv")
def analytics_conversations_csv(
    bot_id: UUID,
    context: TenantContextDep,
    from_date: Annotated[str | None, Query(alias="from")] = None,
    to_date: Annotated[str | None, Query(alias="to")] = None,
) -> Response:
    context.require_role("admin")
    get_bot(context, bot_id)
    start, end = _window(from_date, to_date)
    rows: list[dict[str, object]] = service.conversations_csv(
        context.db, tenant_id=context.tenant_id, bot_id=bot_id, start=start, end=end
    )
    return _csv_response(
        "conversations.csv",
        [
            "conversation_id",
            "created_at",
            "last_message_at",
            "status",
            "mode",
            "channel",
            "contact_name",
            "message_count",
        ],
        rows,
    )


@router.get("/leads.csv")
def analytics_leads_csv(
    bot_id: UUID,
    context: TenantContextDep,
    from_date: Annotated[str | None, Query(alias="from")] = None,
    to_date: Annotated[str | None, Query(alias="to")] = None,
) -> Response:
    context.require_role("admin")
    get_bot(context, bot_id)
    start, end = _window(from_date, to_date)
    rows: list[dict[str, object]] = service.lead_contacts(
        context.db, tenant_id=context.tenant_id, bot_id=bot_id, start=start, end=end
    )
    return _csv_response(
        "leads.csv",
        [
            "contact_id",
            "display_name",
            "email",
            "phone",
            "stage",
            "created_at",
            "conversations",
        ],
        rows,
    )
