from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import psycopg
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.config import Settings, get_settings
from app.db.readiness import database_is_ready
from app.main import create_app


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = create_app()
    # Unit tests override configuration and never connect to a real database.
    app.dependency_overrides[get_settings] = lambda: Settings.model_construct(database_url=None)
    with TestClient(app) as test_client:
        yield test_client


def test_liveness_does_not_depend_on_database(client: TestClient) -> None:
    with patch("app.api.health.database_is_ready", side_effect=AssertionError):
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize("available,status", [(True, 200), (False, 503)])
def test_readiness(client: TestClient, available: bool, status: int) -> None:
    with patch("app.api.health.database_is_ready", return_value=available):
        response = client.get("/ready")
    assert response.status_code == status
    assert response.json() == {"status": "ready" if available else "not_ready"}


def test_missing_database_does_not_connect() -> None:
    with patch("app.db.readiness.psycopg.connect") as connect:
        assert not database_is_ready(Settings.model_construct(database_url=None))
    connect.assert_not_called()


def test_database_error_is_safely_handled() -> None:
    settings = Settings.model_construct(
        database_url=SecretStr("postgresql://unused:secret@invalid/test")
    )
    with patch("app.db.readiness.psycopg.connect", side_effect=psycopg.OperationalError("secret")):
        assert not database_is_ready(settings)
    assert "secret" not in repr(settings)


def test_database_probe_executes_only_select() -> None:
    connection = MagicMock()
    cursor = connection.__enter__.return_value.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = (1,)
    settings = Settings.model_construct(database_url=SecretStr("postgresql://unused@invalid/test"))
    with patch("app.db.readiness.psycopg.connect", return_value=connection):
        assert database_is_ready(settings)
    cursor.execute.assert_called_once_with("SELECT 1")
