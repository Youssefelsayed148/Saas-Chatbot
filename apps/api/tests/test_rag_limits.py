"""RAG quotas, privacy and reservation races use disposable data and fake providers."""

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
from threading import Barrier
from uuid import UUID

import pytest
from fastapi import FastAPI
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.chat.providers import FakeChatModel
from app.core.config import get_settings
from app.core.errors import ApiError
from app.db.models import Bot, Document, Source, UsageEvent
from app.db.session import session_factory
from app.embeddings.providers import EmbeddingBatch
from app.quotas.ai import MeteredChatModel, metered_embed
from app.quotas.rag import monthly_usage, reserve, settle
from app.quotas.rag_contracts import RagLimits
from tests.conftest import build_test_settings
from tests.helpers import make_bot, seeded_tenant
from tests.knowledge_helpers import run_one_ingest_job, start_ingestion, upload_sources


def test_limits_are_optional_inherited_and_staff_only(app: FastAPI, db: Session) -> None:
    users = seeded_tenant(app, db, "rag-limits")
    other = seeded_tenant(app, db, "rag-limits-other")
    settings = build_test_settings(rag_plan_limits={"business": RagLimits(monthly_tokens=1000)})
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        bid = UUID(make_bot(users)["id"])
        path = f"/api/v1/tenants/{users.tenant_id}/bots/{bid}/rag"
        initial = users.call("staff", "GET", path).json()
        assert initial["effective_limits"]["monthly_tokens"] == 1000
        assert initial["effective_limits"]["storage_bytes"] is None
        changed = users.call(
            "staff", "PATCH", path, json={"limits": {"monthly_tokens": None, "storage_bytes": 0}}
        )
        assert changed.status_code == 200
        assert changed.json()["effective_limits"]["monthly_tokens"] is None
        assert changed.json()["effective_limits"]["storage_bytes"] == 0
        assert (
            users.call("staff", "PATCH", path, json={"limits": {"storage_bytes": -1}}).status_code
            == 422
        )
        for role in ("admin", "editor", "viewer"):
            assert users.call(role, "GET", path + "/costs").status_code == 403
            assert users.call(role, "PATCH", path, json={"limits": {}}).status_code == 403
        foreign_bid = make_bot(other)["id"]
        assert (
            users.call("staff", "GET", path.replace(str(bid), foreign_bid) + "/costs").status_code
            == 404
        )
        blocked = upload_sources(users, bid, [("tiny.txt", b"content")], Path("/tmp"))
        assert blocked.status_code == 429 and blocked.json()["error"]["code"] == "QUOTA_EXCEEDED"
        assert "Contact us" in blocked.json()["error"]["message"]
    finally:
        users.cleanup()
        other.cleanup()


@pytest.mark.parametrize("counter", ["documents", "chunks"])
def test_ingestion_caps_fail_before_writing_documents(
    app: FastAPI, db: Session, engine: Engine, tmp_path: Path, counter: str
) -> None:
    users = seeded_tenant(app, db, "rag-ingest-" + counter)
    settings = build_test_settings(storage_root=str(tmp_path))
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        bid = UUID(make_bot(users)["id"])
        bot = db.scalar(select(Bot).where(Bot.tenant_id == users.tenant_id, Bot.id == bid))
        assert bot is not None
        bot.rag_limits = {counter: 0}
        db.commit()
        assert (
            upload_sources(
                users, bid, [("doc.txt", b"Useful source content.")], tmp_path
            ).status_code
            == 201
        )
        assert start_ingestion(users, bid).status_code == 202
        run_one_ingest_job(engine, tmp_path)
        db.expire_all()
        source = db.scalar(
            select(Source).where(Source.tenant_id == users.tenant_id, Source.bot_id == bid)
        )
        assert source is not None and source.status == "failed"
        assert source.error is not None and "QUOTA_EXCEEDED" in source.error
        assert (
            db.scalar(
                select(func.count())
                .select_from(Document)
                .where(Document.tenant_id == users.tenant_id, Document.bot_id == bid)
            )
            == 0
        )
    finally:
        users.cleanup()


