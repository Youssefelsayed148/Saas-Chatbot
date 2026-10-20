"""Single transactional bot construction path for provisioning and operators."""

import secrets
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.core.audit import record_audit
from app.core.errors import ApiError
from app.db.models import Bot, User
from app.quotas.service import lock_tenant, require_capacity


def create_bot_record(
    db: Session,
    *,
    tenant_id: UUID,
    name: str,
    actor: User,
    audit_action: str,
    metadata: dict[str, Any] | None = None,
) -> Bot:
    """Caller authorizes the actor and commits the bot and audit atomically."""
    name = name.strip()
    if not 1 <= len(name) <= 100:
        raise ApiError(422, "VALIDATION_ERROR", "Bot name must be 1 to 100 characters.")
    tenant = lock_tenant(db, tenant_id)
    require_capacity(db, tenant, "bots")
    bot = Bot(
        id=uuid4(),
        tenant_id=tenant.id,
        name=name,
        status="draft",
        config={},
        widget_locator="w" + secrets.token_hex(16),
    )
    db.add(bot)
    db.flush()
    record_audit(
        db,
        action=audit_action,
        tenant_id=tenant.id,
        actor_user_id=actor.id,
        target_type="bot",
        target_id=str(bot.id),
        metadata=metadata,
    )
    return bot
