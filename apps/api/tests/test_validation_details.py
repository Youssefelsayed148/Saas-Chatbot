"""Field-level validation details (A1.2): 422 responses list per-field errors
without ever echoing the submitted values (they may carry secrets)."""

from typing import Any

from tests.helpers import PASSWORD, seeded_tenant
from tests.test_platform import platform_call


def test_validation_details_fields_without_input_echo(app: Any, db: Any) -> None:
    org = seeded_tenant(app, db)
    staff = org.as_user("staff")
    phone = "0123 not a phone"
    response = platform_call(
        staff,
        "POST",
        "/users",
        json={"email": "detail@example.com", "password": PASSWORD, "phone": phone},
    )
    assert response.status_code == 422, response.text
    payload = response.json()
    assert payload["error"]["code"] == "VALIDATION_ERROR"
    # Generic message and code stay unchanged; details are additive.
    assert payload["error"]["message"] == "Request body failed validation."
    fields = payload["error"]["details"]["fields"]
    assert fields[0]["field"] == "phone"
    assert fields[0]["message"]  # a human-readable pydantic message
    # Never echo the submitted values (phone, password or email body).
    for secret in (phone, PASSWORD, "detail@example.com"):
        assert secret not in response.text
