"""Client-admin intake, bounded private attachments and membership-free staff triage."""

from pathlib import Path
from typing import Any

from app.core.config import get_settings
from tests.conftest import build_test_settings
from tests.helpers import seeded_tenant


def test_change_request_roles_isolation_attachments_and_triage(
    app: Any, db: Any, tmp_path: Path
) -> None:
    app.dependency_overrides[get_settings] = lambda: build_test_settings(storage_root=str(tmp_path))
    a, b = seeded_tenant(app, db, "changes-a"), seeded_tenant(app, db, "changes-b")
    base = f"/api/v1/tenants/{a.tenant_id}/change-requests"
    try:
        for role in ["viewer", "editor"]:
            assert a.call(role, "GET", base).status_code == 403
            assert (
                a.call(
                    role, "POST", base, data={"type": "other", "text": "Please update"}
                ).status_code
                == 403
            )
        assert b.call("admin", "GET", base).status_code == 404
        for kind in ["knowledge", "text_change", "domain", "delete_org", "other"]:
            response = a.call(
                "admin",
                "POST",
                base,
                data={"type": kind, "text": "Please update the page"},
                files=[("files", ("evidence.txt", b"private evidence", "text/plain"))],
            )
            assert response.status_code == 201, response.text
        row = response.json()
        assert "storage_key" not in str(row)
        attachment = f"{base}/{row['id']}/attachments/{row['attachments'][0]['id']}"
        assert a.call("admin", "GET", attachment).content == b"private evidence"
        assert a.call("staff", "GET", attachment).status_code == 200
        assert a.call("viewer", "GET", attachment).status_code == 403
        assert b.call("admin", "GET", attachment).status_code == 404
        assert len(a.call("admin", "GET", base).json()) == 5
        assert b.call("admin", "GET", f"/api/v1/tenants/{b.tenant_id}/change-requests").json() == []
        queue = "/api/v1/platform/change-requests"
        assert a.call("admin", "GET", queue).status_code == 403
        assert len(a.call("staff", "GET", queue).json()) == 5
        assert (
            a.call(
                "admin", "PATCH", queue + f"/{row['id']}", json={"status": "triaged"}
            ).status_code
            == 403
        )
        triaged = a.call("staff", "PATCH", queue + f"/{row['id']}", json={"status": "triaged"})
        assert triaged.status_code == 200 and triaged.json()["status"] == "triaged"
        assert (
            a.call(
                "staff", "PATCH", queue + f"/{row['id']}", json={"status": "invented"}
            ).status_code
            == 422
        )
        assert (
            a.call("admin", "POST", base, data={"type": "other", "text": "  "}).status_code == 422
        )
        assert (
            a.call(
                "admin", "POST", base, data={"type": "invented", "text": "Please help"}
            ).status_code
            == 422
        )
    finally:
        a.cleanup()
        b.cleanup()
