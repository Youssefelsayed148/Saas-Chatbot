"""Encrypted storage for per-connection Many signing secrets."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

if TYPE_CHECKING:
    from app.core.config import Settings
    from app.db.models import ChannelConnection


def _key_value(value: object | None) -> str:
    if value is None:
        raise ValueError("Channel secret encryption is not configured.")
    get_secret_value = getattr(value, "get_secret_value", None)
    raw = get_secret_value() if callable(get_secret_value) else str(value)
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("Channel secret encryption is not configured.")
    return raw


def encryption_keys(value: object | None) -> tuple[Fernet, ...]:
    raw = _key_value(value)
    try:
        keys = tuple(
            Fernet(part.strip().encode("ascii")) for part in raw.split(",") if part.strip()
        )
    except (ValueError, UnicodeEncodeError) as exc:
        raise ValueError("CHANNEL_SECRET_ENCRYPTION_KEYS must contain Fernet keys.") from exc
    if not keys:
        raise ValueError("CHANNEL_SECRET_ENCRYPTION_KEYS must contain at least one Fernet key.")
    return keys


def encrypt_secret(secret: str, key_value: object | None) -> str:
    if not secret:
        raise ValueError("A non-empty channel secret is required.")
    return (
        MultiFernet(list(encryption_keys(key_value)))
        .encrypt(secret.encode("utf-8"))
        .decode("ascii")
    )


def decrypt_secret(ciphertext: str, key_value: object | None) -> str:
    try:
        plain = MultiFernet(list(encryption_keys(key_value))).decrypt(ciphertext.encode("ascii"))
        return plain.decode("utf-8")
    except (InvalidToken, UnicodeDecodeError, UnicodeEncodeError) as exc:
        raise ValueError("Stored channel secret cannot be decrypted with configured keys.") from exc


def signing_secrets(
    connection: "ChannelConnection",
    settings: "Settings",
    *,
    now: datetime | None = None,
) -> tuple[str, ...]:
    """Return the current secret and an unexpired previous secret, if present."""
    current = decrypt_secret(connection.secret_ciphertext, settings.channel_secret_encryption_keys)
    values = [current]
    effective_now = now or datetime.now(UTC)
    expires_at = connection.prev_secret_expires_at
    if connection.prev_secret_ciphertext and expires_at and expires_at > effective_now:
        values.append(
            decrypt_secret(
                connection.prev_secret_ciphertext, settings.channel_secret_encryption_keys
            )
        )
    return tuple(values)
