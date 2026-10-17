"""Audit trail helper for privileged writes (docs/06).

Adds events in the caller's transaction; the commit stays with the
service. Tenant id or actor may be None for platform-level events.
"""

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import ColumnElement, or_
from sqlalchemy.orm import Session as OrmSession

from app.db.models import AuditEvent


def record_audit(
    db: OrmSession,
    *,
    action: str,
    tenant_id: UUID | None,
    actor_user_id: UUID | None,
    target_type: str | None = None,
    target_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditEvent(
            id=uuid4(),
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            metadata_json=metadata or {},
        )
    )


def audit_action_matches(query: str) -> ColumnElement[bool]:
    """Search both onboarding vocabularies while preserving immutable history."""
    query = query.strip()
    variants = {query, query.replace("admin", "owner"), query.replace("owner", "admin")}
    return or_(*(AuditEvent.action.ilike(f"%{value}%") for value in sorted(variants)))
