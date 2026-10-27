"""Light CRM API (docs/14 §16). All reads/writes stay inside tenant scope."""

import csv
import io
import json
import re
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import delete, select, update

from app.auth import cookies
from app.contacts.schemas import ContactCreate, ContactOut, ContactUpdate, StageRename
from app.core.audit import record_audit
from app.core.errors import ApiError
from app.core.tenancy import TenantContext, TenantContextDep
from app.db.models import Contact, ContactIdentity, ContactStage, Conversation, Message
from app.quotas.service import lock_tenant, require_capacity

router = APIRouter(prefix="/api/v1/tenants/{tenant_id}/contacts", tags=["contacts"])
CsrfOk = Annotated[None, Depends(cookies.require_csrf)]


def _contact(context: TenantContext, contact_id: UUID) -> Contact:
    row: Contact | None = context.db.execute(
        select(Contact).where(Contact.tenant_id == context.tenant_id, Contact.id == contact_id)
    ).scalar_one_or_none()
    if row is None:
        raise ApiError(404, "NOT_FOUND", "Resource not found.")
    return row


def _stages(context: TenantContext) -> list[ContactStage]:
    rows = (
        context.db.execute(
            select(ContactStage)
            .where(ContactStage.tenant_id == context.tenant_id)
            .order_by(ContactStage.sort_order)
        )
        .scalars()
        .all()
    )
    if not rows:
        rows = [
            ContactStage(tenant_id=context.tenant_id, name=n, sort_order=i)
            for i, n in enumerate(("new", "qualified", "customer", "lost"))
        ]
        context.db.add_all(rows)
        context.db.flush()
    return list(rows)


_EXPORT_SAFE_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
# Only a leading "+" followed by a digit is exempt; a leading "-" or "(" is still escaped.
_PHONE_SHAPE = re.compile(r"^\+\d[\d\s().-]*$")


def _export_safe(value: str) -> str:
    """Neutralize CSV formula injection: escape leading spreadsheet operators."""
    if value.startswith(_EXPORT_SAFE_PREFIXES):
        return f"'{value}"
    return value


def _export_phone(value: str | None) -> str:
    """Only ``+`` then digits is exempt; a leading ``-`` or ``(`` and formulas are escaped."""
    if not value:
        return ""
    if _PHONE_SHAPE.fullmatch(value):
        return value
    # "(" is not a general formula lead, but a phone must not lead with it unescaped.
    return f"'{value}" if value.startswith("(") else _export_safe(value)


def _ensure_reachable_and_unique(
    context: TenantContext,
    *,
    email: str | None,
    phone: str | None,
    exclude_id: UUID | None = None,
) -> None:
    if not email and not (phone and phone.strip()):
        raise ApiError(422, "VALIDATION_ERROR", "email or phone is required.")
    for field, value in ((Contact.email, email), (Contact.phone, phone)):
        if value:
            query = select(Contact.id).where(
                Contact.tenant_id == context.tenant_id,
                field == value,
            )
            if exclude_id is not None:
                query = query.where(Contact.id != exclude_id)
            if context.db.execute(query).first() is not None:
                raise ApiError(
                    409,
                    "CONTACT_EXISTS",
                    "A contact with this email or phone already exists.",
                )


@router.get("")
def list_contacts(
    context: TenantContextDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    q: Annotated[str | None, Query(max_length=100)] = None,
    channel: Annotated[str | None, Query(max_length=32)] = None,
) -> dict[str, object]:
    context.require_role("viewer")
    if channel is not None and channel not in ("website", "whatsapp", "messenger", "instagram"):
        raise ApiError(
            422,
            "VALIDATION_ERROR",
            "channel must be one of website, whatsapp, messenger, instagram.",
        )
    query = select(Contact).where(Contact.tenant_id == context.tenant_id)
    if q:
        query = query.where(
            (Contact.display_name.ilike(f"%{q}%"))
            | (Contact.email.ilike(f"%{q}%"))
            | (Contact.phone.ilike(f"%{q}%"))
        )
    if channel is not None:
        # A contact matches when one of its channel identities is on the
        # requested channel (website sessions and delegated channels both).
        query = query.where(
            Contact.id.in_(
                select(ContactIdentity.contact_id).where(
                    ContactIdentity.tenant_id == context.tenant_id,
                    ContactIdentity.channel == channel,
                )
            )
        )
    rows = (
        context.db.execute(
            query.order_by(Contact.updated_at.desc(), Contact.id).limit(limit).offset(offset)
        )
        .scalars()
        .all()
    )
    # P6-05b: per-contact channels measured from its identities.
    channels_by_contact: dict[UUID, list[str]] = {}
    if rows:
        identity_rows = context.db.execute(
            select(ContactIdentity.contact_id, ContactIdentity.channel)
            .where(
                ContactIdentity.tenant_id == context.tenant_id,
                ContactIdentity.contact_id.in_([row.id for row in rows]),
            )
            .distinct()
            .order_by(ContactIdentity.channel)
        )
        for contact_id, identity_channel in identity_rows:
            channels_by_contact.setdefault(contact_id, []).append(str(identity_channel))
    return {
        "contacts": [
            ContactOut.model_validate(row)
            .model_copy(update={"channels": channels_by_contact.get(row.id, [])})
            .model_dump(mode="json")
            for row in rows
        ]
    }


