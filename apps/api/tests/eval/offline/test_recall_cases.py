"""H4: the recall/dialect/typo eval cases are well formed, fair and leak-free.

Pure file checks against the frozen corpus; no database, no provider.
"""

import re
import unicodedata
from collections import Counter
from functools import cache
from pathlib import Path
from typing import Any

import pypdf
import pytest

from tests.eval import recall_metrics

CORPUS = Path(__file__).resolve().parents[1] / "corpus"
CATEGORIES = {"paraphrase", "typo", "dialect", "mixed", "gap"}
WORD = re.compile(r"\w+", re.UNICODE)
# A question that shares this many consecutive words with an expected page is a quote,
# not a paraphrase.
MAX_SHARED_WORDS = 4


def fold(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


@cache
def page_texts(filename: str) -> tuple[str, ...]:
    reader = pypdf.PdfReader(str(CORPUS / filename), strict=False)
    return tuple(fold(page.extract_text() or "") for page in reader.pages)


def corpus_text() -> str:
    return " ".join(t for path in sorted(CORPUS.glob("*.pdf")) for t in page_texts(path.name))


def cases() -> list[dict[str, Any]]:
    return recall_metrics.load_cases()


def ngrams(text: str, size: int) -> set[tuple[str, ...]]:
    words = WORD.findall(fold(text))
    return {tuple(words[i : i + size]) for i in range(len(words) - size + 1)}


def test_shape_mix_and_unique_ids() -> None:
    rows = cases()
    assert 36 <= len(rows) <= 60
    assert len({row["id"] for row in rows}) == len(rows)
    assert {row["category"] for row in rows} == CATEGORIES
    for row in rows:
        assert row["language"] in ("en", "ar") and row["question"].strip(), row["id"]
        assert row["expected_behavior"] in ("grounded", "abstain"), row["id"]
        assert row["history"] == [], row["id"]
        assert (row["category"] == "gap") == (row["expected_behavior"] == "abstain"), row["id"]
    by_category = Counter((row["category"], row["language"]) for row in rows)
    for key in (
        ("paraphrase", "en"),
        ("paraphrase", "ar"),
        ("typo", "en"),
        ("typo", "ar"),
        ("dialect", "ar"),
        ("gap", "en"),
        ("gap", "ar"),
    ):
        assert by_category[key] >= 3, key


def test_dialect_cases_name_their_dialect() -> None:
    notes = {row["note"] for row in cases() if row["category"] == "dialect"}
    assert {"Egyptian", "Gulf", "Levantine"} <= notes


def test_expected_sources_exist_and_hold_the_expected_text() -> None:
    for row in cases():
        if row["expected_behavior"] == "abstain":
            assert row["expected_sources"] == [] and row["expected_contains"] == [], row["id"]
            continue
        assert row["expected_sources"] and row["expected_contains"], row["id"]
        pages = []
        for source in row["expected_sources"]:
            texts = page_texts(source["file"])
            assert 1 <= source["page"] <= len(texts), row["id"]
            pages.append(texts[source["page"] - 1])
        for needle in row["expected_contains"]:
            assert any(fold(needle) in page for page in pages), (row["id"], needle)


def test_every_case_has_a_fair_expected_source_set() -> None:
    """Answerable cases name only pages that carry an expected fact, never the whole corpus."""
    for row in cases():
        if row["expected_behavior"] != "grounded":
            continue
        assert len(row["expected_sources"]) <= 4, row["id"]
        needles = [fold(n) for n in row["expected_contains"]]
        for source in row["expected_sources"]:
            page = page_texts(source["file"])[source["page"] - 1]
            assert any(n in page for n in needles), (row["id"], source)


def test_no_answer_leaks_into_the_question() -> None:
    for row in cases():
        question = fold(row["question"])
        for needle in row["expected_contains"]:
            assert fold(needle) not in question, (row["id"], needle)


@pytest.mark.parametrize("language", ["en"])
def test_english_paraphrases_do_not_quote_the_page(language: str) -> None:
    for row in cases():
        if row["language"] != language or row["category"] not in ("paraphrase",):
            continue
        asked = ngrams(row["question"], MAX_SHARED_WORDS + 1)
        for source in row["expected_sources"]:
            page = page_texts(source["file"])[source["page"] - 1]
            shared = asked & ngrams(page, MAX_SHARED_WORDS + 1)
            assert not shared, (row["id"], shared)


def test_typo_cases_actually_contain_a_non_word() -> None:
    corpus_words = set(WORD.findall(corpus_text()))
    for row in cases():
        if row["category"] != "typo" or row["language"] != "en":
            continue
        unknown = [w for w in WORD.findall(fold(row["question"])) if w not in corpus_words]
        assert unknown, row["id"]


def test_unanswerable_cases_are_really_absent_from_the_corpus() -> None:
    text = corpus_text()
    for row in cases():
        if row["expected_behavior"] != "abstain":
            continue
        assert row["absent"], row["id"]
        for term in row["absent"]:
            assert fold(term) not in text, (row["id"], term)
