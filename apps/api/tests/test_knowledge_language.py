"""R3-1 (#96): ``knowledge_language`` decides the cross-language fallback; the
widget UI language (``default_language``) no longer does."""

import json
import re
from typing import Any
from uuid import UUID

import pytest
from pydantic import ValidationError
from sqlalchemy import text

import tests.retrieval_helpers as _rh  # noqa: F401 — registers the corpus fixture
from app.bots.schemas import BotConfig
from app.chat.providers import ChatModel
from app.chat.service import chat_answer, knowledge_language
from app.db.models import Bot
from tests.retrieval_helpers import published_revision_id

corpus = _rh.corpus  # fixture alias

AR_QUESTION = "ما هي ساعات العمل لديكم؟"
EN_QUESTION = "What are your opening hours?"


class EchoModel(ChatModel):
    """Translation call → canned text; JSON call → cites the first evidence chunk."""

    def __init__(self, translation: str) -> None:
        self.translation = translation
        self.translated = 0

    def complete(self, messages: list[dict[str, str]], *, json_mode: bool, max_tokens: int) -> str:
        if not json_mode:
            self.translated += 1
            return self.translation
        match = re.search(r"\[([0-9a-f-]{36})\]", messages[0]["content"])
        return json.dumps(
            {
                "answer": "We are open on weekdays.",
                "can_answer": True,
                "sources": [match.group(1) if match else ""],
            }
        )


def make_bot(db: Any, corpus: dict[str, Any], *, drop: str, config: dict[str, Any]) -> Bot:
    """The shared "Main" bot with the ``drop`` language's chunks removed."""
    users = corpus["users_a"]
    revision_id = published_revision_id(db, users.tenant_id, str(corpus["bot_main"]))
    db.execute(
        text("DELETE FROM chunks WHERE revision_id = CAST(:r AS uuid) AND language = :lang"),
        {"r": revision_id, "lang": drop},
    )
    db.commit()
    return Bot(
        id=UUID(str(corpus["bot_main"])),
        tenant_id=users.tenant_id,
        name="Main",
        status="active",
        published_revision_id=UUID(revision_id),
        config={"assistant_name": "Mib", "business_name": "Acme", **config},
    )


def test_arabic_question_english_knowledge_uses_fallback(
    app: Any, db: Any, corpus: dict[str, Any]
) -> None:
    # The widget is Arabic (default_language=ar) but the knowledge is English.
    bot = make_bot(
        db, corpus, drop="ar", config={"default_language": "ar", "knowledge_language": "en"}
    )
    model = EchoModel(EN_QUESTION)
    reply = chat_answer(
        db,
        tenant_id=bot.tenant_id,
        bot=bot,
        question=AR_QUESTION,
        model=model,
        settings=corpus["settings"],
    )
    assert reply.used_fallback is True and reply.kind == "answer"
    assert reply.language == "ar" and model.translated == 1


def test_english_question_arabic_knowledge_uses_fallback(
    app: Any, db: Any, corpus: dict[str, Any]
) -> None:
    bot = make_bot(
        db, corpus, drop="en", config={"default_language": "en", "knowledge_language": "ar"}
    )
    model = EchoModel(AR_QUESTION)
    reply = chat_answer(
        db,
        tenant_id=bot.tenant_id,
        bot=bot,
        question=EN_QUESTION,
        model=model,
        settings=corpus["settings"],
    )
    assert reply.used_fallback is True and reply.kind == "answer"
    assert reply.language == "en" and model.translated == 1


def test_null_knowledge_language_follows_default_language(
    app: Any, db: Any, corpus: dict[str, Any]
) -> None:
    # Same Arabic widget + English knowledge, but knowledge_language unset: the
    # bot's primary language is Arabic, equal to the question's, so no fallback.
    bot = make_bot(db, corpus, drop="ar", config={"default_language": "ar"})
    assert knowledge_language(bot) == "ar"
    model = EchoModel(EN_QUESTION)
    reply = chat_answer(
        db,
        tenant_id=bot.tenant_id,
        bot=bot,
        question=AR_QUESTION,
        model=model,
        settings=corpus["settings"],
    )
    assert reply.used_fallback is False and reply.kind == "cannot_confirm"
    assert model.translated == 0


def test_knowledge_language_resolution_and_schema() -> None:
    assert knowledge_language(Bot(config={"default_language": "ar"})) == "ar"
    assert (
        knowledge_language(Bot(config={"knowledge_language": "en", "default_language": "ar"}))
        == "en"
    )
    assert knowledge_language(Bot(config={"knowledge_language": "fr"})) == "en"
    assert BotConfig(knowledge_language="ar").knowledge_language == "ar"
    with pytest.raises(ValidationError):
        BotConfig(knowledge_language="fr")


def test_patch_null_clears_knowledge_language() -> None:
    from app.bots.service import BotService

    service = BotService(None)  # type: ignore[arg-type] — _merge_config never touches the db
    bot = Bot(config={"knowledge_language": "en", "default_language": "ar"})
    merged = service._merge_config(bot, BotConfig(knowledge_language=None))
    assert "knowledge_language" not in merged and merged["default_language"] == "ar"
    untouched = service._merge_config(bot, BotConfig(default_language="en"))
    assert untouched["knowledge_language"] == "en"
