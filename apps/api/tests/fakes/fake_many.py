"""Many contract peer with signature verification, idempotency and callbacks."""

import json
import time
from collections import deque
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx

from app.channels.signing import sign, verify


class FakeMany:
    def __init__(self, connection_id: str, secret: str) -> None:
        self.connection_id = connection_id
        self.secret = secret
        self.responses: deque[int | Exception | tuple[int, str]] = deque()
        self.requests: list[dict[str, Any]] = []
        self.headers: list[httpx.Headers] = []
        self.deliveries: dict[str, str] = {}
        self.health_requests: list[httpx.Headers] = []
        self.health_responses: deque[int | Exception | str] = deque()
        # Contract v1.1 A4: Many never truncates silently. When set, a text over the
        # platform limit fails permanently with ``message_too_long``.
        self.limit_chars: int | None = None
        self.limit_bytes: int | None = None

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and "/api/saas/connections/" in request.url.path:
            return self.handle_health(request)
        assert request.method == "POST"
        assert request.url.path.endswith("/api/saas/messages")
        assert request.headers["X-Osiris-Connection"] == self.connection_id
        assert verify(
            self.secret,
            request.headers["X-Osiris-Timestamp"],
            request.content,
            request.headers["X-Osiris-Signature"],
        )
        assert request.headers["Host"] == "many.example.test"
        assert request.url.host == "93.184.216.34"
        assert request.extensions["sni_hostname"] == "many.example.test"
        assert request.extensions["timeout"]["connect"] == 5
        assert request.extensions["timeout"]["read"] == 15
        payload = json.loads(request.content)
        self.requests.append(payload)
        self.headers.append(request.headers)
        text = payload.get("text", "")
        if (self.limit_chars is not None and len(text) > self.limit_chars) or (
            self.limit_bytes is not None and len(text.encode("utf-8")) > self.limit_bytes
        ):
            return httpx.Response(
                400,
                stream=httpx.ByteStream(json.dumps({"error_code": "message_too_long"}).encode()),
            )
        outcome = self.responses.popleft() if self.responses else 202
        if isinstance(outcome, Exception):
            raise outcome
        if isinstance(outcome, tuple):
            return httpx.Response(
                outcome[0], headers={"Retry-After": outcome[1]}, stream=httpx.ByteStream(b"")
            )
        if outcome != 202:
            return httpx.Response(
                outcome,
                stream=httpx.ByteStream(json.dumps({"error_code": "window_closed"}).encode()),
            )
        key = payload["message_id"]
        many_id = self.deliveries.setdefault(key, f"many-{len(self.deliveries) + 1}")
        return httpx.Response(202, stream=httpx.ByteStream(json.dumps({"id": many_id}).encode()))

    def handle_health(self, request: httpx.Request) -> httpx.Response:
        """§5.2 health endpoint: GET, signed over an empty body."""
        assert request.method == "GET"
        assert request.url.path.endswith(f"/api/saas/connections/{self.connection_id}/health")
        assert request.headers["X-Osiris-Connection"] == self.connection_id
        verified = verify(
            self.secret,
            request.headers["X-Osiris-Timestamp"],
            b"",
            request.headers["X-Osiris-Signature"],
        )
        assert verified
        assert request.content == b""
        assert request.headers["Host"] == "many.example.test"
        assert request.url.host == "93.184.216.34"
        assert request.extensions["sni_hostname"] == "many.example.test"
        assert request.extensions["timeout"]["connect"] == 5
        assert request.extensions["timeout"]["read"] == 15
        self.health_requests.append(request.headers)
        outcome = self.health_responses.popleft() if self.health_responses else "healthy"
        if isinstance(outcome, Exception):
            raise outcome
        if isinstance(outcome, int):
            return httpx.Response(outcome, stream=httpx.ByteStream(b""))
        return httpx.Response(
            200,
            stream=httpx.ByteStream(json.dumps({"status": outcome}).encode()),
        )

    def client(self) -> httpx.Client:
        return httpx.Client(
            transport=httpx.MockTransport(self.handle),
            follow_redirects=False,
            trust_env=False,
            timeout=httpx.Timeout(15, connect=5),
        )

    def post_status(
        self, client: Any, message_id: str, status: str, error_code: str | None = None
    ) -> Any:
        raw = json.dumps(
            {
                "version": 1,
                "event_id": str(uuid4()),
                "event_type": "message.status",
                "connection_id": self.connection_id,
                "message_id": message_id,
                "status": status,
                "error_code": error_code,
                "occurred_at": datetime.now(UTC).isoformat(),
            }
        ).encode()
        timestamp = int(time.time())
        return client.post(
            "/api/channels/manyosiris/events",
            content=raw,
            headers={
                "Content-Type": "application/json",
                "X-Osiris-Connection": self.connection_id,
                "X-Osiris-Timestamp": str(timestamp),
                "X-Osiris-Signature": sign(self.secret, timestamp, raw),
            },
        )
