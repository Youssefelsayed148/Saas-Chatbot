"""B.1 / B.2: the frozen corpus and the Nile eval cases agree with each other.

Reads the frozen PDFs with pypdf (the ingestion parser) and checks that every
expected page really contains the expected strings, so a case can never point
at a page that does not hold its answer. No database.
"""

import hashlib
import json
import unicodedata
from collections import Counter
from functools import cache
from pathlib import Path
from typing import Any

import pypdf
import pytest

EVAL_DIR = Path(__file__).resolve().parents[1]
CORPUS = EVAL_DIR / "corpus"
CASES_PATH = EVAL_DIR / "nile_eval.jsonl"
BEHAVIOURS = {"grounded", "abstain", "injection"}


def load_nile_cases() -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in CASES_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]


@cache
def page_texts(filename: str) -> tuple[str, ...]:
    reader = pypdf.PdfReader(str(CORPUS / filename), strict=False)
    return tuple(
        unicodedata.normalize("NFKC", page.extract_text() or "").casefold() for page in reader.pages
    )


def test_corpus_hashes_match_the_frozen_list() -> None:
    listed = {}
    for line in (CORPUS / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
        if line.strip():
            digest, name = line.split(None, 1)
            listed[name.strip().lstrip("*")] = digest
    pdfs = sorted(path.name for path in CORPUS.glob("*.pdf"))
    assert len(pdfs) == 10 and sorted(listed) == pdfs
    for name in pdfs:
        assert hashlib.sha256((CORPUS / name).read_bytes()).hexdigest() == listed[name], name


def test_corpus_has_forty_text_pages() -> None:
    total = sum(len(page_texts(path.name)) for path in CORPUS.glob("*.pdf"))
    assert total == 40
    assert all(text.strip() for path in CORPUS.glob("*.pdf") for text in page_texts(path.name))


def test_case_file_shape_and_mix() -> None:
    cases = load_nile_cases()
    assert 38 <= len(cases) <= 45
    assert len({case["id"] for case in cases}) == len(cases)
    for case in cases:
        assert case["expected_behavior"] in BEHAVIOURS, case["id"]
        assert case["language"] in ("en", "ar"), case["id"]
        assert case["question"].strip() and isinstance(case["history"], list)
        if case["expected_behavior"] == "abstain":
            assert case["expected_sources"] == [], case["id"]
        if case["expected_behavior"] == "grounded":
            assert case["expected_sources"], case["id"]
    behaviours = Counter(case["expected_behavior"] for case in cases)
    assert behaviours["grounded"] >= 20 and behaviours["abstain"] >= 10
    assert behaviours["injection"] >= 4
    categories = {case["category"] for case in cases}
    assert {"grounded", "gap", "store_name_only", "follow_up", "injection"} <= categories
    assert {"near_miss_product", "near_miss_policy"} <= categories
    assert sum(1 for case in cases if case["history"]) >= 4


def test_every_english_case_has_an_arabic_twin_with_the_same_expectations() -> None:
    cases = load_nile_cases()
    by_pair: dict[str, dict[str, dict[str, Any]]] = {}
    for case in cases:
        by_pair.setdefault(case["pair_id"], {})[case["language"]] = case
    for pair_id, group in by_pair.items():
        if len(group) == 2:
            en, ar = group["en"], group["ar"]
            assert en["expected_behavior"] == ar["expected_behavior"], pair_id
            assert [s["page"] for s in en["expected_sources"]] == [
                s["page"] for s in ar["expected_sources"]
            ], pair_id
    paired = [pid for pid, group in by_pair.items() if len(group) == 2]
    arabic = [case for case in cases if case["language"] == "ar"]
    assert len(paired) >= 14 and len(arabic) >= 18


def test_expected_pages_contain_the_expected_text() -> None:
    checked = 0
    for case in load_nile_cases():
        for source in case["expected_sources"]:
            assert source["file"].endswith(f"-{case['language']}_1.pdf"), case["id"]
            pages = page_texts(source["file"])
            assert 1 <= source["page"] <= len(pages), case["id"]
            page = pages[source["page"] - 1]
            for needle in case["expected_contains"]:
                folded = unicodedata.normalize("NFKC", needle).casefold()
                assert folded in page, (case["id"], source, needle)
                checked += 1
    assert checked >= 40


@pytest.mark.parametrize("trap", ["nilecart", "نايل كارت"])
def test_the_store_name_is_on_every_policy_so_it_is_a_real_trap(trap: str) -> None:
    for path in sorted(CORPUS.glob("*.pdf")):
        first_page = page_texts(path.name)[0]
        if trap == "nilecart" and "-en_" in path.name:
            assert trap in first_page, path.name
        if trap != "nilecart" and "-ar_" in path.name:
            assert unicodedata.normalize("NFKC", trap).casefold() in first_page, path.name
