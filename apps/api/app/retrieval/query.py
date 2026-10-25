"""Search query builder for keyword-first retrieval (docs/14 §2, §5).

The question is tokenised (``\\w+``), lowercased, 1-char tokens and
stop-words (English + Arabic lists) dropped. Remaining terms are OR-joined
into a ``to_tsquery`` string:

- English → ``to_tsquery('english', …)`` against the GIN-indexed ``fts_en``
  column (title+heading+text of the chunk).
- Arabic → ``to_tsquery('arabic', …)`` against the normalised column
  ``fts_ar`` (Snowball stemming, migration 0016); every Arabic term is matched with
  **and** without a leading ``ال`` and with ``:*`` prefix matching. Terms are
  normalised with the same rules as the stored ``text_norm``.

The tsvector columns are precomputed and indexed — queries never call
``to_tsvector`` on chunk text (docs/14 §5: no per-query recomputation).
"""

import re
from collections.abc import Iterable

from app.knowledge.language import normalise_text

TOKEN_RE = re.compile(r"\w+", re.UNICODE)

# English stop-words are exactly the words PostgreSQL's ``english`` text-search
# configuration drops (its english.stop list). Keeping the two identical means
# a stop-word is never counted as a query term, so it can neither satisfy nor
# block the "2 matched terms" rule. tests/test_retrieval.py checks it against
# the database. Arabic: PostgreSQL's ``arabic`` configuration drops none of the
# words below; they are removed from the query and the term count alike, so the
# two sides still agree.
ENGLISH_STOP_WORDS = frozenset(
    {
        "i",
        "me",
        "my",
        "myself",
        "we",
        "our",
        "ours",
        "ourselves",
        "you",
        "your",
        "yours",
        "yourself",
        "yourselves",
        "he",
        "him",
        "his",
        "himself",
        "she",
        "her",
        "hers",
        "herself",
        "it",
        "its",
        "itself",
        "they",
        "them",
        "their",
        "theirs",
        "themselves",
        "what",
        "which",
        "who",
        "whom",
        "this",
        "that",
        "these",
        "those",
        "am",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "having",
        "do",
        "does",
        "did",
        "doing",
        "a",
        "an",
        "the",
        "and",
        "but",
        "if",
        "or",
        "because",
        "as",
        "until",
        "while",
        "of",
        "at",
        "by",
        "for",
        "with",
        "about",
        "against",
        "between",
        "into",
        "through",
        "during",
        "before",
        "after",
        "above",
        "below",
        "to",
        "from",
        "up",
        "down",
        "in",
        "out",
        "on",
        "off",
        "over",
        "under",
        "again",
        "further",
        "then",
        "once",
        "here",
        "there",
        "when",
        "where",
        "why",
        "how",
        "all",
        "any",
        "both",
        "each",
        "few",
        "more",
        "most",
        "other",
        "some",
        "such",
        "no",
        "nor",
        "not",
        "only",
        "own",
        "same",
        "so",
        "than",
        "too",
        "very",
        "s",
        "t",
        "can",
        "will",
        "just",
        "don",
        "should",
        "now",
    }
)
ARABIC_STOP_WORDS = frozenset(
    {
        "في",
        "من",
        "على",
        "عن",
        "الى",
        "إلى",
        "هو",
        "هي",
        "هما",
        "هم",
        "هذا",
        "هذه",
        "هذان",
        "ذلك",
        "تلك",
        "التي",
        "الذي",
        "الذين",
        "ما",
        "هل",
        "لا",
        "لم",
        "لن",
        "قد",
        "كان",
        "كانت",
        "يكون",
        "كل",
        "بعد",
        "قبل",
        "عند",
        "حيث",
        "بين",
        "مع",
        "لكن",
        "كما",
        "أو",
        "او",
        "ثم",
        "فيه",
        "فيها",
        "منه",
        "منها",
        "عليه",
        "عليها",
        "به",
        "بها",
        "لدي",
        "لدينا",
        "لديكم",
        "لديه",
        "لديها",
        "ماذا",
        "كيف",
        "متى",
        "وين",
    }
)

