"""Sensitive account write parameters must not escape database failures."""

from typing import Any

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from tests.test_platform import platform_call, staff_login


def test_database_failure_returns_safe_error_without_logging_parameters(
    app: Any,
    db: Any,
    monkeypatch: Any,
    caplog: Any,
) -> None:
    staff = staff_login(app, db)

    def fail_flush(*args: Any, **kwargs: Any) -> None:
        raise OperationalError(
            "INSERT users",
            {"phone": "+201234567890", "password_hash": "sensitive-hash"},
            Exception("db unavailable"),
        )

    monkeypatch.setattr(Session, "flush", fail_flush)
    result = platform_call(
        staff,
        "POST",
        "/users",
        json={"email": "private@example.com", "phone": "+201234567890", "generate": True},
    )
    assert result.status_code == 503
    assert result.json()["error"]["code"] == "SERVICE_UNAVAILABLE"
    for value in ("+201234567890", "sensitive-hash", "INSERT users", "db unavailable"):
        assert value not in result.text
        assert value not in caplog.text
