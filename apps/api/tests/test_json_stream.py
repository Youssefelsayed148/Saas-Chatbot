# ruff: noqa: UP031
"""S.2: the incremental reply parser (DB-free).

Chunk boundaries are exercised at EVERY split position and one character at
a time, because the real stream splits tokens, escapes and surrogate pairs
anywhere.
"""

import json
from collections.abc import Iterator

import pytest

from app.chat.json_stream import (
    AnswerDelta,
    IncrementalReplyParser,
    ParserEvent,
    ReplyComplete,
    ReplyVerdict,
)


@pytest.fixture(autouse=True)
def clean_tables() -> Iterator[None]:
    """Override the DB-backed autouse fixture: these tests are DB-free."""
    yield


ID_A = "11111111-1111-1111-1111-111111111111"
ID_B = "22222222-2222-2222-2222-222222222222"
VALID = frozenset({ID_A, ID_B})


def run(
    chunks: list[str], valid: frozenset[str] = VALID
) -> tuple[IncrementalReplyParser, list[ParserEvent]]:
    parser = IncrementalReplyParser(valid)
    events: list[ParserEvent] = []
    for chunk in chunks:
        events.extend(parser.feed(chunk))
    return parser, events


def text_of(events: list[ParserEvent]) -> str:
    return "".join(event.text for event in events if isinstance(event, AnswerDelta))


def reply(answer: str, *, can_answer: bool = True, sources: list[str] | None = None) -> str:
    return json.dumps(
        {
            "can_answer": can_answer,
            "sources": [ID_A] if sources is None else sources,
            "answer": answer,
        },
        ensure_ascii=False,
    )


def all_splits(raw: str) -> list[list[str]]:
    splits = [[raw[:i], raw[i:]] for i in range(len(raw) + 1)]
    splits.append(list(raw))  # one character at a time
    return splits


def test_happy_path_releases_after_verdict_in_order() -> None:
    parser, events = run([reply("We open 9 to 5.")])
    kinds = [type(event) for event in events]
    assert kinds == [ReplyVerdict, AnswerDelta, ReplyComplete]
    verdict = events[0]
    assert isinstance(verdict, ReplyVerdict)
    assert verdict.can_answer is True and verdict.released is True
    assert verdict.sources == (ID_A,)
    assert text_of(events) == "We open 9 to 5."
    assert parser.complete and not parser.invalid


def test_every_split_position_gives_the_same_text() -> None:
    raw = reply('He said "hi"\nand left \\ back/slash ☃')
    for chunks in all_splits(raw):
        parser, events = run(chunks)
        assert not parser.invalid, chunks
        assert text_of(events) == 'He said "hi"\nand left \\ back/slash ☃', chunks
        assert parser.complete


def test_escaped_quotes_do_not_end_the_answer() -> None:
    raw = '{"can_answer": true, "sources": ["%s"], "answer": "a \\"quoted\\" word"}' % ID_A
    for chunks in all_splits(raw):
        parser, events = run(chunks)
        assert text_of(events) == 'a "quoted" word'
        assert parser.complete and not parser.invalid


def test_arabic_text_raw_and_escaped() -> None:
    arabic = "مرحباً بك، ساعات العمل من ٩ إلى ٥"
    for raw in (reply(arabic), json.dumps(json.loads(reply(arabic)), ensure_ascii=True)):
        # json.dumps(ensure_ascii=True) reorders nothing: dict order is kept.
        for chunks in all_splits(raw):
            parser, events = run(chunks)
            assert text_of(events) == arabic
            assert parser.complete and not parser.invalid


def test_surrogate_pair_escape_split_across_chunks() -> None:
    raw = '{"can_answer": true, "sources": ["%s"], "answer": "ok \\ud83d\\ude00 done"}' % ID_A
    for chunks in all_splits(raw):
        parser, events = run(chunks)
        assert text_of(events) == "ok \U0001f600 done"
        assert parser.complete


def test_lone_surrogate_becomes_replacement_character() -> None:
    raw = '{"can_answer": true, "sources": ["%s"], "answer": "a\\ud83dz"}' % ID_A
    parser, events = run([raw])
    assert text_of(events) == "a�z"
    assert parser.complete


def test_whitespace_between_tokens_is_accepted() -> None:
    raw = '\n { "can_answer" : true ,\n "sources" : [ "%s" , "%s" ] ,\n "answer" : "hi" } \n' % (
        ID_A,
        ID_B,
    )
    for chunks in all_splits(raw):
        parser, events = run(chunks)
        verdict = [event for event in events if isinstance(event, ReplyVerdict)][0]
        assert verdict.sources == (ID_A, ID_B)
        assert text_of(events) == "hi"
        assert parser.complete and not parser.invalid


def test_cannot_answer_releases_no_text() -> None:
    parser, events = run([reply("I do not know.", can_answer=False, sources=[])])
    verdict = events[0]
    assert isinstance(verdict, ReplyVerdict)
    assert verdict.can_answer is False and verdict.released is False
    assert text_of(events) == ""
    assert parser.complete  # still parsed to the end, just never released


