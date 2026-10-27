"""PDF structure recovery (chunking quality).

``pypdf`` returns each page as flat text, so a policy's headings are plain lines and a
section that runs over a page break is cut in two. Two pure helpers fix that without
touching the extraction itself:

* ``split_page_sections`` finds headings (numbered lines such as ``1. Returns`` or
  ``2.1 Fees``, and ALL-CAPS lines) and turns one page into several heading sections.
* ``merge_continued_sections`` joins a section that continues on the next page into one
  section, so it is chunked, indexed and cited together ("Pages 1–2").

Detection is deliberately conservative: a line is only a heading when it is short, does
not end like a sentence, is not a bullet, and is not part of a run of numbered list items.
A page with no clear heading keeps one section, exactly as before.
"""

import re

from app.knowledge.chunking import page_break_splits_sentence
from app.knowledge.parsing import ParsedPage, ParsedSection

MAX_HEADING_CHARS = 80
MAX_HEADING_WORDS = 10

_NUMBERED = re.compile(r"^(\d+(?:\.\d+){0,3})[.)]?\s+\S")
_BULLET = re.compile(r"^[-•*–·▪●◦]\s")
_SENTENCE_END = tuple(".!?؟…:;,،")


def _depth(line: str) -> int | None:
    """Nesting depth of a numbered line (``1.`` → 1, ``2.1`` → 2); None if not numbered."""
    match = _NUMBERED.match(line.strip())
    return match.group(1).count(".") + 1 if match else None


def _is_candidate(line: str) -> bool:
    stripped = line.strip()
    if not stripped or len(stripped) > MAX_HEADING_CHARS:
        return False
    if len(stripped.split()) > MAX_HEADING_WORDS:
        return False
    return not (_BULLET.match(stripped) or stripped.endswith(_SENTENCE_END))


def _neighbour(lines: list[str], index: int, step: int) -> str | None:
    """The nearest non-empty line before (-1) or after (+1) ``index``."""
    position = index + step
    while 0 <= position < len(lines):
        if lines[position].strip():
            return lines[position]
        position += step
    return None


def _is_heading(lines: list[str], index: int) -> bool:
    line = lines[index]
    if not _is_candidate(line):
        return False
    following = _neighbour(lines, index, 1)
    if following is None:
        return False  # a last line has no body to head
    depth = _depth(line)
    if depth is not None:
        # A run of numbered lines is a list, not a sequence of headings: a heading is
        # preceded and followed by body text.
        previous = _neighbour(lines, index, -1)
        return _depth(following) != depth and (previous is None or _depth(previous) != depth)
    return line.strip().isupper() and sum(char.isalpha() for char in line) >= 3


def split_page_sections(text: str) -> list[ParsedSection]:
    """Split one page's text into heading sections; one plain section if none is found."""
    lines = text.split("\n")
    headings = [index for index in range(len(lines)) if _is_heading(lines, index)]
    if not headings:
        return [ParsedSection(heading=None, text=text)]

    sections: list[ParsedSection] = []
    preamble = "\n".join(lines[: headings[0]]).strip()
    if preamble:
        sections.append(ParsedSection(heading=None, text=preamble))
    pending: str | None = None  # a heading with no body of its own leads the next one
    for position, start in enumerate(headings):
        end = headings[position + 1] if position + 1 < len(headings) else len(lines)
        heading = lines[start].strip()
        body = "\n".join(lines[start + 1 : end]).strip()
        if not body:
            pending = f"{pending} — {heading}" if pending else heading
            continue
        sections.append(
            ParsedSection(heading=f"{pending} — {heading}" if pending else heading, text=body)
        )
        pending = None
    if pending:
        sections.append(ParsedSection(heading=pending, text=pending))
    return sections


def merge_continued_sections(pages: list[ParsedPage]) -> list[ParsedPage]:
    """Fold a section that runs over a page break into the section it continues.

    Applies when the next page opens without a heading and the previous page ended
    mid-sentence. The merged section keeps the first page's title and is cited as
    ``Pages a–b``; the next page keeps its remaining sections.
    """
    tail: ParsedSection | None = None
    tail_start = 0
    previous_text = ""
    for page in pages:
        if not page.sections or not page.text:
            tail, previous_text = None, ""
            continue
        first = page.sections[0]
        number = page.page_number or 0
        if (
            tail is not None
            and first.heading is None
            and page_break_splits_sentence(previous_text, page.text)
        ):
            tail.text = f"{tail.text}\n{first.text}"
            tail.ref = f"Pages {tail_start}–{number}"
            page.sections = page.sections[1:]
            page.continued_from_previous = True
        if page.sections:
            tail, tail_start = page.sections[-1], number
        previous_text = page.text
    return pages
