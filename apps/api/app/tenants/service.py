"""Tenant service: create/list/get + membership and invitation management.

Business rules (docs/14 s19, docs/06):
- Tenant creation makes the creator admin and audits the event.
- Admins manage invitations and member roles.
- Tokens are single-use, hashed at rest, expire and can be revoked/resended.
- Accepting requires a session whose email matches the invitation.
- The last active admin cannot be demoted or removed (under a tenant row lock).
"""

import re
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session as OrmSession

from app.auth.security import generate_session_token, hash_token
from app.core.audit import record_audit
from app.core.errors import ApiError
from app.core.tenancy import ROLE_LEVELS, TenantContext
from app.db.models import Invitation, Membership, Tenant, User
from app.db.models.core import ClientRole
from app.quotas.service import lock_tenant, require_capacity
from app.tenants.schemas import MAX_INVITATION_EXPIRY_DAYS

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DEFAULT_INVITATION_EXPIRY_DAYS = 7


class TenantService:
    def __init__(self, db: OrmSession) -> None:
        self.db = db

    # --- tenants -----------------------------------------------------------

    def create_tenant(self, user: User, name: str, slug: str | None) -> Tenant:
        slug = self._unique_slug(slug or name)
        tenant = Tenant(
            id=uuid4(), name=name.strip(), slug=slug, status="active", quota_overrides={"bots": 1}
        )
        admin = Membership(tenant_id=tenant.id, user_id=user.id, role="admin", status="active")
        self.db.add_all([tenant, admin])
        self.db.flush()  # tenants row must exist before its audit event
        record_audit(
            self.db,
            action="tenant.created",
            tenant_id=tenant.id,
            actor_user_id=user.id,
            target_type="tenant",
            target_id=str(tenant.id),
        )
        self.db.commit()
        return tenant

    def get_tenant(self, tenant_id: UUID) -> Tenant:
        tenant = self.db.get(Tenant, tenant_id)
        if tenant is None:
            raise ApiError(404, "NOT_FOUND", "Resource not found.")
        return tenant

    def update_tenant(self, context: "TenantContext", retention_days: int | None) -> Tenant:
        """Tenant-level settings (P4-04): the message retention window (docs/14 §7).

        Admin only (privileged write → audited)."""
        tenant = context.tenant
        changed = tenant.retention_days != retention_days
        tenant.retention_days = retention_days
        self.db.add(tenant)
        if changed:
            record_audit(
                self.db,
                action="tenant.updated",
                tenant_id=context.tenant_id,
                actor_user_id=context.user.id,
                target_type="tenant",
                target_id=str(context.tenant_id),
                metadata={"fields": ["retention_days"], "retention_days": retention_days},
            )
        self.db.commit()
        return tenant

    def memberships_of(self, user_id: object) -> list[tuple[Membership, Tenant]]:
        rows = self.db.execute(
            select(Membership, Tenant)
            .join(Tenant, Membership.tenant_id == Tenant.id)
            .where(
                Membership.user_id == user_id,
                Membership.status == "active",
                Tenant.status == "active",
            )
            .order_by(Tenant.created_at)
        ).all()
        return [(membership, tenant) for membership, tenant in rows]

    def members_of(self, tenant_id: UUID) -> list[tuple[Membership, User]]:
        rows = self.db.execute(
            select(Membership, User)
            .join(User, Membership.user_id == User.id)
            .where(Membership.tenant_id == tenant_id, Membership.status == "active")
            .order_by(Membership.created_at)
        ).all()
        return [(membership, user) for membership, user in rows]

    def _unique_slug(self, seed: str) -> str:
        base = re.sub(r"[^a-z0-9]+", "-", seed.lower()).strip("-") or "org"
        base = base[:40].strip("-")
        candidate = base
        while self.db.execute(
            select(Tenant.id).where(Tenant.slug == candidate)
        ).scalar_one_or_none():
            candidate = f"{base}-{uuid4().hex[:8]}"
            if not SLUG_RE.fullmatch(candidate):  # pragma: no cover - hex suffix is safe
                raise ApiError(500, "INTERNAL_ERROR", "Slug generation failed.")
        return candidate

    # --- invitations -------------------------------------------------------

    def create_invitation(
        self,
        context: TenantContext,
        email: str,
        role: str,
        expiry_days: int,
    ) -> tuple[Invitation, str]:
        tenant = lock_tenant(self.db, context.tenant_id)
        require_capacity(self.db, tenant, "seats")
        if role not in ROLE_LEVELS:
            raise ApiError(422, "VALIDATION_ERROR", f"Unknown role: {role}.")
        if expiry_days > MAX_INVITATION_EXPIRY_DAYS:
            raise ApiError(
                422, "VALIDATION_ERROR", f"Expiry cannot exceed {MAX_INVITATION_EXPIRY_DAYS} days."
            )

        existing_member = self.db.execute(
            select(Membership)
            .join(User, Membership.user_id == User.id)
            .where(Membership.tenant_id == context.tenant_id, User.email == email.strip())
        ).scalar_one_or_none()
        if existing_member is not None and existing_member.status == "active":
            raise ApiError(409, "ALREADY_MEMBER", "This user is already a member.")

        token = generate_session_token()
        invitation = Invitation(
            id=uuid4(),
            tenant_id=context.tenant_id,
            email=email.strip().lower(),
            role=role,
            token_hash=hash_token(token),
            expires_at=datetime.now(UTC) + timedelta(days=expiry_days),
            created_by=context.user.id,
        )
        self.db.add(invitation)
        record_audit(
            self.db,
            action="invitation.created",
            tenant_id=context.tenant_id,
            actor_user_id=context.user.id,
            target_type="invitation",
            target_id=str(invitation.id),
            metadata={"role": role, "expiry_days": expiry_days},
        )
        self.db.commit()
        return invitation, token

    def pending_invitations(self, context: TenantContext) -> Sequence[Invitation]:
        return list(
            self.db.execute(
                select(Invitation)
                .where(
                    Invitation.tenant_id == context.tenant_id,
                    Invitation.accepted_at.is_(None),
                    Invitation.revoked_at.is_(None),
                )
                .order_by(Invitation.created_at.desc())
            ).scalars()
        )

    def resend_invitation(
        self, context: TenantContext, invitation_id: UUID, expiry_days: int
    ) -> tuple[Invitation, str]:
        invitation = self._get_invitation(context.tenant_id, invitation_id)
        if invitation.accepted_at is not None:
            raise ApiError(409, "INVITATION_USED", "This invitation was already accepted.")
        if invitation.revoked_at is not None:
            raise ApiError(409, "INVITATION_REVOKED", "This invitation was revoked.")
        token = generate_session_token()
        invitation.token_hash = hash_token(token)
        invitation.expires_at = datetime.now(UTC) + timedelta(days=expiry_days)
        invitation.revoked_at = None
        self.db.add(invitation)
        record_audit(
            self.db,
            action="invitation.resent",
            tenant_id=context.tenant_id,
            actor_user_id=context.user.id,
            target_type="invitation",
            target_id=str(invitation.id),
        )
        self.db.commit()
        return invitation, token

    def revoke_invitation(self, context: TenantContext, invitation_id: UUID) -> Invitation:
        invitation = self._get_invitation(context.tenant_id, invitation_id)
        if invitation.accepted_at is not None:
            raise ApiError(409, "INVITATION_USED", "This invitation was already accepted.")
        if invitation.revoked_at is not None:
            raise ApiError(409, "INVITATION_REVOKED", "This invitation was already revoked.")
        invitation.revoked_at = datetime.now(UTC)
        self.db.add(invitation)
        record_audit(
            self.db,
            action="invitation.revoked",
            tenant_id=context.tenant_id,
            actor_user_id=context.user.id,
            target_type="invitation",
            target_id=str(invitation.id),
        )
        self.db.commit()
        return invitation

    def accept_invitation(self, db: OrmSession, user: User, token: str) -> Membership:
        # Lock the invitation row: two concurrent accepts of one token must
        # serialize, so exactly one performs the accept and the other sees
        # `accepted_at` set (409) instead of creating a duplicate membership.
        invitation = db.execute(
            select(Invitation)
            .where(Invitation.token_hash == hash_token(token.strip()))
            .with_for_update()
        ).scalar_one_or_none()
        now = datetime.now(UTC)
        if invitation is None:
            raise ApiError(404, "NOT_FOUND", "Invitation not found or no longer valid.")
        if invitation.accepted_at is not None:
            raise ApiError(409, "INVITATION_USED", "This invitation was already accepted.")
        if invitation.revoked_at is not None:
            raise ApiError(409, "INVITATION_REVOKED", "This invitation was revoked.")
        if invitation.expires_at <= now:
            raise ApiError(409, "INVITATION_EXPIRED", "This invitation has expired.")
        if user.email.strip().lower() != invitation.email:
            raise ApiError(
                403,
                "INVITEE_EMAIL_MISMATCH",
                "Register or log in with the address the invitation was sent to.",
            )

        tenant = lock_tenant(db, invitation.tenant_id)
        existing_membership = db.execute(
            select(Membership).where(
                Membership.tenant_id == invitation.tenant_id,
                Membership.user_id == user.id,
            )
        ).scalar_one_or_none()
        if existing_membership is None or existing_membership.status != "active":
            # The pending invitation being accepted already holds a seat in the
            # usage count, so accepting needs no extra seat (amount=0); it is only
            # refused if the tenant is already over its limit.
            require_capacity(db, tenant, "seats", amount=0)

        existing = db.execute(
            select(Membership).where(
                Membership.tenant_id == invitation.tenant_id,
                Membership.user_id == user.id,
            )
        ).scalar_one_or_none()
        if existing is not None:
            if existing.status == "active":
                raise ApiError(409, "ALREADY_MEMBER", "You are already a member of this tenant.")
            existing.role = invitation.role
            existing.status = "active"
            membership = existing
        else:
            membership = Membership(
                tenant_id=invitation.tenant_id, user_id=user.id, role=invitation.role
            )
            db.add(membership)
        invitation.accepted_at = now
        db.add(invitation)
        record_audit(
            db,
            action="invitation.accepted",
            tenant_id=invitation.tenant_id,
            actor_user_id=user.id,
            target_type="invitation",
            target_id=str(invitation.id),
            metadata={"role": membership.role},
        )
        db.commit()
        return membership

    def _get_invitation(self, tenant_id: UUID, invitation_id: UUID) -> Invitation:
        invitation = self.db.get(Invitation, invitation_id)
        if invitation is None or invitation.tenant_id != tenant_id:
            raise ApiError(404, "NOT_FOUND", "Invitation not found.")
        return invitation

    # --- members -----------------------------------------------------------

    def change_role(self, context: TenantContext, user_id: UUID, new_role: str) -> Membership:
        lock_tenant(self.db, context.tenant_id)
        if new_role not in ROLE_LEVELS:
            raise ApiError(422, "VALIDATION_ERROR", f"Unknown role: {new_role}.")
        membership = self._get_membership(context.tenant_id, user_id)
        if membership.role == new_role:
            return membership
        if membership.role == "admin" and new_role != "admin":
            # Downgrading an admin: check a second admin remains atomically.
            admins = self.db.execute(
                select(func.count())
                .select_from(Membership)
                .where(
                    Membership.tenant_id == context.tenant_id,
                    Membership.role == "admin",
                    Membership.status == "active",
                    Membership.user_id != user_id,
                )
            ).scalar_one()
            if admins == 0:
                raise ApiError(403, "LAST_ADMIN", "The last admin cannot be demoted or removed.")
        record_audit(
            self.db,
            action="member.role_changed",
            tenant_id=context.tenant_id,
            actor_user_id=context.user.id,
            target_type="membership",
            target_id=str(membership.user_id),
            metadata={"from": membership.role, "to": new_role},
        )
        membership.role = cast(ClientRole, new_role)
        self.db.add(membership)
        self.db.commit()
        return membership

    def remove_member(self, context: TenantContext, user_id: UUID) -> None:
        lock_tenant(self.db, context.tenant_id)
        membership = self._get_membership(context.tenant_id, user_id)
        if membership.role == "admin" and self._admin_count(context.tenant_id) == 1:
            raise ApiError(403, "LAST_ADMIN", "The last admin cannot leave or be removed.")
        record_audit(
            self.db,
            action="member.removed",
            tenant_id=context.tenant_id,
            actor_user_id=context.user.id,
            target_type="membership",
            target_id=str(membership.user_id),
            metadata={"was_role": membership.role},
        )
        # Keep the membership anchor for historical senders/assignments.
        # Authorization and seat counts only include active memberships.
        membership.status = "revoked"
        self.db.add(membership)
        # An older outstanding invite must not restore the access just removed.
        member = self.db.get(User, user_id)
        assert member is not None  # membership FK guarantees presence
        self.db.execute(
            update(Invitation)
            .where(
                Invitation.tenant_id == context.tenant_id,
                Invitation.email == member.email,
                Invitation.accepted_at.is_(None),
                Invitation.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(UTC))
        )
        self.db.commit()

    def _get_membership(self, tenant_id: UUID, user_id: UUID) -> Membership:
        membership = self.db.execute(
            select(Membership).where(
                Membership.tenant_id == tenant_id,
                Membership.user_id == user_id,
                Membership.status == "active",
            )
        ).scalar_one_or_none()
        if membership is None:
            raise ApiError(404, "NOT_FOUND", "Member not found.")
        return membership

    def _admin_count(self, tenant_id: UUID) -> int:
        return int(
            self.db.execute(
                select(func.count())
                .select_from(Membership)
                .where(
                    Membership.tenant_id == tenant_id,
                    Membership.role == "admin",
                    Membership.status == "active",
                )
            ).scalar_one()
        )
