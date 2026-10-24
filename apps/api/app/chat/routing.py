"""Rule-based routing decision before any model call (docs/14 §6).

- smalltalk → the bot's welcome message (per visitor language)
- handoff   → order/account/tracking questions; EN + AR keyword lists; a
  per-bot toggle can disable the rule (then the model answers like always)
The service layer composes the actual localized text (prompts.canned).

Matching is on whole tokens/phrases after normalisation (lowercase, no
punctuation, Arabic diacritics/tatweel/alef/yaa variants folded), never on
substrings. Smalltalk applies only when the whole message is a greeting,
thanks or farewell. A keyword never hands off a message that also asks an
informational question about the bot's own content: when ambiguous the
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

SMALLTALK_KEYWORDS = {
    "en": (
        "hi",
        "hello",
        "hey",
        "hi there",
        "hello there",
        "good morning",
        "good afternoon",
        "good evening",
        "good night",
        "thanks",
        "thank you",
        "thanks a lot",
        "bye",
        "goodbye",
        "see you",
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
        "شكرا",
        "شكرا جزيلا",
        "صباح الخير",
        "مساء الخير",
        "مع السلامة",
        "وداعا",
    ),
}

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


@dataclass
class RoutedReply:
    """A rule match that resolves without any model call."""

    kind: str  # "smalltalk" | "handoff"
    needs_human: bool


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


def keyword_requests_handoff(tokens: list[str], keywords: Iterable[str]) -> bool:
    """A keyword matched as whole tokens and the message is not an info question.

    Ambiguity (keyword plus an informational question about the content, with
    no explicit request and no first-person "my") resolves to retrieval."""
    if not contains_any(tokens, keywords):
        return False
    if is_explicit_handoff_request(tokens) or is_personal(tokens):
        return True
    return not is_informational(tokens)


def _is_smalltalk(tokens: list[str]) -> bool:
    """The whole message is greeting/thanks/farewell phrases (max 4 tokens)."""
    if not tokens or len(tokens) > 4:
        return False
    phrases = sorted(_phrases(_all_languages(SMALLTALK_KEYWORDS)), key=len, reverse=True)
    position = 0
    while position < len(tokens):
        for phrase in phrases:
            if tuple(tokens[position : position + len(phrase)]) == phrase:
                position += len(phrase)
                break
        else:
            return False
    return True


def route(
    question: str,
    language: str,
    *,
    handoff_enabled: bool,
) -> RoutedReply | None:
    del language  # keywords checked for every supported language
    tokens = tokenize(question)
    if _is_smalltalk(tokens):
        return RoutedReply(kind="smalltalk", needs_human=False)
    if keyword_requests_handoff(tokens, _all_languages(ORDER_ACCOUNT_KEYWORDS)):
        return RoutedReply(kind="handoff", needs_human=True) if handoff_enabled else None
    return None
