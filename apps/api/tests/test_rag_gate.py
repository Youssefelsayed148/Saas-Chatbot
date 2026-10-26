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
from app.chat.conversations import append_message
from app.chat.history import history_for_turn
from app.chat.providers import FakeChatModel, OpenAICompatibleModel, ProviderError
from app.chat.service import chat_answer, needs_rewrite
from app.db.models import Bot, Chunk, Conversation
from app.knowledge.storage import get_storage
from app.retrieval.gate import relevance_gate, select_evidence
from app.retrieval.hybrid import retrieve_hybrid
from app.retrieval.service import RetrievalResult, RetrievedChunk
from scripts.seed_demo import FAKE_PASSWORD, demo_id, seed_demo
from tests.conftest import build_test_settings


def chunk(**kwargs: Any) -> RetrievedChunk:
    base = RetrievedChunk(uuid4(), uuid4(), "Hours", None, "Open", "en", 0, 0, None, "1", 4, 0)
    return replace(base, **kwargs)


def test_gate_accepts_either_signal_and_ignores_rrf() -> None:
    vector = chunk(vector_similarity=0.50)
    keyword = chunk(fts_match=0.01, matched_terms=1, query_terms=1)
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
            chunk(fts_match=0.1, matched_terms=1, query_terms=1),
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


@pytest.mark.parametrize("status", [401, 402])
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


def test_provider_has_no_retries_and_walks_the_fallback_chain_once() -> None:
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
    # No retries: exactly one request per configured model (primary + fallback chain).
    assert len(calls) == model.requests_used == 3


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
    cases = [json.loads(line) for line in cases_file.read_text(encoding="utf-8").splitlines()]
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
    settings = build_test_settings(storage_root=str(tmp_path), chat_history_exchanges=2)
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
    for index in range(8):
        append_message(db, thread, sender_type="visitor", text=str(index))
        append_message(
            db, thread, sender_type="ai", text=f"reply {index}", can_answer=True, needs_human=False
        )
    current = append_message(db, thread, sender_type="visitor", text="now")
    history = history_for_turn(db, thread, settings=settings, exclude_message_id=current.id)
    assert history.messages == [
        {"role": "user", "content": "6"},
        {"role": "assistant", "content": "reply 6"},
        {"role": "user", "content": "7"},
        {"role": "assistant", "content": "reply 7"},
    ]


