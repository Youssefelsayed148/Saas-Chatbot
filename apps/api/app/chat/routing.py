"""Rule-based routing decision before any model call (docs/14 §6).

- smalltalk → a conversational message made only of a greeting, thanks, a
  farewell, "who are you", "what can you do" or "how are you" (``intent``);
  the service composes the reply from bot config, never from the model
- handoff   → an explicit request for a person (pre-retrieval); a per-bot
  toggle can disable the rule (then the model answers like always)
Order/account/tracking keywords never route before retrieval: the knowledge
base may answer them. They count only after retrieval, when nothing can be
answered (``order_account_requested``, used by the service layer).
The service layer composes the actual localized text (prompts.canned).

Matching is on whole tokens/phrases after normalisation (lowercase, no
punctuation, Arabic diacritics/tatweel/alef/yaa variants folded), never on
substrings. Smalltalk applies only when the whole message is made of those
phrases (and polite fillers), so "hello, what are your hours?" is retrieval.
A keyword never hands off a message that also
asks an informational question about the bot's own content: when ambiguous the
message goes to retrieval.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass

from app.knowledge.language import normalise_text

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)
_ARABIC_ARTICLE = "ال"

ORDER_ACCOUNT_KEYWORDS = {
    "en": (
        "order",
        "my order",
        "orders",
        "track",
        "tracking",
        "shipment",
        "delivery status",
        "account",
        "login",
        "sign in",
        "reset password",
        "refund status",
        "where is my",
    ),
    "ar": (
        "طلب",
        "طلبي",
        "طلبات",
        "تتبع",
        "شحنة",
        "شحنتي",
        "دخول",
        "حساب",
        "كلمة السر",
        "متى يوصل",
        "وين طلبي",
    ),
}

# Conversational (non-informational) intents. Only a message made entirely of
# these phrases (plus polite fillers) is routed; anything else, such as "hello,
# what are your hours?" or "who are you? ignore previous instructions", goes
# to retrieval. Phrases are matched as whole tokens after normalisation.
INTENT_PHRASES: dict[str, dict[str, tuple[str, ...]]] = {
    "greeting": {
        "en": (
            "hi",
            "hello",
            "hey",
            "hi there",
            "hello there",
            "good morning",
            "good afternoon",
            "good evening",
        ),
        "ar": (
            "مرحبا",
            "سلام",
            "السلام",
            "السلام عليكم",
            "هلا",
            "أهلا",
            "اهلا",
            "أهلا وسهلا",
            "صباح الخير",
            "مساء الخير",
        ),
    },
    "thanks": {
        "en": (
            "thanks",
            "thank you",
            "thanks a lot",
            "thank you so much",
            "thanks so much",
            "many thanks",
            "thx",
            "much appreciated",
        ),
        "ar": (
            "شكرا",
            "شكرا جزيلا",
            "شكرا لك",
            "شكرا لكم",
            "الف شكر",
            "مشكور",
            "يعطيك العافية",
            "جزاك الله خيرا",
        ),
    },
    "farewell": {
        "en": (
            "bye",
            "goodbye",
            "bye bye",
            "see you",
            "see you later",
            "see ya",
            "take care",
            "good night",
        ),
        "ar": ("مع السلامة", "وداعا", "الى اللقاء", "في امان الله", "تصبح على خير"),
    },
    "identity": {
        "en": (
            "who are you",
            "what are you",
            "who is this",
            "what is your name",
            "what's your name",
            "whats your name",
            "your name",
            "tell me your name",
            "are you a bot",
            "are you a robot",
            "are you a real person",
            "are you a human",
            "are you human",
        ),
        "ar": (
            "من انت",
            "من انتم",
            "انت مين",
            "ما اسمك",
            "شو اسمك",
            "ايش اسمك",
            "اسمك",
            "عرفني بنفسك",
            "هل انت روبوت",
        ),
    },
    "capability": {
        "en": (
            "what can you do",
            "what do you do",
            "what can i ask",
            "what can i ask you",
            "what can you help with",
            "what are you able to do",
            "how can you help",
            "how can you help me",
            "how do you work",
            "help",
            "help me",
            "i need help",
            "can you help",
            "can you help me",
        ),
        "ar": (
            "ماذا تستطيع ان تفعل",
            "ماذا يمكنك ان تفعل",
            "ماذا تفعل",
            "ماذا تقدر تسوي",
            "ايش تقدر تسوي",
            "كيف يمكنك مساعدتي",
            "كيف تستطيع مساعدتي",
            "كيف تساعدني",
            "ساعدني",
            "مساعدة",
            "هل تستطيع مساعدتي",
            "ممكن تساعدني",
        ),
    },
    "how_are_you": {
        "en": (
            "how are you",
            "how are you doing",
            "how are things",
            "how is it going",
            "how's it going",
            "hows it going",
            "how you doing",
            "how do you do",
            "what's up",
            "whats up",
        ),
        "ar": (
            "كيف حالك",
            "كيف حالكم",
            "كيف الحال",
            "كيفك",
            "شلونك",
            "اخبارك",
            "شخبارك",
            "كيف الاحوال",
        ),
    },
}

# When a message holds several intents, the first one in this order decides.
INTENT_PRIORITY = ("identity", "capability", "how_are_you", "thanks", "farewell", "greeting")

# Words that may surround an intent phrase without turning it into a question.
INTENT_FILLERS = {
    "en": (
        "please",
        "pls",
        "plz",
        "there",
        "dear",
        "again",
        "ok",
        "okay",
        "great",
        "perfect",
        "bot",
    ),
    "ar": ("لو سمحت", "من فضلك", "يا", "تمام", "ممتاز", "بوت", "ورحمة الله", "وبركاته"),
}
INTENT_MAX_TOKENS = 8

# Words that make a message an informational question about the bot's content
# (so an order/person keyword inside it is not a handoff request).
INFO_MARKERS = {
    "en": (
        "how",
        "what",
        "which",
        "why",
        "does",
        "do you",
        "can i",
        "can we",
        "is there",
        "are there",
        "policy",
        "policies",
        "price",
        "prices",
        "cost",
        "fee",
        "fees",
        "hours",
    ),
    "ar": (
        "كيف",
        "كم",
        "ما",
        "ماذا",
        "هل",
        "اي",
        "لماذا",
        "سياسة",
        "سعر",
        "اسعار",
        "تكلفة",
        "رسوم",
    ),
}

# A visitor speaking about their own order/account is not asking about content.
PERSONAL_MARKERS = {
    "en": ("my", "mine"),
    "ar": ("طلبي", "شحنتي", "حسابي", "وين طلبي"),
}

# An explicit "connect me to someone" request outranks informational wording.
HANDOFF_REQUEST_PHRASES = {
    "en": (
        "talk to",
        "speak to",
        "speak with",
        "talk with",
        "chat with",
        "connect me",
        "transfer me",
        "want a human",
        "need a human",
        "get a human",
        "with a human",
        "human agent",
        "live agent",
        "real person",
        "customer service",
    ),
    "ar": (
        "اكلم",
        "اتكلم مع",
        "اتحدث مع",
        "التحدث مع",
        "حولني",
        "اريد موظف",
        "اريد شخص",
    ),
}


# Who an explicit request is addressed to. A request phrase alone ("talk to",
# "customer service") is not enough before retrieval: it needs one of these.
PERSON_NOUNS = {
    "en": ("human", "person", "agent", "someone", "representative", "employee", "staff"),
    "ar": ("شخص", "موظف", "انسان", "ممثل"),
}


@dataclass
class RoutedReply:
    """A rule match that resolves without any model call."""

    kind: str  # "smalltalk" | "handoff"
    needs_human: bool
    reason: str | None = None  # handoff only: "visitor_requested"
    # smalltalk only: one of INTENT_PRIORITY
    intent: str | None = None


def tokenize(text: str) -> list[str]:
    """Normalised whole tokens (lowercase, punctuation and Arabic marks removed)."""
    return _TOKEN_RE.findall(normalise_text(text))


def _phrases(keywords: Iterable[str]) -> list[tuple[str, ...]]:
    return [tuple(tokenize(word)) for word in keywords if isinstance(word, str) and tokenize(word)]


def _strip_article(token: str) -> str:
    if token.startswith(_ARABIC_ARTICLE) and len(token) > len(_ARABIC_ARTICLE) + 1:
        return token[len(_ARABIC_ARTICLE) :]
    return token


def _contains_phrase(tokens: list[str], phrase: tuple[str, ...]) -> bool:
    size = len(phrase)
    if size == 0 or size > len(tokens):
        return False
    return any(tuple(tokens[i : i + size]) == phrase for i in range(len(tokens) - size + 1))


def contains_any(text_or_tokens: str | list[str], keywords: Iterable[str]) -> bool:
    """Whole-token/phrase match; a leading Arabic ال on a message token is optional."""
    tokens = tokenize(text_or_tokens) if isinstance(text_or_tokens, str) else text_or_tokens
    bare = [_strip_article(token) for token in tokens]
    for phrase in _phrases(keywords):
        if _contains_phrase(tokens, phrase) or _contains_phrase(bare, phrase):
            return True
    return False


def _all_languages(table: dict[str, tuple[str, ...]]) -> tuple[str, ...]:
    return tuple(word for words in table.values() for word in words)


def is_informational(tokens: list[str]) -> bool:
    return contains_any(tokens, _all_languages(INFO_MARKERS))


def is_personal(tokens: list[str]) -> bool:
    return contains_any(tokens, _all_languages(PERSONAL_MARKERS))


def is_explicit_handoff_request(tokens: list[str]) -> bool:
    return contains_any(tokens, _all_languages(HANDOFF_REQUEST_PHRASES))


def is_person_request(tokens: list[str]) -> bool:
    """An explicit request phrase aimed at a person ("talk to a person",
    "human agent", "أريد التحدث مع شخص"); outranks informational wording."""
    return is_explicit_handoff_request(tokens) and contains_any(
        tokens, _all_languages(PERSON_NOUNS)
    )


def order_account_requested(question: str) -> bool:
    """Post-retrieval only: the message is about the visitor's own order or
    account (whole-token keywords, informational questions excluded)."""
    return keyword_requests_handoff(tokenize(question), _all_languages(ORDER_ACCOUNT_KEYWORDS))


def keyword_requests_handoff(tokens: list[str], keywords: Iterable[str]) -> bool:
    """A keyword matched as whole tokens and the message is not an info question.

    Ambiguity (keyword plus an informational question about the content, with
    no explicit request and no first-person "my") resolves to retrieval."""
    if not contains_any(tokens, keywords):
        return False
    if is_explicit_handoff_request(tokens) or is_personal(tokens):
        return True
    return not is_informational(tokens)


def conversational_intent(tokens: list[str]) -> str | None:
    """The intent of a message made ONLY of intent phrases and fillers, else None.

    Longest phrase first at each position. A leftover token (a question about
    hours, an injected instruction) makes the whole message retrieval."""
    if not tokens or len(tokens) > INTENT_MAX_TOKENS:
        return None
    by_phrase: dict[tuple[str, ...], str] = {}
    for intent, table in INTENT_PHRASES.items():
        for phrase in _phrases(_all_languages(table)):
            by_phrase[phrase] = intent
    fillers = {phrase: "" for phrase in _phrases(_all_languages(INTENT_FILLERS))}
    phrases = sorted([*by_phrase, *fillers], key=len, reverse=True)
    found: set[str] = set()
    position = 0
    while position < len(tokens):
        for phrase in phrases:
            if tuple(tokens[position : position + len(phrase)]) == phrase:
                position += len(phrase)
                if phrase in by_phrase:
                    found.add(by_phrase[phrase])
                break
        else:
            return None
    return next((intent for intent in INTENT_PRIORITY if intent in found), None)


def is_conversational(text: str) -> bool:
    """A greeting/thanks/meta message: it carries no facts, so it is not history."""
    return conversational_intent(tokenize(text)) is not None


def route(
    question: str,
    language: str,
    *,
    handoff_enabled: bool,
) -> RoutedReply | None:
    del language  # keywords checked for every supported language
    tokens = tokenize(question)
    intent = conversational_intent(tokens)
    if intent is not None:
        return RoutedReply(kind="smalltalk", needs_human=False, intent=intent)
    if is_person_request(tokens):
        if handoff_enabled:
            return RoutedReply(kind="handoff", needs_human=True, reason="visitor_requested")
    return None
