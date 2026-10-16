"""Owner-approved OR gate, bounded providers and rewrite selection contracts."""

import json
from dataclasses import replace
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.chat import service
from app.chat.conversations import append_message, history_messages
from app.chat.providers import FakeChatModel, OpenAICompatibleModel, ProviderError
from app.chat.service import chat_answer, needs_rewrite
from app.db.models import Bot, Chunk, Conversation
from app.knowledge.storage import get_storage
from app.retrieval.gate import relevance_gate
from app.retrieval.hybrid import retrieve_hybrid
from app.retrieval.service import RetrievalResult, RetrievedChunk
from scripts.seed_demo import FAKE_PASSWORD, demo_id, seed_demo
from tests.conftest import build_test_settings


def chunk(**kwargs: Any) -> RetrievedChunk:
    base = RetrievedChunk(uuid4(), uuid4(), "Hours", None, "Open", "en", 0, 0, None, "1", 4, 0)
    return replace(base, **kwargs)


def test_gate_accepts_either_signal_and_ignores_rrf() -> None:
    vector = chunk(vector_similarity=0.50)
    keyword = chunk(fts_match=0.01, matched_terms=1)
    rejected = chunk(vector_similarity=0.49, fts_match=0.009, rrf_score=999)
    result = RetrievalResult(
        "ar", "en", True, evidence=[vector, keyword, rejected], embedding_model="ollama:bge-m3"
    )
    decision = relevance_gate(result, build_test_settings())
    assert decision.passed == [vector, keyword]
    assert decision.rejected_ids == [str(rejected.chunk_id)]


def test_uncalibrated_models_and_nonfinite_scores_fail_closed() -> None:
    result = RetrievalResult(
        "en",
        "en",
        False,
        evidence=[
            chunk(vector_similarity=1),
            chunk(fts_match=0.1, matched_terms=1),
            chunk(fts_match=float("nan")),
        ],
        embedding_model="unknown:uncalibrated",
    )
    decision = relevance_gate(result, build_test_settings())
    assert decision.vector_floor is None
    assert decision.passed == [result.evidence[1]]


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("and on weekends?", True),
        ("What about those?", True),
        ("What are your opening hours?", False),
        ("How much is cleaning?", False),
    ],
)
def test_self_contained_questions_skip_rewrite(question: str, expected: bool) -> None:
    assert needs_rewrite(question, ["previous question"]) is expected
    assert needs_rewrite(question, []) is False


