"""Language detection and Arabic normalisation (docs/14 §2, ADR-014).

Detection: Arabic when Arabic-script letters ≥ Latin letters; English
otherwise. A text without any letters yields ``None`` (the caller applies the
front-matter language, the bot's default or ``en``).

Normalisation applies to query terms and to stored ``text_norm``: strip
diacritics + tatweel, map أ إ آ → ا and ى → ي.
"""

import hashlib
import unicodedata
from bisect import bisect

# Arabic-script ranges (Unicode 15): base Arabic, supplement, extended,
# presentation forms A/B.
_ARABIC_RANGES = (
    (0x0600, 0x06FF),
    (0x0750, 0x077F),
    (0x08A0, 0x08FF),
    (0xFB50, 0xFDFF),
    (0xFE70, 0xFEFF),
)
_ARABIC_STARTS = [start for start, _ in _ARABIC_RANGES]

# Diacritics and tatweel are dropped in normalisation.
_ARABIC_STRIP_CODEPOINTS = frozenset(
    [*range(0x064B, 0x0653), 0x0640, 0x0670, 0x0653, 0x0654, 0x0655]
)
# أ إ آ → ا ; ى → ي
_ARABIC_MAP = {0x0623: 0x0627, 0x0625: 0x0627, 0x0622: 0x0627, 0x0649: 0x064A}


def detect_language(text: str) -> str | None:
    """'ar' when Arabic-script letters >= Latin letters, else 'en'; None without letters."""
    arabic = 0
    latin = 0
    for ch in text:
        code = ord(ch)
        if bisect(_ARABIC_STARTS, code) and any(
            start <= code <= end for start, end in _ARABIC_RANGES
        ):
            # Count base letters plus presentation forms; marks (combining
            # diacritics) are letters within these ranges too — they still
            # prove Arabic script, which is what the detector needs.
            arabic += 1
        elif ch.isascii() and ch.isalpha():
            latin += 1
    if arabic == 0 and latin == 0:
        return None
    return "ar" if arabic >= latin else "en"


def normalise_text(text: str) -> str:
    """Lowercase and apply the Arabic normalisation of docs/14 §2."""
    builder: list[str] = []
    for ch in text.casefold():
        code = ord(ch)
        if code in _ARABIC_STRIP_CODEPOINTS:
            continue
        if code in _ARABIC_MAP:
            builder.append(chr(_ARABIC_MAP[code]))
        else:
            builder.append(ch)
    # NFC keeps presentation forms readable while removing artefacts.
    return unicodedata.normalize("NFC", "".join(builder))


def content_hash(normalised: str) -> str:
    """Dedupe key: SHA-256 of the normalised chunk text (docs/14 §3)."""
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()
