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

from app.chat.conversations import get_or_create_playground_conversation, visitor_chat_turn
from app.chat.providers import FakeChatModel, ProviderError
from app.core.config import get_settings
from app.core.errors import ApiError
from app.db.models import Bot, Document, Source, UsageEvent
from app.db.session import session_factory
from app.embeddings.providers import EmbeddingBatch, EmbeddingError
from app.quotas.ai import MeteredChatModel, metered_embed
from app.quotas.rag import monthly_usage, reserve, settle
from app.quotas.rag_contracts import RagLimits
from tests.conftest import build_test_settings
from tests.helpers import make_bot, seeded_tenant
from tests.knowledge_helpers import run_one_ingest_job, start_ingestion, upload_sources


def test_tier_targets_are_reported_from_the_api(app: FastAPI, db: Session) -> None:
    """A1.6: the GET response carries the provider/model each tier maps to so
    the UI shows real values instead of hard-coding them."""
    users = seeded_tenant(app, db, "tier-targets")
    settings = build_test_settings(
        chat_free_model_chain=["chain-one:free", "chain-two:free"],
        chat_openai_model="gpt-4.1-nano",
    )
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        bid = UUID(make_bot(users)["id"])
        path = f"/api/v1/tenants/{users.tenant_id}/bots/{bid}/rag"
        status = users.call("staff", "GET", path).json()
        assert status["tier_targets"] == {
            "standard": {"provider": "openrouter", "model": "chain-one:free"},
            "premium": {"provider": "openai", "model": "gpt-4.1-nano"},
        }
        # Tier switching itself is unchanged: same provider mapping.
        patched = users.call("staff", "PATCH", path, json={"tier": "premium"})
        assert patched.status_code == 200, patched.text
        assert patched.json()["generation_provider"] == "openai"
        assert patched.json()["generation_model"] is None
    finally:
        users.cleanup()


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


def _event_status(db: Session, tenant_id: UUID, bot_id: UUID) -> list[tuple[str, int]]:
    db.expire_all()
    rows = db.scalars(
        select(UsageEvent).where(
            UsageEvent.tenant_id == tenant_id,
            UsageEvent.bot_id == bot_id,
            UsageEvent.kind == "ai_usage",
        )
    ).all()
    return sorted((str(r.payload["status"]), int(r.payload["accounted_tokens"])) for r in rows)


def test_definite_provider_failures_release_reservations(app: FastAPI, db: Session) -> None:
    users = seeded_tenant(app, db, "rag-release")
    bid = UUID(make_bot(users)["id"])
    settings = build_test_settings()
    try:
        failing = MeteredChatModel(
            FakeChatModel(raises=True), db, users.tenant_id, bid, settings, "website"
        )
        with pytest.raises(ProviderError):
            failing.complete(
                [{"role": "user", "content": "question"}], json_mode=True, max_tokens=50
            )

        def unavailable(texts: list[str]) -> EmbeddingBatch:
            raise EmbeddingError("Embedding provider is unavailable.")

        with pytest.raises(EmbeddingError):
            metered_embed(
                db,
                users.tenant_id,
                bid,
                settings,
                identity="openai:text-embedding-3-large",
                texts=["question"],
                embed=unavailable,
                event_type="embed_query",
                channel="website",
            )
        assert _event_status(db, users.tenant_id, bid) == [("released", 0), ("released", 0)]
        usage = monthly_usage(db, users.tenant_id, bid)
        assert usage["monthly_tokens"] == 0 and usage["monthly_embedding_tokens"] == 0
    finally:
        users.cleanup()


def test_ambiguous_provider_failures_keep_the_conservative_hold(app: FastAPI, db: Session) -> None:
    users = seeded_tenant(app, db, "rag-ambiguous")
    bid = UUID(make_bot(users)["id"])
    settings = build_test_settings()
    try:

        def unprocessable(texts: list[str]) -> EmbeddingBatch:
            raise EmbeddingError("Embedding response could not be processed.", ambiguous=True)

        with pytest.raises(EmbeddingError):
            metered_embed(
                db,
                users.tenant_id,
                bid,
                settings,
                identity="openai:text-embedding-3-large",
                texts=["question"],
                embed=unprocessable,
                event_type="embed_query",
                channel="website",
            )
        ((status, held),) = _event_status(db, users.tenant_id, bid)
        assert status == "usage_unreported" and held > 0
        assert monthly_usage(db, users.tenant_id, bid)["monthly_embedding_tokens"] == held
    finally:
        users.cleanup()


