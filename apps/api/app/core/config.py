from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: SecretStr | None = None
    database_connect_timeout: int = Field(default=3, ge=1, le=10)

    # Sessions (ADR-004): opaque server-side tokens; only a SHA-256 hash is stored.
    session_cookie_name: str = "chatbot_session"
    session_lifetime_seconds: int = Field(default=14 * 24 * 3600, ge=300, le=90 * 24 * 3600)
    csrf_cookie_name: str = "chatbot_csrf"
    cookie_secure: bool = True  # Secure flag; local development and HTTP tests override it.

    # Login rate limiting (per client IP, in-process fixed window; single-process MVP).
    login_rate_limit_attempts: int = Field(default=10, ge=1, le=1000)
    login_rate_limit_window_seconds: int = Field(default=300, ge=1, le=86400)


@lru_cache
def get_settings() -> Settings:
    return Settings()
