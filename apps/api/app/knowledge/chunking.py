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
    step = max(1, chunk_size - max(0, chunk_overlap))
    return [text[start : start + chunk_size] for start in range(0, len(text), step)]


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
