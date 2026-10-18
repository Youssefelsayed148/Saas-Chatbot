"""HMAC-SHA256 signing for the ManyOsirisChat channel contract."""

import hashlib
import hmac
import time

SIGNATURE_PREFIX = "sha256="
TIMESTAMP_WINDOW_SECONDS = 300


def sign(secret: str | bytes, timestamp: int | str, body: bytes) -> str:
    key = secret.encode("utf-8") if isinstance(secret, str) else secret
    signed = str(timestamp).encode("ascii") + b"." + body
    digest = hmac.new(key, signed, hashlib.sha256).hexdigest()
    return f"{SIGNATURE_PREFIX}{digest}"


def verify(
    secret: str | bytes,
    timestamp: int | str,
    body: bytes,
    signature: str,
    *,
    now: int | None = None,
) -> bool:
    try:
        timestamp_value = int(timestamp)
        if isinstance(timestamp, bool):
            return False
    except (TypeError, ValueError, OverflowError):
        return False
    current_time = int(time.time()) if now is None else now
    if abs(current_time - timestamp_value) > TIMESTAMP_WINDOW_SECONDS:
        return False
    expected = sign(secret, timestamp_value, body)
    return hmac.compare_digest(expected, signature)
