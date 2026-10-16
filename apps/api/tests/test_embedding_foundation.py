"""RAG embedding contracts and a real killed-worker/resumed-backfill test."""

import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import Engine, func, select, text, update
from sqlalchemy.orm import Session

from app.core.config import Settings, validate_startup_settings
from app.db.models import Bot, Chunk, Job
from app.db.session import session_factory
from app.embeddings.backfill import queue_backfill
from app.embeddings.providers import DIMENSION, EmbeddingError, HTTPEmbedder, validate_vector
from app.jobs.queue import claim_job
from app.jobs.runner import execute_claimed_job
from app.knowledge.storage import get_storage
from scripts.seed_demo import FAKE_PASSWORD, seed_demo
from tests.conftest import build_test_settings
from tests.helpers import make_bot, seeded_tenant


@pytest.mark.parametrize("provider", ["ollama", "openai", "openrouter"])
def test_embedding_http_contract_is_mocked(provider: str) -> None:
    vector = [1.0] + [0.0] * (DIMENSION - 1)
    calls = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        body = json.loads(request.content)
        assert body["input"] == ["English and العربية"]
        if provider == "ollama":
            assert request.url.path == "/api/embed"
            assert body["truncate"] is False
            return httpx.Response(200, json={"embeddings": [vector], "prompt_eval_count": 4})
        assert request.url.path == "/v1/embeddings"
        assert body["dimensions"] == 1024
        assert body["encoding_format"] == "float"
        return httpx.Response(
            200, json={"data": [{"index": 0, "embedding": vector}], "usage": {"total_tokens": 4}}
        )

    provider_model = "bge-m3" if provider == "ollama" else "text-embedding-3-large"
    embedder = HTTPEmbedder(
        identity=f"{provider}:{provider_model}",
        base_url="https://fixture.invalid" + ("" if provider == "ollama" else "/v1"),
        api_key="synthetic-key",
        transport=httpx.MockTransport(respond),
    )
    result = embedder.embed(["English and العربية"])
    assert result.vectors == [vector]
    assert result.tokens == 4
    assert len(calls) == 1


@pytest.mark.parametrize("vector", [[0.0] * 1024, [1.0] * 1023, [float("nan")] * 1024])
def test_embedding_rejects_wrong_dimension_zero_and_nonfinite(vector: list[float]) -> None:
    with pytest.raises(EmbeddingError):
        validate_vector(vector)


def test_embedding_failure_has_no_retry_or_provider_body() -> None:
    calls = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(429, json={"error": "sensitive-upstream-diagnostic"})

    embedder = HTTPEmbedder(
        identity="openai:text-embedding-3-large",
        base_url="https://fixture.invalid/v1",
        api_key="synthetic-key",
        transport=httpx.MockTransport(respond),
    )
    with pytest.raises(EmbeddingError) as caught:
        embedder.embed(["hello"])
    assert "sensitive" not in str(caught.value)
    assert "synthetic-key" not in str(caught.value)
    assert len(calls) == 1


def test_embedding_test_vectors_cannot_be_used_in_production() -> None:
    settings = Settings.model_construct(environment="production", embedding_test_stub=True)
    with pytest.raises(RuntimeError, match="test environment"):
        validate_startup_settings(settings)


