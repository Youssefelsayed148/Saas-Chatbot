"""Allowed-domains normalization and localhost policy (A1.4): every entry is
reduced to a bare hostname before validation — client and server agree.
``origin_allowed`` keeps comparing hostnames only; an empty list still means
"check off" (widget service unchanged)."""

from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session as OrmSession

from app.bots.schemas import BotConfig, normalize_domain
from app.core.config import get_settings
from tests.helpers import seeded_tenant

CASES = [
    ("http://localhost:5500/", "localhost"),
    ("https://Example.COM", "example.com"),
    ("EXAMPLE.com.", "example.com"),
    ("  example.com/path?q=1#frag  ", "example.com"),
    ("https://shop.example.com:8443", "shop.example.com"),
    ("example.com/", "example.com"),
    ("http://user:pw@example.com", "example.com"),
    ("1.2.3.4:8080", "1.2.3.4"),
]


@pytest.mark.parametrize(("raw", "expected"), CASES)
def test_normalize_domain(raw: str, expected: str) -> None:
    assert normalize_domain(raw) == expected


def test_config_normalizes_dedupes_and_keeps_rejections() -> None:
    config = BotConfig(allowed_domains=["HTTP://Example.COM/", "example.com", "  example.com "])
    assert config.allowed_domains == ["example.com"]


def test_bare_hostname_without_dot_is_rejected() -> None:
    with pytest.raises(ValidationError):
        BotConfig(allowed_domains=["intranet"])


def test_localhost_accepted_only_outside_production() -> None:
    # The test process runs with environment=test, so localhost is allowed.
    config = BotConfig(allowed_domains=["http://localhost:5500/"])
    assert config.allowed_domains == ["localhost"]
    with pytest.raises(ValidationError):
        BotConfig(allowed_domains=["intranet"])


def test_localhost_rejected_in_production(monkeypatch: Any) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    get_settings.cache_clear()
    try:
        with pytest.raises(ValidationError):
            BotConfig(allowed_domains=["http://localhost:5500/"])
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


def test_api_patch_saves_normalized_entries(app: Any, db: OrmSession) -> None:
    users = seeded_tenant(app, db)
    bot = users.call(
        "staff", "POST", f"/api/v1/tenants/{users.tenant_id}/bots", json={"name": "Dom"}
    ).json()
    url = f"/api/v1/tenants/{users.tenant_id}/bots/{bot['id']}"
    patched = users.call(
        "staff",
        "PATCH",
        url,
        json={"config": {"allowed_domains": ["HTTP://Example.COM/", "example.com"]}},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["config"]["allowed_domains"] == ["example.com"]
