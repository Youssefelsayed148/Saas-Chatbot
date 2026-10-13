"""Chat service (docs/14 §6): grounded answers with a strict output contract.

Pipeline: detect language → rule routing (smalltalk/handoff) → optional
follow-up condensation → retrieval (P3-01) → ChatModel call in strict JSON
mode → validate/repair → localized fallbacks (never a stack trace).

Business facts only come from the knowledge base (via retrieval); the tiger
prompt template is versioned (`prompts.PROMPT_TEMPLATE_VERSION`) and never
contains knowledge content.

The reply marks `needs_human` when the model says `can_answer=false` or the
chain failed — the handoff machine (P5) consumes that flag.
"""

import json
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy.orm import Session as OrmSession

from app.chat import prompts
from app.chat.providers import ChatModel, ProviderError
from app.chat.routing import route
from app.core.config import Settings
from app.db.models import Bot
from app.knowledge.language import detect_language
from app.retrieval.service import RetrievalResult, RetrievedChunk, retrieve

MAX_TOKENS = 700

CONDENSE_SYSTEM = (
    "You condense a visitor follow-up into a standalone search query in the "
    "visitor's language. Use the history only to resolve pronouns and "
    "ellipsis. Output ONE line: the standalone query, nothing else."
)

LANGUAGE_NAMES = {"en": "English", "ar": "Arabic"}

TRANSLATE_SYSTEM_TEMPLATE = (
    "You translate a customer question so it can be searched in the "
    "business's own knowledge base. Translate the question into "
    "{language_name}. Output ONLY the translated question on one line, "
    "nothing else. Keep every name, number and product word."
)


@dataclass
class ChatReply:
    """The chat turn, validated and shaped for storage (P3-03)."""

    answer: str
    can_answer: bool
    needs_human: bool
    language: str
    # "smalltalk" | "handoff" | "answer" | "busy" | "cannot_confirm"
    kind: str
    # Validated citations (subset of retrieved chunks, in retrieval order).
    citations: list[dict[str, str | None]] = field(default_factory=list)
    condensed_question: str | None = None
    used_fallback: bool = False  # cross-language retrieval fallback


def _support_contact(bot: Bot) -> str:
    config = bot.config if isinstance(bot.config, dict) else {}
    parts = [value for value in (config.get("support_email"), config.get("support_phone")) if value]
    return " / ".join(str(part) for part in parts) or "our support team"


def _config_get(bot: Bot, key: str, default: object) -> object:
    config = bot.config if isinstance(bot.config, dict) else {}
    return config.get(key, default)


def _welcome_for(bot: Bot, language: str) -> str:
    welcome = _config_get(bot, "welcome_message", {})
    if isinstance(welcome, dict):
        text = welcome.get(language) or welcome.get("en") or welcome.get("ar")
        if isinstance(text, str) and text.strip():
            return text
    return prompts.canned("hello_default", language)


def _default_answer_language(bot: Bot) -> str:
    configured = _config_get(bot, "default_language", "en")
    return configured if configured in ("en", "ar") else "en"


def condense(
    model: ChatModel,
    *,
    history: list[str],
    question: str,
    language: str,
) -> str | None:
    """Short LLM call; on any failure the raw question is used (docs/14 §6)."""
    if not history:
        return None
    history_block = "\n".join(f"- {message}" for message in history[-6:])
    messages = [
        {"role": "system", "content": CONDENSE_SYSTEM},
        {
            "role": "user",
            "content": f"History (visitor messages):\n{history_block}\n\n"
            f"Language: {language}\nFollow-up: {question}",
        },
    ]
    try:
        condensed = model.complete(messages, json_mode=False, max_tokens=120).strip()
    except ProviderError:
        return None
    if not condensed or "\n" in condensed or len(condensed) > 500:
        return None
    return condensed


def translate_query(
    model: ChatModel,
    *,
    question: str,
    target_language: str,
) -> str | None:
    """Cross-script search bridge (P4-00, ADR-014): translate the question
    into the bot's primary content language with ONE ChatModel call so the
    fallback retrieval pass can keyword-match it. Any failure keeps the raw
    question — the fallback pass still tries it."""
    if not question.strip():
        return None
    language_name = LANGUAGE_NAMES.get(target_language, "English")
    messages = [
        {
            "role": "system",
            "content": TRANSLATE_SYSTEM_TEMPLATE.format(language_name=language_name),
        },
        {"role": "user", "content": question},
    ]
    try:
        translated = model.complete(messages, json_mode=False, max_tokens=120).strip()
    except ProviderError:
        return None
    if not translated or "\n" in translated or len(translated) > 500:
        return None
    return translated


def _parse_reply(raw: str, evidence: list[RetrievedChunk]) -> tuple[str, bool, list[UUID]] | None:
    """Strict output contract: {"answer", "can_answer", "sources"} (docs/14 §6)."""
    try:
        payload = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    answer = payload.get("answer")
    can_answer = payload.get("can_answer")
    sources = payload.get("sources", [])
    if not isinstance(answer, str) or not answer.strip():
        return None
    if not isinstance(can_answer, bool):
        return None
    if not isinstance(sources, list) or len(sources) > 8:
        return None
    valid_ids = {str(chunk.chunk_id) for chunk in evidence}
    kept: list[UUID] = []
    for value in sources:
        if isinstance(value, str) and value in valid_ids:
            chunk_id = UUID(value)
            if chunk_id not in kept:
                kept.append(chunk_id)
    if can_answer and not kept:
        # A grounded "yes" without any valid citation is a fallback case.
        return None
    return answer.strip(), can_answer, kept


