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

    def handle(self, request: httpx.Request) -> httpx.Response:
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
