"""Chat service (docs/14 §6): grounded answers with a strict output contract.

Pipeline: detect language → rule routing (conversational/handoff) → optional
follow-up condensation → retrieval (P3-01, one retry on a condensed query
when the first pass is refused and history exists) → ChatModel call in strict JSON
mode → validate/repair → localized fallbacks (never a stack trace).

Business facts only come from the knowledge base (via retrieval); the tiger
prompt template is versioned (`prompts.PROMPT_TEMPLATE_VERSION`) and never
contains knowledge content.

The reply marks `needs_human` when the model says `can_answer=false` or the
chain failed — the handoff machine (P5) consumes that flag.
"""

import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.chat import prompts
from app.chat.deadline import TurnBudget
from app.chat.history import HistoryMessage, normalize_history, visitor_texts
from app.chat.providers import ChatModel, OpenAICompatibleModel, ProviderError
from app.chat.routing import order_account_requested, route, tokenize
from app.chat.tracing import TracedModel
from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.db.models import Bot, Tenant
from app.knowledge.language import detect_language
from app.knowledge.service import always_include_document_ids
from app.quotas.plans import PLAN_LABELS
from app.retrieval.gate import GateDecision, relevance_gate, select_evidence
from app.retrieval.hybrid import retrieve_hybrid as retrieve
from app.retrieval.query import content_terms
from app.retrieval.service import RetrievalResult, RetrievedChunk
from app.retrieval.trace import (
    candidate_trace,
    document_trace,
    near_miss_topics,
    refusal_diagnosis,
    rejected_candidates,
)

MAX_TOKENS = 700
logger = logging.getLogger(__name__)

# History alone is not a reason to spend a rewrite. A message is condensed when
# it opens like a follow-up, points back at something earlier (a pronoun or
# "the same/other one"), or carries fewer than two content terms once
# stop-words are removed ("tell me more", "كم سعره", "ماذا عن الأحد").
FOLLOW_UP = re.compile(
    r"^(?:and\b|what about\b|how about\b|also\b|then\b|that\b|those\b|it\b|they\b|"
    r"وماذا|ومتى|وهل|وبالنسبة|وكام|وكم|و يوم|طيب)|\b(?:it|them|those|that one)\b",
    re.IGNORECASE,
)
# Whole-token back-references. "that/this/other/another/more" only count in a
# short message: they are ordinary words in a self-contained question.
BACK_REFERENCES = frozenset(
    {"it", "its", "they", "them", "their", "those", "these", "one", "ones", "same", "he", "she"}
    | {"هذا", "هذه", "هذي", "ذلك", "تلك", "نفس", "الاخر", "الاخرى"}
)
WEAK_BACK_REFERENCES = frozenset({"that", "this", "other", "another", "more", "also"})
# Arabic question words are not stop-words for retrieval, but they say nothing
# about the topic: "كم سعره" has one content term, not two.
ARABIC_QUESTION_WORDS = frozenset({"كم", "متى", "اين", "وين", "كيف", "ما", "هل"})
MIN_CONTENT_TERMS = 2
WEAK_REFERENCE_MAX_TERMS = 3


def rewrite_reason(question: str, history: list[str]) -> str | None:
    """Why a follow-up should be condensed (None: search the message as written)."""
    if not history:
        return None
    text = question.strip()
    if FOLLOW_UP.search(text):
        return "follow_up"
    tokens = tokenize(text)
    terms = [term for term in content_terms(text) if term not in ARABIC_QUESTION_WORDS]
    if any(token in BACK_REFERENCES for token in tokens):
        return "back_reference"
    if len(terms) < MIN_CONTENT_TERMS:
        return "few_content_terms"
    if len(terms) <= WEAK_REFERENCE_MAX_TERMS and any(
        token in WEAK_BACK_REFERENCES for token in tokens
    ):
        return "back_reference"
    return None


def needs_rewrite(question: str, history: list[str]) -> bool:
    return rewrite_reason(question, history) is not None


def rewrite_plan_allowed(plan: str | None, settings: Settings) -> bool:
    """Is the rewrite enabled for this plan label?

    ``chat_rewrite_plans`` lists the plans that get it. An empty list or ``*``
    means every plan. A label that is not one of the platform's known plans (or
    a missing one) is never treated as "not listed": the list can only switch
    off plans it was written for, so a new label cannot silently lose rewrite."""
    allowed = settings.chat_rewrite_plans
    if not allowed or "*" in allowed:
        return True
    if plan is None or plan not in PLAN_LABELS:
        return True
    return plan in allowed