def chat_answer(
    db: OrmSession,
    *,
    tenant_id: UUID,
    bot: Bot,
    question: str,
    history: list[str] | None = None,
    language_hint: str | None = None,
    model: ChatModel,
    settings: Settings | None = None,
) -> ChatReply:
    settings = settings or Settings()
    history = [message for message in (history or []) if message.strip()][-6:]

    language = (
        detect_language(question)
        or (language_hint if language_hint in ("en", "ar") else None)
        or _default_answer_language(bot)
    )

    # 1) Rule routing (never a model call).
    routed = route(
        question,
        language,
        handoff_enabled=bool(_config_get(bot, "handoff_enabled", True)),
    )
    if routed is not None:
        contact = _support_contact(bot)
        if routed.kind == "smalltalk":
            text = _welcome_for(bot, language) or prompts.canned(
                "cannot_confirm", language, support_contact=contact
            )
        else:
            text = prompts.canned("handoff", language, support_contact=contact)
        return ChatReply(
            answer=text,
            can_answer=routed.kind != "handoff",
            needs_human=routed.needs_human,
            language=language,
            kind=routed.kind,
        )

    # 2) Follow-up condensation (only with history; failure keeps the raw text).
    condensed = condense(model, history=history, question=question, language=language)

    # 3) Retrieval on the condensed (or raw) question.
    revision_id = bot.published_revision_id
    always_include = _config_get(bot, "always_include_document_ids", [])
    if not isinstance(always_include, list):
        always_include = []
    retrieval: RetrievalResult | None = None
    evidence: list[RetrievedChunk] = []
    if revision_id is not None:
        retrieval = retrieve(
            db,
            tenant_id=tenant_id,
            bot_id=bot.id,
            revision_id=revision_id,
            question=condensed or question,
            question_language=language,
            bot_primary_language=_default_answer_language(bot),
            settings=settings,
            always_include_document_ids={str(value) for value in always_include},
            # Cross-script bridge (P4-00): translate with ONE model call only
            # when the language pass is empty and the languages differ.
            translate_query=lambda raw, target: translate_query(
                model, question=raw, target_language=target
            ),
        )
        evidence = retrieval.evidence

    if not evidence:
        contact = _support_contact(bot)
        return ChatReply(
            answer=prompts.canned("cannot_confirm", language, support_contact=contact),
            can_answer=False,
            needs_human=True,
            language=language,
            kind="cannot_confirm",
            condensed_question=condensed,
            used_fallback=bool(retrieval and retrieval.used_fallback),
        )

    # 4) Build the prompt: evidence as DATA; question (plus condensed note).
    block = prompts.evidence_block(
        [
            (
                str(chunk.chunk_id),
                f"{chunk.title}"
                + (f" — {chunk.heading}" if chunk.heading else "")
                + (f" ({chunk.source_url})" if chunk.source_url else ""),
                chunk.text,
            )
            for chunk in evidence
        ]
    )
    system = prompts.system_prompt(
        assistant_name=str(_config_get(bot, "assistant_name", "") or ""),
        business_name=str(_config_get(bot, "business_name", "") or ""),
        business_description=str(_config_get(bot, "business_description", "") or ""),
        support_contact=_support_contact(bot),
        language=language,
        evidence_block=block,
    )
    user_text = question
    extra: list[str] = []
    if condensed not in (None, question):
        extra.append(f"(Standalone search query: {condensed})")
    if (
        condensed is None
        and retrieval is not None
        and retrieval.used_fallback
        and retrieval.fallback_query
    ):
        # Cross-script case (P4-00): the fallback pass searched the primary
        # content language with the translated query — give the model the
        # actual search terms so the answer stays verifiable, not a translation.
        extra.append(f"(Search query in the knowledge-base language: {retrieval.fallback_query})")
    if extra:
        user_text = f"{question}\n\n" + "\n".join(extra)
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_text},
    ]

    # 5) Model call + strict validation; every failure becomes a canned turn.
    contact = _support_contact(bot)
    try:
        raw = model.complete(messages, json_mode=True, max_tokens=settings.chat_max_tokens)
        parsed = _parse_reply(raw, evidence)
    except ProviderError:
        parsed = None
    if parsed is None:
        return ChatReply(
            answer=prompts.canned("busy", language, support_contact=contact),
            can_answer=False,
            needs_human=True,
            language=language,
            kind="busy",
            condensed_question=condensed,
            used_fallback=bool(retrieval and retrieval.used_fallback),
        )
    answer, can_answer, chunk_ids = parsed
    by_id = {chunk.chunk_id: chunk for chunk in evidence}
    citations = [
        {
            "chunk_id": str(chunk_id),
            "title": by_id[chunk_id].title,
            "heading": by_id[chunk_id].heading,
            "source_url": by_id[chunk_id].source_url,
            "page_ref": by_id[chunk_id].page_ref,
        }
        for chunk_id in chunk_ids
    ]
    return ChatReply(
        answer=answer,
        can_answer=can_answer,
        needs_human=not can_answer,
        language=language,
        kind="answer",
        citations=citations,
        condensed_question=condensed,
        used_fallback=bool(retrieval and retrieval.used_fallback),
    )
