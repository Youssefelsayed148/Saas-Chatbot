"""Bot contracts. `config` mirrors docs/04: assistant/business name,
description, welcome message EN/AR, opening questions, default language,
support email/phone, colour/position, handoff toggle, allowed domains —
validated by a Pydantic schema."""

import re
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.config import get_settings

NAME_MAX_LENGTH = 100
COLOUR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
QUESTION_MAX_LENGTH = 120
TONE_MAX_LENGTH = 2000


def normalize_domain(value: str) -> str:
    """Reduce a user-supplied domain entry to a bare lowercase hostname.

    Accepts pasted URLs such as ``http://localhost:5500/``: trim, lowercase,
    strip the http(s) scheme, credentials, path/query/fragment, port and any
    trailing dot. Mirrors the client-side normalization in apps/web/lib/domains.
    """
    entry = value.strip().lower()
    if entry.startswith("http://"):
        entry = entry[len("http://") :]
    elif entry.startswith("https://"):
        entry = entry[len("https://") :]
    # Credentials before the host never belong in the allow-list.
    if "@" in entry:
        entry = entry.rsplit("@", 1)[-1]
    # Everything from the first path/query/fragment marker is not the host.
    marker = next((position for position, char in enumerate(entry) if char in "/?#"), None)
    if marker is not None:
        entry = entry[:marker]
    # Bare IPv6 keeps its brackets; everything else drops a numeric port.
    if entry.startswith("[") and "]" in entry:
        entry = entry[1 : entry.index("]")]
    else:
        host, separator, port = entry.rpartition(":")
        if separator and port.isdigit():
            entry = host
    while entry.endswith("."):
        entry = entry[:-1]
    return entry


# Widget theme (#14). Slots are optional hex colours; an unset slot keeps
# today's look (the base `colour` for header/send/user bubble/launcher, the
# design tokens for bot bubble and text). Preset ids must match the curated
# list in apps/web/lib/widget-theme.ts (a test keeps the two in step).
THEME_SLOTS = ("header", "send_button", "user_bubble", "bot_bubble", "text", "launcher")
THEME_PRESET_IDS = ("classic", "ocean", "sunset", "forest", "midnight-glass", "custom")
HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def normalize_hex(value: str) -> str:
    """Lowercase 6-digit form of a validated #rgb / #rrggbb colour."""
    colour = value.strip().lower()
    if len(colour) == 4:
        colour = "#" + "".join(ch * 2 for ch in colour[1:])
    return colour


class WidgetTheme(BaseModel):
    """Per-slot widget colours plus the preset they started from."""

    model_config = ConfigDict(extra="forbid")
    preset: str | None = None
    header: str | None = None
    send_button: str | None = None
    user_bubble: str | None = None
    bot_bubble: str | None = None
    text: str | None = None
    launcher: str | None = None

    @field_validator("preset")
    @classmethod
    def preset_known(cls, value: str | None) -> str | None:
        if value is not None and value not in THEME_PRESET_IDS:
            raise ValueError("Unknown theme preset.")
        return value

    @field_validator(*THEME_SLOTS)
    @classmethod
    def slot_is_hex(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not HEX_RE.fullmatch(value.strip()):
            raise ValueError("Theme colours must be hex values like #1a2b3c.")
        return normalize_hex(value)


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
    handoff_after_unanswered: int | None = Field(default=None, ge=1, le=3)
    handoff_keywords_en: list[str] | None = Field(default=None, max_length=20)
    handoff_keywords_ar: list[str] | None = Field(default=None, max_length=20)
    allowed_domains: list[str] | None = Field(default=None, max_length=50)
    theme: WidgetTheme | None = None

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
        normalized: list[str] = []
        for entry in value:
            domain = normalize_domain(entry)
            if not domain or domain in normalized:
                continue  # empty entries and duplicates collapse away
            if domain == "localhost":
                # Localhost is a development aid (docs/14 §7): never part of a
                # production allow-list, same style of rejection either way.
                if get_settings().environment == "production":
                    raise ValueError("Allowed domains must be hostnames like example.com.")
            elif "." not in domain or not host_re.fullmatch(domain):
                raise ValueError("Allowed domains must be hostnames like example.com.")
            normalized.append(domain)
        return normalized


class BotCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=NAME_MAX_LENGTH)


class BotUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=NAME_MAX_LENGTH)
    config: BotConfig | None = None
    # Staff-only tone and rules (#15). Empty string or null clears it.
    tone_and_rules: str | None = Field(default=None, max_length=TONE_MAX_LENGTH)
    # Widget lifecycle transitions (P4-01, docs/04 statuses): draft→active,
    # active→paused and paused→active. Archiving stays DELETE-only; drafts cannot
    # be made and archived bots cannot be revived here.
    status: str | None = None


class ToneOut(BaseModel):
    tone_and_rules: str | None = None


class ReadinessItem(BaseModel):
    """One readiness check. `section` names where in the dashboard to fix it."""

    id: str
    label: str
    status: Literal["ok", "todo", "warning"]
    detail: str
    section: Literal["contact", "messages", "access", "knowledge", "tier"]


class ReadinessOut(BaseModel):
    # True when no item is "todo" (warnings do not block).
    ready: bool
    items: list[ReadinessItem]


class BotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    tenant_id: UUID
    name: str
    status: str
    config: dict[str, object]
    # Staff only: the router blanks it for tenant members (#15).
    tone_and_rules: str | None = None
    # Opaque public widget locator (P4-01): not a secret, shown on the install page.
    widget_locator: str | None = None
    created_at: datetime
    updated_at: datetime
