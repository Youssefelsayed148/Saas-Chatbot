"""P4-00 (2): the startup configuration guard.

`validate_startup_settings` (called by `create_app`) refuses a forbidden
configuration: the deterministic offline stub model (CHAT_STUB_MODEL) must
never run with environment=production.
"""

from typing import Any

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.config import Settings, validate_startup_settings


def _settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {"database_url": None, "cookie_secure": False}
    values.update(overrides)
    return Settings.model_construct(**values)


def test_stub_model_with_production_refused() -> None:
    with pytest.raises(RuntimeError, match="CHAT_STUB_MODEL"):
        validate_startup_settings(_settings(chat_stub_model=True, environment="production"))


def test_stub_model_with_development_allowed() -> None:
    validate_startup_settings(_settings(chat_stub_model=True, environment="development"))
    validate_startup_settings(_settings(chat_stub_model=True, environment="test"))


def test_real_provider_with_production_allowed() -> None:
    validate_startup_settings(
        _settings(
            chat_stub_model=False,
            environment="production",
            embedding_provider="openai",
            channel_secret_encryption_keys=SecretStr(Fernet.generate_key().decode("ascii")),
        )
    )


def test_production_requires_an_explicit_embedding_provider() -> None:
    with pytest.raises(RuntimeError, match="EMBEDDING_PROVIDER"):
        validate_startup_settings(_settings(environment="production"))
    validate_startup_settings(
        _settings(
            environment="production",
            embedding_provider="ollama",
            channel_secret_encryption_keys=SecretStr(Fernet.generate_key().decode("ascii")),
        )
    )
    # Development and test keep the OpenAI default without configuration.
    validate_startup_settings(_settings(environment="development"))
    validate_startup_settings(_settings(environment="test"))


def test_real_settings_object_tracks_explicit_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHAT_STUB_MODEL", "0")
    monkeypatch.setenv("EMBEDDING_TEST_STUB", "0")
    monkeypatch.delenv("EMBEDDING_PROVIDER", raising=False)
    unset = Settings(_env_file=None, environment="production")  # type: ignore[call-arg]
    with pytest.raises(RuntimeError, match="EMBEDDING_PROVIDER"):
        validate_startup_settings(unset)
    monkeypatch.setenv("EMBEDDING_PROVIDER", "openai")
    monkeypatch.setenv("CHANNEL_SECRET_ENCRYPTION_KEYS", Fernet.generate_key().decode("ascii"))
    validate_startup_settings(Settings(_env_file=None, environment="production"))  # type: ignore[call-arg]


def test_production_requires_channel_secret_encryption_key() -> None:
    with pytest.raises(RuntimeError, match="CHANNEL_SECRET_ENCRYPTION_KEYS"):
        validate_startup_settings(_settings(environment="production", embedding_provider="openai"))
    validate_startup_settings(
        _settings(
            environment="production",
            embedding_provider="openai",
            channel_secret_encryption_keys=SecretStr(Fernet.generate_key().decode("ascii")),
        )
    )


def test_create_app_refuses_production_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    # get_settings is called by create_app at startup (module reference, so the
    # cache is bypassed by pointing the name at our factory).
    from app import main as main_module

    monkeypatch.setattr(
        main_module,
        "get_settings",
        lambda: _settings(chat_stub_model=True, environment="production"),
    )
    with pytest.raises(RuntimeError, match="CHAT_STUB_MODEL"):
        main_module.create_app()


def test_create_app_boots_normally_in_development(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import main as main_module

    monkeypatch.setattr(
        main_module,
        "get_settings",
        lambda: _settings(chat_stub_model=True, environment="development"),
    )
    app = main_module.create_app()
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
