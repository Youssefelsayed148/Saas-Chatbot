"""B3: channel event payloads follow the tenant's message retention; the dedupe row
outlives them by 30 days."""

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.chat.conversations import run_retention_purge
from app.db.models import ChannelConnection, ChannelEvent, Tenant
from tests.conftest import build_test_settings
from tests.test_channel_events import _connection, _payload, _post, _post_received

STUB = build_test_settings(chat_stub_model=True)


def _age(db: Session, event_id: str, days: int) -> ChannelEvent:
    event = db.scalar(select(ChannelEvent).where(ChannelEvent.event_id == event_id))
    assert event is not None
    event.received_at = datetime.now(UTC) - timedelta(days=days)
    db.commit()
    return event


def test_purge_nulls_payload_at_retention_keeps_dedupe_30_days_and_is_tenant_scoped(
    client: Any, app: Any, db: Session
) -> None:
    conn_a, secret_a = _connection(app, db)
    conn_b, secret_b = _connection(app, db)
    tenant_a = db.scalar(select(ChannelConnection.tenant_id).where(ChannelConnection.id == conn_a))
    tenant_b = db.scalar(select(ChannelConnection.tenant_id).where(ChannelConnection.id == conn_b))
    db.get(Tenant, tenant_a).retention_days = 7  # type: ignore[union-attr]
    db.get(Tenant, tenant_b).retention_days = 365  # type: ignore[union-attr]
    db.commit()
    for conn, secret, tag in ((conn_a, secret_a, "a"), (conn_b, secret_b, "b")):
        for name in ("fresh", "mid", "old"):
            _post_received(
                client,
                conn,
                secret,
                event_id=f"{tag}-{name}",
                external_message_id=f"{tag}-m-{name}",
                text="call me on +966500000000",
            )
    for tag in ("a", "b"):
        _age(db, f"{tag}-fresh", 1)
        _age(db, f"{tag}-mid", 10)
        _age(db, f"{tag}-old", 40)

    run_retention_purge(db, STUB)
    db.expire_all()

    def row(event_id: str) -> ChannelEvent | None:
        return db.scalar(select(ChannelEvent).where(ChannelEvent.event_id == event_id))

    # Tenant A (7 days): payload gone at the cutoff, dedupe row kept until 30 days.
    assert row("a-fresh") is not None and row("a-fresh").payload is not None  # type: ignore[union-attr]
    mid = row("a-mid")
    assert mid is not None and mid.payload is None
    assert row("a-old") is None
    # Tenant B (365 days): nothing touched except the dedupe rows older than 30 days
    # that are still inside retention are KEPT with their payload.
    for name in ("fresh", "mid", "old"):
        kept = row(f"b-{name}")
        assert kept is not None and kept.payload is not None
    assert db.scalar(select(func.count(ChannelEvent.id))) == 5

    # Dedupe still rejects a duplicate inside the 30 days after the payload was nulled.
    body = _payload(conn_a, event_id="a-mid", external_message_id="a-m-mid")
    again = _post(client, conn_a, secret_a, json.dumps(body).encode())
    assert again.status_code == 202
    assert db.scalar(select(func.count(ChannelEvent.id))) == 5
