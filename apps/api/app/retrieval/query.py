"""Search query builder for keyword-first retrieval (docs/14 §2, §5).

The question is tokenised (``\\w+``), lowercased, 1-char tokens and
stop-words (English + Arabic lists) dropped. Remaining terms are OR-joined
into a ``to_tsquery`` string:

- English → ``to_tsquery('english', …)`` against the GIN-indexed ``fts_en``
  column (title+heading+text of the chunk).
- Arabic → ``to_tsquery('arabic', …)`` against the normalised column
  ``fts_ar`` (Snowball stemming, migration 0016); every Arabic term is matched with **and** without a leading
  ``ال`` and with ``:*`` prefix matching. Terms are normalised with the same
  rules as the stored ``text_norm``.

The tsvector columns are precomputed and indexed — queries never call
``to_tsvector`` on chunk text (docs/14 §5: no per-query recomputation).
"""

import re

from app.knowledge.language import normalise_text

TOKEN_RE = re.compile(r"\w+", re.UNICODE)

# Conservative function-word lists; they only trim queries, recall comes
# from the remaining content words.
ENGLISH_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "but",
        "if",
        "then",
        "than",
        "so",
        "of",
        "to",
        "in",
        "on",
        "at",
        "by",
        "for",
        "with",
        "about",
        "from",
        "as",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "am",
        "do",
        "does",
        "did",
        "have",
        "has",
        "had",
        "will",
        "would",
        "can",
        "could",
        "shall",
        "should",
        "may",
        "might",
        "must",
        "it",
        "its",
        "this",
        "that",
        "these",
        "those",
        "there",
        "here",
        "what",
        "when",
        "where",
        "which",
        "who",
        "whom",
        "whose",
        "why",
        "how",
        "you",
        "your",
        "yours",
        "i",
        "me",
        "my",
        "we",
        "our",
        "ours",
        "they",
        "them",
        "their",
        "he",
        "she",
        "his",
        "her",
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


def term_queries(question: str, language: str) -> list[str]:
    """One OR query per distinct content term; Arabic variants count only once."""
    if language == "ar":
        question = normalise_text(question)
    return [
        " | ".join(_arabic_variants(token)) if language == "ar" else token
        for token in dict.fromkeys(_tokens(question))
    ]
