"""Auth service: register, login (with session rotation), logout, me.

Business rules live here; the router stays thin (docs/03). All writes
commit atomically with the session they create/revoke. Tokens are never
logged; only Argon2id hashes and SHA-256 token hashes are stored
(ADR-004, docs/06).
"""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.auth.security import (
    generate_session_token,
    hash_password,
    hash_token,
    session_expiry,
    verify_password,
)
from app.core.config import Settings
from app.core.errors import ApiError
from app.db.models import Membership, Session, Tenant, User


class AuthService:
    def __init__(self, db: OrmSession, settings: Settings) -> None:
        self.db = db
        self.settings = settings

    # --- queries ----------------------------------------------------------

    def get_user_by_email(self, email: str) -> User | None:
        return self.db.execute(select(User).where(User.email == email)).scalar_one_or_none()

    def memberships_of(self, user_id: object) -> list[tuple[Membership, Tenant]]:
        rows = self.db.execute(
            select(Membership, Tenant)
            .join(Tenant, Membership.tenant_id == Tenant.id)
            .where(Membership.user_id == user_id, Membership.status == "active")
            .order_by(Tenant.created_at)
        ).all()
        return [(membership, tenant) for membership, tenant in rows]

    # --- commands ---------------------------------------------------------

    def register(self, email: str, password: str) -> tuple[User, str]:
        """Create user and start a session. Returns (user, cookie_token).

        EMAIL_TAKEN (409) reveals that an address is registered; accepted MVP
        trade-off per docs/05 409-conflict contract (no email verification in MVP).
        """
        email = email.strip()
        if self.get_user_by_email(email) is not None:
            raise ApiError(409, "EMAIL_TAKEN", "An account with this email already exists.")
        user = User(
            id=uuid4(),
            email=email,
            password_hash=hash_password(password),
            is_platform_staff=False,
        )
        self.db.add(user)
        self.db.flush()
        session_row, token = self._create_session(user)
        self.db.commit()
        return user, token

    def login(self, email: str, password: str, *, rotate_token: str | None) -> tuple[User, str]:
        """Verify credentials, issue a fresh session and rotate the presented one."""
        user = self.get_user_by_email(email.strip())
        if user is None or not verify_password(password, user.password_hash):
            # Same error for unknown email and wrong password: no account enumeration.
            raise ApiError(401, "INVALID_CREDENTIALS", "Email or password is incorrect.")
        session_row, token = self._create_session(user)
        if rotate_token:
            self._revoke_token(rotate_token)
        self.db.commit()
        return user, token

    def logout(self, *, token: str | None) -> None:
        """Revoke the presented session (idempotent) — the caller clears the cookie."""
        if token:
            self._revoke_token(token)
        self.db.commit()

    # --- internals --------------------------------------------------------

    def _create_session(self, user: User) -> tuple[Session, str]:
        token = generate_session_token()
        session_row = Session(
            id=uuid4(),
            token_hash=hash_token(token),
            user_id=user.id,
            expires_at=session_expiry(self.settings.session_lifetime_seconds),
        )
        self.db.add(session_row)
        return session_row, token

    def _revoke_token(self, token: str) -> None:
        row = self.db.execute(
            select(Session).where(Session.token_hash == hash_token(token))
        ).scalar_one_or_none()
        if row is not None and row.revoked_at is None:
            row.revoked_at = datetime.now(UTC)
            self.db.add(row)
