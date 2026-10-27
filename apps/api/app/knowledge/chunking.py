"""Recursive character chunking (docs/14 §4).

Defaults: ``chunk_size=1500``, ``chunk_overlap=200``, separators
``["\n\n", "\n", ". ", "! ", "? ", "؟ ", "، ", " ", ""]``. A document whose
total text is ≤ chunk_size (a short policy, a Q&A row) is one chunk.

Pieces carry their separator at the end so merged chunks keep words and
sentence boundaries intact; no content is ever dropped.
"""

from dataclasses import dataclass

SEPARATORS: tuple[str, ...] = ("\n\n", "\n", ". ", "! ", "? ", "؟ ", "، ", " ", "")


@dataclass
class ChunkPlan:
    """Planned chunk text for one section (no DB concerns here)."""

    text: str


def split_text(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    """Split until every chunk fits ``chunk_size``; later chunks overlap the tail."""
    if len(text) <= chunk_size:
        return [text]
    pieces = _atomic_pieces(text, list(SEPARATORS), chunk_size, chunk_overlap)
    return _merge_with_overlap(pieces, chunk_size, chunk_overlap)


def _atomic_pieces(
    text: str, separators: list[str], chunk_size: int, chunk_overlap: int
) -> list[str]:
    """Pieces of at most ``chunk_size`` characters, separators tried top-down."""
    if len(text) <= chunk_size:
        return [text]
    if not separators:
        # One unbreakable token (e.g. a very long word): hard slices; the
        # overlap keeps every character retrievable.
        return _hard_slices(text, chunk_size, chunk_overlap)
    separator, rest = separators[0], separators[1:]
    if separator == "":
        return _hard_slices(text, chunk_size, chunk_overlap)
    if separator not in text:
        return _atomic_pieces(text, rest, chunk_size, chunk_overlap)

    parts = text.split(separator)
    last = len(parts) - 1
    pieces: list[str] = []
    for index, part in enumerate(parts):
        if part == "":
            continue  # a separator run; collapsing it is covered by text cleaning
        unit = part if index == last else part + separator
        if len(unit) <= chunk_size:
            pieces.append(unit)
        else:
            # The trailing separator is sacrificed on this deep split path.
            pieces.extend(_atomic_pieces(part, rest, chunk_size, chunk_overlap))
    return pieces if pieces else [text[:chunk_size]]


def _hard_slices(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    """Fixed-size windows for text with no usable separator; each window ends on a space
    when one lies in its second half, so words are not cut."""
    slices: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        if end < len(text):
            space = text.rfind(" ", start + chunk_size // 2, end)
            if space > start:
                end = space + 1
        slices.append(text[start:end])
        if end >= len(text):
            break
        start = max(end - max(0, chunk_overlap), start + 1)
        word_start = text.find(" ", start, end)  # begin the overlap on a whole word
        if word_start != -1:
            start = word_start + 1
    return slices


def _merge_with_overlap(pieces: list[str], chunk_size: int, chunk_overlap: int) -> list[str]:
    chunks: list[str] = []
    current = ""
    for piece in pieces:
        if not current:
            current = piece
        elif len(current) + len(piece) <= chunk_size:
            current += piece
        else:
            chunks.append(current)
            tail = current[-chunk_overlap:] if 0 < chunk_overlap <= len(current) else ""
            candidate = tail + piece if tail else piece
            # Never drop content: if the tail would push the piece over the
            # limit, start the chunk with the plain piece instead.
            current = candidate if len(candidate) <= chunk_size else piece
    if current:
        chunks.append(current)
    return chunks


# --- PDF page-break context (H5) --------------------------------------------

_TERMINALS = ".!?؟…:;"
_CLOSERS = "\"'”’)]»"
_SENTENCE_BREAKS = (". ", "! ", "? ", "؟ ", "\n\n")
CARRY_MAX_CHARS = 300


def page_break_splits_sentence(previous: str, following: str) -> bool:
    """True when the break between two PDF pages falls inside a sentence: the
    previous page does not end in terminal punctuation and the next one does not
    open like a new sentence (a lowercase or uncased letter continues one)."""
    before, after = previous.rstrip(), following.lstrip()
    if not before or not after:
        return False
    if before.rstrip(_CLOSERS)[-1:] in _TERMINALS or before[-1] in _TERMINALS:
        return False
    first = after[0]
    if not first.isalpha():
        return False
    return first.islower() or first.upper() == first.lower()  # uncased scripts (Arabic)


def trailing_sentence(text: str, max_chars: int = CARRY_MAX_CHARS) -> str:
    """The last (unfinished) sentence of ``text``, at most ``max_chars`` long and
    cut on a word boundary."""
    body = text.rstrip()
    start = max(
        (body.rfind(mark) + len(mark) for mark in _SENTENCE_BREAKS if mark in body), default=0
    )
    tail = body[start:].strip()
    if len(tail) > max_chars:
        tail = tail[-max_chars:]
        head, space, rest = tail.partition(" ")
        tail = rest if space and rest else tail
    return tail
