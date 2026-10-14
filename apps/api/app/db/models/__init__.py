"""All ORM models. Importing this module registers every table on ``Base.metadata``."""

from app.db.models.types import CITEXT, TSVECTOR

from .chat import (
    Contact,
    ContactIdentity,
    Conversation,
    Message,
    UsageEvent,
)
from .core import (
    AuditEvent,
    Bot,
    Invitation,
    Membership,
    ProvisioningRequest,
    Session,
    Tenant,
    User,
)
from .knowledge import (
    Chunk,
    Document,
    Job,
    KnowledgeRevision,
    Source,
    SourcePage,
)
from .widget import RateLimitCounter, VisitorSession

__all__ = [
    "AuditEvent",
    "Bot",
    "Chunk",
    "CITEXT",
    "Contact",
    "ContactIdentity",
    "Conversation",
    "Document",
    "Invitation",
    "Job",
    "KnowledgeRevision",
    "Membership",
    "Message",
    "ProvisioningRequest",
    "RateLimitCounter",
    "Session",
    "Source",
    "SourcePage",
    "Tenant",
    "TSVECTOR",
    "UsageEvent",
    "User",
    "VisitorSession",
]
