"""H1: embedding readiness is recorded per revision; ingest/backfill never degrade the
live published revision, backfill is batched and scoped to draft + published."""

import math
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from fastapi import FastAPI
from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session as OrmSession

import tests.knowledge_helpers as helpers
from app.core.config import Settings, get_settings
from app.db.models import Bot, Chunk, Job, KnowledgeRevision, UsageEvent
from app.embeddings import backfill
from app.embeddings.providers import EmbeddingBatch, EmbeddingError, TestHashEmbedder
from app.retrieval.hybrid import retrieve_hybrid
from tests.helpers import make_bot, seeded_tenant
from tests.knowledge_helpers import (
    MD_AR,
    MD_EN,
    drain_jobs,
    publish_draft,
    run_one_ingest_job,
    start_ingestion,
    upload_settings,
    upload_sources,
)

IDENTITY = "openai:text-embedding-3-large"


@pytest.fixture
def rooted_app(app: FastAPI, tmp_path: Path) -> FastAPI:
    app.dependency_overrides[get_settings] = lambda: upload_settings(tmp_path)
    return app


def _engine() -> Any:
    from app.db.session import get_engine

    return get_engine()


def _bot(db: OrmSession, users: Any, bot_id: str) -> Bot:
    db.expire_all()
    bot = db.scalar(select(Bot).where(Bot.tenant_id == users.tenant_id, Bot.id == UUID(bot_id)))
    assert bot is not None
    return bot


def _revision(db: OrmSession, users: Any, status: str) -> KnowledgeRevision:
    db.expire_all()
    revision = db.scalar(
        select(KnowledgeRevision).where(
            KnowledgeRevision.tenant_id == users.tenant_id, KnowledgeRevision.status == status
        )
    )
    assert revision is not None
    return revision


def _live(db: OrmSession, rooted_app: FastAPI, tmp_path: Path, name: str) -> tuple[Any, str]:
    """A bot with one published, fully embedded revision (MD_EN)."""
    users = seeded_tenant(rooted_app, db, prefix=name)
    bot_id = str(make_bot(users, name)["id"])
    upload_sources(users, bot_id, [("services.md", MD_EN.read_bytes())], tmp_path)
    start_ingestion(users, bot_id)
    drain_jobs(_engine(), tmp_path)
    publish_draft(users, bot_id)
    drain_jobs(_engine(), tmp_path)
    return users, bot_id


def _retrieve(db: OrmSession, users: Any, bot_id: str, tmp_path: Path) -> Any:
    bot = _bot(db, users, bot_id)
    assert bot.published_revision_id is not None
    return retrieve_hybrid(
        db,
        tenant_id=users.tenant_id,
        bot_id=bot.id,
        revision_id=bot.published_revision_id,
        question="services",
        question_language="en",
        settings=upload_settings(tmp_path),
    )


def _ingest_more(users: Any, bot_id: str, tmp_path: Path) -> None:
    """Run ONLY the ingest job for a second file; its backfill stays queued."""
    upload_sources(users, bot_id, [("faq-ar.md", MD_AR.read_bytes())], tmp_path)
    start_ingestion(users, bot_id)
    run_one_ingest_job(_engine(), tmp_path)


def test_ingest_while_live_keeps_published_hybrid_and_reports_progress(
    rooted_app: FastAPI, db: OrmSession, tmp_path: Path
) -> None:
    users, bot_id = _live(db, rooted_app, tmp_path, "h1-live")
    assert _revision(db, users, "published").embedding_model == IDENTITY
    assert _retrieve(db, users, bot_id, tmp_path).mode == "hybrid"

    _ingest_more(users, bot_id, tmp_path)
    bot = _bot(db, users, bot_id)
    assert bot.embedding_ready is True
    assert _revision(db, users, "published").embedding_model == IDENTITY
    assert _revision(db, users, "draft").embedding_model is None
    pending = db.scalar(
        select(func.count()).select_from(Job).where(Job.type == "reembed_backfill")
    )
    assert pending == 2  # the first one succeeded; the successor is queued
    live = _retrieve(db, users, bot_id, tmp_path)
    assert live.mode == "hybrid" and live.degradation_reason is None

    base = f"/api/v1/tenants/{users.tenant_id}/bots/{bot_id}/revisions"
    rows = {row["status"]: row for row in users.call("staff", "GET", base).json()["revisions"]}
    assert rows["published"]["embedding"]["retrieval_mode"] == "hybrid"
    assert rows["published"]["embedding"]["ready"] is True
    draft = rows["draft"]["embedding"]
    assert draft["retrieval_mode"] == "keyword_only" and draft["ready"] is False
    assert draft["embedded_chunks"] < draft["chunk_count"]

    drain_jobs(_engine(), tmp_path)
    draft = {r["status"]: r for r in users.call("staff", "GET", base).json()["revisions"]}["draft"]
    assert draft["embedding"]["ready"] is True
    assert draft["embedding"]["embedded_chunks"] == draft["embedding"]["chunk_count"]


