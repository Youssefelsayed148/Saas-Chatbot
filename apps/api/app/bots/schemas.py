"""Bot contracts. `config` mirrors docs/04: assistant/business name,
description, welcome message EN/AR, opening questions, default language,
support email/phone, colour/position, handoff toggle, allowed domains —
validated by a Pydantic schema."""

import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

NAME_MAX_LENGTH = 100
COLOUR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
QUESTION_MAX_LENGTH = 120


class WelcomeMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    en: str | None = Field(default=None, max_length=500)
    ar: str | None = Field(default=None, max_length=500)


class BotConfig(BaseModel):
    """Full bot configuration payload for PATCH (partial updates allowed)."""

    model_config = ConfigDict(extra="forbid")
    assistant_name: str | None = Field(default=None, min_length=1, max_length=100)
    business_name: str | None = Field(default=None, min_length=1, max_length=100)
    business_description: str | None = Field(default=None, max_length=1000)
    welcome_message: WelcomeMessage | None = None
    opening_questions: list[str] | None = Field(default=None, max_length=10)
    default_language: str | None = Field(default=None, pattern="^(en|ar)$")
    support_email: EmailStr | None = None
    support_phone: str | None = Field(default=None, max_length=30)
    colour: str | None = None
    # Widget avatar (P4-03, docs/09): a public http(s) URL only.
    avatar: str | None = None
    position: str | None = Field(default=None, pattern="^(left|right)$")
    handoff_enabled: bool | None = None
    allowed_domains: list[str] | None = Field(default=None, max_length=50)

    @field_validator("opening_questions")
    @classmethod
    def questions_shapes(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        if any(not question.strip() or len(question) > QUESTION_MAX_LENGTH for question in value):
            raise ValueError("Each opening question must be 1-120 characters.")
        return [question.strip() for question in value]

    @field_validator("colour")
    @classmethod
    def colour_shape(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not COLOUR_RE.fullmatch(value):
            raise ValueError("Colour must be a hex value like #1a2b3c.")
        return value

    @field_validator("avatar")
    @classmethod
    def avatar_is_public_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        avatar = value.strip()
        if not avatar.startswith(("http://", "https://")) or len(avatar) > 500:
            raise ValueError("Avatar must be a public http(s) URL (max 500 characters).")
        return avatar

    @field_validator("allowed_domains")
    @classmethod
    def domains_shape(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        host_re = re.compile(
            r"^(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)*[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$"
        )
        lowered = [domain.strip().lower() for domain in value]
        for domain in lowered:
            if not domain or "." not in domain or not host_re.fullmatch(domain):
                raise ValueError("Allowed domains must be hostnames like example.com.")
        return lowered


class BotCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=NAME_MAX_LENGTH)


class BotUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=NAME_MAX_LENGTH)
    config: BotConfig | None = None
    # Widget lifecycle transitions (P4-01, docs/04 statuses): draft→active,
    # active→paused and paused→active. Archiving stays DELETE-only; drafts cannot
    # be made and archived bots cannot be revived here.
    status: str | None = None


class BotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    tenant_id: UUID
    name: str
    status: str
    config: dict[str, object]
    # Opaque public widget locator (P4-01): not a secret, shown on the install page.
    widget_locator: str | None = None
    created_at: datetime
    updated_at: datetime
