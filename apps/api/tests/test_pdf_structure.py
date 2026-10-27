"""Chunking quality: PDF heading sections, sections that run over a page break and
word-safe hard slicing. Pure functions: no database."""

from app.knowledge.chunking import _hard_slices
from app.knowledge.parsing import ParsedPage, ParsedSection
from app.knowledge.pdf_structure import merge_continued_sections, split_page_sections

TERMS = (
    "NileCart — Terms of Use\n"
    "Effective 1 October 2026 · Version 2.4\n"
    "1. Account and Ordering Rules\n"
    "You must be at least 18 years old to create an account and place orders.\n"
    "2. Payments\n"
    "Prices are shown in EGP and include VAT."
)


def test_numbered_headings_become_sections() -> None:
    sections = split_page_sections(TERMS)
    assert [section.heading for section in sections] == [
        None,
        "1. Account and Ordering Rules",
        "2. Payments",
    ]
    assert sections[0].text.startswith("NileCart — Terms of Use")
    assert sections[1].text.startswith("You must be at least 18")
    assert sections[2].text == "Prices are shown in EGP and include VAT."


def test_a_page_without_headings_stays_one_section() -> None:
    text = "Delivery takes two days.\nIt is free over 500 EGP.\nSee the zones table."
    sections = split_page_sections(text)
    assert len(sections) == 1 and sections[0].heading is None and sections[0].text == text


def test_numbered_list_items_are_not_headings() -> None:
    text = (
        "How to return an item\n"
        "1. Request the return\n"
        "2. Wait for approval\n"
        "3. Send the parcel\n"
        "Returns without a request number may be rejected."
    )
    assert [section.heading for section in split_page_sections(text)] == [None]


def test_bullets_sentences_and_long_lines_are_not_headings() -> None:
    text = (
        "- Free shipping\n"
        "Refunds are issued within 7 days.\n"
        "This is a very long line that happens to carry no final punctuation at all "
        "and therefore must not be mistaken for a heading\n"
        "More text."
    )
    assert [section.heading for section in split_page_sections(text)] == [None]


def test_all_caps_and_arabic_numbered_headings() -> None:
    caps = split_page_sections("RETURNS\nItems can be returned within 30 days.")
    assert caps[0].heading == "RETURNS"
    arabic = split_page_sections("١. شروط الاستخدام\nيجب أن يكون عمرك ١٨ عاما على الأقل.")
    assert arabic[0].heading == "١. شروط الاستخدام"


def test_heading_without_body_leads_the_next_one() -> None:
    text = "1. Policies\n1.1 Returns\nItems return within 30 days."
    sections = split_page_sections(text)
    assert len(sections) == 1
    assert sections[0].heading == "1. Policies — 1.1 Returns"


def _page(number: int, text: str, sections: list[ParsedSection] | None = None) -> ParsedPage:
    return ParsedPage(
        page_number=number,
        title=f"doc.pdf — Page {number}",
        text=text,
        sections=sections if sections is not None else split_page_sections(text),
    )


def test_section_running_over_a_page_break_is_merged() -> None:
    first = _page(1, "1. Refunds\nRefunds are issued to the original payment method within")
    second = _page(
        2, "seven business days after we receive the item.\n2. Exchanges\nExchange once."
    )
    merged = merge_continued_sections([first, second])
    assert len(merged[0].sections) == 1
    section = merged[0].sections[0]
    assert section.heading == "1. Refunds"
    assert "within\nseven business days" in section.text
    assert section.ref == "Pages 1–2"
    assert [s.heading for s in merged[1].sections] == ["2. Exchanges"]
    assert merged[1].continued_from_previous is True


def test_a_section_over_three_pages_keeps_one_range() -> None:
    pages = [
        _page(1, "1. Terms\nThe customer agrees that"),
        _page(2, "all orders are subject to"),
        _page(3, "availability and confirmation."),
    ]
    merged = merge_continued_sections(pages)
    assert merged[0].sections[0].ref == "Pages 1–3"
    assert merged[0].sections[0].text.endswith("availability and confirmation.")
    assert merged[1].sections == [] and merged[2].sections == []


def test_new_sentence_or_heading_on_next_page_is_not_merged() -> None:
    ended = merge_continued_sections(
        [_page(1, "1. A\nIt ends here."), _page(2, "Next page starts a new sentence.")]
    )
    assert ended[1].continued_from_previous is False
    headed = merge_continued_sections(
        [_page(1, "1. A\nIt runs on and on"), _page(2, "2. B\nA different topic.")]
    )
    assert headed[1].continued_from_previous is False and len(headed[1].sections) == 1


def test_hard_slices_do_not_cut_words() -> None:
    words = [f"word{number}" for number in range(300)]
    text = " ".join(words)
    slices = _hard_slices(text, 100, 20)
    assert len(slices) > 3
    for piece in slices:
        assert len(piece) <= 100
        assert set(piece.split()) <= set(words)  # no half words at either end
    covered = {word for piece in slices for word in piece.split()}
    assert covered == set(words)  # nothing is dropped


def test_hard_slices_without_spaces_still_cover_everything() -> None:
    slices = _hard_slices("x" * 1000, 300, 50)
    assert all(len(piece) <= 300 for piece in slices)
    assert sum(len(piece) for piece in slices) >= 1000
