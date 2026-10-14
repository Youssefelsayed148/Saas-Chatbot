"""Shared ProvisioningService (docs/12): one path for staff onboarding (P4-06)
and, later, self-service signup (P7-03 uses the SAME service).

Creates: tenant (unique slug) → owner one-time invitation (docs/14 §19: staff
copy the link; there is no email provider) → optional bot → optional
website-to-knowledge skill output, stored under generated tenant keys
(uploaded into a bot later through the ordinary Knowledge flow). Durable
request rows: the SAME (mode, idempotency_key) submit re-reads the row —
double submission creates exactly ONE tenant/bot; a DIFFERENT payload with
the same key is 409. Every state change is audited with the actor; staff
actions never borrow tenant roles and there is no impersonation.
"""

import hashlib
import secrets
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, BinaryIO
from uuid import UUID, uuid4

from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as OrmSession

from app.core.audit import record_audit
from app.core.config import Settings
from app.core.errors import ApiError
from app.db.models import Invitation, Membership, ProvisioningRequest, Tenant, User
from app.quotas.plans import PLAN_LABELS

OWNER_INVITATION_EXPIRY_DAYS = 7  # docs/14 §19 default
_MAX_FILES = 20


class ProvisioningPayload(BaseModel):
    client_name: str = Field(min_length=1, max_length=200)
    owner_email: EmailStr
    bot_name: str | None = Field(default=None, min_length=1, max_length=100)
    plan_label: str = "starter"  # PLACEHOLDER plan from quotas.plans
    notes: str | None = Field(default=None, max_length=500)

    @field_validator("plan_label")
    @classmethod
    def known_plan_label(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if cleaned not in PLAN_LABELS:
            raise ValueError("Choose a PLACEHOLDER plan: free, starter, pro, or business.")
        return cleaned


def _hash_payload(payload: ProvisioningPayload, files: Sequence[tuple[str, bytes]]) -> str:
    digest = hashlib.sha256()
    digest.update(payload.model_dump_json(exclude_none=True).encode("utf-8"))
    for name, data in files:
        digest.update(name.encode("utf-8"))
        digest.update(data)
    return digest.hexdigest()


def generate_request_id() -> UUID:
    return uuid4()


class ProvisioningService:
    def __init__(self, db: OrmSession, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or Settings()

    # --- durable request bookkeeping -----------------------------------------

    def _existing(
        self,
        *,
        mode: str,
        idempotency_key: str,
        payload_hash: str,
        actor: User,
    ) -> ProvisioningRequest | None:
        """Same (mode, key): re-read the prior row. A different payload on the
        same key, or another actor's key, is a 409 (never a second tenant)."""
        row = (
            self.db.execute(
                select(ProvisioningRequest).where(
                    ProvisioningRequest.mode == mode,
                    ProvisioningRequest.idempotency_key == idempotency_key,
                )
            )
            .scalars()
            .one_or_none()
        )
        if row is None:
            return None
        if row.payload_hash != payload_hash:
            raise ApiError(
                409,
                "IDEMPOTENCY_KEY_PAYLOAD_MISMATCH",
                "The Idempotency-Key was used with a different payload.",
            )
        if row.actor_user_id is not None and row.actor_user_id != actor.id:
            raise ApiError(
                409, "IDEMPOTENCY_KEY_ACTOR_MISMATCH", "The key belongs to another actor."
            )
        return row

    def onboard_platform_client(
        self,
        *,
        actor: User,
        payload: ProvisioningPayload,
        idempotency_key: str,
        files: Sequence[tuple[str, BinaryIO]] | None = None,
    ) -> dict[str, Any]:
        """Staff onboarding (P4-06). The router enforces the staff flag; this
        service re-checks it (defence in depth)."""
        if not actor.is_platform_staff:
            raise ApiError(403, "FORBIDDEN", "Platform staff access required.")
        mode = "platform"
        file_blobs: list[tuple[str, bytes]] = [
            (name, data.read() or b"") for name, data in (files or [])
        ]
        if len(file_blobs) > self.settings.max_upload_files:
            raise ApiError(
                422,
                "VALIDATION_ERROR",
                f"Up to {self.settings.max_upload_files} files per request.",
            )
        payload_hash = _hash_payload(payload, file_blobs)
        prior = self._existing(
            mode=mode, idempotency_key=idempotency_key, payload_hash=payload_hash, actor=actor
        )
        if prior is not None:
            return {
                "request_id": str(prior.id),
                "status": prior.status,
                "tenant_id": str(prior.tenant_id) if prior.tenant_id else None,
                "result": dict(prior.result),
                "replayed": True,
            }

        row = ProvisioningRequest(
            id=generate_request_id(),
            actor_user_id=actor.id,
            mode=mode,
            status="requested",
            idempotency_key=idempotency_key,
            payload_hash=payload_hash,
            payload=payload.model_dump(exclude_none=True),
        )
        self._actor_id = actor.id
        self.db.add(row)
        self.db.flush()
        row.status = "provisioning"
        self.db.add(row)
        try:
            result = self._provision(row, actor=actor, payload=payload, files=file_blobs)
        except ApiError as api_error:
            self.db.rollback()
            row.status = "failed"
            row.error = api_error.message
            self.db.add(row)
            self.db.commit()
            raise
        except Exception as original:  # noqa: BLE001 — durable failure, then a generic error
            import traceback

            traceback.print_exc()  # diagnostic print (no payload content)
            self.db.rollback()
            row.status = "failed"
            row.error = "Unexpected error during provisioning."
            self.db.add(row)
            self.db.commit()
            raise ApiError(
                500, "INTERNAL_ERROR", "Provisioning failed; the request is recorded."
            ) from original
        row.status = "ready"
        row.result = dict(result)
        row.tenant_id = UUID(str(result["tenant_id"]))
        self.db.add(row)
        self.db.commit()
        return {"request_id": str(row.id), "status": "ready", "result": result}

    def onboard_self_service(
        self,
        *,
        actor: User,
        payload: ProvisioningPayload,
        idempotency_key: str,
    ) -> dict[str, Any]:
        """Create one free tenant and bot for a new account, idempotently."""
        if actor.is_platform_staff:
            raise ApiError(403, "FORBIDDEN", "Self-service signup is for client accounts.")
        if not payload.bot_name:
            raise ApiError(422, "VALIDATION_ERROR", "A bot name is required for signup.")
        mode = "self_service"
        payload_hash = _hash_payload(payload, [])
        prior = self._existing(
            mode=mode, idempotency_key=idempotency_key, payload_hash=payload_hash, actor=actor
        )
        if prior is not None:
            return {
                "request_id": str(prior.id),
                "status": prior.status,
                "tenant_id": str(prior.tenant_id) if prior.tenant_id else None,
                "result": dict(prior.result),
                "replayed": True,
            }
        already_member = self.db.execute(
            select(Membership.tenant_id)
            .where(Membership.user_id == actor.id, Membership.status == "active")
            .limit(1)
        ).first()
        if already_member is not None:
            raise ApiError(
                409, "ALREADY_PROVISIONED", "This account already belongs to an organization."
            )
        row = ProvisioningRequest(
            id=generate_request_id(),
            actor_user_id=actor.id,
            mode=mode,
            status="requested",
            idempotency_key=idempotency_key,
            payload_hash=payload_hash,
            payload=payload.model_dump(exclude_none=True),
        )
        self.db.add(row)
        try:
            self.db.flush()
            row.status = "provisioning"
            result = self._provision(row, actor=actor, payload=payload, files=(), self_service=True)
            row.status = "ready"
            row.tenant_id = UUID(str(result["tenant_id"]))
            row.result = dict(result)
            self.db.add(row)
            self.db.commit()
            return {"request_id": str(row.id), "status": "ready", "result": result}
        except IntegrityError:
            self.db.rollback()
            # A concurrent retry may have inserted and completed the same key.
            prior = self._existing(
                mode=mode, idempotency_key=idempotency_key, payload_hash=payload_hash, actor=actor
            )
            if prior is not None:
                return {
                    "request_id": str(prior.id),
                    "status": prior.status,
                    "tenant_id": str(prior.tenant_id) if prior.tenant_id else None,
                    "result": dict(prior.result),
                    "replayed": True,
                }
            raise ApiError(
                409, "PROVISIONING_CONFLICT", "Signup could not be completed safely."
            ) from None
        except Exception:
            self.db.rollback()
            raise

    # --- provisioning steps ---------------------------------------------------

    def _provision(
        self,
        row: ProvisioningRequest,
        *,
        actor: User,
        payload: ProvisioningPayload,
        files: Sequence[tuple[str, bytes]],
        self_service: bool = False,
    ) -> dict[str, Any]:
        slug = self._unique_slug(payload.client_name)
        tenant = Tenant(
            id=uuid4(),
            name=payload.client_name.strip(),
            slug=slug,
            plan_label="free" if self_service else (payload.plan_label or "starter"),
        )
        self.db.add(tenant)
        self.db.flush()  # tenant must exist before its audit row
        record_audit(
            self.db,
            action=(
                "self_service.tenant_created"
                if self_service
                else "platform.onboarding.tenant_created"
            ),
            tenant_id=tenant.id,
            actor_user_id=actor.id,
            target_type="tenant",
            target_id=str(tenant.id),
            metadata={"request_id": str(row.id), "plan_label": tenant.plan_label},
        )

        # Owner one-time invitation (docs/14 §19): raw token is shown ONCE in
        # the response; only its SHA-256 hash is stored. Ownership arrives
        # when the invited user accepts (no email provider).
        raw_token: str | None = None
        invitation: Invitation | None = None
        if self_service:
            membership = Membership(tenant_id=tenant.id, user_id=actor.id, role="owner")
            self.db.add(membership)
            record_audit(
                self.db,
                action="self_service.owner_assigned",
                tenant_id=tenant.id,
                actor_user_id=actor.id,
                target_type="membership",
                target_id=str(actor.id),
                metadata={"request_id": str(row.id)},
            )
        else:
            raw_token = secrets.token_urlsafe(24)
            invitation = Invitation(
                id=uuid4(),
                tenant_id=tenant.id,
                email=payload.owner_email,
                role="owner",
                token_hash=self._token_hash(raw_token),
                expires_at=datetime.now(UTC) + timedelta(days=OWNER_INVITATION_EXPIRY_DAYS),
                created_by=actor.id,
            )
            self.db.add(invitation)
            self.db.flush()
            record_audit(
                self.db,
                action="platform.onboarding.owner_invited",
                tenant_id=tenant.id,
                actor_user_id=actor.id,
                target_type="invitation",
                target_id=str(invitation.id),
                metadata={"request_id": str(row.id)},
            )

        bot_id: str | None = None
        if payload.bot_name:
            bot = self._make_bot(
                tenant.id, payload.bot_name, actor, row.id, self_service=self_service
            )
            bot_id = str(bot.id)

        stored_files: list[dict[str, str]] = []
        if files:
            stored_files = self._store_files(tenant_id=tenant.id, files=files)

        return {
            "tenant_id": str(tenant.id),
            "tenant_slug": slug,
            "bot_id": bot_id,
            "owner_invite": None
            if self_service
            else {
                "email": str(payload.owner_email),
                "link_path": f"/accept-invite?token={raw_token}",
                "expires_at": invitation.expires_at.isoformat() if invitation else None,
            },
            "files": stored_files,
        }

    def _unique_slug(self, seed: str) -> str:
        """Lowercase tenant slug (unique)."""
        slug_base = "".join(ch.lower() for ch in seed if ch.isalnum() or ch == " ")
        slug_base = "-".join(slug_base.split())[:40] or "client"
        candidate = slug_base
        index = 0
        while (
            self.db.execute(select(Tenant).where(Tenant.slug == candidate)).scalar_one_or_none()
            is not None
        ):
            index += 1
            candidate = f"{slug_base}-{index}"
        return candidate

    def _make_bot(
        self,
        tenant_id: UUID,
        bot_name: str,
        actor: User,
        request_id: UUID,
        *,
        self_service: bool = False,
    ) -> Any:
        from app.db.models import Bot

        bot = Bot(
            id=uuid4(),
            tenant_id=tenant_id,
            name=bot_name.strip(),
            config={},
            widget_locator="w" + secrets.token_hex(16),
        )
        self.db.add(bot)
        self.db.flush()
        record_audit(
            self.db,
            action=(
                "self_service.bot_created" if self_service else "platform.onboarding.bot_created"
            ),
            tenant_id=tenant_id,
            actor_user_id=actor.id,
            target_type="bot",
            target_id=str(bot.id),
            metadata={"request_id": str(request_id)},
        )
        return bot

    def _store_files(
        self, *, tenant_id: UUID, files: Sequence[tuple[str, bytes]]
    ) -> list[dict[str, str]]:
        """Skill-output files land on the tenant's storage under generated
        tenant/bot-namespaced keys — ONLY when an onboarding includes a bot to
        attach them to (storage keys require a bot; docs/14 §3). They are then
        uploaded into that bot through the normal Knowledge flow, whose parsers
        apply. Files are never served raw (docs/06)."""
        from app.db.models import Bot
        from app.knowledge.storage import get_storage

        storage = get_storage(self.settings)
        bot = (
            self.db.execute(
                select(Bot).where(Bot.tenant_id == tenant_id).order_by(Bot.created_at.desc())
            )
            .scalars()
            .first()
        )
        if bot is None:
            raise ApiError(
                422,
                "VALIDATION_ERROR",
                "Files need a bot to attach to — include bot_name with the upload.",
            )
        stored: list[dict[str, str]] = []
        for name, data in files:
            lowered = name.lower()
            if lowered.endswith(".md") or lowered.endswith(".markdown"):
                kind = "md"
            elif lowered.endswith(".txt"):
                kind = "txt"
            elif lowered.endswith(".csv"):
                kind = "qa_csv"
            elif lowered.endswith(".pdf"):
                kind = "pdf"
            elif lowered.endswith(".docx"):
                kind = "docx"
            else:
                raise ApiError(
                    422,
                    "VALIDATION_ERROR",
                    "Onboarding files must be md/txt/csv/pdf/docx (the skill output).",
                )
            saved_key = storage.save(tenant_id, bot.id, kind, data)
            stored.append({"display": name, "bot_id": str(bot.id), "storage_key": saved_key})
            record_audit(
                self.db,
                action="platform.onboarding.file_stored",
                tenant_id=tenant_id,
                actor_user_id=self._actor_id,
                target_type="storage",
                target_id=saved_key,
            )
        return stored

    _actor_id: UUID | None = None

    def _token_hash(self, raw_token: str) -> str:
        from app.auth.security import hash_token

        return hash_token(raw_token)
