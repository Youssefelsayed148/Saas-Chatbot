"""Rule-based routing decision before any model call (docs/14 §6).

- smalltalk → the bot's welcome message (per visitor language)
- handoff   → order/account/tracking questions; EN + AR keyword lists; a
  per-bot toggle can disable the rule (then the model answers like always)
The service layer composes the actual localized text (prompts.canned).
"""

from dataclasses import dataclass

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
    "en": ("hi", "hello", "hey", "good morning", "good evening", "thanks", "thank you"),
    "ar": (
        "مرحبا",
        "سلام",
        "السلام",
        "هلا",
        "أهلا",
        "اهلا",
        "شكرا",
        "شكراً",
        "صباح الخير",
        "مساء الخير",
    ),
}


@dataclass
class RoutedReply:
    """A rule match that resolves without any model call."""

    kind: str  # "smalltalk" | "handoff"
    needs_human: bool


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    lowered = " " + text.lower() + " "
    return any(word in lowered for word in keywords)


def route(
    question: str,
    language: str,
    *,
    handoff_enabled: bool,
) -> RoutedReply | None:
    del language  # keywords checked for every supported language
    for keywords in ORDER_ACCOUNT_KEYWORDS.values():
        if _contains_any(question, keywords):
            return RoutedReply(kind="handoff", needs_human=True) if handoff_enabled else None
    for keywords in SMALLTALK_KEYWORDS.values():
        if len(question.split()) <= 3 and _contains_any(question, keywords):
            return RoutedReply(kind="smalltalk", needs_human=False)
    return None
