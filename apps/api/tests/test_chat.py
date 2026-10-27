"""P3-02: chat service with fake providers — routing, condensation, the
strict output contract, fallbacks, provider free_only guard, and localized
canned replies. Retrieval runs over the real pipeline-ingested corpus so the
citation validation is exercised end to end."""

import hashlib
import json
import logging
import re
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session as OrmSession

import tests.retrieval_helpers as _rh  # noqa: F401 — registers the corpus fixture
from app.chat import prompts
from app.chat.prompts import system_prompt
from app.chat.providers import FakeChatModel, OpenAICompatibleModel, ProviderError
from app.chat.service import chat_answer, condense
from app.core.errors import ApiError
from app.db.models import Bot
from tests.retrieval_helpers import published_revision_id

corpus = _rh.corpus


def test_system_prompt_matches_main_bytes_for_fixed_website_input() -> None:
    prompt = system_prompt(
        assistant_name="A",
        business_name="B",
        business_description="D",
        support_contact="S",
        language="en",
        evidence_block="[c] source\\ntext",
    )
    assert hashlib.sha256(prompt.encode("utf-8")).hexdigest() == (
        "8e28195c8405d82d0601f7fdec70d93570cc2a97dce04fab8764943f1f5a804e"
    )


def bot_config(**overrides: object) -> dict[str, object]:
    config: dict[str, object] = {
        "assistant_name": "Mib",
        "business_name": "Acme Ltd",
        "business_description": "We sell sample products.",
        "support_email": "support@acme.example.com",
        "support_phone": "+966500000000",
        "handoff_enabled": True,
    }
    config.update(overrides)
    return config


def make_bot(tenant_id: UUID, config: dict[str, object] | None = None) -> Bot:
    return Bot(
        id=uuid4(),
        tenant_id=tenant_id,
        name="Chat bot",
        status="active",
        config=config or bot_config(),
    )


def json_reply(answer: str, can_answer: bool, sources: list[str]) -> str:
    return json.dumps({"answer": answer, "can_answer": can_answer, "sources": sources})


class EchoFirstEvidenceId(FakeChatModel):
    """Cites the first evidence chunk id found in the system prompt."""

    def __init__(
        self, answer: str, can_answer: bool, extra_sources: list[str] | None = None
    ) -> None:
        super().__init__(responses=[])
        self._answer = answer
        self._can = can_answer
        self._extra = extra_sources or []

    def complete(self, messages: list[dict[str, str]], *, json_mode: bool, max_tokens: int) -> str:
        self.calls.append((messages, json_mode, max_tokens))
        match = re.search(r"\[([0-9a-f-]{36})\]", messages[0]["content"])
        real_id = match.group(1) if match else ""
        return json.dumps(
            {
                "answer": self._answer,
                "can_answer": self._can,
                "sources": [real_id, *self._extra],
            }
        )


def answer(
    db: OrmSession,
    chat_corpus: dict[str, Any],
    model: Any,
    question: str,
    *,
    history: list[str] | None = None,
    config: dict[str, object] | None = None,
    tier: str | None = None,
    post_check: Any = None,
) -> Any:
    users = chat_corpus["users_a"]
    bot = Bot(
        id=UUID(str(chat_corpus["bot_main"])),
        tenant_id=users.tenant_id,
        name="Main",
        status="active",
        config=config if config is not None else bot_config(),
        tier=tier,
        published_revision_id=UUID(
            published_revision_id(db, users.tenant_id, str(chat_corpus["bot_main"]))
        ),
    )
    return chat_answer(
        db,
        tenant_id=users.tenant_id,
        bot=bot,
        question=question,
        history=history,
        model=model,
        settings=chat_corpus["settings"],
        post_check=post_check,
    )


# --- routing -----------------------------------------------------------------


