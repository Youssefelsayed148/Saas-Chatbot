import os
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
    # Deployment environment. `production` enforces hard guards (see
    # validate_startup_settings): the offline stub model and other dev-only
    # affordances must never run there.
    environment: str = Field(default="development", pattern="^(development|production|test)$")
    self_serve_signup: bool = False
    org_deletion_grace_days: int = Field(default=30, ge=1, le=365)

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
    # Retrieval defaults (docs/14 §5) — tune only via a dated note in docs/14.
    retrieval_top_k: int = Field(default=8, ge=1)
    retrieval_final_k: int = Field(default=4, ge=1)
    retrieval_max_evidence_chunks: int = Field(default=8, ge=1)
    # Chat providers (docs/14 §6, ADR-013): keys come from the environment and
    # are never logged. Free default = OpenRouter :free chain (fallback list).
    chat_openrouter_base_url: str = "https://openrouter.ai/api/v1"
    chat_openrouter_api_key: SecretStr | None = None
    chat_free_model_chain: list[str] = Field(default_factory=list)
    chat_openai_base_url: str = "https://api.openai.com/v1"
    chat_openai_api_key: SecretStr | None = None
    chat_openai_model: str = ""
    chat_max_tokens: int = Field(default=700, ge=64, le=2000)
    # Message retention (docs/14 §7): configurable days; the worker purges.
    retention_days: int = Field(default=30, ge=1, le=365)
    retention_purge_interval_seconds: int = Field(default=86_400, ge=60)
    chat_num_history_messages: int = Field(default=6, ge=0, le=20)
    # --- P4 widget public API (docs/09, docs/14 §7 defaults) ---
    # Visitor capability token lifetime (short-lived; the widget requests a
    # new session when expired).
    widget_session_ttl_seconds: int = Field(default=1800, ge=60, le=86400)
    # Session-creation abuse cap per client IP (fixed window).
    widget_sessions_per_minute_per_ip: int = Field(default=10, ge=1, le=1000)
    # Message requests per (IP, session) minute window (docs/14 §7 default 20).
    widget_messages_per_minute: int = Field(default=20, ge=1, le=1000)
    # Daily message cap per bot (quota hook; enforced against usage events,
    # raised as QUOTA_EXCEEDED — per-plan quotas formalised in P7).
    widget_daily_message_cap: int = Field(default=500, ge=1, le=100000)
    # Deterministic offline stub model for tests/E2E. NEVER in production config.
    chat_stub_model: bool = False
    # Worker loop.
    worker_poll_seconds: float = Field(default=1.0, ge=0.1, le=60)
    worker_heartbeat_file: str = "/tmp/chatbot-worker-heartbeat"
    # E2E/test harness guard: when set, the worker refuses a non-_test database.
    worker_allow_only_test_db: bool = False


@lru_cache
def get_settings() -> Settings:
    # Test and E2E processes never consult the repository dotenv file.
    return Settings(_env_file=None if os.getenv("ENVIRONMENT") == "test" else ".env")


def validate_startup_settings(settings: Settings) -> None:
    """Refuse to start in a configuration that must never serve production.

    The deterministic stub model is a dev/test/eval affordance only
    (P3 carries this guard forward in P4-00)."""
    if settings.chat_stub_model and settings.environment == "production":
        raise RuntimeError(
            "CHAT_STUB_MODEL cannot be enabled with environment=production; "
            "the offline stub model is a development/test aid."
        )
