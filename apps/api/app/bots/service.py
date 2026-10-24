"""Bot service: create/list/get/patch and soft archive (docs/05, docs/18).

Archive is soft: `status` becomes 'archived', the row stays, the default
listing excludes it. Every privileged write is audited in the same
transaction as the change (docs/06). Bots also carry the opaque public
widget locator (P4-01, docs/05): assigned once at creation, never rotatable
by tenant input, and NOT a secret (docs/09) — it only names the bot; all
authority stays server-side.
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.bots.schemas import BotConfig, BotCreateRequest, BotUpdateRequest, ReadinessItem
from app.core.audit import record_audit
from app.core.errors import ApiError
from app.core.tenancy import TenantContext
from app.db.models import Bot

ALLOWED_STATUS_TRANSITIONS = {
    "draft": {"active"},
    "active": {"paused", "active"},
    "paused": {"active", "paused"},
}


def validate_status_transition(current: str, requested: str) -> str:
    if current == requested:
        return requested
    if current == "archived":
        raise ApiError(409, "BOT_ARCHIVED", "An archived bot cannot change status here.")
    if current == "draft" and requested == "paused":
        raise ApiError(422, "VALIDATION_ERROR", "Pause an active bot, not a draft.")
    allowed = ALLOWED_STATUS_TRANSITIONS.get(current, set())
    if requested not in allowed:
        raise ApiError(
            422,
            "VALIDATION_ERROR",
            f"Status cannot change from {current} to {requested}.",
        )
    return requested


def readiness_items(bot: Bot) -> list[ReadinessItem]:
    """Read-only checklist computed from the bot's real state (#26)."""
    config = bot.config if isinstance(bot.config, dict) else {}

    def text(key: str) -> str:
        value = config.get(key)
        return value.strip() if isinstance(value, str) else ""

    welcome_raw = config.get("welcome_message")
    welcome = welcome_raw if isinstance(welcome_raw, dict) else {}
    has_welcome = any(isinstance(v, str) and v.strip() for v in welcome.values())
    domains_raw = config.get("allowed_domains")
    domains = (
        [d for d in domains_raw if isinstance(d, str) and d.strip()]
        if isinstance(domains_raw, list)
        else []
    )
    has_contact = bool(text("support_email") or text("support_phone"))
    published = bot.published_revision_id is not None
    return [
        ReadinessItem(
            id="support_contact",
            label="Support email or phone",
            status="ok" if has_contact else "todo",
            detail="Shown when the assistant cannot answer."
            if has_contact
            else "Add a support email or phone so visitors know where to go.",
            section="contact",
        ),
        ReadinessItem(
            id="welcome_message",
            label="Welcome message",
            status="ok" if has_welcome else "todo",
            detail="Custom welcome message set."
            if has_welcome
            else "Not set: the widget uses a generic greeting.",
            section="messages",
        ),
        ReadinessItem(
            id="allowed_domains",
            label="Allowed websites",
            status="ok" if domains else "warning",
            detail=f"{len(domains)} website(s) can embed the widget."
            if domains
            else "Open: any website can embed this widget. Add the client's domains.",
            section="access",
        ),
        ReadinessItem(
            id="knowledge_published",
            label="Knowledge published",
            status="ok" if published else "todo",
            detail="A knowledge revision is published."
            if published
            else "Nothing is published yet: the assistant has no knowledge to answer from.",
            section="knowledge",
        ),
        ReadinessItem(
            id="tier",
            label="AI tier",
            status="ok" if bot.tier in ("standard", "premium") else "todo",
            detail=f"{bot.tier.capitalize()} tier selected.",
            section="tier",
        ),
    ]


class BotService:
    def __init__(self, db: OrmSession) -> None:
        self.db = db

    def create_bot(self, context: TenantContext, body: BotCreateRequest) -> Bot:
        from app.bots.factory import create_bot_record

        bot = create_bot_record(
            self.db,
            tenant_id=context.tenant_id,
            name=body.name,
            actor=context.user,
            audit_action="bot.created",
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
        requested_status: str | None = None
        if body.status is not None:
            if body.status not in ("draft", "active", "paused", "archived"):
                raise ApiError(422, "VALIDATION_ERROR", "Unknown bot status.")
            requested_status = validate_status_transition(bot.status, body.status)
        if body.name is not None and body.name.strip() != bot.name:
            bot.name = body.name.strip()
            changes.append("name")
        if "tone_and_rules" in body.model_fields_set:
            tone = (body.tone_and_rules or "").strip() or None
            if tone != bot.tone_and_rules:
                bot.tone_and_rules = tone
                changes.append("tone_and_rules")  # field name only, never the text
        if body.config is not None:
            bot.config = self._merge_config(bot, body.config)
            changes.append("config")
        if requested_status is not None and requested_status != bot.status:
            bot.status = requested_status
            changes.append("status")
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
        if "knowledge_language" in patch.model_fields_set and patch.knowledge_language is None:
            merged.pop("knowledge_language", None)  # null clears it: back to default_language
        for key, value in provided.items():
            if key == "welcome_message" and isinstance(value, dict):
                existing = merged.get("welcome_message")
                merged_message = dict(existing) if isinstance(existing, dict) else {}
                merged_message.update({k: v for k, v in value.items()})
                merged["welcome_message"] = merged_message
            else:
                merged[key] = value
        return merged