@router.post("", status_code=201)
def create_contact(body: ContactCreate, context: TenantContextDep, _: CsrfOk) -> ContactOut:
    context.require_role("editor")
    tenant = lock_tenant(context.db, context.tenant_id)
    require_capacity(context.db, tenant, "contacts")
    _ensure_reachable_and_unique(
        context,
        email=str(body.email) if body.email else None,
        phone=body.phone,
    )
    if body.stage not in {row.name for row in _stages(context)}:
        raise ApiError(422, "VALIDATION_ERROR", "Unknown contact stage.")
    row = Contact(id=uuid4(), tenant_id=context.tenant_id, **body.model_dump(mode="json"))
    context.db.add(row)
    context.db.commit()
    return ContactOut.model_validate(row)


@router.get("/stages")
def list_stages(context: TenantContextDep) -> dict[str, object]:
    context.require_role("viewer")
    rows = _stages(context)
    context.db.commit()
    return {"stages": [{"name": row.name, "sort_order": row.sort_order} for row in rows]}


@router.patch("/stages")
def rename_stage(body: StageRename, context: TenantContextDep, _: CsrfOk) -> dict[str, str]:
    context.require_role("admin")
    _stages(context)
    if body.old_name == body.name:
        return {"name": body.name}
    if context.db.get(ContactStage, (context.tenant_id, body.old_name)) is None:
        raise ApiError(404, "NOT_FOUND", "Resource not found.")
    if context.db.get(ContactStage, (context.tenant_id, body.name)) is not None:
        raise ApiError(409, "STAGE_EXISTS", "A contact stage with that name already exists.")
    stage = context.db.get(ContactStage, (context.tenant_id, body.old_name))
    assert stage is not None
    context.db.add(
        ContactStage(tenant_id=context.tenant_id, name=body.name, sort_order=stage.sort_order)
    )
    context.db.flush()
    context.db.execute(
        update(Contact)
        .where(Contact.tenant_id == context.tenant_id, Contact.stage == body.old_name)
        .values(stage=body.name)
    )
    context.db.delete(stage)
    context.db.commit()
    return {"name": body.name}


@router.get("/export.csv")
def export_contacts(context: TenantContextDep) -> Response:
    context.require_role("admin")
    rows = (
        context.db.execute(
            select(Contact).where(Contact.tenant_id == context.tenant_id).order_by(Contact.id)
        )
        .scalars()
        .all()
    )
    identity_rows = context.db.execute(
        select(ContactIdentity.contact_id, ContactIdentity.channel)
        .where(ContactIdentity.tenant_id == context.tenant_id)
        .distinct()
        .order_by(ContactIdentity.channel)
    )
    channels_by_contact: dict[UUID, list[str]] = {}
    for contact_id, identity_channel in identity_rows:
        channels_by_contact.setdefault(contact_id, []).append(str(identity_channel))
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "id",
            "display_name",
            "email",
            "phone",
            "stage",
            "channels",
            "tags",
            "custom_fields",
            "consent",
            "created_at",
        ]
    )
    for row in rows:
        writer.writerow(
            [
                row.id,
                _export_safe(row.display_name or ""),
                _export_safe(row.email or ""),
                _export_phone(row.phone),
                _export_safe(row.stage or ""),
                # Spreadsheet program guard: a value that Excel/Sheets could
                # otherwise evaluate as a formula is quoted out (D12 exports).
                ";".join(_export_safe(value) for value in channels_by_contact.get(row.id, [])),
                ";".join(_export_safe(str(x)) for x in row.tags),
                json.dumps(row.custom_fields, ensure_ascii=False, sort_keys=True),
                json.dumps(row.consent, ensure_ascii=False, sort_keys=True),
                row.created_at.isoformat(),
            ]
        )
    return Response(
        output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=contacts.csv"},
    )


@router.post("/{contact_id}/merge")
def merge_contact(
    contact_id: UUID, target_id: UUID, context: TenantContextDep, _: CsrfOk
) -> ContactOut:
    context.require_role("admin")
    source, target = _contact(context, contact_id), _contact(context, target_id)
    if source.id == target.id:
        raise ApiError(422, "VALIDATION_ERROR", "Choose two different contacts.")
    context.db.execute(
        update(Conversation)
        .where(Conversation.tenant_id == context.tenant_id, Conversation.contact_id == source.id)
        .values(contact_id=target.id)
    )
    context.db.execute(
        update(ContactIdentity)
        .where(
            ContactIdentity.tenant_id == context.tenant_id, ContactIdentity.contact_id == source.id
        )
        .values(contact_id=target.id)
    )
    target.tags = list(dict.fromkeys([*target.tags, *source.tags]))
    target.custom_fields = {**source.custom_fields, **target.custom_fields}
    target.consent = {**source.consent, **target.consent}
    target.updated_at = datetime.now(UTC)
    record_audit(
        context.db,
        action="contact.merge",
        tenant_id=context.tenant_id,
        actor_user_id=context.user.id,
        target_type="contact",
        target_id=str(target.id),
        metadata={"source_contact_id": str(source.id)},
    )
    context.db.delete(source)
    context.db.commit()
    return ContactOut.model_validate(target)