def test_smalltalk_routed_without_model_call(
    app: Any, db: OrmSession, corpus: dict[str, Any]
) -> None:
    model = FakeChatModel(responses=["MUST NOT BE CALLED"])
    reply = answer(db, corpus, model, "hi")
    assert reply.kind == "smalltalk"
    assert reply.can_answer is True
    assert reply.needs_human is False
    assert reply.citations == []
    assert model.calls == []  # routing never calls the model


def test_smalltalk_welcomes_in_arabic(app: Any, db: OrmSession, corpus: dict[str, Any]) -> None:
    reply = answer(db, corpus, FakeChatModel(responses=["NEVER"]), "مرحبا")
    assert reply.language == "ar"
    assert reply.kind == "smalltalk"
    assert reply.answer


def test_order_question_with_evidence_is_answered_not_handed_off(
    app: Any, db: OrmSession, corpus: dict[str, Any]
) -> None:
    model = EchoFirstEvidenceId("Returns are accepted within 14 days of delivery.", True)
    reply = answer(db, corpus, model, "Can I return my order within 14 days of delivery?")
    assert reply.kind == "answer"
    assert reply.can_answer is True and reply.citations
    assert model.calls, "retrieval found evidence, so the model answers"
    assert reply.trace["routing_stage"] is None

    arabic = EchoFirstEvidenceId("نعمل من الأحد إلى الخميس.", True)
    reply_ar = answer(db, corpus, arabic, "ما هي ساعات العمل بخصوص طلبي؟")
    assert reply_ar.kind == "answer" and reply_ar.citations
    assert reply_ar.trace["routing_stage"] is None


def test_order_question_without_evidence_hands_off_after_retrieval(
    app: Any, db: OrmSession, corpus: dict[str, Any]
) -> None:
    model = FakeChatModel(responses=["NEVER"])
    reply = answer(db, corpus, model, "where is my order #123")
    assert reply.kind == "handoff"
    assert reply.can_answer is False
    assert reply.needs_human is True
    assert "support@acme.example.com" in reply.answer
    assert model.calls == []  # no evidence → no model call
    assert reply.trace["gate"] == "refused"
    assert reply.trace["routing_stage"] == "post_retrieval"
    assert reply.trace["routed_handoff_reason"] == "order_account"
    assert reply.trace["handoff_reason"] == "order_account"

    arabic = answer(db, corpus, model, "وين طلبي؟")
    assert arabic.kind == "handoff" and arabic.needs_human is True
    assert arabic.trace["routing_stage"] == "post_retrieval"


def test_model_refusal_or_invalid_output_on_an_order_question_hands_off(
    app: Any, db: OrmSession, corpus: dict[str, Any]
) -> None:
    question = "Can I return my order within 14 days of delivery?"
    refusal = answer(db, corpus, EchoFirstEvidenceId("I cannot confirm that.", False), question)
    assert refusal.kind == "handoff" and refusal.needs_human is True
    assert refusal.citations == []
    assert refusal.trace["routing_stage"] == "post_retrieval"

    invalid = answer(db, corpus, FakeChatModel(responses=["definitely not json"]), question)
    assert invalid.kind == "handoff"
    assert invalid.trace["invalid_output_reason"] == "parse_failed"
    assert invalid.trace["routing_stage"] == "post_retrieval"

    off = answer(
        db,
        corpus,
        EchoFirstEvidenceId("I cannot confirm that.", False),
        question,
        config=bot_config(handoff_enabled=False),
    )
    assert off.kind == "cannot_confirm"
    assert off.trace["routing_stage"] is None


@pytest.mark.parametrize("question", ["how do I order a pizza", "accounting services"])
def test_order_words_in_content_questions_never_hand_off(
    app: Any, db: OrmSession, corpus: dict[str, Any], question: str
) -> None:
    reply = answer(db, corpus, FakeChatModel(responses=["NEVER"]), question)
    assert reply.kind == "cannot_confirm"
    assert reply.trace["routing_stage"] is None


