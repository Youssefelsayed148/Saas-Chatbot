"""Staff-owned RAG caps. None is deliberately uncapped; zero blocks new usage."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

Count = Annotated[int, Field(strict=True, ge=0)]


class RagLimits(BaseModel):
    model_config = ConfigDict(extra="forbid")
    documents: Count | None = None
    chunks: Count | None = None
    storage_bytes: Count | None = None
    monthly_messages: Count | None = None
    monthly_tokens: Count | None = None
    monthly_embedding_tokens: Count | None = None
    monthly_ocr_pages: Count | None = None
