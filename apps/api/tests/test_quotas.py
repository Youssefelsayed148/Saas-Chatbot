"""P7-02 tenant scoped PLACEHOLDER quotas and staff overrides."""

from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from typing import Any
from uuid import uuid4

from pydantic import SecretStr
from sqlalchemy import select

from app.core.config import Settings
from app.db.models import AuditEvent, Bot, Conversation, Job, Message, Tenant, UsageEvent
from tests.helpers import make_bot, seeded_tenant
from tests.test_platform import platform_call, staff_login


def test_quota_snapshot_is_tenant_scoped_and_readable_by_viewers(app: Any, db: Any) -> None:
    tenant_a = seeded_tenant(app, db, prefix="quota-a")
    tenant_b = seeded_tenant(app, db, prefix="quota-b")
    bot_a = make_bot(tenant_a)
    make_bot(tenant_b)

    path_a = f"/api/v1/tenants/{tenant_a.tenant_id}/quota"
    own = tenant_a.call("viewer", "GET", path_a)
    assert own.status_code == 200
    assert own.json()["placeholder"] is True
    assert own.json()["usage"]["bots"] == 1
    hidden = tenant_b.call("viewer", "GET", path_a)
    assert hidden.status_code == 404

    # The owner can see usage and the viewer sees the same tenant-scoped data.
    assert tenant_a.call("owner", "GET", path_a).json() == own.json()
    bot_path = f"/api/v1/tenants/{tenant_a.tenant_id}/bots/{bot_a['id']}/quota"
    assert tenant_a.call("viewer", "GET", bot_path).status_code == 200
    assert tenant_b.call("viewer", "GET", bot_path).status_code == 404
    tenant_a.cleanup()
    tenant_b.cleanup()


def test_bot_quota_blocks_creation_and_viewers_cannot_mutate(app: Any, db: Any) -> None:
    tenant = seeded_tenant(app, db, prefix="quota-bots")
    other_tenant = seeded_tenant(app, db, prefix="quota-bots-other")
    row = db.execute(select(Tenant).where(Tenant.id == tenant.tenant_id)).scalar_one()
    row.plan_label = "free"
    db.commit()
    path = f"/api/v1/tenants/{tenant.tenant_id}/bots"
    assert tenant.call("viewer", "POST", path, json={"name": "Denied"}).status_code == 403
    assert other_tenant.call("owner", "POST", path, json={"name": "Hidden"}).status_code == 404
    created = tenant.call("owner", "POST", path, json={"name": "First"})
    assert created.status_code == 201, created.text
    blocked = tenant.call("owner", "POST", path, json={"name": "Second"})
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "QUOTA_EXCEEDED"
    tenant.cleanup()
    other_tenant.cleanup()


def test_bot_quota_is_serialized_under_concurrent_creation(app: Any, db: Any) -> None:
    tenant = seeded_tenant(app, db, prefix="quota-race")
    row = db.execute(select(Tenant).where(Tenant.id == tenant.tenant_id)).scalar_one()
    row.plan_label = "free"
    db.commit()
    path = f"/api/v1/tenants/{tenant.tenant_id}/bots"

    def create(role: str, name: str) -> int:
        return tenant.call(role, "POST", path, json={"name": name}).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(create, "owner", "Race A"),
            pool.submit(create, "editor", "Race B"),
        ]
        statuses = sorted(future.result() for future in futures)
    assert statuses == [201, 429]
    db.expire_all()
    assert (
        len(db.execute(select(Bot).where(Bot.tenant_id == tenant.tenant_id)).scalars().all()) == 1
    )
    tenant.cleanup()


def test_platform_quota_override_requires_staff_reason_and_audits(app: Any, db: Any) -> None:
    tenant = seeded_tenant(app, db, prefix="quota-override")
    owner = tenant.as_user("owner")
    assert platform_call(owner, "GET", "/quotas").status_code == 403
    path = f"/api/v1/platform/tenants/{tenant.tenant_id}/quota-overrides"
    denied = platform_call(
        owner,
        "PATCH",
        f"/tenants/{tenant.tenant_id}/quota-overrides",
        json={"limits": {"bots": 8}, "reason": "Approved exception"},
    )
    assert denied.status_code == 403
    staff = staff_login(app, db)
    invalid = platform_call(
        staff,
        "PATCH",
        f"/tenants/{tenant.tenant_id}/quota-overrides",
        json={"limits": {"bots": 8}, "reason": " "},
    )
    assert invalid.status_code == 422
    allowed = platform_call(
        staff,
        "PATCH",
        f"/tenants/{tenant.tenant_id}/quota-overrides",
        json={"limits": {"bots": 8}, "reason": "Approved exception"},
    )
    assert allowed.status_code == 200, allowed.text
    db.expire_all()
    row = db.execute(select(Tenant).where(Tenant.id == tenant.tenant_id)).scalar_one()
    assert row.quota_overrides["bots"] == 8
    audit = db.execute(
        select(AuditEvent).where(AuditEvent.action == "platform.tenant.quota_override")
    ).scalar_one()
    assert audit.metadata_json["reason"] == "Approved exception"
    assert path.endswith("quota-overrides")
    tenant.cleanup()


