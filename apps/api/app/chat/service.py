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
from app.chat.routing import route
from app.chat.tracing import TracedModel
from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.db.models import Bot, Tenant
from app.knowledge.language import detect_language
from app.retrieval.gate import relevance_gate, select_evidence
from app.retrieval.hybrid import retrieve_hybrid as retrieve
from app.retrieval.service import RetrievalResult, RetrievedChunk
from app.retrieval.trace import candidate_trace, document_trace, rejected_candidates

MAX_TOKENS = 700
logger = logging.getLogger(__name__)

# Conservative heuristic: history alone is not a reason to spend a rewrite.
FOLLOW_UP = re.compile(
    r"^(?:and\b|what about\b|how about\b|also\b|then\b|that\b|those\b|it\b|they\b|"
    r"وماذا|ومتى|وهل|وبالنسبة|وكام|وكم|و يوم|طيب)|\b(?:it|them|those|that one)\b",
    re.IGNORECASE,
)


def needs_rewrite(question: str, history: list[str]) -> bool:
    return bool(history and FOLLOW_UP.search(question.strip()))


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
) -> ChatReply:
    settings = settings or get_settings()
    budget = TurnBudget.start(settings)
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
        "revision_id": str(bot.published_revision_id) if bot.published_revision_id else None,
        "tier": getattr(bot, "tier", None),
        "generation_provider": getattr(bot, "generation_provider", None),
        "applied_language": None,
        "retrieval_query": None,
        "fallback_query": None,
        "rewrite_text": None,
        "handoff_reason": None,
        "rejected_candidates": [],
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
            trace=trace,
        )

    # 2) Rewrite only context-dependent follow-ups, if enabled for this plan.
    condensed = None
    if settings.chat_rewrite_enabled and needs_rewrite(question, history_visitor):
        plan = db.scalar(
            select(Tenant.plan_label)
            .join(Bot, Bot.tenant_id == Tenant.id)
            .where(Tenant.id == tenant_id, Bot.id == bot.id)
        )
        if plan in settings.chat_rewrite_plans:
            if budget.optional_allowed():
                _set_call_timeout(model, budget.aux_timeout())
                condensed = condense(
                    model, history=history_visitor, question=question, language=language
                )
            else:
                _skip_step(trace, "rewrite")
    trace["rewrite_used"] = condensed is not None
    trace["rewrite_text"] = condensed

    # 3) Retrieval on the condensed (or raw) question.
    revision_id = bot.published_revision_id
    always_include = _config_get(bot, "always_include_document_ids", [])
    if not isinstance(always_include, list):
        always_include = []
    retrieval: RetrievalResult | None = None
    evidence: list[RetrievedChunk] = []

    def translate_within_budget(raw: str, target: str) -> str | None:
        if not budget.optional_allowed():
            _skip_step(trace, "translation")
            return None
        _set_call_timeout(model, budget.aux_timeout())
        return translate_query(model, question=raw, target_language=target)

    if revision_id is not None:
        retrieval = retrieve(
            db,
            tenant_id=tenant_id,
            bot_id=bot.id,
            revision_id=revision_id,
            question=condensed or question,
            question_language=language,
            bot_primary_language=knowledge_language(bot),
            settings=settings,
            always_include_document_ids={str(value) for value in always_include},
            channel=str(getattr(model, "channel", "website")),
            # Cross-script bridge (P4-00): translate with ONE model call only
            # when the language pass is empty and the languages differ.
            translate_query=translate_within_budget,
            embed_timeout=budget.embed_timeout(),
        )
        decision = relevance_gate(retrieval, settings)
        evidence = select_evidence(decision, settings)
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
        if retrieval is not None:
            trace["rejected_candidates"] = rejected_candidates(retrieval, decision)
        contact = _support_contact(bot)
        return ChatReply(
            answer=prompts.canned("cannot_confirm", language, support_contact=contact),
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
        raw = model.complete(messages, json_mode=True, max_tokens=settings.chat_max_tokens)
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
        # Staff-visible failure detail (Playground trace): status + model name
        # only — never a key, header, prompt or provider response body.
        status = _provider_status(model)
        detail = {
            "status": status,
            "http_status": _provider_http_status(model),
            "model": trace.get("model"),
        }
        trace["provider_error"] = detail
        logger.warning(
            "chat.provider_failure tenant=%s bot=%s model=%s status=%s tier=%s",
            tenant_id,
            bot.id,
            detail["model"],
            status,
            getattr(bot, "tier", None),
        )
    if parsed is None and invalid_reason is not None:
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
