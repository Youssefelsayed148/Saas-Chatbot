"""P6-05b unified inbox and insights by channel (mixed-channel data).

Covers the channel filter and connection names in the shared inbox, the
per-channel insights aggregates, by-campaign counts, tenant A/B isolation,
role rules, an empty channel, and the contacts channel column/filter/export.
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from sqlalchemy.orm import Session as OrmSession

from app.channels.secrets import encrypt_secret
from app.db.models import (
    ChannelConnection,
    ContactIdentity,
    Conversation,
    Message,
)
from tests.helpers import make_bot, seeded_tenant


def _connection(
    app: FastAPI,
    db: OrmSession,
    users: Any,
    *,
    channel: str,
    display_name: str,
) -> ChannelConnection:
    from cryptography.fernet import Fernet

    key = getattr(app.state, "channel_test_key", None) or Fernet.generate_key().decode(
        "ascii"
    )
    app.state.channel_test_key = key
    bot = make_bot(users)
    connection = ChannelConnection(
        tenant_id=users.tenant_id,
        bot_id=UUID(bot["id"]),
        channel=channel,
        display_name=display_name,
        many_base_url="https://many.example.test",
        status="active",
        ai_enabled=True,
        secret_ciphertext=encrypt_secret("fixture-secret", key),
        secret_key_version=1,
        health_status="unknown",
    )
    db.add(connection)
    db.commit()
    return connection


def _channel_conversation(
    db: OrmSession,
    users: Any,
    connection: ChannelConnection,
    *,
    channel: str,
    status: str = "open",
    mode: str = "ai",
    campaign: str | None = None,
) -> Conversation:
    conversation = Conversation(
        tenant_id=users.tenant_id,
        bot_id=connection.bot_id,
        contact_id=None,
        source="channel",
        channel=channel,
        connection_id=connection.id,
        mode=mode,
        status=status,
        origin=(
            {"type": "campaign", "campaign_name": campaign} if campaign else None
        ),
    )
    db.add(conversation)
    db.commit()
    return conversation


def _website_conversation(db: OrmSession, users: Any, *, bot_id: UUID) -> Conversation:
    conversation = Conversation(
        tenant_id=users.tenant_id,
        bot_id=bot_id,
        source="website",
        channel="website",
        mode="ai",
        status="open",
    )
    db.add(conversation)
    db.commit()
    return conversation


def _reply_message(
    db: OrmSession,
    users: Any,
    conversation: Conversation,
    seconds_after: int,
    *,
    sender_type: str = "ai",
    can_answer: bool | None = None,
) -> Message:
    message = Message(
        tenant_id=users.tenant_id,
        bot_id=conversation.bot_id,
        conversation_id=conversation.id,
        sender_type=sender_type,
        text="First reply",
        can_answer=can_answer,
        created_at=conversation.created_at + timedelta(seconds=seconds_after)
        if conversation.created_at
        else datetime.now(UTC) + timedelta(seconds=seconds_after),
    )
    db.add(message)
    db.commit()
    return message


@pytest.fixture
def mixed_channel_data(app: FastAPI, db: OrmSession, request: pytest.FixtureRequest) -> Any:
    """Tenant A: website + whatsapp + instagram conversations; tenant B: one."""
    users_a = seeded_tenant(app, db, prefix=f"ins-a-{uuid4().hex[:8]}")
    users_b = seeded_tenant(app, db, prefix=f"ins-b-{uuid4().hex[:8]}")
    request.addfinalizer(users_a.cleanup)
    request.addfinalizer(users_b.cleanup)
    wa = _connection(app, db, users_a, channel="whatsapp", display_name="WA Hotline")
    ig = _connection(app, db, users_a, channel="instagram", display_name="Insta Desk")
    website = _website_conversation(db, users_a, bot_id=UUID(make_bot(users_a)["id"]))
    whatsapp = _channel_conversation(
        db, users_a, wa, channel="whatsapp", campaign="Spring"
    )
    # One measured handoff (human mode), one cannot-answer reply, median 30s.
    whatsapp.mode = "human"
    db.commit()
    _reply_message(db, users_a, whatsapp, 30, can_answer=False)
    instagram = _channel_conversation(
        db, users_a, ig, channel="instagram", status="resolved"
    )
    from tests.test_conversations_view import seed_setup

    seed_setup(app, users_b, db, name="Foreign bot")
    foreign_wa = _connection(
        app, db, users_b, channel="whatsapp", display_name="Foreign WA"
    )
    foreign = _channel_conversation(
        db, users_b, foreign_wa, channel="whatsapp", campaign="Foreign promo"
    )
    _reply_message(db, users_b, foreign, 10)
    return {
        "users_a": users_a,
        "users_b": users_b,
        "connections": {"whatsapp": wa, "instagram": ig},
        "conversations": {
            "website": website,
            "whatsapp": whatsapp,
            "instagram": instagram,
        },
    }


# --- inbox --------------------------------------------------------------------


def test_inbox_channel_filter_and_connection_name(
    app: FastAPI, db: OrmSession, mixed_channel_data: Any
) -> None:
    users_a = mixed_channel_data["users_a"]
    data = mixed_channel_data
    url = f"/api/v1/tenants/{users_a.tenant_id}/inbox"
    all_rows = users_a.as_user("viewer").get(url)
    assert all_rows.status_code == 200, all_rows.text
    by_channel = {row["channel"]: row for row in all_rows.json()["conversations"]}
    assert set(by_channel) == {"website", "whatsapp", "instagram"}
    assert by_channel["whatsapp"]["connection_name"] == "WA Hotline"
    assert by_channel["instagram"]["connection_name"] == "Insta Desk"
    assert by_channel["website"]["connection_name"] is None
    assert by_channel["whatsapp"]["id"] == str(
        data["conversations"]["whatsapp"].id
    )

    filtered = users_a.as_user("viewer").get(url + "?channel=whatsapp")
    assert filtered.status_code == 200, filtered.text
    payload = filtered.json()
    assert payload["total"] == 1
    assert [row["channel"] for row in payload["conversations"]] == ["whatsapp"]
    assert payload["conversations"][0]["connection_name"] == "WA Hotline"

    empty = users_a.as_user("viewer").get(url + "?channel=messenger")
    assert empty.status_code == 200, empty.text
    assert empty.json()["total"] == 0
    assert empty.json()["conversations"] == []

    combined = users_a.as_user("viewer").get(
        url + "?channel=whatsapp&mode=human"
    )
    assert combined.status_code == 200
    assert combined.json()["total"] == 1
    combined = users_a.as_user("viewer").get(url + "?channel=whatsapp&status=waiting_human")
    assert combined.json()["total"] == 0


def test_inbox_tenant_isolation_on_filtered_channel(
    app: FastAPI, db: OrmSession, mixed_channel_data: Any
) -> None:
    users_a = mixed_channel_data["users_a"]
    users_b = mixed_channel_data["users_b"]
    url_a = f"/api/v1/tenants/{users_a.tenant_id}/inbox"
    url_b = f"/api/v1/tenants/{users_b.tenant_id}/inbox"
    rows_a = users_a.as_user("viewer").get(url_a + "?channel=whatsapp").json()
    rows_b = users_b.as_user("viewer").get(url_b + "?channel=whatsapp").json()
    assert rows_a["total"] == 1 and rows_b["total"] == 1
    assert rows_a["conversations"][0]["connection_name"] == "WA Hotline"
    assert rows_b["conversations"][0]["connection_name"] == "Foreign WA"
    assert rows_a["conversations"] != rows_b["conversations"]
    # A viewer of tenant A cannot open tenant B's channel conversation.
    foreign_id = rows_b["conversations"][0]["id"]
    response = users_a.as_user("viewer").get(
        f"/api/v1/tenants/{users_a.tenant_id}/conversations/{foreign_id}"
    )
    assert response.status_code == 404, response.text


def test_thread_detail_connection_name_and_campaign(
    app: FastAPI, db: OrmSession, mixed_channel_data: Any
) -> None:
    users_a = mixed_channel_data["users_a"]
    conversations = mixed_channel_data["conversations"]
    for key, expected_name in (
        ("whatsapp", "WA Hotline"),
        ("instagram", "Insta Desk"),
    ):
        detail = users_a.as_user("viewer").get(
            f"/api/v1/tenants/{users_a.tenant_id}/conversations/{conversations[key].id}"
        )
        assert detail.status_code == 200, detail.text
        state = detail.json()["conversation"]
        assert state["connection_name"] == expected_name
        assert state["channel"] == key
    campaign_state = users_a.as_user("viewer").get(
        f"/api/v1/tenants/{users_a.tenant_id}/conversations/{conversations['whatsapp'].id}"
    ).json()["conversation"]
    assert campaign_state["campaign_name"] == "Spring"
    website_detail = users_a.as_user("viewer").get(
        f"/api/v1/tenants/{users_a.tenant_id}/conversations/{conversations['website'].id}"
    )
    state = website_detail.json()["conversation"]
    assert "connection_name" not in state
    assert "campaign_name" not in state


# --- insights -----------------------------------------------------------------


def _insights(users: Any, query: str = "") -> Any:
    return users.as_user("viewer").get(f"/api/v1/tenants/{users.tenant_id}/analytics{query}")


def test_insights_per_channel_breakdown(
    app: FastAPI, db: OrmSession, mixed_channel_data: Any
) -> None:
    users_a = mixed_channel_data["users_a"]
    response = _insights(users_a)
    assert response.status_code == 200, response.text
    data = response.json()
    breakdown = {row["channel"]: row for row in data["channel_breakdown"]}
    assert set(breakdown) == {"website", "whatsapp", "instagram"}
    wa = breakdown["whatsapp"]
    assert wa["conversations"] == 1
    assert wa["handoff_count"] == 1 and wa["handoff_rate"] == 1.0
    assert wa["unanswered_questions"] == 1
    assert wa["median_first_response_seconds"] == pytest.approx(30.0)
    assert wa["resolved_count"] == 0 and wa["resolved_rate"] == 0.0
    ig = breakdown["instagram"]
    assert ig["conversations"] == 1
    assert ig["resolved_rate"] == 1.0
    assert ig["median_first_response_seconds"] is None
    assert ig["handoff_rate"] == 0.0


def test_insights_campaign_counts_and_channel_filter(
    app: FastAPI, db: OrmSession, mixed_channel_data: Any
) -> None:
    users_a = mixed_channel_data["users_a"]
    data = _insights(users_a).json()
    assert data["conversations_by_campaign"] == {"Spring": 1}
    # Filtering by a channel narrows every measured section.
    filtered = _insights(users_a, "?channel=whatsapp").json()
    assert filtered["total_conversations"] == 1
    assert filtered["conversations_by_channel"] == {"whatsapp": 1}
    assert {
        row["channel"] for row in filtered["channel_breakdown"]
    } == {"website", "whatsapp", "instagram"}
    assert filtered["conversations_by_campaign"] == {"Spring": 1}
    empty = _insights(users_a, "?channel=messenger").json()
    assert empty["total_conversations"] == 0
    assert empty["conversations_by_campaign"] == {}
    invalid = _insights(users_a, "?channel=tiktok")
    assert invalid.status_code == 422, invalid.text


def test_insights_excludes_other_tenants_and_allows_viewer(
    app: FastAPI, db: OrmSession, mixed_channel_data: Any
) -> None:
    users_a = mixed_channel_data["users_a"]
    users_b = mixed_channel_data["users_b"]
    data_b = _insights(users_b).json()
    campaigns_b = data_b["conversations_by_campaign"]
    assert campaigns_b == {"Foreign promo": 1}
    assert users_b.tenant_id != users_a.tenant_id
    wa_rows = [
        row
        for row in data_b["channel_breakdown"]
        if row["channel"] == "whatsapp"
    ]
    assert len(wa_rows) == 1 and wa_rows[0]["conversations"] == 1
    # Viewer (client role) reads its own tenant only; foreign viewer gets nothing.
    # A foreign tenant is hidden, not accessible: 404.
    response = users_a.as_user("viewer").get(
        f"/api/v1/tenants/{users_b.tenant_id}/analytics"
    )
    assert response.status_code == 404, response.text


def test_insights_website_only_tenant_unchanged(
    app: FastAPI, db: OrmSession, request: pytest.FixtureRequest
) -> None:
    from tests.test_conversations_view import seed_setup

    users = seeded_tenant(app, db, prefix=f"ins-wo-{uuid4().hex[:8]}")
    request.addfinalizer(users.cleanup)
    setup = seed_setup(app, users, db, name="Website only")
    request.addfinalizer(setup["client"].close)
    data = _insights(users).json()
    assert data["total_conversations"] == 1
    assert data["conversations_by_channel"] == {"website": 1}
    assert [row["channel"] for row in data["channel_breakdown"]] == ["website"]
    assert data["channel_breakdown"][0]["conversations"] == 1
    assert data["conversations_by_campaign"] == {}
    assert data["handoff_count"] == 0


# --- contacts -----------------------------------------------------------------


def _contact_with_identities(
    app: FastAPI, db: OrmSession, users: Any, *, channels: list[str]
) -> Any:
    response = users.call(
        "admin",
        "POST",
        f"/api/v1/tenants/{users.tenant_id}/contacts",
        json={"email": f"{uuid4().hex}@example.com", "display_name": "Mixed Chan"},
    )
    assert response.status_code == 201, response.text
    contact_id = UUID(response.json()["id"])
    for index, channel in enumerate(channels):
        db.add(
            ContactIdentity(
                tenant_id=users.tenant_id,
                contact_id=contact_id,
                channel=channel,
                external_id=f"ext-{contact_id.hex[:8]}-{index}",
            )
        )
    db.commit()
    return contact_id


def test_contacts_channel_column_and_filter(
    app: FastAPI, db: OrmSession, mixed_channel_data: Any
) -> None:
    users_a = mixed_channel_data["users_a"]
    users_b = mixed_channel_data["users_b"]
    contact_id = _contact_with_identities(
        app, db, users_a, channels=["website", "whatsapp"]
    )
    instagram_id = _contact_with_identities(
        app, db, users_a, channels=["instagram"]
    )
    _contact_with_identities(app, db, users_b, channels=["whatsapp"])
    url = f"/api/v1/tenants/{users_a.tenant_id}/contacts"
    listing = users_a.as_user("viewer").get(url)
    assert listing.status_code == 200, listing.text
    rows = {row["id"]: row for row in listing.json()["contacts"]}
    assert rows[str(contact_id)]["channels"] == ["website", "whatsapp"]
    assert rows[str(instagram_id)]["channels"] == ["instagram"]

    wa = users_a.as_user("viewer").get(url + "?channel=whatsapp")
    ids = {row["id"] for row in wa.json()["contacts"]}
    assert ids == {str(contact_id)}
    ig = users_a.as_user("viewer").get(url + "?channel=instagram")
    assert {row["id"] for row in ig.json()["contacts"]} == {str(instagram_id)}
    invalid = users_a.as_user("viewer").get(url + "?channel=tiktok")
    assert invalid.status_code == 422, invalid.text
    # Tenant B's whatsapp contact stays out of tenant A's filter.
    foreign = users_b.as_user("viewer").get(
        f"/api/v1/tenants/{users_b.tenant_id}/contacts?channel=whatsapp"
    )
    assert foreign.status_code == 200
    assert all(
        foreign_id != str(contact_id)
        for foreign_id in (row["id"] for row in foreign.json()["contacts"])
    )


def test_contacts_export_has_channel_column(
    app: FastAPI, db: OrmSession, mixed_channel_data: Any
) -> None:
    from app.contacts.router import _export_safe

    users_a = mixed_channel_data["users_a"]
    _contact_with_identities(app, db, users_a, channels=["whatsapp", "website"])
    response = users_a.as_user("admin").get(
        f"/api/v1/tenants/{users_a.tenant_id}/contacts/export.csv"
    )
    assert response.status_code == 200, response.text
    body = response.text
    header = body.splitlines()[0]
    row = body.splitlines()[1]
    assert "channels" in header.split(",")
    channels_field = row.split(",")[5]
    assert channels_field == "website;whatsapp"
    forbidden = [char for char in (",", '"') if char in channels_field]
    assert forbidden == []
    # The neutralization guard escapes spreadsheet operators defensively.
    for value, escaped in (("=cmd", "'=cmd"), ("+1-555", "'+1-555"), ("normal", "normal")):
        assert _export_safe(value) == escaped
