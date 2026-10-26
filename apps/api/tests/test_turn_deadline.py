"""R3-4 (#84): one time budget for the visitor turn. Optional steps (rewrite,
translation) are skipped when the budget is short, the embed wait has a short
timeout and a circuit breaker, generation keeps a floor, and a stalled
embedder or provider never hangs the turn. Stubs and mocked HTTP only."""

import json
import time
from collections.abc import Iterator
from threading import Event
from typing import Any
from uuid import UUID

import httpx
import pytest
from sqlalchemy.orm import Session as OrmSession

import tests.retrieval_helpers as _rh  # noqa: F401 — registers the corpus fixture
from app.chat import deadline
from app.chat.providers import FakeChatModel, OpenAICompatibleModel
from app.chat.service import chat_answer
from app.core.config import Settings
from app.db.models import Bot
from app.embeddings.providers import EmbeddingBatch, EmbeddingError
from app.retrieval import hybrid
from tests.retrieval_helpers import published_revision_id
from tests.test_chat import EchoFirstEvidenceId, bot_config
from tests.test_hybrid_retrieval import VECTOR, ready
from tests.test_knowledge_language import EchoModel, make_bot

corpus = _rh.corpus


def settings_of(corpus: dict[str, Any], **overrides: Any) -> Settings:
    return corpus["settings"].model_copy(update=overrides)


def turn(
    db: OrmSession,
    corpus: dict[str, Any],
    model: Any,
    question: str,
    settings: Settings,
    *,
    history: list[str] | None = None,
) -> Any:
    users = corpus["users_a"]
    bot = Bot(
        id=UUID(str(corpus["bot_main"])),
        tenant_id=users.tenant_id,
        name="Main",
        status="active",
        config=bot_config(),
        published_revision_id=UUID(
            published_revision_id(db, users.tenant_id, str(corpus["bot_main"]))
        ),
    )
    return chat_answer(
        db,
        tenant_id=users.tenant_id,
        bot=bot,
        question=question,
        history=history,
        model=model,
        settings=settings,
    )


# --- the budget itself -----------------------------------------------------------


def test_budget_rules(monkeypatch: pytest.MonkeyPatch) -> None:
    now = [100.0]
    monkeypatch.setattr(deadline, "monotonic", lambda: now[0])
    budget = deadline.TurnBudget.start(
        Settings.model_construct(
            chat_turn_deadline_seconds=40.0,
            chat_aux_timeout_seconds=10.0,
            chat_embed_timeout_seconds=5.0,
        )
    )
    assert budget.optional_allowed() and budget.aux_timeout() == 10.0
    assert budget.embed_timeout() == 5.0 and budget.generation_timeout() == 40.0
    now[0] += 31  # 9 s left: under the 10 s optional timeout
    assert not budget.optional_allowed()
    assert budget.embed_timeout() == 5.0 and budget.generation_timeout() == 10.0
    now[0] += 50  # past the deadline: generation still gets its floor
    assert budget.remaining() < 0 and budget.embed_timeout() == 0.0
    assert budget.generation_timeout() == deadline.GENERATION_FLOOR_SECONDS


def test_settings_defaults() -> None:
    settings = Settings.model_construct()
    assert settings.chat_turn_deadline_seconds == 40
    assert settings.chat_embed_timeout_seconds == 5
    assert settings.chat_aux_timeout_seconds == 10


# --- optional steps are skipped when the budget is short ------------------------


def test_rewrite_is_skipped_when_the_budget_is_short(
    app: Any, db: OrmSession, corpus: dict[str, Any]
) -> None:
    model = EchoFirstEvidenceId("Open until 17:00.", True)
    short = settings_of(corpus, chat_turn_deadline_seconds=5.0)  # < the 10 s rewrite timeout
    reply = turn(
        db,
        corpus,
        model,
        "and on weekends?",
        short,
        history=["What are your opening hours?"],
    )
    assert reply.kind in ("answer", "cannot_confirm")
    assert reply.condensed_question is None and reply.trace["rewrite_used"] is False
    assert reply.trace["skipped_steps"] == ["rewrite"]
    assert all(call[1] for call in model.calls)  # only JSON-mode generation calls


def test_translation_is_skipped_when_the_budget_is_short(
    app: Any, db: OrmSession, corpus: dict[str, Any]
) -> None:
    bot = make_bot(db, corpus, drop="ar", config={"knowledge_language": "en"})
    model = EchoModel("What are your opening hours?")
    reply = chat_answer(
        db,
        tenant_id=bot.tenant_id,
        bot=bot,
        question="ما هي ساعات العمل لديكم؟",
        model=model,
        settings=settings_of(corpus, chat_turn_deadline_seconds=5.0),
    )
    assert model.translated == 0
    assert reply.trace["skipped_steps"] == ["translation"]
    assert reply.used_fallback is True  # the raw question still runs the fallback pass


def test_a_normal_budget_runs_the_optional_steps(
    app: Any, db: OrmSession, corpus: dict[str, Any]
) -> None:
    model = FakeChatModel(
        responses=[
            "opening hours",
            json.dumps({"answer": "x", "can_answer": False, "sources": []}),
        ]
    )
    reply = turn(
        db, corpus, model, "and on weekends?", settings_of(corpus),
        history=["What are your opening hours?"],
    )  # fmt: skip
    assert reply.trace["skipped_steps"] == [] and reply.condensed_question == "opening hours"


