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

from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.core.audit import record_audit
from app.core.config import Settings
from app.core.errors import ApiError
from app.db.models import Invitation, ProvisioningRequest, Tenant, User

OWNER_INVITATION_EXPIRY_DAYS = 7  # docs/14 §19 default
_MAX_FILES = 20


class ProvisioningPayload(BaseModel):
    client_name: str = Field(min_length=1, max_length=200)
    owner_email: EmailStr
    bot_name: str | None = Field(default=None, min_length=1, max_length=100)
    plan_label: str = "starter"  # internal label; real plans arrive in P7
    notes: str | None = Field(default=None, max_length=500)


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

    # --- provisioning steps ---------------------------------------------------

    def _provision(
        self,
        row: ProvisioningRequest,
        *,
        actor: User,
        payload: ProvisioningPayload,
        files: Sequence[tuple[str, bytes]],
    ) -> dict[str, Any]:
        slug = self._unique_slug(payload.client_name)
        tenant = Tenant(id=uuid4(), name=payload.client_name.strip(), slug=slug)
        self.db.add(tenant)
        self.db.flush()  # tenant must exist before its audit row
        record_audit(
            self.db,
            action="platform.onboarding.tenant_created",
            tenant_id=tenant.id,
            actor_user_id=actor.id,
            target_type="tenant",
            target_id=str(tenant.id),
            metadata={"request_id": str(row.id), "plan_label": payload.plan_label},
        )

        # Owner one-time invitation (docs/14 §19): raw token is shown ONCE in
        # the response; only its SHA-256 hash is stored. Ownership arrives
        # when the invited user accepts (no email provider).
        raw_token = secrets.token_urlsafe(24)
        invitation = Invitation(
            id=uuid4(),
            tenant_id=tenant.id,
            email=payload.owner_email,  # CITEXT: case-insensitive
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
            bot = self._make_bot(tenant.id, payload.bot_name, actor, row.id)
            bot_id = str(bot.id)

        stored_files: list[dict[str, str]] = []
        if files:
            stored_files = self._store_files(tenant_id=tenant.id, files=files)

        return {
            "tenant_id": str(tenant.id),
            "tenant_slug": slug,
            "bot_id": bot_id,
            "owner_invite": {
                "email": str(payload.owner_email),
                "link_path": f"/accept-invite?token={raw_token}",  # shown once
                "expires_at": invitation.expires_at.isoformat(),
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

    def _make_bot(self, tenant_id: UUID, bot_name: str, actor: User, request_id: UUID) -> Any:
        from app.db.models import Bot

        bot = Bot(id=uuid4(), tenant_id=tenant_id, name=bot_name.strip(), config={})
        self.db.add(bot)
        self.db.flush()
        record_audit(
            self.db,
            action="platform.onboarding.bot_created",
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
        from app.knowledge.storage import LocalStorage

        storage = LocalStorage(self.settings)
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
