"""UI polish B3: tenant time series, previous-period block, question grouping,
inbox list fields/filters, quota at_limit, and token-number definitions."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.orm import Session as OrmSession

from app.analytics.service import question_key
from app.db.models import Contact, Conversation, Message, UsageEvent
from app.quotas.rag import monthly_usage
from app.quotas.service import usage_snapshot
from tests.helpers import make_bot, seeded_tenant


def _day(offset: int, hour: int = 10) -> datetime:
    base = datetime.now(UTC).replace(hour=hour, minute=0, second=0, microsecond=0)
    return base - timedelta(days=offset)


def _conversation(
    db: OrmSession,
    users: Any,
    bot: dict[str, Any],
    created_at: datetime,
    *,
    status: str = "open",
    handoff: bool = False,
    source: str = "website",
    contact_id: UUID | None = None,
) -> Conversation:
    conversation = Conversation(
        id=uuid4(),
        tenant_id=users.tenant_id,
        bot_id=UUID(bot["id"]),
        contact_id=contact_id,
        channel="website",
        mode="human" if handoff else "ai",
        status=status,
        handoff_reason="test" if handoff else None,
        source=source,
        created_at=created_at,
        updated_at=created_at,
        last_message_at=created_at,
    )
    db.add(conversation)
    db.commit()
    return conversation


def _message(
    db: OrmSession,
    conversation: Conversation,
    sender: str,
    text: str,
    created_at: datetime,
    *,
    can_answer: bool | None = None,
) -> None:
    db.add(
        Message(
            tenant_id=conversation.tenant_id,
            bot_id=conversation.bot_id,
            conversation_id=conversation.id,
            sender_type=sender,
            text=text,
            can_answer=can_answer,
            created_at=created_at,
        )
    )
    db.commit()


def _iso(value: datetime) -> str:
    return value.date().isoformat()


def test_timeseries_is_zero_filled_scoped_and_website_only(app: Any, db: OrmSession) -> None:
    users = seeded_tenant(app, db, prefix="b3-ts-a")
    other = seeded_tenant(app, db, prefix="b3-ts-b")
    try:
        bot = make_bot(users)
        other_bot = make_bot(other)
        _conversation(db, users, bot, _day(2))
        _conversation(db, users, bot, _day(2), handoff=True, status="resolved")
        _conversation(db, users, bot, _day(0))
        _conversation(db, users, bot, _day(1), source="playground")
        _conversation(db, other, other_bot, _day(2))

        path = f"/api/v1/tenants/{users.tenant_id}/analytics/timeseries"
        result = users.call(
            "viewer", "GET", path, params={"from": _iso(_day(3)), "to": _iso(_day(0))}
        )
        assert result.status_code == 200, result.text
        days = result.json()["days"]
        assert [row["day"] for row in days] == [_iso(_day(n)) for n in (3, 2, 1, 0)]
        assert [(r["conversations"], r["handoffs"], r["resolved"]) for r in days] == [
            (0, 0, 0),
            (2, 1, 1),
            (0, 0, 0),  # playground thread on this day never counts
            (1, 0, 0),
        ]
        other_days = other.call(
            "viewer", "GET", f"/api/v1/tenants/{other.tenant_id}/analytics/timeseries"
        ).json()["days"]
        assert sum(row["conversations"] for row in other_days) == 1
        assert len(other_days) == 30  # default window is zero-filled too

        assert users.call("viewer", "GET", path, params={"from": "nope"}).status_code == 422
        assert (
            users.call("viewer", "GET", path, params={"from": "2020-01-01", "to": "2026-01-01"})
        ).status_code == 422
        hidden = users.as_user("admin").get(
            f"/api/v1/tenants/{other.tenant_id}/analytics/timeseries"
        )
        assert hidden.status_code == 404
    finally:
        users.cleanup()
        other.cleanup()


def test_analytics_previous_period_block(app: Any, db: OrmSession) -> None:
    users = seeded_tenant(app, db, prefix="b3-prev-a")
    other = seeded_tenant(app, db, prefix="b3-prev-b")
    try:
        bot = make_bot(users)
        other_bot = make_bot(other)
        # Current window: 3 days ago..today; previous: the 4 days before it.
        _conversation(db, users, bot, _day(1))
        current_handoff = _conversation(db, users, bot, _day(1), handoff=True)
        previous_a = _conversation(db, users, bot, _day(5), handoff=True)
        _conversation(db, users, bot, _day(6))
        _conversation(db, users, bot, _day(7))
        _conversation(db, users, bot, _day(20))  # outside both windows
        _conversation(db, other, other_bot, _day(5))  # other tenant never leaks
        db.add(
            Message(
                tenant_id=users.tenant_id,
                bot_id=previous_a.bot_id,
                conversation_id=previous_a.id,
                sender_type="agent",
                text="hi",
                created_at=previous_a.created_at + timedelta(seconds=30),
            )
        )
        db.commit()
        assert current_handoff.id

        path = f"/api/v1/tenants/{users.tenant_id}/analytics"
        data = users.call(
            "viewer", "GET", path, params={"from": _iso(_day(3)), "to": _iso(_day(0))}
        ).json()
        assert data["total_conversations"] == 2  # existing fields unchanged
        assert data["handoff_count"] == 1
        assert data["handoff_rate"] == 0.5
        previous = data["previous"]
        assert previous["from"] == _iso(_day(7))
        assert previous["to"] == _iso(_day(4))
        assert previous["total_conversations"] == 3
        assert previous["handoff_count"] == 1
        assert previous["handoff_rate"] == 1 / 3
        assert previous["average_first_human_reply_seconds"] == 30.0

        empty = other.call(
            "viewer",
            "GET",
            f"/api/v1/tenants/{other.tenant_id}/analytics",
            params={"from": _iso(_day(30)), "to": _iso(_day(28))},
        ).json()["previous"]
        assert empty["total_conversations"] == 0
        assert empty["handoff_rate"] is None
        assert empty["average_first_human_reply_seconds"] is None
    finally:
        users.cleanup()
        other.cleanup()


def test_question_key_groups_english_and_arabic_variants() -> None:
    assert question_key("How can I return an item?") == question_key("  how can i RETURN an item ")
    assert question_key("hello!!") == question_key("Hello?!...")
    assert question_key("هل يوجد توصيل؟") == question_key("هل يوجد توصيل")
    assert question_key("أين الفرع؟") == question_key("اين الفرع")
    assert question_key("إلى متى") == question_key("الى متى")
    assert question_key("مدرسة") == question_key("مدرسه")
    assert question_key("على") == question_key("علي") == question_key("علىٰ")
    assert question_key("كَيْفَ حالك") == question_key("كيف حالك")
    assert question_key("price?") != question_key("prices?")
    assert question_key("?") == ""


def test_top_and_unanswered_group_near_duplicates(app: Any, db: OrmSession) -> None:
    users = seeded_tenant(app, db, prefix="b3-q-a")
    other = seeded_tenant(app, db, prefix="b3-q-b")
    try:
        bot = make_bot(users)
        other_bot = make_bot(other)
        now = datetime.now(UTC).replace(microsecond=0) - timedelta(hours=2)
        variants = [
            ("how can i return an item?", 0),
            ("How can I return an item", 10),
            ("how can i   return an item??", 20),
            ("هل يوجد توصيل؟", 30),
            ("هل يوجد توصيل", 40),
            ("What are your hours?", 50),
        ]
        for text, offset in variants:
            at = now + timedelta(minutes=offset)
            conversation = _conversation(db, users, bot, at)
            _message(db, conversation, "visitor", text, at)
            _message(
                db,
                conversation,
                "ai",
                "I am not sure.",
                at + timedelta(seconds=5),
                can_answer=False,
            )
        foreign = _conversation(db, other, other_bot, now)
        _message(db, foreign, "visitor", "How can I return an item", now)

        base = f"/api/v1/tenants/{users.tenant_id}/bots/{bot['id']}/analytics"
        top = users.call("viewer", "GET", f"{base}/top-questions").json()["questions"]
        assert top[0] == {"question": "how can i   return an item??", "asked": 3}
        assert top[1] == {"question": "هل يوجد توصيل", "asked": 2}
        assert top[2] == {"question": "What are your hours?", "asked": 1}
        assert len(top) == 3
        assert (
            len(
                users.call("viewer", "GET", f"{base}/top-questions", params={"limit": 2}).json()[
                    "questions"
                ]
            )
            == 2
        )

        unanswered = users.call("viewer", "GET", f"{base}/unanswered").json()["questions"]
        assert [(q["question"], q["asked"]) for q in unanswered] == [
            ("What are your hours?", 1),
            ("هل يوجد توصيل", 2),
            ("how can i   return an item??", 3),
        ]
        assert all(q["last"] for q in unanswered)

        hidden = users.as_user("admin").get(
            f"/api/v1/tenants/{other.tenant_id}/bots/{other_bot['id']}/analytics/top-questions"
        )
        assert hidden.status_code == 404
    finally:
        users.cleanup()
        other.cleanup()


def test_inbox_list_rows_total_and_created_range(app: Any, db: OrmSession) -> None:
    users = seeded_tenant(app, db, prefix="b3-inbox-a")
    other = seeded_tenant(app, db, prefix="b3-inbox-b")
    try:
        bot = make_bot(users)
        other_bot = make_bot(other)
        contact = Contact(
            id=uuid4(), tenant_id=users.tenant_id, display_name="Sara Ali", email="s@example.com"
        )
        other_contact = Contact(
            id=uuid4(),
            tenant_id=other.tenant_id,
            display_name="Other Person",
            email="o@example.com",
        )
        db.add_all([contact, other_contact])
        db.commit()
        old = _conversation(db, users, bot, _day(10), contact_id=contact.id)
        recent = _conversation(db, users, bot, _day(1))
        _message(db, old, "visitor", "old question", _day(10))
        _message(db, recent, "visitor", "recent question", _day(1))
        _conversation(db, other, other_bot, _day(1), contact_id=other_contact.id)

        url = f"/api/v1/tenants/{users.tenant_id}/inbox"
        everything = users.call("viewer", "GET", url).json()
        assert everything["total"] == 2
        rows = {row["id"]: row for row in everything["conversations"]}
        row = rows[str(old.id)]
        assert row["contact_name"] == "Sara Ali"
        assert row["last_message"] == "old question"
        assert row["bot_id"] == bot["id"]
        assert {"status", "channel", "mode", "unread_count", "created_at"} <= set(row)
        assert rows[str(recent.id)]["contact_name"] is None

        ranged = users.call(
            "viewer",
            "GET",
            url,
            params={"created_from": _iso(_day(11)), "created_to": _iso(_day(9)), "limit": 1},
        ).json()
        assert ranged["total"] == 1
        assert ranged["conversations"][0]["id"] == str(old.id)
        same_day = users.call(
            "viewer",
            "GET",
            url,
            params={"created_from": _iso(_day(1)), "created_to": _iso(_day(1))},
        ).json()
        assert [r["id"] for r in same_day["conversations"]] == [str(recent.id)]
        paged = users.call("viewer", "GET", url, params={"limit": 1, "offset": 1}).json()
        assert paged["total"] == 2 and len(paged["conversations"]) == 1
        assert users.call("viewer", "GET", url, params={"created_from": "bad"}).status_code == 422

        foreign = other.call("viewer", "GET", f"/api/v1/tenants/{other.tenant_id}/inbox").json()
        assert foreign["conversations"][0]["contact_name"] == "Other Person"
        assert (
            users.as_user("admin").get(f"/api/v1/tenants/{other.tenant_id}/inbox").status_code
            == 404
        )
    finally:
        users.cleanup()
        other.cleanup()


def test_quota_at_limit_is_a_subset_of_warnings(app: Any, db: OrmSession) -> None:
    users = seeded_tenant(app, db, prefix="b3-quota-a", plan_label="starter")
    try:
        make_bot(users)
        snapshot = users.call("viewer", "GET", f"/api/v1/tenants/{users.tenant_id}/quota").json()
        assert snapshot["usage"]["bots"] >= snapshot["limits"]["bots"] > 0
        assert "bots" in snapshot["at_limit"]
        assert "bots" in snapshot["warnings"]
        assert set(snapshot["at_limit"]) <= set(snapshot["warnings"])
        for name in snapshot["at_limit"]:
            assert snapshot["usage"][name] >= snapshot["limits"][name]
        for name in set(snapshot["warnings"]) - set(snapshot["at_limit"]):
            assert snapshot["usage"][name] < snapshot["limits"][name]
    finally:
        users.cleanup()


def test_token_numbers_measure_different_things_by_design(app: Any, db: OrmSession) -> None:
    """BE-5 evidence: measured_tokens_this_month is tenant-wide provider-reported chat
    tokens; monthly_tokens is per bot, includes embeddings and reserved bounds."""
    users = seeded_tenant(app, db, prefix="b3-tokens-a")
    try:
        bot = make_bot(users)
        bot_id = UUID(bot["id"])

        def event(kind: str, payload: dict[str, object]) -> None:
            db.add(
                UsageEvent(
                    tenant_id=users.tenant_id,
                    bot_id=bot_id,
                    kind=kind,
                    external_key=f"{kind}:{uuid4()}",
                    payload=payload,
                )
            )

        # One chat turn: provider reported 100 tokens across its model calls.
        event("message", {"provider_usage": {"total_tokens": 100}, "ai_metered": True})
        event(
            "ai_usage", {"event_type": "generation", "status": "settled", "accounted_tokens": 100}
        )
        # A rewrite whose usage was never reported keeps its conservative reserved bound.
        event(
            "ai_usage",
            {"event_type": "rewrite", "status": "usage_unreported", "accounted_tokens": 900},
        )
        # Embeddings count in monthly_tokens and in monthly_embedding_tokens, not in measured.
        event(
            "ai_usage",
            {
                "event_type": "embed_ingest",
                "status": "settled",
                "accounted_tokens": 400,
                "embedding_tokens": 400,
            },
        )
        db.commit()

        from app.db.models import Tenant

        tenant = db.get(Tenant, users.tenant_id)
        assert tenant is not None
        assert usage_snapshot(db, tenant)["measured_tokens_this_month"] == 100
        used = monthly_usage(db, users.tenant_id, bot_id)
        assert used["monthly_tokens"] == 1400
        assert used["monthly_embedding_tokens"] == 400
    finally:
        users.cleanup()