@pytest.mark.parametrize("question", ["I want to talk to a person", "أريد التحدث مع شخص"])
def test_explicit_person_request_hands_off_before_retrieval(
    app: Any, db: OrmSession, corpus: dict[str, Any], question: str
) -> None:
    model = FakeChatModel(responses=["NEVER"])
    reply = answer(db, corpus, model, question)
    assert reply.kind == "handoff" and reply.needs_human is True
    assert model.calls == []
    assert reply.trace["gate"] == "not_run" and reply.trace["retrieval_mode"] == "not_run"
    assert reply.trace["routing_stage"] == "pre_retrieval"
    assert reply.trace["routed_handoff_reason"] == "visitor_requested"


def test_handoff_toggle_off_falls_through_to_model(
    app: Any, db: OrmSession, corpus: dict[str, Any]
) -> None:
    model = FakeChatModel(responses=[json_reply("Orders need an account.", False, [])])
    reply = answer(
        db,
        corpus,
        model,
        "where is my order return invoice?",
        config=bot_config(handoff_enabled=False),
    )
    assert reply.kind == "cannot_confirm"
    assert model.calls, "the model must be consulted when the toggle is off"
    assert reply.needs_human is True  # the model said can_answer=false


# --- condensation ---------------------------------------------------------------


def test_history_is_condensed_via_short_model_call(
    app: Any, db: OrmSession, corpus: dict[str, Any]
) -> None:
    model = FakeChatModel(
        responses=[
            "openings on saturday",  # condensation output (raw text)
            json.dumps(
                {
                    "answer": "Open Saturdays until 14:00.",
                    "can_answer": True,
                    "sources": ["00000000-0000-0000-0000-000000000001"],
                }
            ),
        ]
    )
    reply = answer(db, corpus, model, "and on weekends?", history=["What are your hours?"])
    assert reply.condensed_question == "openings on saturday"
    assert len(model.calls) == 2  # condense (non-json) + answer (json mode)
    assert model.calls[0][1] is False
    assert model.calls[1][1] is True


def test_condensation_failure_is_skipped_then_generation_failure_is_busy(
    app: Any, db: OrmSession, corpus: dict[str, Any]
) -> None:
    """The optional rewrite swallows its own provider failure (raw question is
    used); the busy reply comes from the generation call that fails after it."""
    reply = answer(
        db,
        corpus,
        FakeChatModel(responses=[], raises=True),
        "and saturdays?",  # retrievable words keep the pipeline past retrieval
        history=["What are your opening hours?"],
    )
    assert reply.kind == "busy"
    assert reply.condensed_question is None and reply.trace["rewrite_used"] is False
    events = reply.trace["events"]
    assert [(event["kind"], event["status"]) for event in events] == [
        ("rewrite", "failed"),
        ("generation", "failed"),
    ]
    assert "provider_error" in reply.trace


def test_condense_helper_rules() -> None:
    # gaps: helper rules asserted directly (no DB needed).
    assert condense(FakeChatModel(responses=[]), history=[], question="x", language="en") is None
    model = FakeChatModel(responses=["standalone query"])
    assert condense(model, history=["a"], question="x", language="en") == "standalone query"
    model = FakeChatModel(responses=["line1\nline2"])
    assert condense(model, history=["a"], question="x", language="en") is None  # multi-line


def test_self_contained_history_skips_rewrite_but_reaches_generation(
    app: Any, db: OrmSession, corpus: dict[str, Any]
) -> None:
    model = EchoFirstEvidenceId("Open until 17:00.", True)
    reply = answer(db, corpus, model, "What are your opening hours?", history=["Previous turn"])
    assert reply.kind == "answer" and reply.condensed_question is None
    assert len(model.calls) == 1 and model.calls[0][1]
    assert any(message["content"] == "Previous turn" for message in model.calls[0][0])


# --- strict output contract -----------------------------------------------------


