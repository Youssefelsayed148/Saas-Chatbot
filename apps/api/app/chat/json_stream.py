"""Incremental parser for the streamed model reply (S.2).

The model emits ONE JSON object whose keys come in EXACTLY this order:

    {"can_answer": true|false, "sources": ["<chunk id>", ...], "answer": "..."}

so the verdict and the citations arrive before the text. The parser is fed
arbitrary text fragments (chunk boundaries may fall inside a token, an
escape sequence or a surrogate pair) and yields events:

- ``ReplyVerdict``  once ``can_answer`` and ``sources`` are both known, with
  the release decision (``released``);
- ``AnswerDelta``   decoded fragments of ``answer``, ONLY when released;
- ``ReplyComplete`` when the closing ``}`` arrives with all three keys.

Release rules (the same guarantees as the buffered ``_parse_reply``): text
is released only when ``can_answer`` is true AND at least one citation
exists AND every cited id is valid evidence. Anything else never releases a
single character of model text.

Structural problems (keys out of order, duplicate or unknown keys, wrong
value types, more than 8 sources, bad escapes, trailing garbage) set
``invalid`` so the caller can fall back to the buffered path. The parser
never raises on input.
"""

from dataclasses import dataclass

EXPECTED_KEYS = ("can_answer", "sources", "answer")
MAX_SOURCES = 8


@dataclass(frozen=True)
class ReplyVerdict:
    can_answer: bool
    sources: tuple[str, ...]
    released: bool


@dataclass(frozen=True)
class AnswerDelta:
    text: str


@dataclass(frozen=True)
class ReplyComplete:
    pass


ParserEvent = ReplyVerdict | AnswerDelta | ReplyComplete

_SIMPLE_ESCAPES = {
    '"': '"',
    "\\": "\\",
    "/": "/",
    "b": "\b",
    "f": "\f",
    "n": "\n",
    "r": "\r",
    "t": "\t",
}
_HEX = set("0123456789abcdefABCDEF")


class _StringDecoder:
    """Decodes the body of a JSON string one character at a time."""

    def __init__(self) -> None:
        self._escape: str | None = None  # None | "" (after backslash) | "u..." digits
        self._high_surrogate: int | None = None
        self.invalid = False

    def feed(self, char: str) -> tuple[str, bool]:
        """(decoded text, finished) for one raw character."""
        if self._escape is not None:
            return self._feed_escape(char)
        if char == '"':
            lone = self._flush_surrogate()
            return lone, True
        if char == "\\":
            self._escape = ""
            return "", False
        if ord(char) < 0x20:
            self.invalid = True  # raw control characters are not valid JSON
            return "", False
        return self._flush_surrogate() + char, False

    def _feed_escape(self, char: str) -> tuple[str, bool]:
        assert self._escape is not None
        if self._escape == "":
            if char == "u":
                self._escape = "u"
                return "", False
            decoded = _SIMPLE_ESCAPES.get(char)
            self._escape = None
            if decoded is None:
                self.invalid = True
                return "", False
            return self._flush_surrogate() + decoded, False
        if char not in _HEX:
            self._escape = None
            self.invalid = True
            return "", False
        self._escape += char
        if len(self._escape) < 5:
            return "", False
        code = int(self._escape[1:], 16)
        self._escape = None
        return self._code_unit(code), False

    def _code_unit(self, code: int) -> str:
        if 0xD800 <= code <= 0xDBFF:
            lone = self._flush_surrogate()
            self._high_surrogate = code
            return lone
        if 0xDC00 <= code <= 0xDFFF:
            if self._high_surrogate is not None:
                joined = 0x10000 + ((self._high_surrogate - 0xD800) << 10) + (code - 0xDC00)
                self._high_surrogate = None
                return chr(joined)
            return "�"
        return self._flush_surrogate() + chr(code)

    def _flush_surrogate(self) -> str:
        if self._high_surrogate is None:
            return ""
        self._high_surrogate = None
        return "�"


