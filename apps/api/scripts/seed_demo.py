"""Fictional, offline demo fixtures. CLI never accepts pytest or production databases."""

import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from pydantic import SecretStr
from sqlalchemy import make_url, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth.security import hash_password, verify_password
from app.core.config import Settings
from app.db.models import Bot, Membership, Tenant, User
from app.db.models.chat import Contact, ContactStage, Conversation, Message, UsageEvent
from app.db.models.knowledge import Chunk, Document, KnowledgeRevision, Source, SourcePage
from app.db.session import create_db_engine, session_factory
from app.knowledge.ingest import plan_source
from app.knowledge.parsers import parse_text
from app.knowledge.storage import Storage, get_storage

SLUG = "demo-dental-clinic"
FAKE_PASSWORD = "FakeDemoOnly!123"
ROLES = ("admin", "editor", "viewer")
FAQS = (
    ("hours", "Opening hours", "We are open Monday to Friday from 09:00 to 17:00."),
    (
        "pricing",
        "Pricing",
        "A fictional checkup costs 50 demo credits. Cleaning costs 80 demo credits.",
    ),
    ("booking", "Booking", "Request a booking in this chat. A demo agent will confirm a time."),
    ("location", "Location", "Find our fictional clinic at 42 Example Lane, Demo City."),
)


def demo_id(key: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"https://demo.example.com/{SLUG}/{key}")


@dataclass(frozen=True)
class SeedResult:
    tenant_id: UUID
    bot_id: UUID
    created: bool


def guard_database(database_url: str, environment: str = "development") -> tuple[str, str]:
    """Fail closed, before connecting; return only safe host/database display values."""
    try:
        url = make_url(database_url)
    except Exception:
        raise ValueError("DATABASE_URL must be a PostgreSQL URL.") from None
    name = url.database or ""
    host = url.host or ""
    production = re.search(r"prod|live|staging", f"{host}/{name}", re.IGNORECASE)
    if (
        url.get_backend_name() != "postgresql"
        or not re.fullmatch(r"[a-zA-Z0-9_]+_(dev|demo)", name)
        or production
        or "test" in name.lower().split("_")
        or environment.lower() != "development"
        or url.query  # connection options must not redirect to a different host/database
        or not host
        or not re.fullmatch(r"[a-zA-Z0-9.:-]+", host)
    ):
        raise ValueError(
            "Demo seed requires a development PostgreSQL database ending _dev or _demo."
        )
    return host, name


def demo_password(database_name: str) -> str:
    password = os.environ.get("DEMO_SEED_PASSWORD")
    if not password and database_name.endswith("_dev"):
        password = FAKE_PASSWORD
    if not password or len(password) < 8 or len(password) > 128:
        raise ValueError("Set DEMO_SEED_PASSWORD to an 8–128 character demo-only password.")
    return password


