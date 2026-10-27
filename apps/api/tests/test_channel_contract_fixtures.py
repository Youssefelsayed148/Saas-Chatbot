"""Shared contract fixtures: signing vectors and example payloads (docs/17 section 11)."""

import json
import time
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session

from app.channels.events import ORIGIN_FIELD_LIMITS, _validate_payload
from app.channels.signing import sign, verify
from tests.test_channel_events import _connection, _post

FIXTURES = Path(__file__).parent / "fixtures" / "contract"
VECTORS = json.loads((FIXTURES / "signing_vectors.json").read_text(encoding="utf-8"))["vectors"]
EXAMPLES = sorted((FIXTURES / "examples").glob("*.json"))


def _render(path: Path, connection_id: UUID) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    now = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
    for key, value in {
        "connection_id": str(connection_id),
        "event_id": f"fixture-{uuid4()}",
        "now": now,
        "message_id": str(uuid4()),
    }.items():
        raw = raw.replace("{{" + key + "}}", value)
    assert "{{" not in raw
    payload: dict[str, Any] = json.loads(raw)
    return payload


def _body(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def test_vector_file_pins_the_agreed_values() -> None:
    first, second = VECTORS
    assert first["secret"] == "s" * 40 and len(first["secret"]) == 40
    assert first["timestamp"] == "1760000000"
    assert first["body_utf8"] == '{"text":"مرحبا ✓"}'
    assert first["signature"] == (
        "sha256=5e40dcd701ffe2adc2ba2940bf94a02f3cbe639b1e7ec9a4ac59c4c146f13d50"
    )
    assert second["body_utf8"] == "" and second["timestamp"] == first["timestamp"]


@pytest.mark.parametrize("vector", VECTORS, ids=[v["name"] for v in VECTORS])
def test_sign_matches_vector_and_verify_accepts_it(vector: dict[str, str]) -> None:
    body = vector["body_utf8"].encode("utf-8")
    assert sign(vector["secret"], vector["timestamp"], body) == vector["signature"]
    assert verify(
        vector["secret"],
        vector["timestamp"],
        body,
        vector["signature"],
        now=int(vector["timestamp"]),
    )
    assert not verify(
        vector["secret"],
        vector["timestamp"],
        body + b" ",
        vector["signature"],
        now=int(vector["timestamp"]),
    )


def test_every_accepted_event_type_has_an_example() -> None:
    assert [p.stem for p in EXAMPLES] == [
        "channel_status",
        "message_received_origin_at_caps",
        "message_received_text",
        "message_received_unsupported",
        "message_status_failed",
    ]


@pytest.mark.parametrize("path", EXAMPLES, ids=[p.stem for p in EXAMPLES])
def test_example_validates_and_is_accepted(path: Path, client: Any, app: Any, db: Session) -> None:
    connection_id, secret = _connection(app, db)
    payload = _render(path, connection_id)
    assert _validate_payload(payload, connection_id, "whatsapp") == payload
    response = _post(client, connection_id, secret, _body(payload))
    assert response.status_code == 202, response.text


def test_origin_example_sits_exactly_on_the_caps() -> None:
    origin = _render(FIXTURES / "examples" / "message_received_origin_at_caps.json", uuid4())[
        "origin"
    ]
    assert {key: len(origin[key]) for key in ORIGIN_FIELD_LIMITS} == ORIGIN_FIELD_LIMITS


@pytest.mark.parametrize(
    ("example", "change"),
    [
        ("message_received_origin_at_caps", {"origin": {"campaign_name": "c" * 121}}),
        ("message_received_origin_at_caps", {"origin": {"opening_message_text": "o" * 2001}}),
        ("message_received_origin_at_caps", {"origin": {"campaign_ref": "r" * 129}}),
        ("message_received_origin_at_caps", {"origin": {"campaign_name": 7}}),
        ("message_received_text", {"text": 5}),
        ("message_received_text", {"channel": "messenger"}),
        ("message_received_unsupported", {"type": "image"}),
        ("message_status_failed", {"status": "exploded"}),
        ("message_status_failed", {"error_code": 12}),
        ("channel_status", {"status": "great"}),
        ("channel_status", {"detail": "d" * 201}),
    ],
)
def test_over_cap_and_wrong_type_variants_get_signed_422(
    client: Any, app: Any, db: Session, example: str, change: dict[str, Any]
) -> None:
    connection_id, secret = _connection(app, db)
    payload = _render(FIXTURES / "examples" / f"{example}.json", connection_id)
    for key, value in change.items():
        payload[key] = {**payload[key], **value} if key == "origin" else value
    with pytest.raises(ValueError):
        _validate_payload(payload, connection_id, "whatsapp")
    response = _post(client, connection_id, secret, _body(payload))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
