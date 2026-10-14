from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FollowUpCreate(BaseModel):
    conversation_id: UUID
    contact_id: UUID | None = None
    send_at: datetime
    text: str = Field(min_length=1, max_length=4000)

    @model_validator(mode="after")
    def validate_schedule(self) -> "FollowUpCreate":
        if self.send_at.tzinfo is None or self.send_at.utcoffset() is None:
            raise ValueError("send_at must include a timezone")
        if not self.text.strip():
            raise ValueError("text cannot be blank")
        return self


class FollowUpOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    conversation_id: UUID
    contact_id: UUID | None
    send_at: datetime
    text: str
    status: str
    created_at: datetime
    delivered_at: datetime | None
