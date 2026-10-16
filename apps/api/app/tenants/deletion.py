"""Organization disablement and retryable storage-first purging."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session as OrmSession

from app.core.audit import record_audit
from app.core.config import Settings
from app.core.errors import ApiError
from app.core.tenancy import TenantContext
from app.db.models import (
    Bot,
    ChangeRequest,
    Contact,
    Conversation,
    Invitation,
    Job,
    Membership,
    Message,
    OrganizationDeletion,
    ProvisioningRequest,
    RateLimitCounter,
    Session,
    Source,
    Tenant,
    VisitorSession,
)
from app.knowledge.storage import get_storage
from app.quotas.service import lock_tenant


def deletion_counts(db: OrmSession, tenant_id: UUID) -> dict[str, int]:
    return {
        model.__tablename__: db.scalar(
            select(func.count()).select_from(model).where(model.tenant_id == tenant_id)
        )
        or 0
        for model in (Bot, Membership, Contact, Conversation, Message, Source, ChangeRequest)
    }


def schedule_deletion(context: TenantContext, name: str, reason: str, settings: Settings) -> None:
    context.require_operator()
    db, tenant_id = context.db, context.tenant_id
    tenant = lock_tenant(db, tenant_id)
    if name != tenant.name:
        raise ApiError(
            422, "CONFIRMATION_MISMATCH", "Enter the organization name exactly to confirm deletion."
        )
    if db.scalar(select(OrganizationDeletion).where(OrganizationDeletion.tenant_id == tenant_id)):
        return
    now = datetime.now(UTC)
    keys = list(db.scalars(select(Source.storage_key).where(Source.tenant_id == tenant_id)))
    for request in db.scalars(select(ChangeRequest).where(ChangeRequest.tenant_id == tenant_id)):
        keys.extend(str(item["storage_key"]) for item in request.attachments)
    for provision in db.scalars(
        select(ProvisioningRequest).where(ProvisioningRequest.tenant_id == tenant_id)
    ):
        keys.extend(
            item["storage_key"]
            for item in provision.result.get("files", [])
            if isinstance(item, dict) and "storage_key" in item
        )
    db.add(
        OrganizationDeletion(
            tenant_id=tenant_id,
            organization_name=tenant.name,
            actor_user_id=context.user.id,
            reason=reason,
            requested_at=now,
            storage_keys=sorted(set(keys)),
            counts=deletion_counts(db, tenant_id),
            purge_after=now + timedelta(days=settings.org_deletion_grace_days),
        )
    )
    record_audit(
        db,
        action="tenant.deletion.scheduled",
        tenant_id=None,
        actor_user_id=context.user.id,
        target_type="tenant",
        target_id=str(tenant_id),
        metadata={"reason": reason, "grace_days": settings.org_deletion_grace_days},
    )
    tenant.status = "archived"
    # Revoke current login sessions; membership and tenant status also deny newly
    # authenticated requests. Users with other organizations can sign in again.
    members = select(Membership.user_id).where(Membership.tenant_id == tenant_id)
    db.execute(update(Session).where(Session.user_id.in_(members)).values(revoked_at=now))
    db.execute(update(Membership).where(Membership.tenant_id == tenant_id).values(status="revoked"))
    db.execute(update(Invitation).where(Invitation.tenant_id == tenant_id).values(revoked_at=now))
    db.execute(update(Bot).where(Bot.tenant_id == tenant_id).values(status="archived"))
    db.execute(
        update(VisitorSession).where(VisitorSession.tenant_id == tenant_id).values(expires_at=now)
    )
    db.execute(update(Job).where(Job.tenant_id == tenant_id).values(cancel_requested=True))
    db.commit()


def purge_deleted_organizations(db: OrmSession, settings: Settings) -> int:
    """Worker maintenance: failures retain the manifest for the next attempt."""
    now = datetime.now(UTC)
    records = list(
        db.scalars(
            select(OrganizationDeletion)
            .where(
                OrganizationDeletion.purged_at.is_(None),
                OrganizationDeletion.purge_after <= now,
            )
            .with_for_update(skip_locked=True)
        )
    )
    storage = get_storage(settings)
    for record in records:
        # Storage deletion must raise on failure. LocalStorage's regular delete
        # is best effort, so use strict deletion for this lifecycle operation.
        for key in record.storage_keys:
            storage.delete_strict(key)
        storage.purge_tenant_strict(record.tenant_id)
        db.execute(
            delete(ProvisioningRequest).where(ProvisioningRequest.tenant_id == record.tenant_id)
        )
        visitor_ids = list(
            db.scalars(
                select(VisitorSession.id).where(VisitorSession.tenant_id == record.tenant_id)
            )
        )
        if visitor_ids:
            db.execute(
                delete(RateLimitCounter).where(
                    or_(
                        *(
                            RateLimitCounter.bucket_key.like(f"widget:msg:%:{sid}")
                            for sid in visitor_ids
                        )
                    )
                )
            )
        db.execute(delete(Tenant).where(Tenant.id == record.tenant_id))
        record.storage_keys = []
        record.purged_at = now
        record_audit(
            db,
            action="tenant.data.purged",
            tenant_id=None,
            actor_user_id=None,
            target_type="tenant",
            target_id=str(record.tenant_id),
        )
    db.commit()
    return len(records)