@pytest.mark.parametrize("identity", ["unknown:model", "", None])
def test_missing_model_row_never_passes_vector_or_empty_fts(identity: str | None) -> None:
    evidence = [
        chunk(vector_similarity=1),
        chunk(fts_match=0),
        chunk(fts_match=0.01, matched_terms=1, query_terms=1),
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


def test_keyword_leg_needs_two_matched_terms_unless_the_query_has_one() -> None:
    one_of_three = chunk(fts_match=0.5, matched_terms=1, query_terms=3)
    two_of_three = chunk(fts_match=0.5, matched_terms=2, query_terms=3)
    one_word = chunk(fts_match=0.5, matched_terms=1, query_terms=1)
    result = RetrievalResult(
        "en", "en", False, evidence=[one_of_three, two_of_three, one_word], embedding_model=None
    )
    decision = relevance_gate(result, build_test_settings())
    assert decision.passed == [two_of_three, one_word]


def test_keyword_thresholds_are_configured_per_embedding_model() -> None:
    from app.core.config import KeywordGate

    weak = chunk(fts_match=0.05, matched_terms=2, query_terms=3)
    strong = chunk(fts_match=0.30, matched_terms=3, query_terms=3)
    gates = {
        "openai:text-embedding-3-large": KeywordGate(min_fts_match=0.2, min_matched_terms=3),
    }
    settings = build_test_settings(retrieval_keyword_gates=gates)
    openai = RetrievalResult(
        "en", "en", False, evidence=[weak, strong], embedding_model="openai:text-embedding-3-large"
    )
    assert relevance_gate(openai, settings).passed == [strong]
    # Another model (or keyword-only mode) keeps the deployment default.
    other = RetrievalResult(
        "en", "en", False, evidence=[weak, strong], embedding_model="ollama:bge-m3"
    )
    # Documents are ordered by relevance: the stronger FTS score first.
    assert relevance_gate(other, settings).passed == [strong, weak]
    assert relevance_gate(openai, settings).fts_minimum == 0.2


def test_refusal_copy_offers_handoff_in_both_languages() -> None:
    from app.chat.prompts import CANNED

    assert "inbox" in CANNED["en"]["cannot_confirm"]
    assert "صندوق" in CANNED["ar"]["cannot_confirm"]
    assert "{support_contact}" in CANNED["ar"]["cannot_confirm"]


def test_optional_steps_skip_when_the_token_cap_is_spent() -> None:
    from app.core.errors import ApiError

    class CapSpent(FakeChatModel):
        def complete(
            self, messages: list[dict[str, str]], *, json_mode: bool, max_tokens: int
        ) -> str:
            raise ApiError(429, "QUOTA_EXCEEDED", "The bot's usage limit has been reached.")

    assert service.translate_query(CapSpent(), question="كم السعر؟", target_language="en") is None
    assert (
        service.condense(
            CapSpent(), history=["What are your hours?"], question="and Friday?", language="en"
        )
        is None
    )


def sibling(document_id: Any, ordinal: int, **kwargs: Any) -> RetrievedChunk:
    return chunk(document_id=document_id, ordinal=ordinal, text=f"part {ordinal}", **kwargs)


def test_document_with_one_strong_chunk_keeps_all_weak_siblings_and_ranks_first() -> None:
    strong_doc, other_doc = uuid4(), uuid4()
    weak_first = sibling(strong_doc, 0)
    weak_last = sibling(strong_doc, 2)
    strong = sibling(strong_doc, 1, vector_similarity=0.80, rrf_score=0.02)
    lesser = sibling(other_doc, 0, vector_similarity=0.55, rrf_score=0.03)
    result = RetrievalResult(
        "en",
        "en",
        False,
        evidence=[lesser, weak_last, strong, weak_first],
        embedding_model="ollama:bge-m3",
    )
    decision = relevance_gate(result, build_test_settings())
    # lesser has the better RRF score, so it leads; siblings stay in ordinal order.
    assert decision.passed == [lesser, weak_first, strong, weak_last]
    verdicts = {v.document_id: v for v in decision.document_verdicts}
    assert verdicts[str(strong_doc)].accepted
    assert verdicts[str(strong_doc)].passed_chunk_ids == [str(strong.chunk_id)]
    assert verdicts[str(strong_doc)].chunk_count == 3
    assert "1 of 3 chunks passed" in verdicts[str(strong_doc)].reason
    assert decision.rejected_ids == []


def test_failed_document_is_rejected_whole_with_a_document_verdict() -> None:
    bad_doc = uuid4()
    bad = [sibling(bad_doc, 0, vector_similarity=0.1), sibling(bad_doc, 1)]
    result = RetrievalResult("en", "en", False, evidence=bad, embedding_model="ollama:bge-m3")
    decision = relevance_gate(result, build_test_settings())
    assert decision.passed == []
    assert [v.accepted for v in decision.document_verdicts] == [False]
    assert decision.document_verdicts[0].reason.startswith("rejected")
    assert decision.rejected_ids == [str(c.chunk_id) for c in bad]


def test_relevance_order_beats_ordinal_order_when_slicing() -> None:
    first_doc, best_doc = uuid4(), uuid4()
    # Retrieval order puts the weaker document first; the better one must lead.
    weaker = [sibling(first_doc, i, vector_similarity=0.51, rrf_score=0.01) for i in range(2)]
    better = [sibling(best_doc, i, vector_similarity=0.9, rrf_score=0.05) for i in range(2)]
    result = RetrievalResult(
        "en", "en", False, evidence=[*weaker, *better], embedding_model="ollama:bge-m3"
    )
    decision = relevance_gate(result, build_test_settings())
    assert decision.passed[:2] == better
    selected = select_evidence(decision, build_test_settings(retrieval_final_k=2))
    assert selected == better


def test_extra_document_never_displaces_part_of_a_passed_document() -> None:
    big_doc, small_doc, tiny_doc = uuid4(), uuid4(), uuid4()
    big = [sibling(big_doc, i, vector_similarity=0.9, rrf_score=0.05) for i in range(6)]
    small = [sibling(small_doc, i, vector_similarity=0.7, rrf_score=0.04) for i in range(2)]
    tiny = [sibling(tiny_doc, 0, vector_similarity=0.6, rrf_score=0.03)]
    result = RetrievalResult(
        "en", "en", False, evidence=[*big, *small, *tiny], embedding_model="ollama:bge-m3"
    )
    decision = relevance_gate(result, build_test_settings())
    # The best document is whole (6 > final_k 4), nothing else squeezes in.
    assert select_evidence(decision, build_test_settings()) == big
    roomy = build_test_settings(retrieval_final_k=8, retrieval_max_evidence_chunks=8)
    assert select_evidence(decision, roomy) == [*big, *small]
    # The hard cap trims only the best document itself, never the others.
    capped = build_test_settings(retrieval_final_k=4, retrieval_max_evidence_chunks=3)
    assert select_evidence(decision, capped) == big[:3]


def _chain_model(handler: Any, fallbacks: list[str]) -> OpenAICompatibleModel:
    return OpenAICompatibleModel(
        base_url="https://fixture.invalid/v1/",
        api_key="synthetic-key",
        model="one:free",
        fallback_models=fallbacks,
        transport=httpx.MockTransport(handler),
    )


@pytest.mark.parametrize("status", [429, 403, 500, 503])
def test_rate_limit_forbidden_and_server_errors_move_to_the_next_model(status: int) -> None:
    seen: list[str] = []

    def response(request: httpx.Request) -> httpx.Response:
        model_id = json.loads(request.content)["model"]
        seen.append(model_id)
        if model_id == "one:free":
            return httpx.Response(status, json={})
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    model = _chain_model(response, ["two:free", "three:free"])
    assert model.complete([], json_mode=False, max_tokens=50) == "ok"
    assert seen == ["one:free", "two:free"] and model.model_used == "two:free"
    assert model.blocked is False and model.last_http_status == 200


def test_all_models_rate_limited_fails_the_turn_without_blocking_the_instance() -> None:
    model = _chain_model(lambda request: httpx.Response(429, json={}), ["two:free"])
    with pytest.raises(ProviderError):
        model.complete([], json_mode=False, max_tokens=50)
    assert model.blocked is False and model.last_http_status == 429
    assert model.requests_used == 2


def test_single_model_chain_still_blocks_on_429() -> None:
    model = _chain_model(lambda request: httpx.Response(429, json={}), [])
    with pytest.raises(ProviderError):
        model.complete([], json_mode=False, max_tokens=50)
    assert model.blocked is True and model.requests_used == 1


def test_provider_trace_keeps_the_real_http_status(monkeypatch: Any) -> None:
    result = RetrievalResult(
        "en", "en", False, evidence=[chunk(vector_similarity=0.9)], embedding_model="ollama:bge-m3"
    )
    monkeypatch.setattr(service, "retrieve", lambda *args, **kwargs: result)
    bot = Bot(id=uuid4(), tenant_id=uuid4(), published_revision_id=uuid4(), config={})
    for status, expected in ((402, "blocked"), (429, "failed")):
        model = _chain_model(lambda request, s=status: httpx.Response(s, json={}), ["two:free"])
        with Session() as db:
            reply = chat_answer(
                db,
                tenant_id=bot.tenant_id,
                bot=bot,
                question="What are your opening hours?",
                model=model,
                settings=build_test_settings(),
            )
        assert reply.kind == "busy"
        detail: Any = reply.trace["provider_error"]
        assert detail["http_status"] == status and detail["status"] == expected
