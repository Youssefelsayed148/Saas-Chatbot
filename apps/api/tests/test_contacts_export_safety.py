"""S4: the contacts CSV export neutralises spreadsheet formulas in every text column."""

import csv
import io
from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy.orm import Session as OrmSession

import tests.retrieval_helpers as _rh  # noqa: F401
from app.contacts.router import _export_phone, _export_safe

corpus = _rh.corpus


@pytest.mark.parametrize("lead", ["=", "+", "-", "@", "\t", "\r"])
def test_export_safe_quotes_every_formula_lead(lead: str) -> None:
    assert _export_safe(f"{lead}SUM(A1)") == f"'{lead}SUM(A1)"
    assert _export_safe("Ada") == "Ada"


def test_phone_numbers_keep_their_plus_but_formulas_are_quoted() -> None:
    assert _export_phone("+966 50 000 0000") == "+966 50 000 0000"
    assert _export_phone("=1+1") == "'=1+1"
    assert _export_phone(None) == ""


def test_export_csv_quotes_display_name_and_other_text_columns(
    app: FastAPI, db: OrmSession, corpus: dict[str, Any]
) -> None:
    users = corpus["users_a"]
    base = f"/api/v1/tenants/{users.tenant_id}/contacts"
    names = ["=cmd|' /C calc'!A0", "+1+1", "-2+3", "@SUM(A1)", "\tTabbed", "\rReturned", "Plain"]
    for index, name in enumerate(names):
        response = users.call(
            "admin",
            "POST",
            base,
            json={"display_name": name, "email": f"s4-{index}@example.com", "tags": [name]},
        )
        assert response.status_code in (200, 201), response.text
    exported = users.call("admin", "GET", f"{base}/export.csv")
    assert exported.status_code == 200
    rows = list(csv.DictReader(io.StringIO(exported.text, newline="")))
    by_email = {row["email"]: row for row in rows}
    for index, name in enumerate(names):
        row = by_email[f"s4-{index}@example.com"]
        expected = f"'{name}" if name[0] in "=+-@\t\r" else name
        assert row["display_name"] == expected
        assert row["tags"] == expected