def test_failed_backfill_keeps_live_hybrid(
    rooted_app: FastAPI, db: OrmSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    users, bot_id = _live(db, rooted_app, tmp_path, "h1-fail")
    _ingest_more(users, bot_id, tmp_path)

    class Broken(TestHashEmbedder):
        def embed(self, texts: list[str]) -> EmbeddingBatch:
            raise EmbeddingError("synthetic provider outage")

    monkeypatch.setattr(backfill, "from_settings", lambda settings, identity: Broken(identity))
    run_one_ingest_job(_engine(), tmp_path)
    assert _revision(db, users, "published").embedding_model == IDENTITY
    assert _revision(db, users, "draft").embedding_model is None
    assert _bot(db, users, bot_id).embedding_ready is True
    assert _retrieve(db, users, bot_id, tmp_path).mode == "hybrid"


def test_queue_backfill_error_after_ingest_is_a_job_warning(
    rooted_app: FastAPI, db: OrmSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    users = seeded_tenant(rooted_app, db, prefix="h1-warn")
    bot_id = str(make_bot(users, "warn")["id"])
    upload_sources(users, bot_id, [("services.md", MD_EN.read_bytes())], tmp_path)
    start_ingestion(users, bot_id)

    def boom(*args: Any, **kwargs: Any) -> Any:
        raise EmbeddingError("An embedding model must be explicitly configured.")

    monkeypatch.setattr("app.embeddings.backfill.queue_backfill", boom)
    job = run_one_ingest_job(_engine(), tmp_path)
    db.expire_all()
    stored = db.get(Job, job.id)
    assert stored is not None and stored.status == "succeeded"
    assert stored.payload["warnings"] and "Embedding not queued" in stored.payload["warnings"][0]


def test_backfill_skips_archived_and_rollback_embeds_on_demand(
    rooted_app: FastAPI, db: OrmSession, tmp_path: Path
) -> None:
    users, bot_id = _live(db, rooted_app, tmp_path, "h1-roll")
    first = _revision(db, users, "published")
    first_id = first.id
    _ingest_more(users, bot_id, tmp_path)
    drain_jobs(_engine(), tmp_path)
    publish_draft(users, bot_id)
    drain_jobs(_engine(), tmp_path)
    assert _revision(db, users, "published").id != first_id
    assert _bot(db, users, bot_id).embedding_ready is True

    # Make the archived revision stale; a backfill must leave it alone.
    db.execute(
        update(Chunk).where(Chunk.revision_id == first_id).values(
            embedding=None, embedding_model=None, embedding_dim=None
        )
    )
    db.execute(
        update(KnowledgeRevision).where(KnowledgeRevision.id == first_id).values(embedding_model=None)
    )
    db.commit()
    backfill_job = None
    with db.begin_nested():
        backfill_job = backfill.queue_backfill(
            db, users.tenant_id, UUID(bot_id), upload_settings(tmp_path)
        )
    db.commit()
    assert backfill_job is not None
    drain_jobs(_engine(), tmp_path)
    db.expire_all()
    still_pending = db.scalar(
        select(func.count()).select_from(Chunk).where(
            Chunk.revision_id == first_id, Chunk.embedding.is_(None)
        )
    )
    assert still_pending and still_pending > 0

    base = f"/api/v1/tenants/{users.tenant_id}/bots/{bot_id}/revisions"
    rollback = users.call("staff", "POST", f"{base}/{first_id}/publish")
    assert rollback.status_code == 200, rollback.text
    assert rollback.json()["retrieval_mode"] == "keyword_only"
    assert _bot(db, users, bot_id).embedding_ready is False
    served = _retrieve(db, users, bot_id, tmp_path)
    assert served.mode == "fts_only" and served.evidence  # FTS serves meanwhile
    drain_jobs(_engine(), tmp_path)
    assert _revision(db, users, "published").id == first_id
    assert _bot(db, users, bot_id).embedding_ready is True
    assert _retrieve(db, users, bot_id, tmp_path).mode == "hybrid"


def test_batching_checkpoint_resume_and_metering(
    rooted_app: FastAPI, db: OrmSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = upload_settings

    def small_batches(root: Path) -> Settings:
        settings = original(root)
        settings.embedding_batch_size = 2
        return settings

    monkeypatch.setattr(helpers, "upload_settings", small_batches)
    monkeypatch.setattr("tests.test_embedding_readiness.upload_settings", small_batches)
    calls: list[int] = []
    fail_on = {"call": 2}

    class Counting(TestHashEmbedder):
        def embed(self, texts: list[str]) -> EmbeddingBatch:
            calls.append(len(texts))
            if len(calls) == fail_on["call"]:
                raise EmbeddingError("synthetic outage on one batch")
            return super().embed(texts)

    monkeypatch.setattr(backfill, "from_settings", lambda settings, identity: Counting(identity))
    users = seeded_tenant(rooted_app, db, prefix="h1-batch")
    bot_id = str(make_bot(users, "batch")["id"])
    upload_sources(users, bot_id, [("a.md", MD_EN.read_bytes()), ("b.md", MD_AR.read_bytes())], tmp_path)
    start_ingestion(users, bot_id)
    run_one_ingest_job(_engine(), tmp_path)  # ingest
    run_one_ingest_job(_engine(), tmp_path)  # backfill: batch 2 fails
    db.expire_all()
    total = db.scalar(select(func.count()).select_from(Chunk).where(Chunk.tenant_id == users.tenant_id))
    embedded = db.scalar(
        select(func.count()).select_from(Chunk).where(
            Chunk.tenant_id == users.tenant_id, Chunk.embedding.is_not(None)
        )
    )
    assert total and total > 4
    assert embedded == 2  # the first batch is checkpointed; the failed one is not lost work
    assert all(size <= 2 for size in calls)
    assert _revision(db, users, "draft").embedding_model is None

    fail_on["call"] = -1
    db.execute(text("UPDATE jobs SET run_at = NOW() - INTERVAL '1 day' WHERE status = 'pending'"))
    db.commit()
    drain_jobs(_engine(), tmp_path)
    db.expire_all()
    assert _revision(db, users, "draft").embedding_model == IDENTITY
    # 1 + 1 (failed) + ceil(remaining / 2) provider calls; one metering event per call.
    assert sum(calls) == total + 2  # the failed batch's texts were re-sent once
    events = db.scalar(
        select(func.count()).select_from(UsageEvent).where(
            UsageEvent.tenant_id == users.tenant_id,
            UsageEvent.payload["event_type"].as_string() == "embed_ingest",
        )
    )
    assert events == len(calls) - 1 or events == len(calls)
    assert len(calls) == 2 + math.ceil((total - 2) / 2)


def test_other_tenant_cannot_see_embedding_state(
    rooted_app: FastAPI, db: OrmSession, tmp_path: Path
) -> None:
    users_a, bot_a = _live(db, rooted_app, tmp_path, "h1-ta")
    users_b = seeded_tenant(rooted_app, db, prefix="h1-tb")
    base = f"/api/v1/tenants/{users_b.tenant_id}/bots/{bot_a}/revisions"
    assert users_b.call("staff", "GET", base).status_code == 404
    assert users_a.call(
        "staff", "GET", f"/api/v1/tenants/{users_a.tenant_id}/bots/{bot_a}/revisions"
    ).status_code == 200
