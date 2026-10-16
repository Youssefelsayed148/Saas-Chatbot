"""Offline seed guard tests plus disposable-PostgreSQL idempotency/isolation checks."""

from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.security import hash_password, verify_password
from app.core.config import Settings
from app.db.models import Bot, Membership, Tenant, User
from app.db.models.chat import Contact, ContactStage, Conversation, Message, UsageEvent
from app.db.models.knowledge import Chunk, Document, KnowledgeRevision, Source, SourcePage
from app.knowledge.storage import get_storage
from scripts.seed_demo import (
    FAKE_PASSWORD,
    ROLES,
    demo_id,
    demo_password,
    guard_database,
    main,
    seed_demo,
)


@pytest.mark.parametrize("name", ["chatbot_dev", "chatbot_demo"])
def test_guard_accepts_only_demo_or_dev(name: str) -> None:
    assert guard_database(f"postgresql+psycopg://u:secret@localhost:55432/{name}") == (
        "localhost",
        name,
    )


@pytest.mark.parametrize(
    "url",
    [
        "",
        "not-a-url",
        "sqlite:///chatbot_dev",
        "postgresql://u:secret@localhost/chatbot_dev_test",
        "postgresql://u:secret@localhost/chatbot_test",
        "postgresql://u:secret@localhost/chatbot",
        "postgresql://u:secret@prod-db/chatbot_dev",
        "postgresql://u:secret@localhost/production_demo",
        "postgresql://u:secret@localhost/live_dev",
        "postgresql://u:secret@localhost/staging_demo",
        "postgresql://u:secret@localhost/chatbot_demo?host=prod-db",
        "postgresql://u:secret@localhost/chatbot_test_demo",
    ],
)
def test_guard_rejects_unsafe_targets_without_credentials(url: str) -> None:
    with pytest.raises(ValueError) as error:
        guard_database(url)
    assert "secret" not in str(error.value)


def test_guard_refuses_production_environment() -> None:
    with pytest.raises(ValueError):
        guard_database("postgresql://u:secret@localhost/chatbot_dev", "production")


def test_password_default_only_in_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEMO_SEED_PASSWORD", raising=False)
    assert demo_password("chatbot_dev") == FAKE_PASSWORD
    with pytest.raises(ValueError):
        demo_password("chatbot_demo")
    monkeypatch.setenv("DEMO_SEED_PASSWORD", "FakeExplicit!123")
    assert demo_password("chatbot_demo") == "FakeExplicit!123"


