"""Bot service: create/list/get/patch and soft archive (docs/05, docs/18).

Archive is soft: `status` becomes 'archived', the row stays, the default
listing excludes it. Every privileged write is audited in the same
transaction as the change (docs/06).
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.bots.schemas import BotConfig, BotCreateRequest, BotUpdateRequest
from app.core.audit import record_audit
from app.core.errors import ApiError
from app.core.tenancy import TenantContext
from app.db.models import Bot


class BotService:
    def __init__(self, db: OrmSession) -> None:
        self.db = db

    def create_bot(self, context: TenantContext, body: BotCreateRequest) -> Bot:
        bot = Bot(
            id=uuid4(),
            tenant_id=context.tenant_id,
            name=body.name.strip(),
            status="draft",
            config={},
        )
        self.db.add(bot)
        self.db.flush()  # bots row must exist before its audit event
        record_audit(
            self.db,
            action="bot.created",
            tenant_id=context.tenant_id,
            actor_user_id=context.user.id,
            target_type="bot",
            target_id=str(bot.id),
        )
        self.db.commit()
        return bot

    def list_bots(self, context: TenantContext, *, include_archived: bool = False) -> Sequence[Bot]:
        statement = select(Bot).where(Bot.tenant_id == context.tenant_id)
        if not include_archived:
            statement = statement.where(Bot.status != "archived")
        return list(self.db.execute(statement.order_by(Bot.created_at.desc())).scalars())

    def get_bot(self, context: TenantContext, bot_id: UUID) -> Bot:
        bot = self.db.get(Bot, bot_id)
        # Tenant-scoped read: another tenant's id (or an unknown id) is a plain 404.
        if bot is None or bot.tenant_id != context.tenant_id:
            raise ApiError(404, "NOT_FOUND", "Resource not found.")
        return bot

    def update_bot(self, context: TenantContext, bot_id: UUID, body: BotUpdateRequest) -> Bot:
        bot = self.get_archivable_bot(context, bot_id)
        changes: list[str] = []
        if body.name is not None and body.name.strip() != bot.name:
            bot.name = body.name.strip()
            changes.append("name")
        if body.config is not None:
            bot.config = self._merge_config(bot, body.config)
            changes.append("config")
        if changes:
            bot.updated_at = datetime.now(UTC)
            self.db.add(bot)
            record_audit(
                self.db,
                action="bot.updated",
                tenant_id=context.tenant_id,
                actor_user_id=context.user.id,
                target_type="bot",
                target_id=str(bot.id),
                metadata={"fields": changes},
            )
            self.db.commit()
        return bot

    def archive_bot(self, context: TenantContext, bot_id: UUID) -> Bot:
        """Soft archive (idempotent): archived bots keep config and stay out of the default list."""
        bot = self.get_bot(context, bot_id)
        if bot.status != "archived":
            bot.status = "archived"
            bot.updated_at = datetime.now(UTC)
            self.db.add(bot)
            record_audit(
                self.db,
                action="bot.archived",
                tenant_id=context.tenant_id,
                actor_user_id=context.user.id,
                target_type="bot",
                target_id=str(bot.id),
            )
            self.db.commit()
        return bot

    # --- internals -----------------------------------------------------------

    def get_archivable_bot(self, context: TenantContext, bot_id: UUID) -> Bot:
        """Editable bots are the caller's tenant's non-archived ones."""
        bot = self.get_bot(context, bot_id)
        if bot.status == "archived":
            raise ApiError(409, "BOT_ARCHIVED", "An archived bot cannot be edited.")
        return bot

    def _merge_config(self, bot: Bot, patch: BotConfig) -> dict[str, object]:
        merged: dict[str, object] = dict(bot.config)
        provided = patch.model_dump(exclude_unset=True, exclude_none=True)
        for key, value in provided.items():
            if key == "welcome_message" and isinstance(value, dict):
                existing = merged.get("welcome_message")
                merged_message = dict(existing) if isinstance(existing, dict) else {}
                merged_message.update({k: v for k, v in value.items()})
                merged["welcome_message"] = merged_message
            else:
                merged[key] = value
        return merged