@pytest.mark.parametrize("status", [401, 402, 403, 429])
def test_provider_quota_auth_stops_fallback_and_subsequent_calls(status: int) -> None:
    calls = []

    def response(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(status, json={"error": "private-upstream-details"})

    model = OpenAICompatibleModel(
        base_url="https://fixture.invalid/v1/",
        api_key="synthetic-key",
        model="one:free",
        fallback_models=["two:free", "three:free"],
        transport=httpx.MockTransport(response),
    )
    for _ in range(2):
        with pytest.raises(ProviderError) as caught:
            model.complete([], json_mode=False, max_tokens=120)
        assert "private-upstream" not in str(caught.value)
        assert "synthetic-key" not in str(caught.value)
    assert len(calls) == model.requests_used == 1


def test_provider_has_no_retries_and_only_one_fallback() -> None:
    calls = []

    def response(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert request.url.path == "/v1/chat/completions"
        return httpx.Response(503, json={})

    model = OpenAICompatibleModel(
        base_url="https://fixture.invalid/v1/",
        api_key="synthetic-key",
        model="one:free",
        fallback_models=["two:free", "three:free"],
        retries=4,
        transport=httpx.MockTransport(response),
    )
    with pytest.raises(ProviderError):
        model.complete([], json_mode=True, max_tokens=120)
    assert len(calls) == model.requests_used == 2


def test_failed_gate_never_calls_generation_and_returns_safe_handoff(monkeypatch: Any) -> None:
    evidence = chunk(vector_similarity=0.49, fts_match=0.009, rrf_score=999)
    result = RetrievalResult(
        "en", "en", False, evidence=[evidence], embedding_model="ollama:bge-m3"
    )
    monkeypatch.setattr(service, "retrieve", lambda *args, **kwargs: result)
    bot = Bot(id=uuid4(), tenant_id=uuid4(), published_revision_id=uuid4(), config={})
    model = FakeChatModel(responses=["MUST NOT CALL"])
    with Session() as db:
        reply = chat_answer(
            db,
            tenant_id=bot.tenant_id,
            bot=bot,
            question="opening hours",
            model=model,
            settings=build_test_settings(),
        )
    assert reply.answer.startswith("I don't have that information")
    assert reply.needs_human and not reply.can_answer and reply.kind == "cannot_confirm"
    assert "inbox" in reply.answer and model.calls == [] and reply.citations == []


def test_stage0_raw_fts_gate_measurements(db: Session, tmp_path: Path) -> None:
    settings = build_test_settings(storage_root=str(tmp_path / "storage"))
    seed = seed_demo(db, get_storage(settings), settings, FAKE_PASSWORD)
    bot = db.scalar(select(Bot).where(Bot.tenant_id == seed.tenant_id, Bot.id == seed.bot_id))
    assert bot is not None and bot.published_revision_id is not None
    cases_file = Path(__file__).parent / "fixtures" / "rag-phase2-eval.jsonl"
    cases = [json.loads(line) for line in cases_file.read_text().splitlines()]
    chunks = list(
        db.scalars(
            select(Chunk).where(
                Chunk.tenant_id == seed.tenant_id,
                Chunk.bot_id == seed.bot_id,
                Chunk.revision_id == bot.published_revision_id,
            )
        )
    )
    rows = []
    for case in cases:
        result = retrieve_hybrid(
            db,
            tenant_id=seed.tenant_id,
            bot_id=seed.bot_id,
            revision_id=bot.published_revision_id,
            question=case["question"],
            question_language=case["language"],
            settings=settings,
            mode_override="fts_only",
        )
        decision = relevance_gate(result, settings)
        source = case["expected_source"]
        expected = {
            str(item.id)
            for item in chunks
            if source and item.source_id == demo_id(f"source/{source}")
        }
        rows.append(
            {
                "id": case["id"],
                "type": case["type"],
                "unanswerable": source is None,
                "gate_passed": bool(decision.passed),
                "expected_hit": bool(expected & {str(item.chunk_id) for item in decision.passed}),
                "fts_scores": [item.fts_match for item in result.evidence],
                "generation_measured": False,
            }
        )
    assert len(rows) >= 30
    (tmp_path / "stage3-gate-results.json").write_text(json.dumps(rows, indent=2))


def test_rewrite_history_is_recent_prior_messages_only(db: Session, tmp_path: Path) -> None:
    settings = build_test_settings(storage_root=str(tmp_path), chat_num_history_messages=2)
    seed = seed_demo(db, get_storage(settings), settings, FAKE_PASSWORD)
    thread = Conversation(
        tenant_id=seed.tenant_id,
        bot_id=seed.bot_id,
        channel="website",
        mode="ai",
        status="open",
        source="playground",
    )
    db.add(thread)
    db.flush()
    current = None
    for index in range(8):
        current = append_message(db, thread, sender_type="visitor", text=str(index))
    assert current is not None
    assert history_messages(db, thread, settings=settings, exclude_message_id=current.id) == [
        "5",
        "6",
    ]


@pytest.mark.parametrize("identity", ["unknown:model", "", None])
def test_missing_model_row_never_passes_vector_or_empty_fts(identity: str | None) -> None:
    evidence = [
        chunk(vector_similarity=1),
        chunk(fts_match=0),
        chunk(fts_match=0.01, matched_terms=1),
    ]
    result = RetrievalResult("en", "en", False, evidence=evidence, embedding_model=identity)
    decision = relevance_gate(result, build_test_settings())
    assert decision.vector_floor is None and decision.passed == evidence[2:]


def test_openai_untuned_floor_and_min_matched_terms_keep_or_semantics() -> None:
    evidence = [
        chunk(vector_similarity=0.5),
        chunk(fts_match=0.1, matched_terms=1),
        chunk(fts_match=0.01, matched_terms=2),
    ]
    result = RetrievalResult(
        "en", "en", False, evidence=evidence, embedding_model="openai:text-embedding-3-large"
    )
    decision = relevance_gate(result, build_test_settings(retrieval_min_matched_terms=2))
    assert decision.passed == [evidence[0], evidence[2]]
