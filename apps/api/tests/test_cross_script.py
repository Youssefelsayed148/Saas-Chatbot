"""P4-00 (1): cross-script retrieval — when the question-language pass finds
no evidence and the question language differs from the bot's primary
language, the chat service translates the QUERY into the primary language
with ONE ChatModel call (docs/14 §2, ADR-014; on failure the raw question
runs the fallback pass). Must also work for the FIRST message (no history):
`condense()` returns None without history, and no condense call is made.
"""

import re
from typing import Any
from uuid import UUID

from sqlalchemy import text

import tests.retrieval_helpers as _rh  # noqa: F401 — registers the corpus fixture
from app.chat.providers import ChatModel, FakeChatModel
from app.chat.service import chat_answer
from app.db.models import Bot
from tests.retrieval_helpers import published_revision_id

corpus = _rh.corpus  # fixture alias

AR_QUESTION = "ما هي ساعات العمل لديكم؟"  # Arabic: "What are your working hours?"
EN_TRANSLATED = "What are your opening hours?"


def make_en_only_bot(db: Any, corpus: dict[str, Any]) -> Bot:
    """The shared corpus "Main" bot; strip its Arabic chunks so its published
    content is EN-only for these tests."""
    users = corpus["users_a"]
    revision_id = published_revision_id(db, users.tenant_id, str(corpus["bot_main"]))
    db.execute(
        text("DELETE FROM chunks WHERE revision_id = CAST(:r AS uuid) AND language = 'ar'"),
        {"r": revision_id},
    )
    db.commit()
    return Bot(
        id=UUID(str(corpus["bot_main"])),
        tenant_id=users.tenant_id,
        name="Main",
        status="active",
        published_revision_id=UUID(revision_id),
        config={
            "assistant_name": "Mib",
            "business_name": "Acme Ltd",
            "support_email": "support@acme.example.com",
            "default_language": "en",
        },
    )


class TranslatingEchoModel(ChatModel):
    """Non-json call → returns the canned translation; json call → cites the
    first evidence chunk in the system prompt (the evidence ids are DATA)."""

    def __init__(self, translation: str) -> None:
        self.translation = translation
        self.calls: list[tuple[list[dict[str, str]], bool, int]] = []

    def complete(self, messages: list[dict[str, str]], *, json_mode: bool, max_tokens: int) -> str:
        self.calls.append((messages, json_mode, max_tokens))
        if not json_mode:
            return self.translation
        match = re.search(r"\[([0-9a-f-]{36})\]", messages[0]["content"])
        import json

        return json.dumps(
            {
                "answer": "We are open on weekdays and Saturdays.",
                "can_answer": True,
                "sources": [match.group(1) if match else ""],
            }
        )


def test_first_message_arabic_translated_once_and_grounded(
    app: Any, db: Any, corpus: dict[str, Any]
) -> None:
    bot = make_en_only_bot(db, corpus)
    model = TranslatingEchoModel(EN_TRANSLATED)
    reply = chat_answer(
        db,
        tenant_id=bot.tenant_id,
        bot=bot,
        question=AR_QUESTION,
        model=model,
        settings=corpus["settings"],
    )
    # The question-language pass is empty; the fallback pass ran with the
    # translated query and returned grounded evidence; the answer cites it.
    assert reply.used_fallback is True
    assert reply.kind == "answer"
    assert reply.can_answer is True
    assert len(reply.citations) >= 1
    assert all(citation["source_url"] for citation in reply.citations)
    # The reply language follows the visitor (the citation text is EN content).
    assert reply.language == "ar"
    # Exactly ONE non-json model call (the translation; no history → no
    # condense), plus the single json answering call.
    non_json = [call for call in model.calls if call[1] is False]
    assert len(non_json) == 1, [message[0][-1]["content"] for message in model.calls]
    # It is the translate prompt, NOT the condense prompt.
    assert "Follow-up:" not in non_json[0][0][-1]["content"]
    assert "Translate the question" in non_json[0][0][0]["content"]
    assert len([call for call in model.calls if call[1]]) == 1


def test_translation_failure_falls_back_to_raw_question(
    app: Any, db: Any, corpus: dict[str, Any]
) -> None:
    bot = make_en_only_bot(db, corpus)
    model = FakeChatModel(responses=[], raises=True)
    reply = chat_answer(
        db,
        tenant_id=bot.tenant_id,
        bot=bot,
        question=AR_QUESTION,
        model=model,
        settings=corpus["settings"],
    )
    # The ProviderError from translation is swallowed: the raw Arabic question
    # runs the fallback pass against EN-only content → clean abstention.
    assert reply.kind == "cannot_confirm"
    assert reply.used_fallback is True
    assert reply.citations == []
    # The raw Arabic fallback pass may still match Arabic stops; the outcome is
    # a stable canned reply either way (verified above) and a busy path never.
    assert reply.kind != "busy"


def test_no_translate_call_when_languages_match(app: Any, db: Any, corpus: dict[str, Any]) -> None:
    bot = make_en_only_bot(db, corpus)
    model = TranslatingEchoModel(EN_TRANSLATED)  # would translate if asked
    reply = chat_answer(
        db,
        tenant_id=bot.tenant_id,
        bot=bot,
        question="What are your opening hours?",
        model=model,
        settings=corpus["settings"],
    )
    assert reply.kind == "answer"
    assert reply.used_fallback is False
    assert len(reply.citations) >= 1
    # Same language: no translation call (and no condense call with no history).
    assert model.calls and all(call[1] for call in model.calls), model.calls
