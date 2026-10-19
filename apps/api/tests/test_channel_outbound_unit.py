"""Pure outbound security and splitting tests; no network or database."""

import socket
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from typing import Any

import pytest

import app.channels.outbound as outbound
from app.channels.config import SEND_RESPONSE_BYTES
from app.channels.outbound import resolve_target, split_reply
from tests.conftest import build_test_settings


@pytest.fixture(autouse=True)
def clean_tables() -> None:
    """Override the integration-only DB cleanup for this pure unit suite."""


def test_dns_pin_and_date_retry_after(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def resolve(host: str, *_args: Any, **_kwargs: Any) -> Any:
        calls.append(host)
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]

    monkeypatch.setattr(socket, "getaddrinfo", resolve)
    url, host = resolve_target("https://many.example.test", build_test_settings())
    assert url.host == "93.184.216.34" and host == "many.example.test"
    assert calls == [host]
    future = format_datetime(datetime.now(UTC) + timedelta(seconds=150))
    assert 148 <= outbound.retry_delay(1, future) <= 151
    assert 14 <= outbound.retry_delay(1, "bad-date") <= 22
    assert 14 <= outbound.retry_delay(1, "NaN") <= 22


@pytest.mark.parametrize("channel", ["whatsapp", "instagram", "messenger"])
def test_split_sentence_boundaries_and_unbroken_text(channel: str) -> None:
    full = "One sentence. " * 140
    parts = split_reply(full, channel)
    assert "".join(parts) == full and all(len(p) <= 1000 for p in parts)
    assert all(p.endswith(". ") for p in parts)
    assert split_reply("س" * 2100, channel) == ["س" * 1000, "س" * 1000, "س" * 100]


def test_fake_many_real_streaming_client_and_signature(monkeypatch: pytest.MonkeyPatch) -> None:
    import json
    import time

    import httpx

    from app.channels.signing import sign
    from tests.fakes.fake_many import FakeMany

    fake = FakeMany("connection-1", "current-secret")
    monkeypatch.setattr(outbound, "_client", fake.client)
    body = json.dumps({"message_id": "message-1", "text": "Private text"}).encode()
    timestamp = int(time.time())
    status, retry_after, raw = outbound.post_message(
        httpx.URL("https://93.184.216.34/api/saas/messages"),
        "many.example.test",
        body,
        {
            "X-Osiris-Connection": "connection-1",
            "X-Osiris-Timestamp": str(timestamp),
            "X-Osiris-Signature": sign(fake.secret, timestamp, body),
        },
    )
    assert status == 202 and retry_after is None and json.loads(raw) == {"id": "many-1"}
    assert len(fake.requests) == 1


@pytest.mark.parametrize(
    "address", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1", "fc00::1", "::ffff:127.0.0.1"]
)
def test_non_global_dns_answers_are_rejected(monkeypatch: pytest.MonkeyPatch, address: str) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_a, **_k: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443)),
        ],
    )
    with pytest.raises(outbound.UnsafeTarget):
        resolve_target("https://many.example.test", build_test_settings())


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost",
        "https://127.0.0.1",
        "ftp://many.example.test",
        "https://user:pass@many.example.test",
    ],
)
def test_invalid_target_rejected_before_dns(monkeypatch: pytest.MonkeyPatch, url: str) -> None:
    def forbidden(*_a: Any, **_k: Any) -> Any:
        pytest.fail("Invalid URLs must not reach DNS")

    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    with pytest.raises(outbound.UnsafeTarget):
        resolve_target(url, build_test_settings())


def test_transport_cap_and_no_redirects(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    requests: list[httpx.Request] = []
    response_size = 0

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            302,
            stream=httpx.ByteStream(b"x" * response_size),
            headers={"Location": "http://127.0.0.1/"},
        )

    monkeypatch.setattr(
        outbound,
        "_client",
        lambda: httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False),
    )
    status, _, _ = outbound.post_message(
        httpx.URL("https://93.184.216.34/api/saas/messages"), "many.example.test", b"{}", {}
    )
    assert status == 302 and len(requests) == 1
    response_size = SEND_RESPONSE_BYTES + 1
    with pytest.raises(ValueError, match="size limit"):
        outbound.post_message(
            httpx.URL("https://93.184.216.34/api/saas/messages"), "many.example.test", b"{}", {}
        )
    assert len(requests) == 2