def seed_demo(db: Session, storage: Storage, settings: Settings, password: str) -> SeedResult:
    """Seed in one transaction, without a model call or migrations.

    The CLI owns the database-name guard. Tests call this core with their guarded
    disposable session and temporary storage. A completed seed is left unchanged
    on re-run so manual testing edits survive. Existing unrelated accounts are refused.
    """
    tenant_id, bot_id = demo_id("tenant"), demo_id("bot")
    saved_keys: list[str] = []
    try:
        # Serialize concurrent CLI runs; PostgreSQL releases this on commit/rollback.
        db.execute(text("SELECT pg_advisory_xact_lock(74180314)"))
        tenant = db.scalar(select(Tenant).where(Tenant.slug == SLUG))
        if tenant is not None:
            owner = db.scalar(select(User).where(User.id == demo_id("user/admin")))
            bot = db.scalar(select(Bot).where(Bot.tenant_id == tenant.id, Bot.id == bot_id))
            if (
                tenant.id != tenant_id
                or owner is None
                or not verify_password(password, owner.password_hash)
                or bot is None
            ):
                raise ValueError("Demo identity conflict or password mismatch; no data changed.")
            db.commit()
            return SeedResult(tenant_id, bot_id, False)

        tenant = Tenant(id=tenant_id, name="Demo Dental Clinic", slug=SLUG, plan_label="business")
        db.add(tenant)
        db.flush()
        for role in ROLES:
            email = f"demo-{role}@example.com"
            if db.scalar(select(User).where(User.email == email)) is not None:
                raise ValueError(
                    "A demo email already belongs to an existing account; no data changed."
                )
            user = User(
                id=demo_id(f"user/{role}"), email=email, password_hash=hash_password(password)
            )
            db.add(user)
            db.flush()
            db.add(Membership(tenant_id=tenant_id, user_id=user.id, role=role))
        db.flush()
        bot = Bot(
            id=bot_id,
            tenant_id=tenant_id,
            name="Demo Dental Assistant",
            status="active",
            widget_locator=uuid4().hex,
            config={"handoff_enabled": True, "default_language": "en"},
        )
        db.add(bot)
        db.flush()
        revision = KnowledgeRevision(
            id=demo_id("revision"),
            tenant_id=tenant_id,
            bot_id=bot_id,
            status="published",
            published_at=datetime.now(UTC),
            created_by=demo_id("user/admin"),
        )
        db.add(revision)
        db.flush()
        citation: dict[str, object] = {}
        for key, title, body in FAQS:
            url = f"https://demo.example.com/{key}"
            data = (
                f"---\ntitle: {title}\nsource_url: {url}\nlanguage: en\n---\n"
                f"\n# {title}\n\n{body}\n"
            ).encode()
            storage_key = storage.save(tenant_id, bot_id, "md", data)
            saved_keys.append(storage_key)
            source = Source(
                id=demo_id(f"source/{key}"),
                tenant_id=tenant_id,
                bot_id=bot_id,
                kind="md",
                original_name=f"{key}.md",
                storage_key=storage_key,
                size_bytes=len(data),
                sha256=sha256(data).hexdigest(),
                status="ingested",
                created_by=demo_id("user/admin"),
            )
            db.add(source)
            db.flush()
            pages, documents = plan_source(
                source, parse_text(data, source.original_name), bot, settings
            )
            for page in pages:
                db.add(
                    SourcePage(
                        tenant_id=tenant_id,
                        bot_id=bot_id,
                        source_id=source.id,
                        page_number=page.page_number,
                        title=page.title,
                        source_url=page.source_url,
                        page_type=page.page_type,
                        language=page.language,
                        raw_text=page.raw_text,
                    )
                )
            for plan in documents:
                document = Document(
                    tenant_id=tenant_id,
                    bot_id=bot_id,
                    revision_id=revision.id,
                    source_id=source.id,
                    title=plan.title,
                    heading=plan.heading,
                    source_url=plan.source_url,
                    page_ref=plan.page_ref,
                    ordinal=plan.ordinal,
                    language=plan.language,
                    priority=plan.priority,
                    text=plan.text,
                    total_chars=plan.total_chars,
                )
                db.add(document)
                db.flush()
                for chunk_plan in plan.chunks:
                    chunk = Chunk(
                        id=uuid4(),
                        tenant_id=tenant_id,
                        bot_id=bot_id,
                        revision_id=revision.id,
                        source_id=source.id,
                        document_id=document.id,
                        title=chunk_plan.title,
                        heading=chunk_plan.heading,
                        text=chunk_plan.text,
                        text_norm=chunk_plan.text_norm,
                        language=chunk_plan.language,
                        priority=chunk_plan.priority,
                        content_hash=chunk_plan.content_hash,
                        ordinal=chunk_plan.ordinal,
                    )
                    db.add(chunk)
                    if key == "hours":
                        citation = {
                            "chunk_id": str(chunk.id),
                            "title": plan.title,
                            "heading": plan.heading,
                            "source_url": url,
                            "page_ref": plan.page_ref,
                        }
        db.flush()
        bot.published_revision_id = revision.id
        for order, stage in enumerate(("new", "qualified", "booked")):
            db.add(ContactStage(tenant_id=tenant_id, name=stage, sort_order=order))
            db.add(
                Contact(
                    id=demo_id(f"contact/{order}"),
                    tenant_id=tenant_id,
                    display_name=f"Fictional Visitor {order + 1}",
                    email=f"demo-visitor-{order + 1}@example.com",
                    stage=stage,
                    tags=["demo"],
                    source_channel="website",
                    consent={"website": True},
                )
            )
        db.flush()
        _seed_conversations(db, tenant_id, bot_id, citation)
        db.commit()
        return SeedResult(tenant_id, bot_id, True)
    except Exception:
        db.rollback()
        for storage_key in saved_keys:
            storage.delete(storage_key)
        raise


