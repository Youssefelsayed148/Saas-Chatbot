"""P7-04 tenant export, deletion, and audit review."""

import base64
import json
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from app.auth import cookies
from app.core.audit import record_audit
from app.core.config import Settings, get_settings
from app.core.tenancy import TenantContextDep
from app.db.models import (
    AuditEvent,
    Bot,
    Chunk,
    Contact,
    ContactIdentity,
    ContactStage,
    Conversation,
    ConversationRead,
    ConversationTag,
    Document,
    FollowUp,
    InboxEvent,
    Invitation,
    Job,
    KnowledgeRevision,
    Membership,
    Message,
    Source,
    SourcePage,
    UsageEvent,
    User,
)
from app.knowledge.storage import Storage, get_storage

router = APIRouter(prefix="/api/v1/tenants/{tenant_id}/data", tags=["tenant-data"])
CsrfOk = Annotated[None, Depends(cookies.require_csrf)]


class DeleteTenantRequest(BaseModel):
    confirm_name: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("reason")
    @classmethod
    def reason_has_content(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 3:
            raise ValueError("Deletion reason must contain at least three non-space characters.")
        return cleaned


def _rows(db: Any, model: Any, tenant_id: UUID) -> list[Any]:
    return list(db.execute(select(model).where(model.tenant_id == tenant_id)).scalars())


def _serialize(rows: list[Any], fields: tuple[str, ...]) -> list[dict[str, Any]]:
    return [{field: getattr(row, field) for field in fields} for row in rows]


@router.get("/export")
def export_tenant_data(
    context: TenantContextDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    context.require_role("admin")
    tenant_id = context.tenant_id
    tenant = context.tenant
    db = context.db

    member_rows = db.execute(
        select(Membership, User)
        .join(User, Membership.user_id == User.id)
        .where(Membership.tenant_id == tenant_id)
    ).all()
    invitations = _rows(db, Invitation, tenant_id)
    sources = _rows(db, Source, tenant_id)
    audit_rows = _rows(db, AuditEvent, tenant_id)
    storage: Storage | None = (
        get_storage(settings) if sources and context.user.is_platform_staff else None
    )
    source_files: list[dict[str, Any]] = []
    for source in sources if context.user.is_platform_staff else []:
        try:
            assert storage is not None
            raw_file = storage.open(source.storage_key)
        except (FileNotFoundError, ValueError):
            source_files.append(
                {
                    "source_id": source.id,
                    "original_name": source.original_name,
                    "kind": source.kind,
                    "available": False,
                    "content_base64": None,
                }
            )
        else:
            source_files.append(
                {
                    "source_id": source.id,
                    "original_name": source.original_name,
                    "kind": source.kind,
                    "available": True,
                    "content_base64": base64.b64encode(raw_file).decode("ascii"),
                }
            )
    export_data: dict[str, Any] = {
        "format": "saas-chats-ai-tenant-export/v1",
        "exported_at": datetime.now(UTC).isoformat(),
        "tenant": _serialize(
            [tenant], ("id", "name", "slug", "status", "plan_label", "created_at")
        )[0],
        "members": [
            {
                "user_id": member.user_id,
                "email": user.email,
                "role": member.role,
                "status": member.status,
            }
            for member, user in member_rows
        ],
        "invitations": _serialize(
            invitations,
            ("id", "email", "role", "expires_at", "accepted_at", "revoked_at", "created_at"),
        ),
        "bots": _serialize(
            _rows(db, Bot, tenant_id),
            ("id", "name", "status", "config", "created_at", "updated_at"),
        ),
        "contacts": _serialize(
            _rows(db, Contact, tenant_id),
            (
                "id",
                "display_name",
                "email",
                "phone",
                "stage",
                "tags",
                "custom_fields",
                "consent",
                "source_channel",
                "created_at",
                "updated_at",
            ),
        ),
        "contact_identities": _serialize(
            _rows(db, ContactIdentity, tenant_id),
            ("id", "contact_id", "channel", "external_id", "created_at"),
        ),
        "contact_stages": _serialize(_rows(db, ContactStage, tenant_id), ("name", "sort_order")),
        "conversations": _serialize(
            _rows(db, Conversation, tenant_id),
            (
                "id",
                "bot_id",
                "contact_id",
                "channel",
                "connection_id",
                "mode",
                "status",
                "assigned_user_id",
                "handoff_reason",
                "last_message_at",
                "sentiment",
                "source",
                "created_at",
                "updated_at",
            ),
        ),
        "messages": _serialize(
            _rows(db, Message, tenant_id),
            (
                "id",
                "bot_id",
                "conversation_id",
                "sender_type",
                "sender_user_id",
                "text",
                "citations",
                "can_answer",
                "needs_human",
                "response_ms",
                "delivery_status",
                "error_code",
                "created_at",
            ),
        ),
        "conversation_reads": _serialize(
            _rows(db, ConversationRead, tenant_id),
            ("conversation_id", "user_id", "last_read_at", "last_read_message_id", "updated_at"),
        ),
        "conversation_tags": _serialize(
            _rows(db, ConversationTag, tenant_id), ("conversation_id", "tag", "created_at")
        ),
        "inbox_events": _serialize(
            _rows(db, InboxEvent, tenant_id),
            ("id", "conversation_id", "message_id", "event_type", "created_at"),
        ),
        "follow_ups": _serialize(
            _rows(db, FollowUp, tenant_id),
            (
                "id",
                "bot_id",
                "conversation_id",
                "contact_id",
                "text",
                "send_at",
                "status",
                "created_by",
                "created_at",
                "delivered_at",
            ),
        ),
        "usage_events": _serialize(
            _rows(db, UsageEvent, tenant_id),
            (
                "id",
                "bot_id",
                "kind",
                "message_id",
                "conversation_id",
                "payload",
                "external_key",
                "created_at",
            ),
        ),
        "jobs": _serialize(
            _rows(db, Job, tenant_id),
            (
                "id",
                "bot_id",
                "type",
                "status",
                "payload",
                "attempts",
                "max_attempts",
                "run_at",
                "error",
                "created_at",
                "updated_at",
            ),
        ),
        "sources": _serialize(
            sources,
            (
                "id",
                "bot_id",
                "kind",
                "original_name",
                "size_bytes",
                "sha256",
                "status",
                "error",
                "row_errors",
                "valid_rows",
                "total_rows",
                "created_at",
            ),
        ),
        "source_files": source_files,
        "source_pages": _serialize(
            _rows(db, SourcePage, tenant_id),
            (
                "id",
                "bot_id",
                "source_id",
                "page_number",
                "title",
                "source_url",
                "page_type",
                "language",
                "raw_text",
                "created_at",
            ),
        ),
        "knowledge_revisions": _serialize(
            _rows(db, KnowledgeRevision, tenant_id),
            ("id", "bot_id", "status", "published_at", "created_at"),
        ),
        "documents": _serialize(
            _rows(db, Document, tenant_id),
            (
                "id",
                "bot_id",
                "revision_id",
                "source_id",
                "title",
                "heading",
                "source_url",
                "page_ref",
                "ordinal",
                "language",
                "priority",
                "text",
                "total_chars",
                "created_at",
            ),
        ),
        "chunks": _serialize(
            _rows(db, Chunk, tenant_id),
            (
                "id",
                "bot_id",
                "revision_id",
                "source_id",
                "document_id",
                "title",
                "heading",
                "text",
                "text_norm",
                "language",
                "priority",
                "content_hash",
                "ordinal",
                "created_at",
            ),
        ),
        "audit_events": _serialize(
            audit_rows,
            (
                "id",
                "actor_user_id",
                "action",
                "target_type",
                "target_id",
                "metadata_json",
                "created_at",
            ),
        ),
    }
    if not context.user.is_platform_staff:
        for key in (
            "sources",
            "source_files",
            "source_pages",
            "documents",
            "chunks",
            "knowledge_revisions",
            "jobs",
        ):
            export_data.pop(key, None)
        for bot in export_data["bots"]:
            bot.pop("config", None)
        for message in export_data["messages"]:
            message["citations"] = []
        # Usage payloads are private operator instrumentation, including traces,
        # provider usage and cost reservations. Keep only operational counters.
        export_data["usage_events"] = [
            {**event, "payload": {}}
            for event in export_data["usage_events"]
            if event["kind"] != "ai_usage"
        ]
    record_audit(
        db,
        action="tenant.data.exported",
        tenant_id=tenant_id,
        actor_user_id=context.user.id,
        target_type="tenant",
        target_id=str(tenant_id),
    )
    db.flush()
    exported_audit = db.execute(
        select(AuditEvent)
        .where(
            AuditEvent.tenant_id == tenant_id,
            AuditEvent.action == "tenant.data.exported",
            AuditEvent.actor_user_id == context.user.id,
        )
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        .limit(1)
    ).scalar_one()
    export_data["audit_events"].append(
        {
            "id": exported_audit.id,
            "actor_user_id": exported_audit.actor_user_id,
            "action": exported_audit.action,
            "target_type": exported_audit.target_type,
            "target_id": exported_audit.target_id,
            "metadata_json": exported_audit.metadata_json,
            "created_at": exported_audit.created_at,
        }
    )
    db.commit()
    return Response(
        content=json.dumps(
            export_data,
            ensure_ascii=False,
            default=lambda value: value.isoformat() if isinstance(value, datetime) else str(value),
        ),
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="tenant-{tenant_id}-export.json"'},
    )


@router.get("/audit")
def tenant_audit_review(
    context: TenantContextDep,
    q: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=100, ge=1, le=200),
) -> dict[str, Any]:
    context.require_role("admin")
    statement = select(AuditEvent).where(AuditEvent.tenant_id == context.tenant_id)
    if q and q.strip():
        statement = statement.where(AuditEvent.action.ilike(f"%{q.strip()}%"))
    rows = list(
        context.db.execute(statement.order_by(AuditEvent.created_at.desc()).limit(limit)).scalars()
    )
    return {
        "events": [
            {
                "id": str(row.id),
                "action": row.action,
                "actor_user_id": str(row.actor_user_id) if row.actor_user_id else None,
                "target_type": row.target_type,
                "target_id": row.target_id,
                "metadata": row.metadata_json,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]
    }


@router.get("/deletion-preview")
def deletion_preview(context: TenantContextDep) -> dict[str, Any]:
    context.require_operator()
    from app.tenants.deletion import deletion_counts

    return {"name": context.tenant.name, "counts": deletion_counts(context.db, context.tenant_id)}


@router.delete("", status_code=204)
def delete_tenant_data(
    body: DeleteTenantRequest,
    context: TenantContextDep,
    settings: Annotated[Settings, Depends(get_settings)],
    _: CsrfOk,
) -> Response:
    context.require_operator()
    from app.tenants.deletion import schedule_deletion

    schedule_deletion(context, body.confirm_name, body.reason, settings)
    return Response(status_code=204)