def test_reservations_are_serialized_and_unknown_usage_keeps_budget(
    app: FastAPI, db: Session, engine: Engine
) -> None:
    users = seeded_tenant(app, db, "rag-race")
    settings = build_test_settings()
    bid = UUID(make_bot(users)["id"])
    bot = db.scalar(select(Bot).where(Bot.tenant_id == users.tenant_id, Bot.id == bid))
    assert bot is not None
    bot.rag_limits = {"monthly_tokens": 100}
    db.commit()
    barrier = Barrier(2)

    def request() -> str:
        with session_factory(engine)() as worker:
            barrier.wait(timeout=5)
            try:
                reserve(
                    worker,
                    users.tenant_id,
                    bid,
                    settings,
                    event_type="generation",
                    model="mock",
                    channel="website",
                    token_bound=60,
                )
                return "reserved"
            except ApiError as error:
                worker.rollback()
                return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: request(), range(2)))
    assert sorted(outcomes) == ["QUOTA_EXCEEDED", "reserved"]
    assert monthly_usage(db, users.tenant_id, bid)["monthly_tokens"] == 60
    event = db.scalar(
        select(UsageEvent).where(
            UsageEvent.tenant_id == users.tenant_id,
            UsageEvent.bot_id == bid,
            UsageEvent.kind == "ai_usage",
        )
    )
    assert event is not None
    settle(db, users.tenant_id, bid, event.id, settings, tokens=None, cost_usd=None)
    assert monthly_usage(db, users.tenant_id, bid)["monthly_tokens"] == 60
    settle(db, users.tenant_id, bid, event.id, settings, tokens=0, cost_usd=Decimal(0))
    assert (
        monthly_usage(db, users.tenant_id, bid)["monthly_tokens"] == 60
    )  # settlement cannot release twice
    users.cleanup()


@pytest.mark.parametrize(
    "counter,event_type,kwargs",
    [
        ("monthly_messages", "message", {}),
        ("monthly_embedding_tokens", "embed_query", {"token_bound": 1}),
        ("monthly_ocr_pages", "ocr", {"ocr_pages": 1}),
    ],
)
def test_zero_caps_block_new_work(
    app: FastAPI, db: Session, counter: str, event_type: str, kwargs: dict[str, int]
) -> None:
    users = seeded_tenant(app, db, "rag-zero-" + counter)
    bid = UUID(make_bot(users)["id"])
    bot = db.scalar(select(Bot).where(Bot.tenant_id == users.tenant_id, Bot.id == bid))
    assert bot is not None
    bot.rag_limits = {counter: 0}
    db.commit()
    with pytest.raises(ApiError) as caught:
        reserve(
            db,
            users.tenant_id,
            bid,
            build_test_settings(),
            event_type=event_type,
            model="mock",
            channel="website",
            **kwargs,
        )
    assert caught.value.code == "QUOTA_EXCEEDED"
    db.rollback()
    users.cleanup()


def test_measured_events_cost_view_and_exports_are_private(app: FastAPI, db: Session) -> None:
    users = seeded_tenant(app, db, "rag-meter")
    bid = UUID(make_bot(users)["id"])
    settings = build_test_settings()

    class Model(FakeChatModel):
        model = "fixture:free"
        free_only = True
        last_cost_usd = Decimal("0.1")

        def complete(
            self, messages: list[dict[str, str]], *, json_mode: bool, max_tokens: int
        ) -> str:
            self.usage_totals = {"total_tokens": 12}
            return "fixture"

    wrapped = MeteredChatModel(Model(), db, users.tenant_id, bid, settings, "website")
    assert (
        wrapped.complete([{"role": "user", "content": "question"}], json_mode=True, max_tokens=50)
        == "fixture"
    )
    batch = metered_embed(
        db,
        users.tenant_id,
        bid,
        settings,
        identity="ollama:bge-m3",
        texts=["fixture"],
        embed=lambda texts: EmbeddingBatch([[1.0] + [0.0] * 1023], tokens=4, cost_usd=Decimal(0)),
        event_type="embed_ingest",
        channel="ingestion",
    )
    assert batch.tokens == 4 and monthly_usage(db, users.tenant_id, bid)["monthly_tokens"] == 16
    path = f"/api/v1/tenants/{users.tenant_id}/bots/{bid}/rag/costs"
    costs = users.call("staff", "GET", path)
    assert costs.status_code == 200
    assert {row["channel"] for row in costs.json()["costs"]} == {"website", "ingestion"}
    assert (
        next(row for row in costs.json()["costs"] if row["channel"] == "website")["cost_usd"]
        == "0.1"
    )
    exported = users.call("admin", "GET", f"/api/v1/tenants/{users.tenant_id}/data/export").json()
    assert all(row["kind"] != "ai_usage" for row in exported["usage_events"])
    assert "reserved_tokens" not in str(exported)
    users.cleanup()