def test_plan_file_limit_applies_to_chunked_stream_without_content_length() -> None:
    from app.core.config import Settings
    from app.knowledge.service import read_upload

    settings = Settings.model_construct(max_upload_file_bytes=5)
    assert read_upload(BytesIO(b"12345"), settings) == b"12345"


def test_contact_and_seat_quotas_are_scoped_and_viewer_writes_are_denied(app: Any, db: Any) -> None:
    tenant_a = seeded_tenant(app, db, prefix="quota-create-a")
    tenant_b = seeded_tenant(app, db, prefix="quota-create-b")
    row = db.execute(select(Tenant).where(Tenant.id == tenant_a.tenant_id)).scalar_one()
    row.quota_overrides = {"contacts": 0, "seats": 4}
    db.commit()
    contact_url = f"/api/v1/tenants/{tenant_a.tenant_id}/contacts"
    payload = {"display_name": "Quota contact", "email": "quota@example.com"}
    assert tenant_a.call("viewer", "POST", contact_url, json=payload).status_code == 403
    assert tenant_b.call("owner", "POST", contact_url, json=payload).status_code == 404
    assert tenant_a.call("owner", "POST", contact_url, json=payload).status_code == 429

    invite_url = f"/api/v1/tenants/{tenant_a.tenant_id}/invitations"
    invite_payload = {"email": "new-seat@example.com", "role": "viewer"}
    assert tenant_a.call("viewer", "POST", invite_url, json=invite_payload).status_code == 403
    assert tenant_b.call("owner", "POST", invite_url, json=invite_payload).status_code == 404
    assert tenant_a.call("owner", "POST", invite_url, json=invite_payload).status_code == 429
    tenant_a.cleanup()
    tenant_b.cleanup()


def test_sentiment_is_queued_for_resolved_conversation_with_tenant_and_role_guards(
    app: Any, db: Any
) -> None:
    tenant_a = seeded_tenant(app, db, prefix="sentiment-a")
    tenant_b = seeded_tenant(app, db, prefix="sentiment-b")
    bot = make_bot(tenant_a)
    conversation = Conversation(
        tenant_id=tenant_a.tenant_id,
        bot_id=bot["id"],
        channel="website",
        source="website",
        mode="ai",
        status="open",
    )
    db.add(conversation)
    db.commit()
    url = f"/api/v1/tenants/{tenant_a.tenant_id}/conversations/{conversation.id}/resolve"
    assert tenant_a.call("viewer", "POST", url).status_code == 403
    assert tenant_b.call("editor", "POST", url).status_code == 404
    resolved = tenant_a.call("editor", "POST", url)
    assert resolved.status_code == 200, resolved.text
    db.expire_all()
    jobs = (
        db.execute(
            select(Job).where(
                Job.tenant_id == tenant_a.tenant_id,
                Job.type == "sentiment_classify",
            )
        )
        .scalars()
        .all()
    )
    assert len(jobs) == 1
    assert jobs[0].payload["conversation_id"] == str(conversation.id)
    tenant_a.cleanup()
    tenant_b.cleanup()


def test_sentiment_worker_records_one_measured_classification(db: Any, monkeypatch: Any) -> None:
    import app.chat.providers as providers
    from app.chat.providers import FakeChatModel
    from app.quotas.sentiment import run_sentiment_job

    tenant = Tenant(id=uuid4(), name="Sentiment", slug="sentiment-worker", plan_label="starter")
    db.add(tenant)
    db.flush()  # composite tenant FKs need the tenant row first
    # A membership is unnecessary for worker-owned rows; create a bot and conversation directly.
    bot = Bot(id=uuid4(), tenant_id=tenant.id, name="Sentiment bot", status="active", config={})
    db.add(bot)
    db.flush()  # composite (tenant_id, bot_id) FK needs the bot row first
    conversation = Conversation(
        tenant_id=tenant.id,
        bot_id=bot.id,
        status="resolved",
        channel="website",
        source="website",
    )
    db.add(conversation)
    db.flush()
    db.add(
        Message(
            tenant_id=tenant.id,
            bot_id=bot.id,
            conversation_id=conversation.id,
            sender_type="visitor",
            text="Thank you, this was helpful.",
        )
    )
    job = Job(
        tenant_id=tenant.id,
        bot_id=bot.id,
        type="sentiment_classify",
        status="running",
        payload={"conversation_id": str(conversation.id)},
    )
    db.add(job)
    db.commit()
    fake = FakeChatModel(['{"sentiment":"positive"}'])
    monkeypatch.setattr(providers, "OpenAICompatibleModel", lambda **_kwargs: fake)
    settings = Settings.model_construct(
        chat_stub_model=False,
        chat_openrouter_api_key=SecretStr("test-key"),
        chat_free_model_chain=["test-model:free"],
        chat_openrouter_base_url="https://example.invalid",
    )
    assert run_sentiment_job(db, job, settings) is None
    db.expire_all()
    assert db.get(Conversation, conversation.id).sentiment == "positive"
    assert (
        len(
            db.execute(
                select(UsageEvent).where(
                    UsageEvent.tenant_id == tenant.id, UsageEvent.kind == "sentiment_run"
                )
            )
            .scalars()
            .all()
        )
        == 1
    )