# A leading Arabic article stripped as an additional match variant.
_ARABIC_ARTICLE = "ال"


def _tokens(question: str) -> list[str]:
    tokens: list[str] = []
    for token in TOKEN_RE.findall(question.lower()):
        if len(token) < 2:
            continue
        if token in ENGLISH_STOP_WORDS or token in ARABIC_STOP_WORDS:
            continue
        tokens.append(token)
    return tokens


def _arabic_variants(token: str) -> list[str]:
    """Match with and without the leading ال, each also as a ``:*`` prefix query.

    A query word that carries ال adds the bare form; a bare query word adds
    the ال-prefixed form — the store keeps whichever shape the content used.
    """
    variants: list[str] = []
    base = normalise_text(token)
    if base.startswith(_ARABIC_ARTICLE) and len(base) > len(_ARABIC_ARTICLE) + 1:
        candidates = [base, base[len(_ARABIC_ARTICLE) :]]
    else:
        candidates = [base, _ARABIC_ARTICLE + base]
    for candidate in candidates:
        if not candidate:
            continue
        variants.append(candidate)
        variants.append(candidate + ":*")
    return variants


def build_tsquery(question: str, language: str) -> str | None:
    """Build the tsquery text for one language pass; None without content words."""
    if language == "ar":
        # Normalise first so combining diacritics do not shatter \w tokens.
        question = normalise_text(question)
    tokens = _tokens(question)
    if not tokens:
        return None
    if language == "ar":
        # Dedupe while keeping order; each variant OR-joined.
        variants: list[str] = []
        seen: set[str] = set()
        for token in tokens:
            for variant in _arabic_variants(token):
                if variant not in seen:
                    seen.add(variant)
                    variants.append(variant)
        return " | ".join(variants)
    # English: to_tsquery('english') lexemizes; plain tokens are safe (\w+ only).
    return " | ".join(dict.fromkeys(tokens))


def _content_tokens(question: str, language: str, ignore: frozenset[str]) -> list[str]:
    """Distinct content tokens, minus the configured store-name/filler words."""
    if language == "ar":
        question = normalise_text(question)
    tokens = list(dict.fromkeys(_tokens(question)))
    if not ignore:
        return tokens
    return [token for token in tokens if not _is_ignored(token, language, ignore)]


def normalise_ignore_terms(values: Iterable[str]) -> frozenset[str]:
    """Lowercase (and Arabic-normalise) the configured ignore list once."""
    out: set[str] = set()
    for value in values:
        for token in TOKEN_RE.findall(str(value).lower()):
            out.add(token)
            out.add(normalise_text(token))
    return frozenset(out)


def _is_ignored(token: str, language: str, ignore: frozenset[str]) -> bool:
    if token in ignore:
        return True
    if language == "ar":
        base = normalise_text(token)
        if base in ignore:
            return True
        if base.startswith(_ARABIC_ARTICLE) and base[len(_ARABIC_ARTICLE) :] in ignore:
            return True
    return False


def term_queries(question: str, language: str, ignore: frozenset[str] = frozenset()) -> list[str]:
    """One OR query per distinct content term; Arabic variants count only once.

    ``ignore`` (normalised, see ``normalise_ignore_terms``) drops store-name and
    filler words from the term count only; the ranking query is unchanged.
    """
    return [
        " | ".join(_arabic_variants(token)) if language == "ar" else token
        for token in _content_tokens(question, language, ignore)
    ]


def term_labels(question: str, language: str, ignore: frozenset[str] = frozenset()) -> list[str]:
    """Readable label per term, parallel to ``term_queries`` (for the staff trace)."""
    return _content_tokens(question, language, ignore)


def content_terms(text: str) -> list[str]:
    """Query terms of ``text`` once stop-words and one-letter tokens are removed."""
    return _tokens(text)