class IncrementalReplyParser:
    def __init__(self, valid_ids: set[str] | frozenset[str]) -> None:
        self._valid_ids = valid_ids
        self._state = "start"
        self._key_index = 0
        self._buffer = ""
        self._decoder: _StringDecoder | None = None
        self.invalid = False
        self.invalid_reason: str | None = None
        self.complete = False
        self.can_answer: bool | None = None
        self.sources: list[str] = []
        self.released = False
        self.verdict_seen = False
        self.answer = ""  # the decoded answer text so far (released or not)

    # -- public ---------------------------------------------------------

    def feed(self, chunk: str) -> list[ParserEvent]:
        events: list[ParserEvent] = []
        delta: list[str] = []
        for char in chunk:
            if self.invalid:
                break
            self._step(char, events, delta)
        if delta and self.released and not self.invalid:
            events.append(AnswerDelta("".join(delta)))
        return events

    # -- internals ------------------------------------------------------

    def _fail(self, reason: str) -> None:
        self.invalid = True
        self.invalid_reason = reason

    def _step(self, char: str, events: list[ParserEvent], delta: list[str]) -> None:
        state = self._state
        whitespace = char in " \t\r\n"
        if state == "start":
            if whitespace:
                return
            if char != "{":
                self._fail("not_an_object")
                return
            self._state = "key_start"
        elif state == "key_start":
            if whitespace:
                return
            if char != '"':
                self._fail("expected_key")
                return
            self._buffer = ""
            self._state = "key"
        elif state == "key":
            if char == '"':
                if (
                    self._key_index >= len(EXPECTED_KEYS)
                    or self._buffer != EXPECTED_KEYS[self._key_index]
                ):
                    self._fail("key_order")
                    return
                self._state = "colon"
            elif char == "\\" or ord(char) < 0x20:
                self._fail("bad_key")
            else:
                self._buffer += char
        elif state == "colon":
            if whitespace:
                return
            if char != ":":
                self._fail("expected_colon")
                return
            self._state = "value_start"
        elif state == "value_start":
            if whitespace:
                return
            self._start_value(char)
        elif state == "bool":
            if char.isalpha():
                self._buffer += char
                if len(self._buffer) > 5:
                    self._fail("bad_bool")
                return
            if self._buffer not in ("true", "false"):
                self._fail("bad_bool")
                return
            self.can_answer = self._buffer == "true"
            self._key_index += 1
            self._state = "after_value"
            self._step(char, events, delta)
        elif state == "arr_start":
            if whitespace:
                return
            if char == "]":
                self._finish_sources(events)
            elif char == '"':
                self._begin_source()
            else:
                self._fail("bad_sources")
        elif state == "src_string":
            assert self._decoder is not None
            text, finished = self._decoder.feed(char)
            if self._decoder.invalid:
                self._fail("bad_string")
                return
            self._buffer += text
            if finished:
                self.sources.append(self._buffer)
                if len(self.sources) > MAX_SOURCES:
                    self._fail("too_many_sources")
                    return
                self._state = "arr_after"
        elif state == "arr_after":
            if whitespace:
                return
            if char == ",":
                self._state = "arr_next"
            elif char == "]":
                self._finish_sources(events)
            else:
                self._fail("bad_sources")
        elif state == "arr_next":
            if whitespace:
                return
            if char == '"':
                self._begin_source()
            else:
                self._fail("bad_sources")
        elif state == "answer":
            assert self._decoder is not None
            text, finished = self._decoder.feed(char)
            if self._decoder.invalid:
                self._fail("bad_string")
                return
            if text:
                self.answer += text
                delta.append(text)
            if finished:
                if delta and self.released:
                    # Flush before ReplyComplete so the order is always
                    # verdict -> delta(s) -> complete.
                    events.append(AnswerDelta("".join(delta)))
                delta.clear()
                self._key_index += 1
                self._state = "after_value"
        elif state == "after_value":
            if whitespace:
                return
            if char == ",":
                self._state = "key_start"
            elif char == "}":
                if self._key_index != len(EXPECTED_KEYS):
                    self._fail("missing_keys")
                    return
                self.complete = True
                self._state = "done"
                events.append(ReplyComplete())
            else:
                self._fail("expected_comma")
        elif state == "done" and not whitespace:
            self._fail("trailing_data")

    def _start_value(self, char: str) -> None:
        key = EXPECTED_KEYS[self._key_index]
        if key == "can_answer":
            if not char.isalpha():
                self._fail("bad_bool")
                return
            self._buffer = char
            self._state = "bool"
        elif key == "sources":
            if char != "[":
                self._fail("bad_sources")
                return
            self.sources = []
            self._state = "arr_start"
        else:
            if char != '"':
                self._fail("bad_answer")
                return
            self._decoder = _StringDecoder()
            self._state = "answer"

    def _begin_source(self) -> None:
        self._decoder = _StringDecoder()
        self._buffer = ""
        self._state = "src_string"

    def _finish_sources(self, events: list[ParserEvent]) -> None:
        self._key_index += 1
        self._state = "after_value"
        self.verdict_seen = True
        self.released = bool(
            self.can_answer is True
            and self.sources
            and all(source in self._valid_ids for source in self.sources)
        )
        events.append(
            ReplyVerdict(
                can_answer=bool(self.can_answer),
                sources=tuple(self.sources),
                released=self.released,
            )
        )


__all__ = [
    "AnswerDelta",
    "IncrementalReplyParser",
    "ParserEvent",
    "ReplyComplete",
    "ReplyVerdict",
]
