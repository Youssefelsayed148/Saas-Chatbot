"""Argon2id password hashing and opaque session-token handling (ADR-004).

Token values are random 256-bit strings; only their SHA-256 hashes are
persisted, and tokens are never logged (docs/06).
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_hasher = PasswordHasher()  # argon2-cffi defaults: Argon2id, memory 64 MiB, 3 iterations.

SESSION_TOKEN_BYTES = 32  # 256 bits after urlsafe base64.


def hash_password(password: str) -> str:
    """Argon2id hash; salt random per call."""
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False
    except Exception:
        # Malformed/stored hash must not leak internals or crash the request.
        return False


def generate_session_token() -> str:
    return secrets.token_urlsafe(SESSION_TOKEN_BYTES)


def hash_token(token: str) -> str:
    """SHA-256 hex of a token; used for sessions and invitation one-time links."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def session_expiry(lifetime_seconds: int) -> datetime:
    return datetime.now(UTC) + timedelta(seconds=lifetime_seconds)


def invitation_expiry(days: int) -> datetime:
    return session_expiry(days * 24 * 3600)