def _seed_conversations(
    db: Session,
    tenant_id: UUID,
    bot_id: UUID,
    citation: dict[str, object],
) -> None:
    now = datetime.now(UTC)
    scenarios = (
        ("answered", "ai", "open", None, None, "What are your opening hours?"),
        (
            "unanswered",
            "human",
            "waiting_human",
            "unanswered_threshold",
            None,
            "Do you offer moon dentistry?",
        ),
        (
            "waiting",
            "human",
            "waiting_human",
            "visitor_requested",
            None,
            "Please connect me to a person.",
        ),
        ("handled", "human", "open", "manual_takeover", None, "Can an agent confirm my booking?"),
        (
            "resolved",
            "human",
            "resolved",
            "manual_takeover",
            "positive",
            "Thank you for confirming!",
        ),
        (
            "arabic",
            "human",
            "waiting_human",
            "visitor_requested",
            None,
            "أريد التحدث مع موظف لحجز موعد.",
        ),
    )
    for index, (key, mode, status, reason, sentiment, question) in enumerate(scenarios):
        start = now - timedelta(minutes=30 - index * 4)
        conversation = Conversation(
            id=demo_id(f"conversation/{key}"),
            tenant_id=tenant_id,
            bot_id=bot_id,
            contact_id=demo_id(f"contact/{index % 3}"),
            mode=mode,
            status=status,
            handoff_reason=reason,
            sentiment=sentiment,
            created_at=start,
            assigned_user_id=demo_id("user/admin") if key in ("handled", "resolved") else None,
        )
        db.add(conversation)
        db.flush()
        turns: list[tuple[str, str, bool | None, bool]] = [("visitor", question, None, False)]
        if key == "answered":
            turns.append(("ai", FAQS[0][2], True, False))
        elif key == "unanswered":
            turns.extend(
                [
                    ("ai", "I cannot confirm that from our demo FAQ.", False, False),
                    ("visitor", "Can you confirm lunar appointments?", None, False),
                    ("ai", "A human will help with your question.", False, True),
                ]
            )
        elif key in ("handled", "resolved"):
            turns.append(
                ("agent", "Your fictional booking is confirmed for Tuesday at 10:00.", None, False)
            )
        else:
            reply = (
                "سيساعدك أحد الموظفين قريباً."
                if key == "arabic"
                else "A human will help you shortly."
            )
            turns.append(("ai", reply, False, True))
        for ordinal, (sender, body, can_answer, needs_human) in enumerate(turns):
            created_at = start + timedelta(seconds=ordinal)
            message = Message(
                id=demo_id(f"message/{key}/{ordinal}"),
                tenant_id=tenant_id,
                bot_id=bot_id,
                conversation_id=conversation.id,
                sender_type=sender,
                text=body,
                sender_user_id=demo_id("user/admin") if sender == "agent" else None,
                citations=[citation] if can_answer else None,
                can_answer=can_answer,
                needs_human=needs_human,
                response_ms=120 if sender == "ai" else None,
                created_at=created_at,
            )
            db.add(message)
            if sender == "ai":
                db.add(
                    UsageEvent(
                        tenant_id=tenant_id,
                        bot_id=bot_id,
                        kind="message",
                        message_id=message.id,
                        conversation_id=conversation.id,
                        external_key=f"demo:message:{message.id}",
                        payload={"demo": True},
                        created_at=created_at,
                    )
                )
            conversation.last_message_at = created_at
            conversation.updated_at = created_at
        db.add(
            UsageEvent(
                tenant_id=tenant_id,
                bot_id=bot_id,
                kind="widget_open",
                conversation_id=conversation.id,
                external_key=f"demo:open:{conversation.id}",
                payload={"demo": True},
                created_at=start,
            )
        )


def main() -> int:
    try:
        database_url = os.environ.get("DATABASE_URL", "")
        host, database_name = guard_database(
            database_url, os.environ.get("ENVIRONMENT", "development")
        )
        password = demo_password(database_name)
        print(f"Demo seed target: {host}/{database_name}", flush=True)
        # Explicit environment only: never load .env or provider keys.
        settings = Settings.model_construct(database_url=SecretStr(database_url))
        if storage_root := os.environ.get("STORAGE_ROOT"):
            settings.storage_root = storage_root
        engine = create_db_engine(settings)
        try:
            with session_factory(engine)() as db:
                result = seed_demo(db, get_storage(settings), settings, password)
        finally:
            engine.dispose()
        print(f"Demo tenant {'created' if result.created else 'reused'}: {result.tenant_id}")
        if result.created:
            for role in ROLES:
                print(f"{role}: demo-{role}@example.com / {password}")
        else:
            print("Existing demo logins and manual edits were preserved.")
        return 0
    except ValueError as error:
        print(str(error))
    except SQLAlchemyError:
        print("Demo seed failed; check connectivity and apply existing Alembic migrations first.")
    except Exception:
        print("Demo seed failed; transaction rolled back. Check local storage permissions.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
