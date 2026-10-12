from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# Default storage root: relative to the API directory (apps/api), not the
# working directory, so host runs and container runs resolve the same place.
_DEFAULT_STORAGE_ROOT = Path(__file__).resolve().parents[2] / ".data" / "storage"


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

    # --- P2 knowledge ingestion (docs/14 §3–§5 defaults; composable via env) ---
    # Local-disk storage root for uploaded files (shared volume in Compose).
    storage_root: str = str(_DEFAULT_STORAGE_ROOT)
    # Upload limits: ≤10 MB/file, ≤20 files per batch (docs/14 §3 defaults;
    # per-plan caps arrive with quotas in P5/P7).
    max_upload_file_bytes: int = Field(default=10 * 1024 * 1024, ge=1)
    max_upload_files: int = Field(default=20, ge=1, le=200)
    # Parsed-input caps (docs/06): PDF pages, DOCX zip expansion.
    max_pdf_pages: int = Field(default=300, ge=1)
    max_docx_uncompressed_bytes: int = Field(default=100 * 1024 * 1024, ge=1)
    max_docx_zip_ratio: int = Field(default=200, ge=1)
    # Parsing happens in the worker, bounded by this wall-clock timeout per source.
    parse_timeout_seconds: int = Field(default=120, ge=1, le=3600)
    # Chunking defaults (docs/14 §4) — tune only via a dated note in docs/14.
    chunk_size: int = Field(default=1500, ge=100)
    chunk_overlap: int = Field(default=200, ge=0)
    # Job queue (ADR-011).
    job_lease_seconds: int = Field(default=900, ge=30)
    job_backoff_seconds: int = Field(default=30, ge=1)
    job_max_attempts: int = Field(default=3, ge=1, le=10)
    # Worker loop.
    worker_poll_seconds: float = Field(default=1.0, ge=0.1, le=60)
    worker_heartbeat_file: str = "/tmp/chatbot-worker-heartbeat"
    # E2E/test harness guard: when set, the worker refuses a non-_test database.
    worker_allow_only_test_db: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
