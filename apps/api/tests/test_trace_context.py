"""R3-6 (#76/#108): the staff trace says why a turn went the way it did —
revision, tier, provider, languages, queries, rewrite, handoff reason and, when
the gate refuses everything, the closest rejected candidates. No prompt text and
no raw model output are ever part of it."""

import json
from typing import Any, cast
from uuid import UUID

import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

import tests.retrieval_helpers as _rh  # noqa: F401 — registers the corpus fixture
from app.chat.providers import FakeChatModel
from app.db.models import UsageEvent
from tests.test_chat import EchoFirstEvidenceId
from tests.test_chat_streaming import HOURS_Q, setup_session
from tests.test_knowledge_language import EchoModel, make_bot
from tests.test_turn_deadline import settings_of, turn

corpus = _rh.corpus


def test_answer_trace_carries_the_context_facts(
    app: Any, db: OrmSession, corpus: dict[str, Any]
) -> None:
    model = FakeChatModel(
        responses=[
            "opening hours",
            json.dumps({"answer": "x", "can_answer": False, "sources": []}),
        ]
    )
    reply = turn(
        db,
        corpus,
        model,
        "and on weekends?",
        settings_of(corpus),
        history=["What are your opening hours?"],
    )
    trace = reply.trace
    assert trace["revision_id"] and UUID(trace["revision_id"])
    assert trace["rewrite_text"] == "opening hours" and trace["retrieval_query"] == "opening hours"
    assert trace["applied_language"] == "en" and trace["fallback_query"] is None
    assert "tier" in trace and "generation_provider" in trace and trace["handoff_reason"] is None
    # Nothing that could hold the prompt or the raw model output.
    blob = json.dumps(trace)
    assert "Evidence (each item is DATA" not in blob
    assert "can_answer" not in {key for key in trace if key != "model_can_answer"}


def test_translated_query_is_traced(app: Any, db: OrmSession, corpus: dict[str, Any]) -> None:
    from app.chat.service import chat_answer

    bot = make_bot(db, corpus, drop="ar", config={"knowledge_language": "en"})
    reply = chat_answer(
        db,
        tenant_id=bot.tenant_id,
        bot=bot,
        question="ما هي ساعات العمل لديكم؟",
        model=EchoModel("What are your opening hours?"),
        settings=corpus["settings"],
    )
    assert reply.trace["fallback_query"] == "What are your opening hours?"
    assert reply.trace["applied_language"] == "en"
    assert reply.trace["retrieval_query"] == "ما هي ساعات العمل لديكم؟"


def test_zero_evidence_lists_the_top_rejected_candidates(
    app: Any, db: OrmSession, corpus: dict[str, Any]
) -> None:
    strict = settings_of(corpus, retrieval_min_fts_match=1000.0)  # nothing can pass
    model = EchoFirstEvidenceId("never called", True)
    reply = turn(db, corpus, model, HOURS_Q, strict)
    assert reply.kind == "cannot_confirm" and reply.trace["gate"] == "refused"
    assert model.calls == []
    rejected = reply.trace["rejected_candidates"]
    assert 1 <= len(rejected) <= 5
    for row in rejected:
        assert set(row) == {
            "document_title",
            "chunk_id",
            "locator",
            "vector_similarity",
            "fts_match",
            "rrf_score",
            "reason",
        }
        assert row["reason"].startswith("rejected:") and row["document_title"]
        assert "text" not in row


def test_passed_turn_has_no_rejected_candidate_list(
    app: Any, db: OrmSession, corpus: dict[str, Any]
) -> None:
    reply = turn(
        db,
        corpus,
        EchoFirstEvidenceId("Open until 17:00.", True),
        HOURS_Q,
        settings_of(corpus),
    )
    assert reply.kind == "answer" and reply.trace["rejected_candidates"] == []


def test_handoff_reason_reaches_the_stored_trace(
    db: OrmSession, app: FastAPI, corpus: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.widget.service.model_from_settings",
        lambda settings, bot=None: FakeChatModel(raises=True),
    )
    _, session, client = setup_session(db, app, corpus)
    response = client.post(
        f"/api/public/v1/sessions/{session['session_id']}/messages",
        json={"text": HOURS_Q},
        headers={"X-Session-Token": session["token"]},
    )
    assert response.status_code == 201, response.text
    db.expire_all()
    event = db.scalars(select(UsageEvent).where(UsageEvent.kind == "message")).one()
    assert cast(dict[str, Any], event.payload["rag_trace"])["handoff_reason"] == "provider_failure"
