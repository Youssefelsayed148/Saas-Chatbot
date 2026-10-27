"""Plain-text output for direct-message channels (R-02).

WhatsApp, Messenger and Instagram do not render markdown, and citation markers
or source links mean nothing to a customer in a DM. Citations stay stored on the
message for staff; only the outbound text is cleaned.
"""

import re

_FENCE = re.compile(r"```[^\n]*\n?(.*?)```", re.S)
_INLINE_CODE = re.compile(r"`([^`\n]*)`")
_IMAGE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)[^)]*\)")
_BARE_URL = re.compile(r"https?://\S+")
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+", re.M)
_QUOTE = re.compile(r"^\s{0,3}>\s?", re.M)
_BULLET = re.compile(r"^(\s*)[-*+•]\s+", re.M)
# Emphasis. Double/triple markers and strikethrough may sit inside a word; a single
# ``*`` or any ``_`` must not touch a word character outside the pair, so ``2 * 3 * 4``,
# ``5*3 and 2*4``, ``snake_case`` and ``file_name__init__`` survive untouched.
_STRONG = re.compile(r"(\*\*\*|\*\*|~~)(?=\S)(.+?)(?<=\S)\1", re.S)
_STAR = re.compile(r"(?<![\w*])(\*)(?=[^\s*])(.+?)(?<=[^\s*])\1(?![\w*])", re.S)
_UNDERSCORE = re.compile(r"(?<!\w)(___|__|_)(?=[^\s_])(.+?)(?<=[^\s_])\1(?!\w)", re.S)
_CITATION = re.compile(r"\s?\[(?:c|s|src|source)?[ _-]?\d{1,3}(?:\s*,\s*\d{1,3})*\]", re.I)
_BLANKS = re.compile(r"\n{3,}")
_SPACES = re.compile(r"[ \t]{2,}")


def to_plain_text(text: str, *, allow_links: bool = False, keep: tuple[str, ...] = ()) -> str:
    """Strip markdown and citation markers; keep line breaks and `- ` bullets.

    ``keep`` lists literal strings that must survive untouched (the bot's own support
    contact, which may be a URL): they are swapped for placeholders while stripping."""
    protected = [value for value in dict.fromkeys(keep) if value]
    for index, value in enumerate(protected):
        text = text.replace(value, f"\ue000{index}\ue001")
    out = _plain_text(text, allow_links=allow_links)
    for index, value in enumerate(protected):
        out = out.replace(f"\ue000{index}\ue001", value)
    return out


def _plain_text(text: str, *, allow_links: bool) -> str:
    out = _FENCE.sub(lambda m: m.group(1), text)
    out = _INLINE_CODE.sub(r"\1", out)
    out = _IMAGE.sub(r"\1", out)
    if allow_links:
        out = _LINK.sub(lambda m: f"{m.group(1)}: {m.group(2)}", out)
    else:
        out = _LINK.sub(r"\1", out)
        out = _BARE_URL.sub("", out)
    out = _HEADING.sub("", out)
    out = _QUOTE.sub("", out)
    out = _BULLET.sub(r"\1- ", out)
    for _ in range(2):  # nested emphasis such as **bold *italic***
        for pattern in (_STRONG, _STAR, _UNDERSCORE):
            out = pattern.sub(r"\2", out)
    out = _CITATION.sub("", out)
    out = _SPACES.sub(" ", out)
    out = "\n".join(line.rstrip() for line in out.splitlines())
    out = _BLANKS.sub("\n\n", out)
    return out.strip()