def test_no_citation_releases_no_text() -> None:
    parser, events = run([reply("Yes we do.", sources=[])])
    verdict = events[0]
    assert isinstance(verdict, ReplyVerdict)
    assert verdict.released is False
    assert text_of(events) == ""
    assert parser.answer == "Yes we do."  # accumulated for the buffered fallback only


def test_unknown_citation_releases_no_text() -> None:
    other = "33333333-3333-3333-3333-333333333333"
    _, events = run([reply("x", sources=[ID_A, other])])
    verdict = events[0]
    assert isinstance(verdict, ReplyVerdict)
    assert verdict.released is False
    assert text_of(events) == ""


def test_no_delta_before_the_verdict_event() -> None:
    raw = reply("hello world")
    parser = IncrementalReplyParser(VALID)
    seen: list[ParserEvent] = []
    for char in raw:
        seen.extend(parser.feed(char))
    first_delta = next(i for i, event in enumerate(seen) if isinstance(event, AnswerDelta))
    verdict_at = next(i for i, event in enumerate(seen) if isinstance(event, ReplyVerdict))
    assert verdict_at < first_delta


def test_answer_before_verdict_keys_is_invalid_and_releases_nothing() -> None:
    raw = '{"answer": "secret", "can_answer": true, "sources": ["%s"]}' % ID_A
    for chunks in all_splits(raw):
        parser, events = run(chunks)
        assert parser.invalid and parser.invalid_reason == "key_order"
        assert text_of(events) == ""
        assert not any(isinstance(event, ReplyVerdict) for event in events)


def test_sources_before_can_answer_is_invalid() -> None:
    raw = '{"sources": ["%s"], "can_answer": true, "answer": "x"}' % ID_A
    parser, events = run([raw])
    assert parser.invalid and text_of(events) == ""


def test_duplicate_keys_are_invalid() -> None:
    raw = '{"can_answer": true, "can_answer": false, "sources": [], "answer": "x"}'
    parser, events = run([raw])
    assert parser.invalid and parser.invalid_reason == "key_order"
    assert text_of(events) == ""


def test_duplicate_answer_key_after_release_is_invalid() -> None:
    raw = '{"can_answer": true, "sources": ["%s"], "answer": "a", "answer": "b"}' % ID_A
    parser, _ = run([raw])
    assert parser.invalid


def test_unknown_extra_key_is_invalid() -> None:
    raw = '{"can_answer": true, "sources": ["%s"], "answer": "a", "extra": 1}' % ID_A
    parser, _ = run([raw])
    assert parser.invalid and not parser.complete


def test_missing_answer_key_is_invalid() -> None:
    raw = '{"can_answer": true, "sources": ["%s"]}' % ID_A
    parser, _ = run([raw])
    assert parser.invalid and parser.invalid_reason == "missing_keys"


def test_wrong_types_are_invalid() -> None:
    for raw in (
        '{"can_answer": "yes", "sources": [], "answer": "x"}',
        '{"can_answer": true, "sources": "abc", "answer": "x"}',
        '{"can_answer": true, "sources": [1], "answer": "x"}',
        '{"can_answer": true, "sources": [], "answer": 5}',
        "[1, 2]",
        "```json\n{}",
    ):
        parser, events = run([raw])
        assert parser.invalid, raw
        assert text_of(events) == ""


def test_more_than_eight_sources_is_invalid() -> None:
    many = json.dumps([ID_A] * 9)
    raw = '{"can_answer": true, "sources": %s, "answer": "x"}' % many
    parser, events = run([raw])
    assert parser.invalid and text_of(events) == ""


def test_trailing_garbage_after_object_is_invalid() -> None:
    parser, _ = run([reply("ok") + " junk"])
    assert parser.invalid and parser.invalid_reason == "trailing_data"


def test_raw_newline_inside_answer_is_invalid_like_json_loads() -> None:
    raw = '{"can_answer": true, "sources": ["%s"], "answer": "line1\nline2"}' % ID_A
    parser, _ = run([raw])
    assert parser.invalid


def test_truncated_stream_is_incomplete_but_released_text_was_valid() -> None:
    raw = reply("a long answer that never finishes")
    cut = raw[: raw.index("never")]
    parser, events = run([cut])
    assert not parser.complete and not parser.invalid
    assert text_of(events) == "a long answer that "


def test_truncated_before_verdict_releases_nothing() -> None:
    parser, events = run(['{"can_answer": true, "sources": ["' + ID_A[:10]])
    assert not parser.complete
    assert events == []


def test_parser_never_raises_on_arbitrary_text() -> None:
    parser = IncrementalReplyParser(VALID)
    for chunk in ("\x00", "}}}{", '{"', "\\", "\ud800", "{" * 50):
        parser.feed(chunk)