CONDENSE_SYSTEM = (
    "You condense a visitor follow-up into a standalone search query in the "
    "visitor's language. Use the history only to resolve pronouns and "
    "ellipsis. Output ONE line: the standalone query, nothing else."
)

LANGUAGE_NAMES = prompts.LANGUAGE_NAMES

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
    # "smalltalk" | "handoff" | "answer" | "busy" | "cannot_confirm" | "invalid_output"
    # busy = the provider failed; invalid_output = the model answered but the reply
    # was unusable (not a provider failure, never a handoff).
    kind: str
    # Validated citations (subset of retrieved chunks, in retrieval order).
    citations: list[dict[str, str | None]] = field(default_factory=list)
    condensed_question: str | None = None
    used_fallback: bool = False  # cross-language retrieval fallback
    trace: dict[str, object] = field(default_factory=dict)


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


def _config_text(bot: Bot, key: str) -> str:
    value = _config_get(bot, key, "")
    return value.strip() if isinstance(value, str) else ""


def conversational_reply(bot: Bot, intent: str, language: str) -> str:
    """The reply to a greeting/thanks/farewell/identity/capability/how-are-you
    message. Built from the bot's settings only (never the model, never the
    knowledge base), in the visitor's language."""
    if intent == "greeting":
        return _welcome_for(bot, language)
    questions = _config_get(bot, "opening_questions", [])
    return prompts.meta_reply(
        intent,
        language,
        assistant_name=_config_text(bot, "assistant_name"),
        business_name=_config_text(bot, "business_name"),
        business_description=_config_text(bot, "business_description"),
        opening_questions=[q for q in questions if isinstance(q, str)]
        if isinstance(questions, list)
        else [],
        support_contact=_support_contact(bot),
    )


def refusal_text(bot: Bot, language: str, topics: list[str]) -> str:
    """The canned cannot-confirm text, with up to three suggested topics when
    the gate had near-miss candidates."""
    if topics:
        separator = "، " if language == "ar" else ", "
        return prompts.canned(
            "cannot_confirm_topics",
            language,
            support_contact=_support_contact(bot),
            topics=separator.join(topics),
        )
    return prompts.canned("cannot_confirm", language, support_contact=_support_contact(bot))


def _default_answer_language(bot: Bot) -> str:
    configured = _config_get(bot, "default_language", "en")
    return configured if configured in ("en", "ar") else "en"


def knowledge_language(bot: Bot) -> str:
    """The knowledge base's primary language: ``knowledge_language`` when set,
    else ``default_language`` (which only controls the widget UI otherwise)."""
    configured = _config_get(bot, "knowledge_language", None)
    return configured if configured in ("en", "ar") else _default_answer_language(bot)


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
    except ApiError as error:  # optional step: a spent token cap skips it
        if error.code != "QUOTA_EXCEEDED":
            raise
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
    except ApiError as error:  # optional step: a spent token cap skips it
        if error.code != "QUOTA_EXCEEDED":
            raise
        return None
    if not translated or "\n" in translated or len(translated) > 500:
        return None
    return translated


@dataclass
class ParsedReply:
    answer: str
    can_answer: bool
    sources: list[UUID]  # valid, de-duplicated evidence ids
    model_source_count: int  # what the model listed, before validation


def _parse_reply(raw: str, evidence: list[RetrievedChunk]) -> ParsedReply | None:
    return _check_reply(raw, evidence)[0]


def _check_reply(raw: str, evidence: list[RetrievedChunk]) -> tuple[ParsedReply | None, str | None]:
    """Strict output contract: {"answer", "can_answer", "sources"} (docs/14 §6).

    Returns the parsed reply, or None plus why: ``parse_failed`` (not the JSON
    shape, empty answer) or ``no_valid_source`` (a "yes" with no valid citation)."""
    try:
        payload = json.loads(raw)
    except ValueError:
        return None, "parse_failed"
    if not isinstance(payload, dict):
        return None, "parse_failed"
    answer = payload.get("answer")
    can_answer = payload.get("can_answer")
    sources = payload.get("sources", [])
    if not isinstance(answer, str) or not answer.strip():
        return None, "parse_failed"
    if not isinstance(can_answer, bool):
        return None, "parse_failed"
    if not isinstance(sources, list) or len(sources) > 8:
        return None, "parse_failed"
    valid_ids = {str(chunk.chunk_id) for chunk in evidence}
    kept: list[UUID] = []
    for value in sources:
        if isinstance(value, str) and value in valid_ids:
            chunk_id = UUID(value)
            if chunk_id not in kept:
                kept.append(chunk_id)
    if can_answer and not kept:
        # A grounded "yes" without any valid citation is unusable output.
        return None, "no_valid_source"
    return ParsedReply(answer.strip(), can_answer, kept, len(sources)), None


