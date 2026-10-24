"""R2-1: rule routing and person-handoff keywords match whole tokens only."""

import pytest

from app.chat.routing import route
from app.inbox.handoff import PERSON_KEYWORDS, _contains

RETRIEVAL = [
    "shipping cost?",
    "is this open",
    "which branch",
    "how do I order a pizza",
    "accounting services",
    "personal data policy",
    "how do I return an item?",
    "what is the refund policy?",
    "hi, what are your opening hours?",
    "hello what is the delivery fee",
    "ما هي سياسة الطلب",
    "كيف اطلب بيتزا",
    "هل لديكم خدمات المحاسبة",
]
SMALLTALK = [
    "hi",
    "hello!",
    "thanks",
    "Thank you",
    "good morning",
    "bye",
    "شكرا",
    "شكراً",
    "مرحبا",
    "أهلا",
    "السلام عليكم",
    "صباح الخير",
]
HANDOFF = [
    "where is my order?",
    "track my shipment",
    "I can't login",
    "وين طلبي؟",
    "متى يوصل",
    "what is my order status",
]
PERSON = [
    "I want to talk to a person",
    "human agent please",
    "Please let me speak to an agent",
    "can I speak to a human?",
    "أريد التحدث مع شخص",
    "اكلم موظف",
]
NOT_PERSON = [
    "personal data policy",
    "how do I contact an agent about pricing?",
    "do you have a human resources page",
    "what is a representative sample",
    "super agentic tools",
    "شخصي",
]


@pytest.mark.parametrize("question", RETRIEVAL)
def test_ordinary_questions_reach_retrieval(question: str) -> None:
    assert route(question, "en", handoff_enabled=True) is None


@pytest.mark.parametrize("question", SMALLTALK)
def test_whole_message_greetings_are_smalltalk(question: str) -> None:
    routed = route(question, "en", handoff_enabled=True)
    assert routed is not None and routed.kind == "smalltalk" and not routed.needs_human


@pytest.mark.parametrize("question", HANDOFF)
def test_clear_order_questions_hand_off(question: str) -> None:
    routed = route(question, "en", handoff_enabled=True)
    assert routed is not None and routed.kind == "handoff" and routed.needs_human
    assert route(question, "en", handoff_enabled=False) is None


@pytest.mark.parametrize("question", PERSON)
def test_person_requests_match(question: str) -> None:
    assert _contains(question, PERSON_KEYWORDS["en"] + PERSON_KEYWORDS["ar"])


@pytest.mark.parametrize("question", NOT_PERSON)
def test_person_keywords_never_match_substrings_or_content_questions(question: str) -> None:
    assert not _contains(question, PERSON_KEYWORDS["en"] + PERSON_KEYWORDS["ar"])


def test_configured_keywords_are_whole_tokens_too() -> None:
    assert _contains("call the manager now", ["manager"])
    assert not _contains("our managerial team", ["manager"])
