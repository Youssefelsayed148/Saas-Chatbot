"""Invitation payload helper — the one-time link carries the raw token exactly once."""

from typing import Any

from app.tenants.schemas import InvitationCreatedOut


def invitation_payload(invitation: Any, token: str) -> InvitationCreatedOut:
    return InvitationCreatedOut(
        id=invitation.id,
        email=invitation.email,
        role=invitation.role,
        expires_at=invitation.expires_at,
        created_at=invitation.created_at,
        expired=False,
        link_path=f"/accept-invite?token={token}",
    )