def test_backfill_worker_kill_resume_and_atomic_flip(
    engine: Engine, db: Session, tmp_path: Path
) -> None:
    settings = build_test_settings(storage_root=str(tmp_path))
    seed = seed_demo(db, get_storage(settings), settings, FAKE_PASSWORD)
    bot = db.scalar(select(Bot).where(Bot.tenant_id == seed.tenant_id, Bot.id == seed.bot_id))
    assert bot is not None
    bot.active_embedding_model = "ollama:old-model"
    db.flush()
    job = queue_backfill(db, seed.tenant_id, seed.bot_id, settings)
    assert queue_backfill(db, seed.tenant_id, seed.bot_id, settings).id == job.id
    db.commit()
    child_environment = {
        **os.environ,
        "ENVIRONMENT": "test",
        "DATABASE_URL": engine.url.render_as_string(hide_password=False),
    }
    child_code = """
import time
from app.core.config import Settings
from app.db.session import create_db_engine, session_factory
from app.embeddings import backfill
from app.embeddings.providers import TestHashEmbedder
from app.jobs.queue import claim_job
from app.jobs.runner import execute_claimed_job
from app.knowledge.storage import get_storage
class Slow(TestHashEmbedder):
    def embed(self, texts):
        time.sleep(0.5)
        return super().embed(texts)
backfill.from_settings = lambda settings, identity: Slow(identity)
s = Settings(_env_file=None, embedding_test_stub=True, storage_root='/tmp/rag-kill-storage')
e = create_db_engine(s)
with session_factory(e)() as db:
    job = claim_job(db, 'killed-worker', s)
    execute_claimed_job(db, job, s, get_storage(s))
"""
    process = subprocess.Popen(
        [sys.executable, "-c", child_code],
        env=child_environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 15
        done = 0
        while time.monotonic() < deadline:
            with engine.connect() as connection:
                done = int(
                    connection.execute(
                        select(func.count())
                        .select_from(Chunk)
                        .where(
                            Chunk.tenant_id == seed.tenant_id,
                            Chunk.bot_id == seed.bot_id,
                            Chunk.embedding_model == "ollama:bge-m3",
                        )
                    ).scalar_one()
                )
            if done >= 1:
                break
            assert process.poll() is None, "worker exited before checkpoint"
            time.sleep(0.02)
        assert 0 < done < 4
        process.kill()
        process.wait(timeout=5)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
    db.expire_all()
    assert bot.active_embedding_model == "ollama:old-model"
    assert bot.embedding_ready is False
    checkpoint = dict(job.payload)
    assert isinstance(checkpoint["done"], int)
    assert 0 < checkpoint["done"] < 4
    job.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()
    resumed = claim_job(db, "resumed-worker", settings)
    assert resumed is not None and resumed.id == job.id
    execute_claimed_job(db, resumed, settings, get_storage(settings))
    db.expire_all()
    assert job.status == "succeeded"
    assert job.payload["done"] == job.payload["total"] == 4
    assert job.payload["failed"] == 0
    assert bot.active_embedding_model == "ollama:bge-m3"
    assert bot.embedding_ready is True
    chunks = list(
        db.scalars(
            select(Chunk).where(Chunk.tenant_id == seed.tenant_id, Chunk.bot_id == seed.bot_id)
        )
    )
    assert len(chunks) == 4
    assert all(chunk.embedding_dim == 1024 for chunk in chunks)
    assert db.execute(
        text("SELECT extversion FROM pg_extension WHERE extname='vector'")
    ).scalar_one()


def test_stale_worker_cannot_release_a_replacement_lease(
    engine: Engine, db: Session, tmp_path: Path
) -> None:
    settings = build_test_settings(storage_root=str(tmp_path))
    seed = seed_demo(db, get_storage(settings), settings, FAKE_PASSWORD)
    queued = queue_backfill(db, seed.tenant_id, seed.bot_id, settings)
    db.commit()
    with session_factory(engine)() as worker:
        old = claim_job(worker, "old-worker", settings)
        assert old is not None
        db.execute(
            update(Job)
            .where(
                Job.tenant_id == seed.tenant_id,
                Job.bot_id == seed.bot_id,
                Job.id == queued.id,
            )
            .values(leased_by="replacement-worker")
        )
        db.commit()
        execute_claimed_job(worker, old, settings, get_storage(settings))
    db.expire_all()
    assert queued.status == "running"
    assert queued.leased_by == "replacement-worker"
    assert queued.attempts == 1


def test_rag_controls_are_staff_only_and_client_navigation_is_redacted(
    app: FastAPI, db: Session
) -> None:
    users = seeded_tenant(app, db, "rag-controls")
    foreign = seeded_tenant(app, db, "rag-foreign")
    try:
        bot = make_bot(users, "Controlled")
        foreign_bot = make_bot(foreign, "Foreign")
        path = f"/api/v1/tenants/{users.tenant_id}/bots/{bot['id']}/rag"
        for role in ("admin", "editor", "viewer"):
            assert users.call(role, "GET", path).status_code == 403
            assert (
                users.call(role, "PATCH", path, json={"retrieval_mode": "fts_only"}).status_code
                == 403
            )
            assert users.call(role, "POST", path + "/backfill", json={}).status_code == 403
            navigation = users.call(role, "GET", path.removesuffix("/rag")).json()
            assert navigation["config"] == {} and navigation["widget_locator"] is None
            assert "active_embedding_model" not in navigation
            assert "generation_provider" not in navigation
        changed = users.call(
            "staff", "PATCH", path, json={"retrieval_mode": "fts_only", "tier": "premium"}
        )
        assert changed.status_code == 200
        assert changed.json()["retrieval_mode"] == "fts_only"
        assert changed.json()["generation_provider"] == "openai"
        hidden = path.replace(str(bot["id"]), str(foreign_bot["id"]))
        assert users.call("staff", "GET", hidden).status_code == 404
    finally:
        users.cleanup()
        foreign.cleanup()
