"""Optional YAML front matter on .md/.txt files (docs/14 §3).

A block between two leading ``---`` lines holding ``title``, ``source_url``,
``language`` (en|ar), ``page_type`` and ``captured_at`` (ISO date). ``title``
and ``source_url`` are kept on every chunk of the file; ``source_url`` is
cited later and must be http(s) — anything else is dropped.
"""

from dataclasses import dataclass, field
from datetime import date

import yaml

FRONT_MATTER_KEYS = frozenset({"title", "source_url", "language", "page_type", "captured_at"})


@dataclass
class FrontMatter:
    title: str | None = None
    source_url: str | None = None
    language: str | None = None
    page_type: str | None = None
    captured_at: date | None = None
    unknown_keys: list[str] = field(default_factory=list)


def split_front_matter(text: str) -> tuple[FrontMatter, str]:
    """Split an optional leading ``---`` block; returns (front matter, body)."""
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return FrontMatter(), text
    closing = next(
        (index for index in range(1, len(lines)) if lines[index].strip() == "---"),
        None,
    )
    if closing is None:
        # No closing fence: the whole file is body text.
        return FrontMatter(), text
    block = "\n".join(lines[1:closing])
    body_start = closing + 1
    # Only a blank line directly after the fence is consumed with the block.
    if body_start < len(lines) and lines[body_start].strip() == "":
        body_start += 1
    return parse_front_matter(block), "\n".join(lines[body_start:])


def parse_front_matter(block: str) -> FrontMatter:
    try:
        loaded = yaml.safe_load(block)
    except yaml.YAMLError:
        # Malformed YAML is ignored: the file still parses as plain body text.
        return FrontMatter()
    if not isinstance(loaded, dict):
        return FrontMatter()
    front = FrontMatter()
    for key, value in loaded.items():
        if key not in FRONT_MATTER_KEYS or value is None:
            front.unknown_keys.append(str(key))
            continue
        if key == "title":
            front.title = _clean_scalar(value)
        elif key == "page_type":
            front.page_type = _clean_scalar(value)
        elif key == "language":
            language = _clean_scalar(value)
            # Only the two product languages are accepted; anything else is an
            # override attempt that must not silently corrupt chunking.
            front.language = language if language in ("en", "ar") else None
        elif key == "captured_at":
            front.captured_at = value if isinstance(value, date) else None
        elif key == "source_url":
            url = _clean_scalar(value)
            # Citations link to this URL: http/https only (docs/06, docs/14 §3).
            if url and url.startswith(("http://", "https://")) and " " not in url:
                front.source_url = url
    return front


def _clean_scalar(value: object) -> str | None:
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    return None
