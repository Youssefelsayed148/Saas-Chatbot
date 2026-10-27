from typing import Any

import pytest
from sqlalchemy import select

from app.auth.security import verify_password
from app.db.models import User
from scripts.create_platform_staff import PASSWORD_ENV, read_password, upsert_staff


def test_staff_is_created_then_updated_without_logging_the_password(db: Any, capsys: Any) -> None:
    assert upsert_staff(db, "Staff-One@Example.com", "first-password-1") is True
    assert upsert_staff(db, "staff-one@example.com", "second-password-2") is False
    user = db.scalar(select(User).where(User.email == "staff-one@example.com"))
    assert user.is_platform_staff is True
    assert verify_password("second-password-2", user.password_hash)
    assert "password-" not in capsys.readouterr().out


def test_password_comes_from_env_and_is_validated(monkeypatch: Any) -> None:
    monkeypatch.setenv(PASSWORD_ENV, "long-enough-password")
    assert read_password(interactive=False) == "long-enough-password"
    monkeypatch.setenv(PASSWORD_ENV, "short")
    with pytest.raises(ValueError):
        read_password(interactive=False)
    monkeypatch.delenv(PASSWORD_ENV)
    with pytest.raises(ValueError):
        read_password(interactive=False)


def test_production_environment_accepts_a_non_demo_database_name() -> None:
    from scripts.create_platform_staff import guard_staff_database

    url = "postgresql://saas:secret@db:5432/saas"
    assert guard_staff_database(url, "production") == ("db", "saas")
    with pytest.raises(ValueError):
        guard_staff_database(url, "development")  # the demo-only guard still applies elsewhere
    with pytest.raises(ValueError):
        guard_staff_database("mysql://u:p@db/saas", "production")
