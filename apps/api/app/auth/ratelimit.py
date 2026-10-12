"""Login rate limiting (docs/06).

In-process fixed-window counter per client IP — adequate for the P1
single-process API. Survives neither restarts nor multiple processes;
a DB-backed counter is deferred per the jobs/tables scope of P1.
"""

import threading
import time
from collections import deque
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends

from app.core.config import Settings, get_settings
from app.core.errors import ApiError


class LoginRateLimiter:
    """Fixed-window limiter. ``attempt`` counts an attempt and may raise 429."""

    def __init__(self, max_attempts: int, window_seconds: int) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._attempts: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def attempt(self, key: str, *, now: Callable[[], float] = time.monotonic) -> None:
        window = self.window_seconds
        with self._lock:
            hits = self._attempts.setdefault(key, deque())
            boundary = now() - window
            while hits and hits[0] <= boundary:
                hits.popleft()
            if len(hits) >= self.max_attempts:
                raise ApiError(
                    429,
                    "RATE_LIMITED",
                    "Too many login attempts. Try again later.",
                )
            hits.append(now())

    def reset(self) -> None:
        with self._lock:
            self._attempts.clear()


_limiter: LoginRateLimiter | None = None


def get_login_rate_limiter(
    settings: Annotated[Settings, Depends(get_settings)],
) -> LoginRateLimiter:
    """App dependency; tests override with a fresh limiter to keep cases deterministic."""
    global _limiter
    if _limiter is None or (
        _limiter.max_attempts != settings.login_rate_limit_attempts
        or _limiter.window_seconds != settings.login_rate_limit_window_seconds
    ):
        _limiter = LoginRateLimiter(
            max_attempts=settings.login_rate_limit_attempts,
            window_seconds=settings.login_rate_limit_window_seconds,
        )
    return _limiter


def reset_login_rate_limiter() -> None:
    global _limiter
    _limiter = None
