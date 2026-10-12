from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel

from app.core.config import Settings, get_settings
from app.db.readiness import database_is_ready

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok", "ready", "not_ready"]


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/ready", response_model=HealthResponse)
def ready(
    response: Response, settings: Annotated[Settings, Depends(get_settings)]
) -> HealthResponse:
    if not database_is_ready(settings):
        response.status_code = 503
        return HealthResponse(status="not_ready")
    return HealthResponse(status="ready")
