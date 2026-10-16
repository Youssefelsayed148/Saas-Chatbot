"""OpenAPI tenant-role inventory and all-role/cross-tenant request smoke matrix."""

import re
from typing import Any
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.helpers import seeded_tenant

TENANT_ROLES = ("viewer", "editor", "admin", "owner")
DECLARED_MINIMUMS = {*TENANT_ROLES, "authenticated", "platform_staff_only"}


def test_openapi_tenant_routes_are_classified_and_exercised_for_every_role(
    app: FastAPI, db: Any
) -> None:
    suffix = uuid4().hex
    user_a = seeded_tenant(app, db, prefix=f"route-matrix-a-{suffix}")
    user_b = seeded_tenant(app, db, prefix=f"route-matrix-b-{suffix}")
    try:
        tenant_ops: list[tuple[str, str, str]] = []
        for path, path_item in app.openapi()["paths"].items():
            if not path.startswith("/api/v1/tenants"):
                continue
            for method, operation in path_item.items():
                if method.lower() not in {"get", "post", "patch", "delete"}:
                    continue
                minimum = operation.get("x-minimum-role")
                assert minimum in DECLARED_MINIMUMS, f"Unclassified tenant route: {method} {path}"
                tenant_ops.append((method.upper(), path, minimum))
        assert tenant_ops, "No tenant-owned routes were found in OpenAPI."

        for method, template, minimum in tenant_ops:
            for role in TENANT_ROLES:
                path = template.replace("{tenant_id}", str(user_a.tenant_id))
                path = re.sub(r"\{[^}]+\}", lambda _: str(uuid4()), path)
                body = {"name": "matrix bot"} if method == "POST" and template.endswith("/bots") else {}
                kwargs = {"json": body} if method in {"POST", "PATCH", "DELETE"} else {}
                # SSE is intentionally open-ended. Exercise its authorization
                # using foreign tenant URLs, which must fail before streaming.
                is_sse = template.endswith("/events")
                if not is_sse:
                    response = user_a.call(role, method, path, **kwargs)
                    assert response.status_code < 500, (
                        f"{role} {method} {template} returned {response.status_code}: {response.text}"
                    )
                    if minimum == "platform_staff_only":
                        assert response.status_code == 403

                if "{tenant_id}" in template:
                    foreign_path = template.replace("{tenant_id}", str(user_b.tenant_id))
                    foreign_path = re.sub(r"\{[^}]+\}", lambda _: str(uuid4()), foreign_path)
                    foreign = user_a.call(role, method, foreign_path, **kwargs)
                    assert foreign.status_code == 404, (
                        f"Tenant A {role} {method} {template} against tenant B returned "
                        f"{foreign.status_code}: {foreign.text}"
                    )
    finally:
        user_a.cleanup()
        user_b.cleanup()
