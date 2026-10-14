"""Self-service onboarding through the shared ProvisioningService (P7-03)."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as OrmSession

from app.auth import cookies
from app.core.config import Settings, get_settings
from app.core.tenancy import CurrentUserDep
from app.db.session import get_session
from app.provisioning.service import ProvisioningPayload, ProvisioningService

router = APIRouter(prefix="/api/v1/provisioning", tags=["provisioning"])
DbSession = Annotated[OrmSession, Depends(get_session)]
CurrentSettings = Annotated[Settings, Depends(get_settings)]
CsrfOk = Annotated[None, Depends(cookies.require_csrf)]


class SelfServiceSignupRequest(BaseModel):
    client_name: str = Field(min_length=1, max_length=200)
    bot_name: str = Field(min_length=1, max_length=100)


@router.post("/self-service", status_code=status.HTTP_201_CREATED)
def self_service_signup(
    body: SelfServiceSignupRequest,
    actor: CurrentUserDep,
    db: DbSession,
    settings: CurrentSettings,
    _: CsrfOk,
) -> dict[str, Any]:
    payload = ProvisioningPayload(
        client_name=body.client_name,
        owner_email=actor.email,
        bot_name=body.bot_name,
        plan_label="free",
    )
    return ProvisioningService(db, settings).onboard_self_service(
        actor=actor,
        payload=payload,
        idempotency_key=f"signup:{actor.id}",
    )
