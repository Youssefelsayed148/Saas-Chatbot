"""Private trace persistence, citation boundary and mocked per-bot providers."""

import json
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.chat import service
from app.chat.conversations import get_or_create_playground_conversation, visitor_chat_turn
from app.chat.models import model_from_settings
from app.chat.providers import FakeChatModel, OpenAICompatibleModel
from app.chat.service import chat_answer
from app.db.models import Bot, UsageEvent
from app.knowledge.storage import get_storage
from app.retrieval.service import RetrievalResult, RetrievedChunk
from scripts.seed_demo import FAKE_PASSWORD, seed_demo
from tests.conftest import build_test_settings
from tests.helpers import make_bot, seeded_tenant


def test_premium_and_standard_provider_contracts_are_mocked() -> None:
    settings = build_test_settings(
        chat_openai_api_key=SecretStr("synthetic-openai"),
        chat_openrouter_api_key=SecretStr("synthetic-router"),
        chat_free_model_chain=["fixture:free"],
        chat_openai_model="configured-premium",
    )
    bot = Bot(generation_provider="openai", generation_model="premium-override")
    model = model_from_settings(settings, bot)
    assert isinstance(model, OpenAICompatibleModel) and model.free_only is False
    calls = []

    def response(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert json.loads(request.content)["model"] == "premium-override"
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "fixture answer"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 3, "total_tokens": 13},
            },
        )

    model.transport = httpx.MockTransport(response)
    assert model.complete([], json_mode=True, max_tokens=120) == "fixture answer"
    assert len(calls) == 1 and model.usage_totals == {
        "prompt_tokens": 10,
        "completion_tokens": 3,
        "total_tokens": 13,
    }
    bot.generation_provider, bot.generation_model = "openrouter", None
    standard = model_from_settings(settings, bot)
    assert isinstance(standard, OpenAICompatibleModel) and standard.free_only
    assert standard.model == "fixture:free"


def test_sample_traces_and_postcheck_hook(db: Session, tmp_path: Path, monkeypatch: Any) -> None:
    settings = build_test_settings(storage_root=str(tmp_path))
    seed = seed_demo(db, get_storage(settings), settings, FAKE_PASSWORD)
    bot = db.scalar(select(Bot).where(Bot.tenant_id == seed.tenant_id, Bot.id == seed.bot_id))
    assert bot is not None
    evidence = RetrievedChunk(
        uuid4(),
        uuid4(),
        "Hours",
        None,
        "Open 09 to 17",
        "en",
        0,
        0,
        None,
        "Section 1",
        13,
        0,
        vector_similarity=0.8,
    )
    retrieved = RetrievalResult(
        "en",
        "en",
        False,
        evidence=[evidence],
        candidates=[evidence],
        mode="hybrid",
        embedding_model="ollama:bge-m3",
    )
    monkeypatch.setattr(service, "retrieve", lambda *args, **kwargs: retrieved)
    generated = json.dumps(
        {
            "answer": "Open 09 to 17",
            "can_answer": True,
            "sources": [str(evidence.chunk_id), "foreign-citation"],
        }
    )
    samples = []
    for question, history in [("Opening hours?", []), ("and on weekdays?", ["Hours?"])]:
        model = FakeChatModel(responses=["opening hours", generated] if history else [generated])
        reply = chat_answer(
            db,
            tenant_id=seed.tenant_id,
            bot=bot,
            question=question,
            history=history,
            model=model,
            settings=settings,
        )
        assert reply.can_answer and len(reply.citations) == 1
        assert reply.trace["gate"] == "passed" and reply.trace["rewrite_used"] == bool(history)
        samples.append(reply.trace)
    rejected = chat_answer(
        db,
        tenant_id=seed.tenant_id,
        bot=bot,
        question="Opening hours?",
        model=FakeChatModel(responses=[generated]),
        settings=settings,
        post_check=lambda answer, chunks: False,
    )
    assert rejected.kind == "invalid_output" and rejected.trace["post_check"] == "rejected"
    retrieved.evidence = []
    refusal_model = FakeChatModel()
    refusal = chat_answer(
        db,
        tenant_id=seed.tenant_id,
        bot=bot,
        question="Unsupported price?",
        model=refusal_model,
        settings=settings,
    )
    assert refusal.trace["gate"] == "refused" and refusal_model.calls == []
    samples.insert(1, refusal.trace)
    (tmp_path / "sample-traces.json").write_text(json.dumps(samples, indent=2))


def test_trace_storage_route_is_staff_only_and_tenant_bot_scoped(app: FastAPI, db: Session) -> None:
    users = seeded_tenant(app, db, "trace-main")
    foreign = seeded_tenant(app, db, "trace-foreign")
    try:
        bot_id = make_bot(users, "Trace")["id"]
        bot = db.scalar(select(Bot).where(Bot.tenant_id == users.tenant_id, Bot.id == bot_id))
        assert bot is not None
        conversation = get_or_create_playground_conversation(
            db,
            tenant_id=users.tenant_id,
            bot_id=bot.id,
            user_id=UUID(users.users["staff"]["id"]),
        )
        result = visitor_chat_turn(
            db,
            tenant_id=users.tenant_id,
            bot=bot,
            conversation=conversation,
            question="Unsupported factual question?",
            model=FakeChatModel(),
            settings=build_test_settings(),
        )
        path = f"/api/v1/tenants/{users.tenant_id}/bots/{bot.id}/rag/traces"
        for role in ("admin", "editor", "viewer"):
            assert users.call(role, "GET", path).status_code == 403
        traces = users.call("staff", "GET", path)
        assert traces.status_code == 200 and len(traces.json()["traces"]) == 1
        trace = traces.json()["traces"][0]
        assert trace["message_id"] == result["ai_message"]["id"]
        assert trace["trace"]["channel"] == "website" and trace["trace"]["gate"] == "refused"
        assert "rag_trace" not in json.dumps(result)
        other_bot = make_bot(users, "Other")["id"]
        assert users.call("staff", "GET", path.replace(str(bot.id), str(other_bot))).json() == {
            "traces": []
        }
        other_tenant_bot = make_bot(foreign, "Foreign")["id"]
        assert (
            users.call("staff", "GET", path.replace(str(bot.id), str(other_tenant_bot))).status_code
            == 404
        )
        row = db.scalar(
            select(UsageEvent).where(
                UsageEvent.tenant_id == users.tenant_id,
                UsageEvent.bot_id == bot.id,
                UsageEvent.kind == "message",
            )
        )
        assert row is not None
        stored = row.payload["rag_trace"]
        assert isinstance(stored, dict) and stored["gate"] == "refused"
    finally:
        users.cleanup()
        foreign.cleanup()