def reconcile_refusal(
    bot: Bot,
    *,
    language: str,
    condensed: str | None,
    used_fallback: bool,
    trace: dict[str, object],
) -> ChatReply:
    """The single rule for a model that says ``can_answer=false`` (buffered and
    streamed turns both end here): the reply is the canned cannot_confirm text,
    with no citations, and a human is needed. Model text and sources are dropped."""
    return ChatReply(
        answer=prompts.canned("cannot_confirm", language, support_contact=_support_contact(bot)),
        can_answer=False,
        needs_human=True,
        language=language,
        kind="cannot_confirm",
        condensed_question=condensed,
        used_fallback=used_fallback,
        trace=trace,
    )


def invalid_output_reply(
    bot: Bot,
    *,
    language: str,
    reason: str,
    condensed: str | None,
    used_fallback: bool,
    trace: dict[str, object],
) -> ChatReply:
    """The model answered but the reply was unusable: canned cannot_confirm text,
    no citations, a human is needed. Not a provider failure (no busy text, no
    handoff, no provider_error); ``reason`` goes to the staff trace."""
    trace["invalid_output_reason"] = reason
    return ChatReply(
        answer=prompts.canned("cannot_confirm", language, support_contact=_support_contact(bot)),
        can_answer=False,
        needs_human=True,
        language=language,
        kind="invalid_output",
        condensed_question=condensed,
        used_fallback=used_fallback,
        trace=trace,
    )


def order_account_handoff_applies(bot: Bot, question: str) -> bool:
    """After retrieval found nothing usable: is this the visitor's own order or
    account question, with handoff enabled for the bot?"""
    return bool(_config_get(bot, "handoff_enabled", True)) and order_account_requested(question)


def post_retrieval_handoff(
    bot: Bot,
    *,
    language: str,
    condensed: str | None,
    used_fallback: bool,
    trace: dict[str, object],
) -> ChatReply:
    """Nothing could be answered (no evidence, refusal or unusable output) and
    the message is an order/account question: hand off, not the plain
    cannot_confirm text. The inbox decision turns this kind into order_account."""
    trace["routing_stage"] = "post_retrieval"
    trace["routed_handoff_reason"] = "order_account"
    trace["handoff_reason"] = "order_account"
    return ChatReply(
        answer=prompts.canned("handoff", language, support_contact=_support_contact(bot)),
        can_answer=False,
        needs_human=True,
        language=language,
        kind="handoff",
        condensed_question=condensed,
        used_fallback=used_fallback,
        trace=trace,
    )


def _set_call_timeout(model: ChatModel, seconds: float) -> None:
    """Cap the next provider call at ``seconds`` (the turn budget, #84)."""
    current: ChatModel | None = model
    while current is not None:
        if isinstance(current, OpenAICompatibleModel):
            current.call_timeout = seconds
            return
        current = vars(current).get("inner")


def _skip_step(trace: dict[str, object], step: str) -> None:
    skipped = trace.setdefault("skipped_steps", [])
    if isinstance(skipped, list):
        skipped.append(step)  # not enough turn budget left for an optional step


def _provider_client(model: ChatModel) -> ChatModel:
    """The wrapped client that owns the ``blocked`` state, if there is one.

    TracedModel and MeteredChatModel wrap the real client; walk down to it."""
    current = model
    while not hasattr(current, "blocked"):
        deeper = getattr(current, "inner", None)
        if deeper is None:
            break
        current = deeper
    return current


def _provider_status(model: ChatModel) -> str:
    """Blocked (auth/payment) vs failed, read from the underlying client."""
    return "blocked" if getattr(_provider_client(model), "blocked", False) else "failed"


def _provider_http_status(model: ChatModel) -> int | None:
    """The last real HTTP status the provider answered with (None: no response)."""
    status = getattr(_provider_client(model), "last_http_status", None)
    return status if isinstance(status, int) and not isinstance(status, bool) else None