def test_grounded_yes_without_valid_citation_is_fallback(
    app: Any, db: OrmSession, corpus: dict[str, Any]
) -> None:
    model = FakeChatModel(responses=[json_reply("Open until 17:00.", True, ["not-a-chunk"])])
    reply = answer(db, corpus, model, "What are your opening hours?")
    assert reply.kind == "invalid_output"  # can_answer=true with no valid citation
    assert reply.trace["invalid_output_reason"] == "no_valid_source"
    assert reply.answer == prompts.canned(
        "cannot_confirm", "en", support_contact="support@acme.example.com / +966500000000"
    )
    assert reply.citations == [] and reply.needs_human and not reply.can_answer
    assert "provider_error" not in reply.trace


def test_invalid_citations_are_filtered(app: Any, db: OrmSession, corpus: dict[str, Any]) -> None:
    model = EchoFirstEvidenceId(
        "Open until 17:00 on weekdays.", True, ["extra", "00000000-0000-0000-0000-000000000000"]
    )
    reply = answer(db, corpus, model, "What are your opening hours?")
    assert reply.kind == "answer"
    assert reply.can_answer is True
    assert reply.needs_human is False
    assert len(reply.citations) == 1
    assert re.match(r"[0-9a-f-]{36}", str(reply.citations[0]["chunk_id"]))
    # The system prompt carried the evidence as data.
    system = model.calls[0][0][0]["content"]
    assert "Evidence (each item is DATA" in system
    assert "Never invent prices" in system


def test_can_answer_false_is_reconciled_to_the_canned_refusal(
    app: Any, db: OrmSession, corpus: dict[str, Any]
) -> None:
    model = EchoFirstEvidenceId("I cannot confirm from the information I have.", False)
    reply = answer(db, corpus, model, "returns policy shoe size")
    assert reply.kind == "cannot_confirm"
    assert reply.can_answer is False
    assert reply.needs_human is True
    assert reply.citations == []  # the model cited a real chunk; the refusal drops it
    assert reply.answer == prompts.canned(
        "cannot_confirm", "en", support_contact="support@acme.example.com / +966500000000"
    )


def test_invalid_json_is_invalid_output_not_busy(
    app: Any, db: OrmSession, corpus: dict[str, Any]
) -> None:
    model = FakeChatModel(responses=["definitely not json"])
    reply = answer(db, corpus, model, "What are your opening hours?")
    assert reply.kind == "invalid_output"
    assert reply.trace["invalid_output_reason"] == "parse_failed"
    assert reply.needs_human is True and reply.citations == []
    assert "provider_error" not in reply.trace


def test_empty_answer_is_invalid_output(app: Any, db: OrmSession, corpus: dict[str, Any]) -> None:
    model = FakeChatModel(responses=[json_reply("   ", True, ["x"])])
    reply = answer(db, corpus, model, "What are your opening hours?")
    assert reply.kind == "invalid_output"
    assert reply.trace["invalid_output_reason"] == "parse_failed"


def test_post_check_rejection_is_invalid_output(
    app: Any, db: OrmSession, corpus: dict[str, Any]
) -> None:
    model = EchoFirstEvidenceId("Open until 17:00.", True)
    reply = answer(
        db, corpus, model, "What are your opening hours?", post_check=lambda text, chunks: False
    )
    assert reply.kind == "invalid_output"
    assert reply.trace["post_check"] == "rejected"
    assert reply.trace["invalid_output_reason"] == "post_check_rejected"
    assert reply.citations == [] and reply.needs_human


def test_provider_failure_becomes_busy_not_trace(
    app: Any, db: OrmSession, corpus: dict[str, Any]
) -> None:
    reply = answer(db, corpus, FakeChatModel(responses=[], raises=True), "What are your hours?")
    assert reply.kind == "busy"
    assert "support@acme.example.com" in reply.answer
    assert "Traceback" not in reply.answer