def test_provider_outage_loop_does_not_exhaust_caps(app: FastAPI, db: Session) -> None:
    users = seeded_tenant(app, db, "rag-outage")
    bid = UUID(make_bot(users)["id"])
    bot = db.scalar(select(Bot).where(Bot.tenant_id == users.tenant_id, Bot.id == bid))
    assert bot is not None
    bot.rag_limits = {"monthly_tokens": 1000, "monthly_embedding_tokens": 1000}
    db.commit()
    settings = build_test_settings()
    try:

        def unavailable(texts: list[str]) -> EmbeddingBatch:
            raise EmbeddingError("Embedding provider is unavailable.")

        for _ in range(25):  # would exceed both caps if failures kept their holds
            with pytest.raises(EmbeddingError):
                metered_embed(
                    db,
                    users.tenant_id,
                    bid,
                    settings,
                    identity="openai:text-embedding-3-large",
                    texts=["question " * 20],
                    embed=unavailable,
                    event_type="embed_query",
                    channel="website",
                )
        assert monthly_usage(db, users.tenant_id, bid)["monthly_embedding_tokens"] == 0
    finally:
        users.cleanup()


class _Boom(FakeChatModel):
    def complete(self, messages: list[dict[str, str]], *, json_mode: bool, max_tokens: int) -> str:
        raise RuntimeError("unexpected failure inside the turn")


def test_aborted_turn_releases_the_message_reservation(app: FastAPI, db: Session) -> None:
    users = seeded_tenant(app, db, "rag-abort")
    bid = UUID(make_bot(users)["id"])
    bot = db.scalar(select(Bot).where(Bot.tenant_id == users.tenant_id, Bot.id == bid))
    assert bot is not None
    bot.rag_limits = {"monthly_messages": 1}
    db.commit()
    settings = build_test_settings()
    try:
        conversation = get_or_create_playground_conversation(
            db, tenant_id=users.tenant_id, bot_id=bid, user_id=UUID(users.users["staff"]["id"])
        )
        monkey_chat = pytest.MonkeyPatch()
        monkey_chat.setattr(
            "app.chat.conversations.chat_answer",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("aborted")),
        )
        try:
            with pytest.raises(RuntimeError):
                visitor_chat_turn(
                    db,
                    tenant_id=users.tenant_id,
                    bot=bot,
                    conversation=conversation,
                    question="Anything?",
                    model=_Boom(),
                    settings=settings,
                )
        finally:
            monkey_chat.undo()
        assert _event_status(db, users.tenant_id, bid) == [("released", 0)]
        assert monthly_usage(db, users.tenant_id, bid)["monthly_messages"] == 0
        # The single allowed message is still available after the failure.
        reply = visitor_chat_turn(
            db,
            tenant_id=users.tenant_id,
            bot=bot,
            conversation=conversation,
            question="Unsupported factual question?",
            model=FakeChatModel(),
            settings=settings,
        )
        assert reply["ai_message"] is not None
    finally:
        users.cleanup()


def test_http_failure_kinds_decide_release_or_hold(app: FastAPI, db: Session) -> None:
    import httpx

    from app.chat.providers import OpenAICompatibleModel

    users = seeded_tenant(app, db, "rag-http-kinds")
    bid = UUID(make_bot(users)["id"])
    settings = build_test_settings()

    def run(handler: object) -> None:
        inner = OpenAICompatibleModel(
            base_url="https://provider.invalid/v1",
            api_key="synthetic-key",
            model="fixture:free",
            transport=httpx.MockTransport(handler),  # type: ignore[arg-type]
        )
        wrapped = MeteredChatModel(inner, db, users.tenant_id, bid, settings, "website")
        with pytest.raises(ProviderError):
            wrapped.complete([{"role": "user", "content": "q"}], json_mode=True, max_tokens=50)

    def server_error(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    def connect_error(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    def read_timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    def empty_200(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": ""}}]})

    try:
        run(server_error)
        run(connect_error)
        assert _event_status(db, users.tenant_id, bid) == [("released", 0), ("released", 0)]
        run(read_timeout)
        run(empty_200)
        statuses = _event_status(db, users.tenant_id, bid)
        assert [s for s, _ in statuses].count("usage_unreported") == 2
        assert all(held > 0 for status, held in statuses if status == "usage_unreported")
    finally:
        users.cleanup()


def test_quota_details_are_hidden_from_public_visitors() -> None:
    from fastapi.testclient import TestClient

    from app.core.errors import install_error_handlers
    from app.quotas.rag import quota

    tiny = FastAPI()
    install_error_handlers(tiny)

    @tiny.get("/api/public/v1/x")
    def public() -> None:
        raise quota("monthly_tokens")

    @tiny.get("/api/v1/x")
    def staff() -> None:
        raise quota("monthly_tokens")

    client = TestClient(tiny)
    visitor = client.get("/api/public/v1/x").json()["error"]
    assert visitor["code"] == "QUOTA_EXCEEDED" and "details" not in visitor
    assert client.get("/api/v1/x").json()["error"]["details"] == {"counter": "monthly_tokens"}
