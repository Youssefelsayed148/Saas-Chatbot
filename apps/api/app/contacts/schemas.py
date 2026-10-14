from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


class ContactCreate(BaseModel):
    display_name: str = Field(default="", max_length=200)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=64)
    stage: str = Field(default="new", min_length=1, max_length=64)
    tags: list[str] = Field(default_factory=list, max_length=50)
    custom_fields: dict[str, Any] = Field(default_factory=dict, max_length=20)
    consent: dict[str, Any] = Field(default_factory=dict)
    source_channel: str | None = Field(default=None, max_length=32)

    @model_validator(mode="after")
    def reachable_and_valid(self) -> "ContactCreate":
        if not self.email and not (self.phone and self.phone.strip()):
            raise ValueError("email or phone is required")
        if any(not tag.strip() or len(tag) > 64 for tag in self.tags):
            raise ValueError("tags must be 1-64 characters")
        if any(not key.strip() or len(key) > 64 for key in self.custom_fields):
            raise ValueError("custom field names must be 1-64 characters")
        return self


class ContactUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=200)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=64)
    stage: str | None = Field(default=None, min_length=1, max_length=64)
    tags: list[str] | None = Field(default=None, max_length=50)
    custom_fields: dict[str, Any] | None = Field(default=None, max_length=20)
    consent: dict[str, Any] | None = None


class ContactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    display_name: str
    email: str | None
    phone: str | None
    stage: str
    tags: list[object]
    custom_fields: dict[str, object]
    consent: dict[str, object]
    source_channel: str | None
    created_at: datetime
    updated_at: datetime


class StageRename(BaseModel):
    old_name: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=64)