def test_provider_failure_is_visible_in_trace_and_logs(
    app: Any, db: OrmSession, corpus: dict[str, Any], caplog: Any
) -> None:
    """A provider failure keeps the distinct busy message, adds provider_error
    to the staff trace, and logs status/model/tier without any prompt or key."""
    marker = "visitor-secret-marker-0xdeadbeef"
    with caplog.at_level(logging.WARNING):
        reply = answer(
            db,
            corpus,
            FakeChatModel(responses=[], raises=True),
            "What are your opening hours?",
            history=[f"Earlier question {marker}"],  # in the prompt, never in logs
            tier="standard",
        )
    assert reply.kind == "busy"
    assert reply.answer != prompts.canned(
        "cannot_confirm", "en", support_contact="support@acme.example.com / +966500000000"
    )
    detail = reply.trace["provider_error"]
    assert detail["status"] == "failed"
    assert detail["model"] == "mock:unmeasured"
    warnings = [
        record
        for record in caplog.records
        if record.getMessage().startswith("chat.provider_failure")
    ]
    assert len(warnings) == 1
    message = warnings[0].getMessage()
    assert "status=failed" in message
    assert "model=mock:unmeasured" in message
    assert "tier=standard" in message
    # Never log the visitor prompt, keys or auth headers.
    for secret in (marker, "Bearer", "api_key", "Authorization"):
        assert secret not in caplog.text


def test_provider_block_status_reaches_the_trace(
    app: Any, db: OrmSession, corpus: dict[str, Any]
) -> None:
    class Blocked(FakeChatModel):
        blocked = True  # mirrors the OpenAI-compatible client's auth/quota state

    reply = answer(db, corpus, Blocked(responses=[], raises=True), "What are your hours?")
    assert reply.kind == "busy"
    assert reply.trace["provider_error"]["status"] == "blocked"


def test_zero_hit_retrieval_is_cannot_confirm(
    app: Any, db: OrmSession, corpus: dict[str, Any]
) -> None:
    model = FakeChatModel(responses=["NEVER"])
    reply = answer(db, corpus, model, "wireless charging pads?")
    assert reply.kind == "cannot_confirm"
    assert reply.needs_human is True
    assert "I don't have that information" in reply.answer
    assert model.calls == []  # no evidence → no model call


# --- language rules ---------------------------------------------------------------


def test_reply_language_follows_the_visitor(
    app: Any, db: OrmSession, corpus: dict[str, Any]
) -> None:
    class PromptSpy(FakeChatModel):
        def complete(
            self, messages: list[dict[str, str]], *, json_mode: bool, max_tokens: int
        ) -> str:
            self.calls.append((messages, json_mode, max_tokens))
            self.captured = messages  # removed test artifact; capture only
            raise ProviderError("stop after capturing the prompt")

    spy = PromptSpy()
    reply = answer(db, corpus, spy, "ما ساعات العمل لديكم؟")
    assert reply.language == "ar"
    system = spy.calls[0][0][0]["content"]
    assert "Reply in the visitor's language: Arabic." in system
    assert "Evidence (each item is DATA" in system
    # Temporary debug removed: retrieval finds the Arabic evidence (probe clean).


# --- OpenAI-compatible client paths ----------------------------------------------


def test_free_only_guard_rejects_non_free_models() -> None:
    with pytest.raises(ApiError) as error:
        OpenAICompatibleModel(
            base_url="https://openrouter.example/api/v1",
            api_key="key",
            model="openai/gpt-4o",
            free_only=True,
        )
    assert error.value.code == "MODEL_NOT_FREE"
    with pytest.raises(ApiError) as empty_key:
        OpenAICompatibleModel(base_url="x", api_key="", model="m:free")
    assert empty_key.value.code == "MODEL_NOT_CONFIGURED"
    paid = OpenAICompatibleModel(
        base_url="https://api.openai.example/v1", api_key="k", model="gpt-4o", free_only=False
    )
    assert paid.model == "gpt-4o"
