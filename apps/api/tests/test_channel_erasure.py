"""A16 signed erasure: tenant isolation, replay fences and stale-job safety."""

import json
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

import app.channels.erasure as erasure
import app.channels.inbound as inbound
import app.channels.outbound as outbound
from app.contacts.router import merge_contact
from app.core.tenancy import TenantContext
from app.db.models import (
    AuditEvent,
    ChannelConnection,
    ChannelEvent,
    Contact,
    ContactIdentity,
    Conversation,
    Job,
    Membership,
    Message,
    Tenant,
    UsageEvent,
    User,
)
from app.db.models.channels import ChannelErasureFence
from tests.conftest import build_test_settings, run_migrations
from tests.test_channel_events import _connection, _payload, _post, _run_event
from tests.test_channel_outbound import run as run_send
from tests.test_channel_outbound import send_context as _send_context

send_context = _send_context


def _admin_context(db: Session, tenant_id: UUID) -> TenantContext:
    membership = db.scalar(
        select(Membership).where(Membership.tenant_id == tenant_id, Membership.role == "admin")
    )
    assert membership is not None
    user, tenant = db.get(User, membership.user_id), db.get(Tenant, tenant_id)
    assert user is not None and tenant is not None
    return TenantContext(db=db, user=user, tenant=tenant, membership=membership)


def _erase_payload(connection_id: UUID, **overrides: object) -> dict[str, Any]:
    return {
        "version": 1,
        "event_id": str(uuid4()),
        "event_type": "contact.erasure",
        "connection_id": str(connection_id),
        "occurred_at": datetime.now(UTC).isoformat(),
        "external_contact_id": "contact-1",
        **overrides,
    }


def _send(client: Any, conn: UUID, secret: str, payload: dict[str, Any]) -> Any:
    return _post(client, conn, secret, json.dumps(payload).encode())


def _seed(client: Any, app: Any, db: Session) -> tuple[UUID, str, UUID]:
    conn, secret = _connection(app, db, status="paused")
    event_id = str(uuid4())
    assert _send(client, conn, secret, _payload(conn, event_id=event_id)).status_code == 202
    _run_event(db, event_id)
    contact_id = db.scalar(
        select(ContactIdentity.contact_id).where(ContactIdentity.connection_id == conn)
    )
    assert contact_id is not None
    return conn, secret, contact_id


@pytest.mark.parametrize("value", [None, "", "   ", 123, "person\x00x"])
def test_erasure_rejects_malformed_identity_without_effects(
    client: Any,
    app: Any,
    db: Session,
    value: object,
) -> None:
    conn, secret = _connection(app, db)
    response = _send(client, conn, secret, _erase_payload(conn, external_contact_id=value))
    assert response.status_code == 422
    assert db.scalar(select(func.count(ChannelEvent.id))) == 0
    assert db.scalar(select(func.count(ChannelErasureFence.identity_digest))) == 0