# --- provider timeouts ------------------------------------------------------------


def stalled_provider(seen: list[dict[str, float | None]]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(dict(request.extensions["timeout"]))
        raise httpx.ReadTimeout("stalled", request=request)

    return httpx.MockTransport(handler)


def test_stalled_provider_ends_the_turn_busy_with_bounded_timeouts(
    app: Any, db: OrmSession, corpus: dict[str, Any]
) -> None:
    seen: list[dict[str, float | None]] = []
    model = OpenAICompatibleModel(
        base_url="https://llm.test/v1",
        api_key="k",
        model="vendor/m",
        free_only=False,
        transport=stalled_provider(seen),
    )
    started = time.monotonic()
    reply = turn(db, corpus, model, "What are your opening hours?", settings_of(corpus))
    assert time.monotonic() - started < 5  # the mock stalls instantly; no real waiting
    assert reply.kind == "busy" and reply.trace["provider_error"]["http_status"] is None
    assert seen and all((entry["read"] or 0) <= 25.0 for entry in seen)


def test_provider_call_timeout_caps_each_attempt() -> None:
    seen: list[dict[str, float | None]] = []
    model = OpenAICompatibleModel(
        base_url="https://llm.test/v1",
        api_key="k",
        model="vendor/m",
        free_only=False,
        transport=stalled_provider(seen),
    )
    model.call_timeout = 3.0
    with pytest.raises(Exception):  # noqa: B017 — ProviderError, asserted below via the timeout
        model.complete([{"role": "user", "content": "x"}], json_mode=True, max_tokens=10)
    assert seen and (seen[0]["read"] or 99) <= 3.0
    # A spent budget makes no request at all.
    seen.clear()
    model.call_timeout = 0.0
    with pytest.raises(Exception):  # noqa: B017
        model.complete([{"role": "user", "content": "x"}], json_mode=True, max_tokens=10)
    assert seen == []
    # The second attempt only gets what is left of the call budget.
    model.call_timeout = 40.0
    assert model._attempt_timeout(time.monotonic() - 30) <= 10.0  # type: ignore[operator]


# --- the embedding leg ------------------------------------------------------------


@pytest.fixture
def release() -> Iterator[Event]:
    event = Event()
    yield event
    event.set()  # let a stalled embed thread finish before the tables are truncated
    time.sleep(0.5)


def test_stalled_embedder_degrades_to_keyword_within_the_embed_timeout(
    app: Any, db: OrmSession, corpus: dict[str, Any], monkeypatch: Any, release: Event
) -> None:
    ready(db, corpus)

    class Stalled:
        def embed(self, texts: list[str]) -> EmbeddingBatch:
            release.wait(10)
            return EmbeddingBatch([VECTOR])

    monkeypatch.setattr(hybrid, "from_settings", lambda *args: Stalled())
    started = time.monotonic()
    reply = turn(
        db,
        corpus,
        EchoFirstEvidenceId("Open until 17:00.", True),
        "What are your opening hours?",
        settings_of(corpus, chat_embed_timeout_seconds=0.3),
    )
    assert time.monotonic() - started < 5, "the turn must not wait for the stalled embedder"
    assert reply.trace["retrieval_mode"] == "fts_only"
    assert reply.trace["degradation_reason"] == "embedding_timeout"
    assert reply.kind == "answer" and reply.citations  # the keyword-only answer


def test_three_embed_failures_suspend_the_vector_leg_for_a_minute(
    app: Any, db: OrmSession, corpus: dict[str, Any], monkeypatch: Any
) -> None:
    ready(db, corpus)
    calls: list[int] = []

    class Failing:
        def embed(self, texts: list[str]) -> EmbeddingBatch:
            calls.append(1)
            raise EmbeddingError("safe synthetic failure")

    clock = [1000.0]
    monkeypatch.setattr(hybrid, "_clock", lambda: clock[0])
    monkeypatch.setattr(hybrid, "from_settings", lambda *args: Failing())
    from tests.test_hybrid_retrieval import run

    reasons = [run(db, corpus).degradation_reason for _ in range(3)]
    assert reasons == ["embedding_or_vector_failure"] * 3 and len(calls) == 3
    suspended = run(db, corpus)
    assert suspended.degradation_reason == "embedding_suspended_after_failures"
    assert suspended.mode == "fts_only" and suspended.evidence and len(calls) == 3
    clock[0] += 61  # the window is over: the provider is tried again
    assert run(db, corpus).degradation_reason == "embedding_or_vector_failure"
    assert len(calls) == 4


def test_failures_outside_the_window_do_not_add_up(
    app: Any, db: OrmSession, corpus: dict[str, Any], monkeypatch: Any
) -> None:
    ready(db, corpus)

    class Failing:
        def embed(self, texts: list[str]) -> EmbeddingBatch:
            raise EmbeddingError("safe synthetic failure")

    clock = [1000.0]
    monkeypatch.setattr(hybrid, "_clock", lambda: clock[0])
    monkeypatch.setattr(hybrid, "from_settings", lambda *args: Failing())
    from tests.test_hybrid_retrieval import run

    for _ in range(5):
        assert run(db, corpus).degradation_reason == "embedding_or_vector_failure"
        clock[0] += 31  # two failures never fall inside one 60 s window... three would
    # 5 failures 31 s apart: at most 2 per window, so the leg is never suspended.