def test_guard_cli_rejects_test_database_before_connecting(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:secret@localhost/chatbot_dev_test")

    def forbidden_connection(settings: Settings) -> None:
        pytest.fail("Guard must run before opening a connection")

    monkeypatch.setattr("scripts.seed_demo.create_db_engine", forbidden_connection)
    assert main() == 1
    assert "secret" not in capsys.readouterr().out


def test_seed_twice_has_expected_counts_and_keeps_other_tenant(
    db: Session,
    tmp_path: Path,
) -> None:
    other = Tenant(id=uuid4(), name="Other tenant", slug="other-tenant", plan_label="free")
    db.add(other)
    db.flush()
    db.add(
        Contact(
            tenant_id=other.id, display_name="Other fictional visitor", email="other@example.com"
        )
    )
    db.commit()
    settings = Settings.model_construct(storage_root=str(tmp_path))
    storage = get_storage(settings)
    first = seed_demo(db, storage, settings, FAKE_PASSWORD)
    assert first.created
    files_before = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*.md"))
    second = seed_demo(db, storage, settings, FAKE_PASSWORD)
    assert not second.created
    assert (first.tenant_id, first.bot_id) == (second.tenant_id, second.bot_id)
    assert sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*.md")) == files_before
    assert len(files_before) == 4
    assert db.scalar(select(func.count()).select_from(Tenant)) == 2
    assert db.scalar(select(func.count()).select_from(User)) == 3
    for model, expected in (
        (Membership, 3),
        (Bot, 1),
        (Source, 4),
        (SourcePage, 4),
        (Document, 4),
        (Chunk, 4),
        (KnowledgeRevision, 1),
        (Contact, 3),
        (ContactStage, 3),
        (Conversation, 6),
        (Message, 14),
        (UsageEvent, 11),
    ):
        assert (
            db.scalar(
                select(func.count()).select_from(model).where(model.tenant_id == first.tenant_id)
            )
            == expected
        )
    tenant = db.scalar(select(Tenant).where(Tenant.id == first.tenant_id))
    assert tenant is not None and tenant.plan_label == "business"
    bot = db.scalar(select(Bot).where(Bot.tenant_id == first.tenant_id, Bot.id == first.bot_id))
    assert bot is not None and bot.status == "active" and bot.widget_locator
    revision = db.scalar(
        select(KnowledgeRevision).where(KnowledgeRevision.tenant_id == first.tenant_id)
    )
    assert revision is not None and revision.status == "published"
    assert bot.published_revision_id == revision.id
    for role in ROLES:
        user = db.scalar(select(User).where(User.email == f"demo-{role}@example.com"))
        assert user is not None and verify_password(FAKE_PASSWORD, user.password_hash)
        assert not user.is_platform_staff
        member = db.scalar(
            select(Membership).where(
                Membership.tenant_id == first.tenant_id, Membership.user_id == user.id
            )
        )
        assert member is not None and member.role == role
    answered = db.scalar(
        select(Message).where(Message.tenant_id == first.tenant_id, Message.can_answer.is_(True))
    )
    assert answered is not None and answered.citations
    chunk_id = answered.citations[0]["chunk_id"]
    assert (
        db.scalar(select(Chunk).where(Chunk.tenant_id == first.tenant_id, Chunk.id == chunk_id))
        is not None
    )
    unanswered = list(
        db.scalars(
            select(Message).where(
                Message.tenant_id == first.tenant_id,
                Message.conversation_id == demo_id("conversation/unanswered"),
                Message.sender_type == "ai",
            )
        )
    )
    assert len(unanswered) == 2 and all(message.can_answer is False for message in unanswered)
    assert sum(message.needs_human for message in unanswered) == 1
    conversations = list(
        db.scalars(select(Conversation).where(Conversation.tenant_id == first.tenant_id))
    )
    assert sum(conversation.status == "waiting_human" for conversation in conversations) == 3
    assert any(
        conversation.status == "resolved" and conversation.sentiment == "positive"
        for conversation in conversations
    )
    arabic = db.scalar(
        select(Message).where(
            Message.tenant_id == first.tenant_id,
            Message.conversation_id == demo_id("conversation/arabic"),
            Message.sender_type == "visitor",
        )
    )
    assert arabic is not None and arabic.text == "أريد التحدث مع موظف لحجز موعد."
    assert (
        db.scalar(select(func.count()).select_from(Contact).where(Contact.tenant_id == other.id))
        == 1
    )
    other_after = db.scalar(select(Tenant).where(Tenant.id == other.id))
    assert other_after is not None and other_after.plan_label == "free"
    for source in db.scalars(select(Source).where(Source.tenant_id == first.tenant_id)):
        assert sha256_bytes(storage.open(source.storage_key)) == source.sha256


def sha256_bytes(data: bytes) -> str:
    from hashlib import sha256

    return sha256(data).hexdigest()


def test_seed_conflicting_email_rolls_back(db: Session, tmp_path: Path) -> None:
    unrelated = User(
        id=uuid4(), email="demo-admin@example.com", password_hash=hash_password("OtherFake!123")
    )
    db.add(unrelated)
    db.commit()
    settings = Settings.model_construct(storage_root=str(tmp_path))
    with pytest.raises(ValueError, match="existing account"):
        seed_demo(db, get_storage(settings), settings, FAKE_PASSWORD)
    assert db.scalar(select(func.count()).select_from(Tenant)) == 0
    assert db.scalar(select(func.count()).select_from(User)) == 1
    assert verify_password("OtherFake!123", unrelated.password_hash)


def test_seed_wrong_password_preserves_existing_data(db: Session, tmp_path: Path) -> None:
    settings = Settings.model_construct(storage_root=str(tmp_path))
    storage = get_storage(settings)
    seed_demo(db, storage, settings, FAKE_PASSWORD)
    with pytest.raises(ValueError, match="password mismatch"):
        seed_demo(db, storage, settings, "OtherFake!123")
    admin = db.scalar(select(User).where(User.id == demo_id("user/admin")))
    assert admin is not None and verify_password(FAKE_PASSWORD, admin.password_hash)
    assert db.scalar(select(func.count()).select_from(Tenant)) == 1
    assert len(list(tmp_path.rglob("*.md"))) == 4


def test_seed_storage_failure_rolls_back_and_cleans_files(
    db: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings.model_construct(storage_root=str(tmp_path))
    storage = get_storage(settings)
    save = storage.save
    calls = 0

    def fail_second_save(tenant_id: UUID, bot_id: UUID, kind: str, data: bytes) -> str:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("Simulated local storage failure")
        return save(tenant_id, bot_id, kind, data)

    monkeypatch.setattr(storage, "save", fail_second_save)
    with pytest.raises(OSError, match="Simulated"):
        seed_demo(db, storage, settings, FAKE_PASSWORD)
    assert db.scalar(select(func.count()).select_from(Tenant)) == 0
    assert db.scalar(select(func.count()).select_from(User)) == 0
    assert db.scalar(select(func.count()).select_from(Source)) == 0
    assert list(tmp_path.rglob("*.md")) == []