@router.get("/{contact_id}")
def get_contact(contact_id: UUID, context: TenantContextDep) -> dict[str, object]:
    context.require_role("viewer")
    row = _contact(context, contact_id)
    identities = (
        context.db.execute(
            select(ContactIdentity)
            .where(
                ContactIdentity.tenant_id == context.tenant_id, ContactIdentity.contact_id == row.id
            )
            .order_by(ContactIdentity.channel, ContactIdentity.external_id)
        )
        .scalars()
        .all()
    )
    conversations = (
        context.db.execute(
            select(Conversation)
            .where(Conversation.tenant_id == context.tenant_id, Conversation.contact_id == row.id)
            .order_by(Conversation.created_at.desc())
        )
        .scalars()
        .all()
    )
    timeline: list[dict[str, object]] = []
    for conversation in conversations:
        timeline.append(
            {
                "type": "conversation",
                "id": str(conversation.id),
                "channel": conversation.channel,
                "status": conversation.status,
                "created_at": conversation.created_at.isoformat(),
            }
        )
        notes = (
            context.db.execute(
                select(Message)
                .where(
                    Message.tenant_id == context.tenant_id,
                    Message.conversation_id == conversation.id,
                    Message.sender_type == "system",
                    Message.text.like("Internal note:%"),
                )
                .order_by(Message.created_at)
            )
            .scalars()
            .all()
        )
        timeline.extend(
            {
                "type": "note",
                "conversation_id": str(conversation.id),
                "text": note.text.removeprefix("Internal note: "),
                "created_at": note.created_at.isoformat(),
            }
            for note in notes
        )
    timeline.sort(key=lambda item: str(item["created_at"]), reverse=True)
    return {
        "contact": ContactOut.model_validate(row).model_dump(mode="json"),
        "identities": [
            {
                "channel": identity.channel,
                "external_id": identity.external_id,
                "created_at": identity.created_at.isoformat(),
            }
            for identity in identities
        ],
        "timeline": timeline,
    }


@router.patch("/{contact_id}")
def update_contact(
    contact_id: UUID, body: ContactUpdate, context: TenantContextDep, _: CsrfOk
) -> ContactOut:
    context.require_role("editor")
    row = _contact(context, contact_id)
    changes = body.model_dump(exclude_unset=True, mode="json")
    next_email = changes.get("email", row.email)
    next_phone = changes.get("phone", row.phone)
    _ensure_reachable_and_unique(
        context,
        email=str(next_email) if next_email else None,
        phone=str(next_phone) if next_phone else None,
        exclude_id=row.id,
    )
    if "stage" in changes and changes["stage"] not in {stage.name for stage in _stages(context)}:
        raise ApiError(422, "VALIDATION_ERROR", "Unknown contact stage.")
    if (
        "custom_fields" in changes
        and changes["custom_fields"] is not None
        and len(changes["custom_fields"]) > 20
    ):
        raise ApiError(422, "VALIDATION_ERROR", "A contact can have at most 20 custom fields.")
    if (
        "tags" in changes
        and changes["tags"] is not None
        and any(not tag.strip() or len(tag) > 64 for tag in changes["tags"])
    ):
        raise ApiError(422, "VALIDATION_ERROR", "Tags must be 1-64 characters.")
    for key, value in changes.items():
        setattr(row, key, value)
    row.updated_at = datetime.now(UTC)
    context.db.commit()
    return ContactOut.model_validate(row)


@router.delete("/{contact_id}", status_code=204)
def erase_contact(
    contact_id: UUID,
    context: TenantContextDep,
    _: CsrfOk,
    erase_messages: bool = Query(default=False),
) -> Response:
    context.require_role("admin")
    row = _contact(context, contact_id)
    conversations = (
        context.db.execute(
            select(Conversation).where(
                Conversation.tenant_id == context.tenant_id, Conversation.contact_id == row.id
            )
        )
        .scalars()
        .all()
    )
    if erase_messages:
        for conv in conversations:
            context.db.execute(
                delete(Message).where(
                    Message.tenant_id == context.tenant_id, Message.conversation_id == conv.id
                )
            )
    context.db.execute(
        update(Conversation)
        .where(Conversation.tenant_id == context.tenant_id, Conversation.contact_id == row.id)
        .values(contact_id=None)
    )
    record_audit(
        context.db,
        action="contact.erase",
        tenant_id=context.tenant_id,
        actor_user_id=context.user.id,
        target_type="contact",
        target_id=str(row.id),
        metadata={"erase_messages": erase_messages},
    )
    context.db.delete(row)
    context.db.commit()
    return Response(status_code=204)
