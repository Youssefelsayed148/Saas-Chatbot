"""Shared parsing dataclasses and errors (P2-02).

Parsers turn stored file bytes into ``ParsedPage`` structures with
``sections``; the ingest job turns sections into documents + chunks.
"""

from dataclasses import dataclass, field


class ParseError(Exception):
    """A source could not be parsed; the message is shown to the user."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@dataclass
class ParsedSection:
    """One heading section / Q&A row: the future ``documents`` row."""

    # Section heading text (None for per-page sections like PDF pages).
    heading: str | None
    text: str
    # Per-row values (Q&A CSV); None means "derive/detect".
    language: str | None = None
    priority: int | None = None
    # Provenance hint for the document page_ref ("Row 12" for Q&A rows).
    ref: str | None = None


@dataclass
class ParsedPage:
    """One parsed page (``source_pages`` row) and its sections."""

    page_number: int | None
    title: str
    text: str
    sections: list[ParsedSection] = field(default_factory=list)
    source_url: str | None = None
    page_type: str | None = None
    language: str | None = None