def _provider_attempts(model: ChatModel) -> list[dict[str, object]]:
    """What the underlying client did on its latest call, one record per model
    tried (status, sanitized error code, finish reason, content state)."""
    log = getattr(_provider_client(model), "attempt_log", None)
    return [dict(item) for item in log] if isinstance(log, list) else []


def _generation_max_tokens(model: ChatModel, settings: Settings) -> int:
    """Completion cap: the free chain gets more headroom for reasoning models."""
    free = getattr(_provider_client(model), "free_only", False) is True
    return settings.chat_max_tokens_free if free else settings.chat_max_tokens


def _attempts_for_log(attempts: list[dict[str, object]]) -> str:
    """A compact, key-free line: ``model:outcome:http:code`` per attempt."""
    return ",".join(
        f"{item.get('model')}:{item.get('outcome')}:{item.get('http_status')}:"
        f"{item.get('error_code') or item.get('content') or '-'}"
        for item in attempts
    )


def chat_answer(
    db: OrmSession,
    *,
    tenant_id: UUID,
    bot: Bot,
    question: str,
    history: list[str] | list[HistoryMessage] | None = None,
    language_hint: str | None = None,
    model: ChatModel,
    settings: Settings | None = None,
    history_skipped: int = 0,
    post_check: Callable[[str, list[RetrievedChunk]], bool] | None = None,
    preview_revision_id: UUID | None = None,
    channel_style: str = "",
    campaign_context: str = "",
) -> ChatReply:
    """``preview_revision_id``: staff-playground draft preview. When set, retrieval
    reads that revision (validated against tenant + bot as a draft); None keeps
    the published pointer, which is the only thing the widget path ever uses."""
    settings = settings or get_settings()
    budget = TurnBudget.start(settings)
    answering_revision = preview_revision_id or bot.published_revision_id
    trace: dict[str, object] = {
        "retrieval_mode": "not_run",
        "gate": "not_run",
        "chunks": [],
        "rewrite_used": False,
        "model": None,
        "tokens": None,
        "cost_usd": None,
        "post_check": "not_configured",
        "prompt_version": prompts.PROMPT_TEMPLATE_VERSION,
        "history_count": 0,
        "history_skipped_count": history_skipped,
        "parsed_ok": False,
        "model_can_answer": None,
        "model_source_count": 0,
        "kept_source_count": 0,
        "reconciled": False,
        "skipped_steps": [],
        # Why-this-answer facts for staff (no prompt text, no raw model output).
        "revision_id": str(answering_revision) if answering_revision else None,
        "revision_kind": "draft" if preview_revision_id else "published",
        "tier": getattr(bot, "tier", None),
        "generation_provider": getattr(bot, "generation_provider", None),
        "applied_language": None,
        "retrieval_query": None,
        "fallback_query": None,
        "rewrite_text": None,
        "rewrite_trigger": None,
        "rewrite_retry": False,
        "rewrite_skipped": None,
        "meta_intent": None,
        "suggested_topics": [],
        "handoff_reason": None,
        "routing_stage": None,  # "pre_retrieval" | "post_retrieval" when routed to a handoff
        "routed_handoff_reason": None,
        "rejected_candidates": [],
        "refusal_diagnosis": None,
    }
    model = TracedModel(model, trace)
    history_turns = normalize_history(history)
    trace["history_count"] = len(visitor_texts(history_turns))
    history_visitor = visitor_texts(history_turns)[-6:]

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
            trace["routing_stage"] = "pre_retrieval"
            trace["meta_intent"] = routed.intent
            text = conversational_reply(bot, routed.intent or "greeting", language)
        else:
            text = prompts.canned("handoff", language, support_contact=contact)
            trace["routing_stage"] = "pre_retrieval"
            trace["routed_handoff_reason"] = routed.reason
            trace["handoff_reason"] = routed.reason
        return ChatReply(
            answer=text,
            can_answer=routed.kind != "handoff",
            needs_human=routed.needs_human,
            language=language,
            kind=routed.kind,
            trace=trace,
        )

    # 2) Rewrite context-dependent follow-ups (and, below, a refused first pass).
    condensed = None
    plan_checked: list[bool] = []

    def rewrite_allowed() -> bool:
        """Rewrite switched on for this deployment and this tenant's plan (one lookup)."""
        if not settings.chat_rewrite_enabled:
            return False
        if not plan_checked:
            plan = db.scalar(
                select(Tenant.plan_label)
                .join(Bot, Bot.tenant_id == Tenant.id)
                .where(Tenant.id == tenant_id, Bot.id == bot.id)
            )
            allowed = rewrite_plan_allowed(plan, settings)
            plan_checked.append(allowed)
            if not allowed:
                trace["rewrite_skipped"] = "plan"
        return plan_checked[0]

    trigger = rewrite_reason(question, history_visitor)

    def run_condense(reason: str) -> str | None:
        if not budget.optional_allowed():
            _skip_step(trace, "rewrite")
            return None
        trace["rewrite_trigger"] = reason
        _set_call_timeout(model, budget.aux_timeout())
        return condense(model, history=history_visitor, question=question, language=language)

    if trigger is not None and rewrite_allowed():
        condensed = run_condense(trigger)
    trace["rewrite_used"] = condensed is not None
    trace["rewrite_text"] = condensed

    # 3) Retrieval on the condensed (or raw) question.
    revision_id = answering_revision
    retrieval: RetrievalResult | None = None
    decision: GateDecision | None = None
    evidence: list[RetrievedChunk] = []

    def translate_within_budget(raw: str, target: str) -> str | None:
        if not budget.optional_allowed():
            _skip_step(trace, "translation")
            return None
        _set_call_timeout(model, budget.aux_timeout())
        return translate_query(model, question=raw, target_language=target)

    def search(query: str) -> tuple[RetrievalResult, GateDecision, list[RetrievedChunk]]:
        assert revision_id is not None
        found = retrieve(
            db,
            tenant_id=tenant_id,
            bot_id=bot.id,
            revision_id=revision_id,
            question=query,
            question_language=language,
            bot_primary_language=knowledge_language(bot),
            settings=settings,
            always_include_document_ids=always_include_document_ids(db, bot, revision_id, settings),
            channel=str(getattr(model, "channel", "website")),
            # Cross-script bridge (P4-00): translate with ONE model call only
            # when the language pass is empty and the languages differ.
            translate_query=translate_within_budget,
            embed_timeout=budget.embed_timeout(),
            preview=preview_revision_id is not None,
        )
        verdict = relevance_gate(found, settings)
        return found, verdict, select_evidence(verdict, settings)

    if revision_id is not None:
        retrieval, decision, evidence = search(condensed or question)
        if (
            not evidence
            and condensed is None
            and trigger is None
            and history_visitor
            and rewrite_allowed()
        ):
            # One more try: a refused message that was searched as written may
            # be a follow-up the trigger did not recognise.
            retry_query = run_condense("retry_after_refusal")
            if retry_query is not None and retry_query.casefold() != question.strip().casefold():
                condensed = retry_query
                trace["rewrite_used"] = True
                trace["rewrite_text"] = condensed
                trace["rewrite_retry"] = True
                retrieval, decision, evidence = search(condensed)
        trace.update(
            retrieval_mode=retrieval.mode,
            degradation_reason=retrieval.degradation_reason,
            embedding_model=retrieval.embedding_model,
            embedding_tokens=retrieval.embedding_tokens,
            embedding_cost_usd=(
                str(retrieval.embedding_cost_usd)
                if retrieval.embedding_cost_usd is not None
                else None
            ),
            gate="passed" if evidence else "refused",
            applied_language=retrieval.applied_language,
            retrieval_query=condensed or question,
            fallback_query=retrieval.fallback_query,
            vector_floor=decision.vector_floor,
            fts_minimum=decision.fts_minimum,
            chunks=candidate_trace(retrieval, decision, evidence),
            documents=document_trace(decision, evidence),
        )
        logger.info(
            "rag.gate tenant=%s bot=%s mode=%s accepted=%s rejected=%s rewrite=%s",
            tenant_id,
            bot.id,
            retrieval.mode,
            len(evidence),
            len(decision.rejected_ids),
            condensed is not None,
        )

    if not evidence:
        trace["gate"] = "refused"
        topics: list[str] = []
        if retrieval is not None and decision is not None:
            trace["rejected_candidates"] = rejected_candidates(retrieval, decision)
            trace["refusal_diagnosis"] = refusal_diagnosis(retrieval, decision)
            topics = near_miss_topics(retrieval)
        if order_account_handoff_applies(bot, question):
            return post_retrieval_handoff(
                bot,
                language=language,
                condensed=condensed,
                used_fallback=bool(retrieval and retrieval.used_fallback),
                trace=trace,
            )
        trace["suggested_topics"] = topics
        return ChatReply(
            answer=refusal_text(bot, language, topics),
            can_answer=False,
            needs_human=True,
            language=language,
            kind="cannot_confirm",
            condensed_question=condensed,
            used_fallback=bool(retrieval and retrieval.used_fallback),
            trace=trace,
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
        tone_and_rules=str(getattr(bot, "tone_and_rules", None) or ""),
        channel_style=channel_style,
        campaign_context=campaign_context,
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
        *({"role": turn["role"], "content": turn["content"]} for turn in history_turns),
        {"role": "user", "content": user_text},
    ]

    # 5) Model call + strict validation; every failure becomes a canned turn.
    contact = _support_contact(bot)
    invalid_reason: str | None = None
    try:
        _set_call_timeout(model, budget.generation_timeout())
        raw = model.complete(
            messages,
            json_mode=True,
            max_tokens=_generation_max_tokens(model, settings),
        )
        parsed, invalid_reason = _check_reply(raw, evidence)
        trace["parsed_ok"] = parsed is not None
        if parsed is not None:
            trace["model_can_answer"] = parsed.can_answer
            trace["model_source_count"] = parsed.model_source_count
        if parsed and parsed.can_answer and post_check is not None:
            accepted = post_check(parsed.answer, evidence)
            trace["post_check"] = "passed" if accepted else "rejected"
            if not accepted:
                parsed, invalid_reason = None, "post_check_rejected"
    except ProviderError:
        parsed = None
        # Staff-visible failure detail (Playground trace): per-attempt status,
        # sanitized provider error code and finish reason — never a key,
        # header, prompt or provider response body.
        status = _provider_status(model)
        attempts = _provider_attempts(model)
        last = attempts[-1] if attempts else {}
        detail: dict[str, object] = {
            "status": status,
            "http_status": last.get("http_status", _provider_http_status(model)),
            "model": last.get("model") or trace.get("model"),
            "error_code": last.get("error_code"),
            "finish_reason": last.get("finish_reason"),
            "content": last.get("content"),
            "attempts": attempts,
        }
        trace["provider_error"] = detail
        logger.warning(
            "chat.provider_failure tenant=%s bot=%s model=%s status=%s tier=%s "
            "http_status=%s error_code=%s attempts=%s",
            tenant_id,
            bot.id,
            detail["model"],
            status,
            getattr(bot, "tier", None),
            detail["http_status"],
            detail["error_code"],
            _attempts_for_log(attempts),
        )
    else:
        attempts = _provider_attempts(model)
        if len(attempts) > 1:
            trace["provider_attempts"] = attempts  # an earlier model failed, a later one answered
    if parsed is None and invalid_reason is not None:
        if order_account_handoff_applies(bot, question):
            trace["invalid_output_reason"] = invalid_reason
            return post_retrieval_handoff(
                bot,
                language=language,
                condensed=condensed,
                used_fallback=bool(retrieval and retrieval.used_fallback),
                trace=trace,
            )
        return invalid_output_reply(
            bot,
            language=language,
            reason=invalid_reason,
            condensed=condensed,
            used_fallback=bool(retrieval and retrieval.used_fallback),
            trace=trace,
        )
    if parsed is None:
        return ChatReply(
            answer=prompts.canned("busy", language, support_contact=contact),
            can_answer=False,
            needs_human=True,
            language=language,
            kind="busy",
            condensed_question=condensed,
            used_fallback=bool(retrieval and retrieval.used_fallback),
            trace=trace,
        )
    chunk_ids = parsed.sources
    if not parsed.can_answer:
        trace["reconciled"] = True
        if order_account_handoff_applies(bot, question):
            return post_retrieval_handoff(
                bot,
                language=language,
                condensed=condensed,
                used_fallback=bool(retrieval and retrieval.used_fallback),
                trace=trace,
            )
        return reconcile_refusal(
            bot,
            language=language,
            condensed=condensed,
            used_fallback=bool(retrieval and retrieval.used_fallback),
            trace=trace,
        )
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
    trace["kept_source_count"] = len(citations)
    return ChatReply(
        answer=parsed.answer,
        can_answer=True,
        needs_human=False,
        language=language,
        kind="answer",
        citations=citations,
        condensed_question=condensed,
        used_fallback=bool(retrieval and retrieval.used_fallback),
        trace=trace,
    )
