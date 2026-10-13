"""P4-04: widget lead capture with EXPLICIT consent (docs/14 §14, §16).

Consent is required before any contact write; the lead creates OR updates a
tenant contact and binds the conversation; tenant isolation holds (a session
can only ever touch its own tenant's contacts)."""

from typing import Any
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session as OrmSession

import tests.retrieval_helpers as _rh  # noqa: F401 — registers the corpus fixture
from app.db.models import Contact, ContactIdentity, Conversation
from tests.test_widget_public import _override_widget_settings, make_active_bot_with_knowledge

corpus = _rh.corpus


def _uuid(value: str) -> UUID:
    return UUID(value)


def _client(app_: FastAPI) -> TestClient:
    return TestClient(app_)


def _session(client: TestClient, locator: str) -> dict[str, Any]:
    response = client.post(f"/api/public/v1/widgets/{locator}/sessions", json={})
    assert response.status_code == 201, response.text
    payload: dict[str, Any] = response.json()
    return payload


def _lead(
    client: TestClient,
    session: dict[str, Any],
    *,
    name: str = "Dana Lead",
    email: str | None = "dana@example.com",
    phone: str | None = None,
    consent: bool = True,
) -> Any:
    return client.post(
        f"/api/public/v1/sessions/{session['session_id']}/lead",
        json={
            "name": name,
            "email": email,
            "phone": phone,
            "consent_accepted": consent,
            "consent_language": "en",
        },
        headers={"X-Session-Token": session["token"]},
    )


def test_lead_requires_consent_and_a_reachable_channel(
    app: FastAPI,
    db: OrmSession,
    corpus: dict[str, Any],
) -> None:
    users = corpus["users_a"]
    _override_widget_settings(app)
    bot = make_active_bot_with_knowledge(app, users, db)
    client = _client(app)
    session = _session(client, bot["widget_locator"])
    no_consent = _lead(client, session, consent=False)
    assert no_consent.status_code == 422
    assert no_consent.json()["error"]["code"] == "CONSENT_REQUIRED"
    unreachable = _lead(client, session, email=None, phone=None)
    assert unreachable.status_code == 422
    assert db.query(Contact).count() == 0
    del bot


def test_lead_creates_a_contact_with_consent_and_binds_the_conversation(
    app: FastAPI,
    db: OrmSession,
    corpus: dict[str, Any],
) -> None:
    users = corpus["users_a"]
    _override_widget_settings(app)
    bot = make_active_bot_with_knowledge(app, users, db)
    client = _client(app)
    session = _session(client, bot["widget_locator"])
    # a visit turns into a conversation first (widget pipeline)
    turn = client.post(
        f"/api/public/v1/sessions/{session['session_id']}/messages",
        json={"text": "What are your opening hours?"},
        headers={"X-Session-Token": session["token"]},
    )
    assert turn.status_code == 201
    response = _lead(client, session)
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["created"] is True
    contact = db.get(Contact, _uuid(payload["contact_id"]))
    assert contact is not None
    assert str(contact.email).lower() == "dana@example.com"
    consent = contact.consent if isinstance(contact.consent, dict) else {}
    website_value = consent.get("website")
    website_consent: dict[str, Any] | None = (
        website_value if isinstance(website_value, dict) else None
    )
    assert website_consent is not None
    assert str(website_consent["text_version"]).startswith("widget-lead/v1")
    assert contact.source_channel == "website"
    # identity binds the session; the conversation carries the contact
    identity = (
        db.query(ContactIdentity)
        .filter(
            ContactIdentity.tenant_id == users.tenant_id,
            ContactIdentity.channel == "website",
        )
        .one()
    )
    assert identity.contact_id == contact.id
    conversation = (
        db.query(Conversation)
        .filter(
            Conversation.tenant_id == users.tenant_id,
            Conversation.contact_id == contact.id,
        )
        .one()
    )
    assert str(conversation.contact_id) == payload["contact_id"]


def test_lead_updates_an_existing_contact_without_duplicates(
    app: FastAPI,
    db: OrmSession,
    corpus: dict[str, Any],
) -> None:
    users = corpus["users_a"]
    _override_widget_settings(app)
    bot = make_active_bot_with_knowledge(app, users, db)
    client = _client(app)
    first = _session(client, bot["widget_locator"])
    second = _session(client, bot["widget_locator"])
    first_lead = _lead(client, first)
    assert first_lead.status_code == 201
    second_lead = _lead(
        client,
        second,
        name="Dana Update",
        email="DANA@example.com",  # citext case-insensitive match
    )
    assert second_lead.status_code == 201
    assert second_lead.json()["created"] is False
    contacts = db.query(Contact).filter(Contact.email.isnot(None)).all()
    assert len(contacts) == 1  # one contact, twice captured
    assert contacts[0].display_name == "Dana Update"  # name filled from update
    del bot


def test_lead_phone_match_creates_one_contact(
    app: FastAPI,
    db: OrmSession,
    corpus: dict[str, Any],
) -> None:
    users = corpus["users_a"]
    _override_widget_settings(app)
    bot = make_active_bot_with_knowledge(app, users, db)
    client = _client(app)
    first = _session(client, bot["widget_locator"])
    second = _session(client, bot["widget_locator"])
    r1 = _lead(client, first, email=None, phone="+966500000001")
    assert r1.status_code == 201
    r2 = _lead(client, second, email=None, phone="+966500000001")
    assert r2.status_code == 201
    assert r2.json()["created"] is False
    assert db.query(Contact).count() == 1
    del bot


def test_tenant_isolation_of_leads(
    app: FastAPI,
    db: OrmSession,
    corpus: dict[str, Any],
) -> None:
    users_a = corpus["users_a"]
    users_b = corpus["users_b"]
    _override_widget_settings(app)
    bot_a = make_active_bot_with_knowledge(app, users_a, db, name="Leads A")
    bot_b = make_active_bot_with_knowledge(app, users_b, db, name="Leads B")
    client = _client(app)
    session_a = _session(client, bot_a["widget_locator"])
    _lead(client, session_a, email="shared@example.com")
    session_b = _session(client, bot_b["widget_locator"])
    _lead(client, session_b, email="shared@example.com")
    emails_a = db.query(Contact).filter(Contact.tenant_id == users_a.tenant_id).all()
    emails_b = db.query(Contact).filter(Contact.tenant_id == users_b.tenant_id).all()
    assert len(emails_a) == 1 and len(emails_b) == 1  # never mixed, never shared
    assert emails_a[0].tenant_id == users_a.tenant_id
    assert emails_b[0].tenant_id == users_b.tenant_id
    del bot_a, bot_b