def test_erasure_auth_header_match_paused_acceptance_and_revocation(
    client: Any,
    app: Any,
    db: Session,
) -> None:
    conn, secret = _connection(app, db, status="paused")
    body = _erase_payload(conn)
    raw = json.dumps(body).encode()
    assert _post(client, conn, secret, raw, signature="sha256=bad").status_code == 401
    assert _send(client, conn, secret, {**body, "connection_id": str(uuid4())}).status_code == 422
    assert _send(client, conn, secret, body).json() == {"status": "accepted"}
    event = db.scalar(select(ChannelEvent).where(ChannelEvent.connection_id == conn))
    assert event is not None and event.status == "received" and event.payload is not None
    # 202 is durable acceptance, not completion.
    assert (
        db.scalar(select(func.count(AuditEvent.id)).where(AuditEvent.action == "contact.erasure"))
        == 0
    )
    assert _send(client, conn, secret, body).json() == {"status": "duplicate"}
    accepted_connection = db.get(ChannelConnection, conn)
    assert accepted_connection is not None
    accepted_connection.status = "revoked"
    db.commit()
    # Revoking after acceptance cannot silently abandon a durable erasure.
    assert _run_event(db, str(body["event_id"])).status == "processed"
    revoked, key = _connection(app, db, status="revoked")
    response = _send(client, revoked, key, _erase_payload(revoked))
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_erasure_is_tenant_and_connection_scoped_and_cancels_pending_content(
    client: Any,
    app: Any,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    a, secret_a, contact_a = _seed(client, app, db)
    b, _secret_b, contact_b = _seed(client, app, db)  # same external id, another tenant
    tenant_a = db.scalar(select(ChannelConnection.tenant_id).where(ChannelConnection.id == a))
    conversation = db.scalar(select(Conversation).where(Conversation.connection_id == a))
    assert conversation is not None
    pending = _payload(
        a,
        event_id="pending-before-erase",
        external_message_id="pending-message",
        text="private pending text",
    )
    assert _send(client, a, secret_a, pending).status_code == 202
    message = Message(
        tenant_id=tenant_a,
        bot_id=conversation.bot_id,
        conversation_id=conversation.id,
        sender_type="agent",
        text="private outgoing",
        delivery_status="pending",
    )
    db.add(message)
    db.flush()
    send = Job(
        tenant_id=tenant_a,
        bot_id=conversation.bot_id,
        type="channel_send",
        status="pending",
        payload={"message_id": str(message.id)},
        attempts=0,
        max_attempts=6,
    )
    db.add(send)
    db.commit()
    send_id = send.id
    monkeypatch.setattr(
        inbound,
        "channel_chat_turn",
        lambda *args, **kwargs: pytest.fail("AI called during erasure"),
    )
    monkeypatch.setattr(
        outbound,
        "post_message",
        lambda *args, **kwargs: pytest.fail("external send during erasure"),
    )
    tenant_b = db.scalar(select(ChannelConnection.tenant_id).where(ChannelConnection.id == b))
    request = _erase_payload(a, event_id="erase-a", tenant_id=str(tenant_b))
    assert _send(client, a, secret_a, request).status_code == 202
    completed = _run_event(db, "erase-a")
    db.expire_all()
    assert completed.status == "processed" and completed.payload is None
    assert db.scalar(select(Contact).where(Contact.id == contact_a)) is None
    assert db.scalar(select(Contact).where(Contact.id == contact_b)) is not None
    assert (
        db.scalar(select(func.count(Conversation.id)).where(Conversation.connection_id == a)) == 0
    )
    assert (
        db.scalar(select(func.count(Conversation.id)).where(Conversation.connection_id == b)) == 1
    )
    for row in db.scalars(select(ChannelEvent).where(ChannelEvent.connection_id == a)):
        assert row.payload is None
    assert all(
        row.payload is not None
        for row in db.scalars(select(ChannelEvent).where(ChannelEvent.connection_id == b))
    )
    cleared = db.get(Job, send_id)
    assert (
        cleared is not None
        and cleared.payload == {}
        and cleared.cancel_requested
        and cleared.status == "cancelled"
    )
    # Retry a previously claimed inbound after purge: no resurrection or AI/send.
    _run_event(db, "pending-before-erase")
    assert db.scalar(select(func.count(Contact.id))) == 1
    assert _send(client, a, secret_a, request).json() == {"status": "duplicate"}
    audit = db.scalar(select(AuditEvent).where(AuditEvent.action == "contact.erasure"))
    assert audit is not None and audit.tenant_id == tenant_a and audit.target_id is None
    serialized = json.dumps(audit.metadata_json)
    assert "contact-1" not in serialized and "private" not in serialized
    fence = db.scalar(select(ChannelErasureFence).where(ChannelErasureFence.tenant_id == tenant_a))
    assert (
        fence is not None
        and len(fence.identity_digest) == 64
        and "contact-1" not in fence.identity_digest
    )


def test_missing_identity_is_success_and_delayed_input_is_fenced_but_new_recontact_allowed(
    client: Any,
    app: Any,
    db: Session,
) -> None:
    conn, secret = _connection(app, db, status="paused")
    cutoff = datetime.now(UTC) - timedelta(minutes=1)
    body = _erase_payload(conn, event_id="erase-missing", occurred_at=cutoff.isoformat())
    assert _send(client, conn, secret, body).status_code == 202
    _run_event(db, "erase-missing")
    old = _payload(
        conn, event_id="delayed-old", occurred_at=(cutoff + timedelta(seconds=30)).isoformat()
    )
    assert _send(client, conn, secret, old).status_code == 202
    assert _run_event(db, "delayed-old").error_code == "contact_erased"
    assert db.scalar(select(func.count(Contact.id))) == 0
    later = _payload(conn, event_id="genuine-recontact", occurred_at=datetime.now(UTC).isoformat())
    assert _send(client, conn, secret, later).status_code == 202
    assert _run_event(db, "genuine-recontact").status == "processed"
    assert db.scalar(select(func.count(Contact.id))) == 1


def test_same_tenant_same_external_id_on_other_connection_is_preserved(
    client: Any,
    app: Any,
    db: Session,
) -> None:
    conn, secret, contact_id = _seed(client, app, db)
    source = db.get(ChannelConnection, conn)
    assert source is not None
    other = ChannelConnection(
        tenant_id=source.tenant_id,
        bot_id=source.bot_id,
        channel="whatsapp",
        display_name="Another number",
        many_base_url=source.many_base_url,
        status="paused",
        secret_ciphertext=source.secret_ciphertext,
    )
    db.add(other)
    db.commit()
    assert (
        _send(
            client, other.id, secret, _payload(other.id, event_id="same-id-other-connection")
        ).status_code
        == 202
    )
    _run_event(db, "same-id-other-connection")
    other_contact = db.scalar(
        select(ContactIdentity.contact_id).where(ContactIdentity.connection_id == other.id)
    )
    assert other_contact != contact_id
    assert (
        _send(
            client, conn, secret, _erase_payload(conn, event_id="erase-one-connection")
        ).status_code
        == 202
    )
    _run_event(db, "erase-one-connection")
    assert db.get(Contact, other_contact) is not None
    assert db.get(Contact, contact_id) is None
    assert db.scalar(select(func.count(ChannelErasureFence.identity_digest))) == 1


def test_explicitly_merged_contact_erases_linked_connection_payloads(
    client: Any,
    app: Any,
    db: Session,
) -> None:
    conn, secret, contact_id = _seed(client, app, db)
    original = db.get(ChannelConnection, conn)
    assert original is not None
    second = ChannelConnection(
        tenant_id=original.tenant_id,
        bot_id=original.bot_id,
        channel="instagram",
        display_name="Merged",
        many_base_url=original.many_base_url,
        status="paused",
        secret_ciphertext=original.secret_ciphertext,
    )
    db.add(second)
    db.flush()
    db.add(
        ContactIdentity(
            tenant_id=original.tenant_id,
            contact_id=contact_id,
            channel="instagram",
            connection_id=second.id,
            external_id="linked-instagram",
        )
    )
    db.commit()
    linked = _payload(
        second.id,
        event_id="merged-event",
        channel="instagram",
        external_contact_id="linked-instagram",
    )
    assert _send(client, second.id, secret, linked).status_code == 202
    _run_event(db, "merged-event")
    assert (
        _send(client, conn, secret, _erase_payload(conn, event_id="erase-merged")).status_code
        == 202
    )
    _run_event(db, "erase-merged")
    assert db.scalar(select(func.count(Contact.id))) == 0
    assert db.scalar(select(func.count(Conversation.id))) == 0
    assert db.scalar(select(func.count(ChannelErasureFence.identity_digest))) == 2
    assert all(row.payload is None for row in db.scalars(select(ChannelEvent)))


def test_worker_refreshes_after_waiting_for_erasure_lock(
    client: Any,
    app: Any,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn, secret, _contact = _seed(client, app, db)
    before = _payload(conn, event_id="claimed-stale", external_message_id="stale-msg")
    assert _send(client, conn, secret, before).status_code == 202
    assert (
        _send(client, conn, secret, _erase_payload(conn, event_id="erase-interleave")).status_code
        == 202
    )
    original_lock = inbound.channel_work_lock

    @contextmanager
    def finish_erasure_while_waiting(*args: Any, **kwargs: Any) -> Any:
        _run_event(db, "erase-interleave")
        with original_lock(*args, **kwargs):
            yield

    monkeypatch.setattr(inbound, "channel_work_lock", finish_erasure_while_waiting)
    monkeypatch.setattr(inbound, "channel_chat_turn", lambda *a, **k: pytest.fail("stale AI turn"))
    _run_event(db, "claimed-stale")
    assert db.scalar(select(func.count(Contact.id))) == 0
    assert db.scalar(select(func.count(Message.id))) == 0


def test_erasure_failure_rolls_back_and_can_retry(
    client: Any,
    app: Any,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn, secret, contact_id = _seed(client, app, db)
    assert (
        _send(client, conn, secret, _erase_payload(conn, event_id="retry-erase")).status_code == 202
    )
    original_audit = erasure.record_audit
    monkeypatch.setattr(
        erasure, "record_audit", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("injected"))
    )
    with pytest.raises(RuntimeError, match="injected"):
        _run_event(db, "retry-erase")
    db.rollback()
    assert db.get(Contact, contact_id) is not None
    assert db.scalar(select(func.count(ChannelErasureFence.identity_digest))) == 0
    monkeypatch.setattr(erasure, "record_audit", original_audit)
    assert _run_event(db, "retry-erase").status == "processed"
    assert db.get(Contact, contact_id) is None


def test_missing_erasure_payload_remains_visible_for_operator_action(
    client: Any,
    app: Any,
    db: Session,
) -> None:
    conn, secret, contact_id = _seed(client, app, db)
    assert (
        _send(
            client, conn, secret, _erase_payload(conn, event_id="lost-erasure-payload")
        ).status_code
        == 202
    )
    event = db.scalar(
        select(ChannelEvent).where(
            ChannelEvent.connection_id == conn, ChannelEvent.event_id == "lost-erasure-payload"
        )
    )
    assert event is not None
    event.payload = None  # e.g. retention ran after repeated processing failure
    job = db.scalar(
        select(Job).where(
            Job.tenant_id == event.tenant_id,
            Job.payload["channel_event_id"].as_string() == str(event.id),
        )
    )
    assert job is not None
    db.commit()
    error = inbound.run_channel_inbound(db, job, build_test_settings())
    db.commit()
    assert error == "Erasure payload unavailable; operator action required."
    assert event.status == "failed" and event.error_code == "erasure_payload_unavailable"
    assert db.get(Contact, contact_id) is not None
    assert (
        db.scalar(select(func.count(AuditEvent.id)).where(AuditEvent.action == "contact.erasure"))
        == 0
    )


def test_claimed_send_revalidates_after_erasure_before_http(
    client: Any,
    app: Any,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn, secret, _contact = _seed(client, app, db)
    conversation = db.scalar(select(Conversation).where(Conversation.connection_id == conn))
    assert conversation is not None
    message = Message(
        tenant_id=conversation.tenant_id,
        bot_id=conversation.bot_id,
        conversation_id=conversation.id,
        sender_type="agent",
        text="erase before send",
        delivery_status="pending",
    )
    db.add(message)
    db.flush()
    job = Job(
        tenant_id=conversation.tenant_id,
        bot_id=conversation.bot_id,
        type="channel_send",
        status="running",
        payload={"message_id": str(message.id)},
        attempts=1,
        max_attempts=6,
    )
    db.add(job)
    db.commit()
    assert (
        _send(client, conn, secret, _erase_payload(conn, event_id="erase-before-http")).status_code
        == 202
    )
    original_lock = erasure.channel_work_lock
    triggered = False

    @contextmanager
    def erase_before_sender_takes_lock(*args: Any, **kwargs: Any) -> Any:
        nonlocal triggered
        if not triggered:
            triggered = True
            _run_event(db, "erase-before-http")
        with original_lock(*args, **kwargs):
            yield

    monkeypatch.setattr(erasure, "channel_work_lock", erase_before_sender_takes_lock)
    monkeypatch.setattr(outbound, "post_message", lambda *a, **k: pytest.fail("HTTP after erase"))
    assert outbound.run_channel_send(db, job, build_test_settings()) is None
    assert triggered and db.scalar(select(func.count(Message.id))) == 0


def test_erasure_scrubs_usage_trace_without_refunding_consumed_quota(
    client: Any,
    app: Any,
    db: Session,
) -> None:
    from app.quotas.rag import monthly_usage

    conn, secret, _contact = _seed(client, app, db)
    conversation = db.scalar(select(Conversation).where(Conversation.connection_id == conn))
    assert conversation is not None
    message_id = db.scalar(select(Message.id).where(Message.conversation_id == conversation.id))
    usage = UsageEvent(
        tenant_id=conversation.tenant_id,
        bot_id=conversation.bot_id,
        kind="message",
        external_key=f"message:{message_id}",
        message_id=message_id,
        conversation_id=conversation.id,
        payload={
            "rag_trace": {"rewrite_text": "private customer question"},
            "provider_usage": {"total_tokens": 77, "private": "customer"},
            "ai_metered": False,
            "source": "channel",
        },
    )
    db.add(usage)
    db.commit()
    usage_id, tenant_id, bot_id = usage.id, conversation.tenant_id, conversation.bot_id
    before = monthly_usage(db, tenant_id, bot_id)
    assert before["monthly_messages"] == 1 and before["monthly_tokens"] == 77
    assert (
        _send(client, conn, secret, _erase_payload(conn, event_id="erase-accounting")).status_code
        == 202
    )
    _run_event(db, "erase-accounting")
    assert monthly_usage(db, tenant_id, bot_id) == before
    retained = db.get(UsageEvent, usage_id)
    assert retained is not None and retained.message_id is None and retained.conversation_id is None
    assert retained.external_key == f"erased:{usage_id}"
    assert retained.payload == {
        "provider_usage": {"total_tokens": 77},
        "ai_metered": False,
        "source": "channel",
    }


def test_identity_lock_and_digest_are_scoped_and_release(db: Session) -> None:
    tenant, conn = uuid4(), uuid4()
    digest = erasure.identity_digest(tenant, conn, "same-id")
    assert digest != erasure.identity_digest(uuid4(), conn, "same-id")
    assert digest != erasure.identity_digest(tenant, uuid4(), "same-id")
    key = f"channel-work:{digest}"
    with db.get_bind().connect() as peer:  # type: ignore[union-attr]
        with erasure.channel_work_lock(db, tenant, [(conn, "same-id")]):
            assert (
                peer.execute(
                    text("SELECT pg_try_advisory_lock(hashtextextended(:k, 0))"), {"k": key}
                ).scalar()
                is False
            )
        assert (
            peer.execute(
                text("SELECT pg_try_advisory_lock(hashtextextended(:k, 0))"), {"k": key}
            ).scalar()
            is True
        )
        peer.execute(text("SELECT pg_advisory_unlock(hashtextextended(:k, 0))"), {"k": key})


@pytest.mark.parametrize("move_source", [True, False])
def test_staff_merge_between_identity_read_and_contact_lock_requires_retry(
    client: Any,
    app: Any,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
    move_source: bool,
) -> None:
    conn, secret, contact_id = _seed(client, app, db)
    connection = db.get(ChannelConnection, conn)
    assert connection is not None
    tenant_id = connection.tenant_id
    target = Contact(tenant_id=tenant_id, display_name="Merge peer", source_channel="whatsapp")
    db.add(target)
    db.flush()
    target_id = target.id
    db.add(
        ContactIdentity(
            tenant_id=tenant_id,
            contact_id=target_id,
            channel="whatsapp",
            connection_id=conn,
            external_id="merge-peer",
        )
    )
    db.commit()
    assert (
        _send(client, conn, secret, _erase_payload(conn, event_id="merge-during-lock")).status_code
        == 202
    )
    original = erasure._linked_identities
    reads = 0

    def merge_after_final_prelock_read(*args: Any, **kwargs: Any) -> Any:
        nonlocal reads
        result = original(*args, **kwargs)
        reads += 1
        if reads == 2:
            # Execute the real admin merge route in a separate transaction,
            # precisely after erasure read its source mapping, before FOR UPDATE.
            with Session(db.get_bind(), expire_on_commit=False) as peer:
                source, destination = (
                    (contact_id, target_id) if move_source else (target_id, contact_id)
                )
                merge_contact(source, destination, _admin_context(peer, tenant_id), None)
        return result

    monkeypatch.setattr(erasure, "_linked_identities", merge_after_final_prelock_read)
    with pytest.raises(RuntimeError, match="Contact .*changed"):
        _run_event(db, "merge-during-lock")
    db.rollback()
    assert db.scalar(select(func.count(ChannelErasureFence.identity_digest))) == 0
    assert (
        db.scalar(select(func.count(AuditEvent.id)).where(AuditEvent.action == "contact.erasure"))
        == 0
    )
    event = db.scalar(
        select(ChannelEvent).where(
            ChannelEvent.connection_id == conn, ChannelEvent.event_id == "merge-during-lock"
        )
    )
    assert event is not None and event.status == "received" and event.payload is not None
    monkeypatch.setattr(erasure, "_linked_identities", original)
    assert _run_event(db, "merge-during-lock").status == "processed"
    assert db.scalar(select(func.count(Contact.id))) == 0
    assert db.scalar(select(func.count(Message.id))) == 0
    assert db.scalar(select(func.count(ContactIdentity.id))) == 0


@pytest.mark.parametrize("legacy", ["bound", "historical", "ambiguous"])
def test_same_connection_merged_identities_keep_each_conversation_recipient(
    send_context: Any,
    client: Any,
    app: Any,
    db: Session,
    legacy: str,
) -> None:
    connection, first, first_message, first_job, settings, fake = send_context
    payload = _payload(
        connection.id,
        event_id="second-recipient-event",
        external_contact_id="second-recipient",
        external_conversation_id="second-conversation",
        external_message_id="second-message",
    )
    # The first send_context has disabled AI; both conversations remain local/human.
    assert _send(client, connection.id, fake.secret, payload).status_code == 202
    _run_event(db, "second-recipient-event")
    second = db.scalar(
        select(Conversation).where(
            Conversation.tenant_id == connection.tenant_id,
            Conversation.external_conversation_id == "second-conversation",
        )
    )
    assert second is not None and second.contact_id is not None and first.contact_id is not None
    merge_contact(
        second.contact_id, first.contact_id, _admin_context(db, connection.tenant_id), None
    )
    assert (
        len(
            list(
                db.scalars(
                    select(ContactIdentity).where(ContactIdentity.connection_id == connection.id)
                )
            )
        )
        == 2
    )
    second_message = Message(
        tenant_id=second.tenant_id,
        bot_id=second.bot_id,
        conversation_id=second.id,
        sender_type="agent",
        text="Second reply",
        delivery_status="pending",
    )
    db.add(second_message)
    db.flush()
    outbound.enqueue_message(db, second, second_message, settings)
    if legacy != "bound":
        first.external_contact_id = None
        second.external_contact_id = None
    if legacy == "ambiguous":
        for event in db.scalars(
            select(ChannelEvent).where(ChannelEvent.tenant_id == connection.tenant_id)
        ):
            event.payload = None
    db.commit()
    second_job = db.scalar(
        select(Job).where(
            Job.tenant_id == connection.tenant_id,
            Job.payload["message_id"].as_string() == str(second_message.id),
        )
    )
    assert second_job is not None
    run_send(db, first_job, settings)
    run_send(db, second_job, settings)
    if legacy == "ambiguous":
        assert fake.requests == []
        assert (
            first_message.error_code == second_message.error_code == "channel_recipient_ambiguous"
        )
    else:
        assert [item["external_contact_id"] for item in fake.requests] == [
            "contact-1",
            "second-recipient",
        ]
        assert (
            first.external_contact_id == "contact-1"
            and second.external_contact_id == "second-recipient"
        )


def test_mismatched_conversation_identity_is_rejected_or_quarantined_without_processing_other_identity(
    client: Any,
    app: Any,
    db: Session,
) -> None:
    conn, secret = _connection(app, db, status="paused")
    wrong = _payload(
        conn,
        event_id="earlier-other-identity",
        external_contact_id="other-person",
        external_message_id="wrong-message",
    )
    correct = _payload(conn, event_id="current-identity")
    assert _send(client, conn, secret, wrong).status_code == 202
    assert _send(client, conn, secret, correct).status_code == 202
    _run_event(db, "current-identity")
    earlier = db.scalar(
        select(ChannelEvent).where(
            ChannelEvent.connection_id == conn, ChannelEvent.event_id == "earlier-other-identity"
        )
    )
    assert earlier is not None and earlier.status == "received"
    assert db.scalar(select(func.count(Contact.id))) == 1
    assert db.scalar(select(func.count(Message.id))) == 1
    assert _run_event(db, "earlier-other-identity").error_code == "conversation_recipient_mismatch"
    assert db.scalar(select(func.count(Contact.id))) == 1
    assert db.scalar(select(func.count(Message.id))) == 1
    # Once the recipient is bound, a signed mismatch is rejected at intake.
    wrong["event_id"] = "mismatch-at-intake"
    assert _send(client, conn, secret, wrong).status_code == 422
    assert (
        db.scalar(
            select(ChannelEvent).where(
                ChannelEvent.connection_id == conn, ChannelEvent.event_id == "mismatch-at-intake"
            )
        )
        is None
    )


def test_erasure_schema_recipient_column_and_fence_round_trip(db: Session, engine: Any) -> None:
    url = engine.url.render_as_string(hide_password=False)
    db.close()
    run_migrations(url, upgrade_to="", downgrade_to="0030_channel_health_poll_index")
    with engine.connect() as connection:
        assert (
            connection.scalar(text("SELECT to_regclass('public.channel_erasure_fences')")) is None
        )
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM information_schema.columns WHERE table_name='conversations' AND column_name='external_contact_id'"
                )
            )
            == 0
        )
    run_migrations(url)
    with engine.connect() as connection:
        assert (
            connection.scalar(text("SELECT to_regclass('public.channel_erasure_fences')"))
            is not None
        )
        assert (
            connection.scalar(
                text(
                    "SELECT is_nullable FROM information_schema.columns WHERE table_name='conversations' AND column_name='external_contact_id'"
                )
            )
            == "YES"
        )
