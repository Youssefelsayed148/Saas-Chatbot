"""Revocation must serialize with concurrent session issuance."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.models import Session
from tests.helpers import PASSWORD
from tests.test_platform import platform_call, staff_login
from tests.test_staff_members import create


@pytest.mark.parametrize("action", ["deactivate", "password"])
def test_login_racing_revocation_cannot_leave_a_live_session(
    app: Any,
    db: Any,
    action: str,
) -> None:
    staff = staff_login(app, db)
    user_id = create(staff).json()["user"]["id"]
    barrier = Barrier(2)
    client = TestClient(app)

    def login() -> Any:
        barrier.wait(timeout=10)
        return client.post(
            "/api/v1/auth/login", json={"email": "test.owner@example.com", "password": PASSWORD}
        )

    def revoke() -> Any:
        barrier.wait(timeout=10)
        return platform_call(
            staff,
            "POST",
            f"/users/{user_id}/{action}",
            **({"json": {"generate": True}} if action == "password" else {}),
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        logged_in = pool.submit(login)
        revoked = pool.submit(revoke)
        assert logged_in.result(timeout=30).status_code in (200, 401)
        assert revoked.result(timeout=30).status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401
    assert not list(
        db.scalars(
            select(Session.id).where(Session.user_id == UUID(user_id), Session.revoked_at.is_(None))
        )
    )
