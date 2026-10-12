"""All ORM models. Importing this module registers every table on ``Base.metadata``."""

from app.db.models.types import CITEXT, TSVECTOR

from .core import AuditEvent, Bot, Invitation, Membership, Session, Tenant, User
from .knowledge import (
    Chunk,
    Document,
    Job,
    KnowledgeRevision,
    Source,
    SourcePage,
)

__all__ = [
    "AuditEvent",
    "Bot",
    "Chunk",
    "CITEXT",
    "Document",
    "Invitation",
    "Job",
    "KnowledgeRevision",
    "Membership",
    "Session",
    "Source",
    "SourcePage",
    "Tenant",
    "TSVECTOR",
    "User",
]
