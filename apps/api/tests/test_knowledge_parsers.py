"""P2-02: parsers, chunking, language detection/Arabic normalisation, Q&A CSV.

Covers docs/14 §2 (languages), §3 (parsing rules + limits), §4 (chunking).
"""

import os
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.db.models import Source
from app.knowledge.chunking import split_text
from app.knowledge.csv_qa import CsvStructureError, parse_qa_csv, qa_template_csv
from app.knowledge.ingest import parse_source
from app.knowledge.language import content_hash, detect_language, normalise_text
from app.knowledge.parsers import ParseLimits, normalise_pdf_text, parse_docx, parse_pdf, parse_text
from app.knowledge.parsing import ParsedPage, ParseError
from tests.fixtures_factory import (
    make_corrupt_pdf,
    make_docx,
    make_docx_with_table,
    make_pdf_pages,
    make_scanned_pdf,
    make_zip_bomb_docx,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _slow_parse_for_timeout_test(
    kind: str, original_name: str, data: bytes, parser_limits: ParseLimits
) -> list[ParsedPage]:
    del kind, original_name, data, parser_limits
    time.sleep(5)
    return []


def _parser_with_child(
    kind: str, original_name: str, data: bytes, parser_limits: ParseLimits
) -> list[ParsedPage]:
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    Path(original_name).write_text(str(child.pid))
    time.sleep(60)
    return []


@pytest.mark.skipif(
    os.name != "posix", reason="POSIX process group integration; Windows unverified"
)
def test_parse_timeout_kills_descendant_process(tmp_path: Path) -> None:
    marker = tmp_path / "child.pid"
    source = Source(kind="txt", original_name=str(marker))
    started = time.monotonic()
    with pytest.raises(ParseError, match="Parsing timed out"):
        parse_source(
            source,
            b"fixture",
            parse_limits_settings(parse_timeout_seconds=2),
            parser=_parser_with_child,
        )
    assert time.monotonic() - started < 5
    assert marker.exists(), "nested helper must actually have started"
    pid = int(marker.read_text())
    # A dead zombie may await adoption/reaping in a minimal container; it cannot
    # run or retain parser handles. Accept only absent or dead, never sleeping.
    stat = Path(f"/proc/{pid}/stat")
    deadline = time.monotonic() + 2
    while stat.exists() and stat.read_text().split()[2] != "Z" and time.monotonic() < deadline:
        time.sleep(0.02)
    assert not stat.exists() or stat.read_text().split()[2] == "Z"


def test_parse_source_enforces_byte_cap_before_starting_child() -> None:
    source = Source(kind="txt", original_name="large.txt")
    settings = Settings.model_construct(max_upload_file_bytes=3)
    with pytest.raises(ParseError, match="parsing size"):
        parse_source(source, b"1234", settings)


def parse_limits_settings(**overrides: int) -> Settings:
    """Parser limits matching the product defaults (docs/14 §3)."""
    return Settings.model_construct(
        max_pdf_pages=overrides.get("max_pdf_pages", 300),
        max_docx_uncompressed_bytes=100 << 20,
        max_docx_zip_ratio=200,
        parse_timeout_seconds=overrides.get("parse_timeout_seconds", 60),
        chunk_size=1500,
        chunk_overlap=200,
    )


def test_parse_subprocess_is_terminated_at_timeout() -> None:
    settings = parse_limits_settings(parse_timeout_seconds=2)
    source = Source(
        id=uuid4(),
        tenant_id=uuid4(),
        bot_id=uuid4(),
        kind="txt",
        original_name="slow.txt",
        storage_key="not-used",
        size_bytes=1,
        sha256="0" * 64,
        created_by=uuid4(),
    )
    with pytest.raises(ParseError, match="Parsing timed out"):
        parse_source(source, b"x", settings, parser=_slow_parse_for_timeout_test)


def limits(settings: Settings) -> ParseLimits:
    return ParseLimits(
        max_pdf_pages=settings.max_pdf_pages,
        max_docx_uncompressed_bytes=settings.max_docx_uncompressed_bytes,
        max_docx_zip_ratio=settings.max_docx_zip_ratio,
    )


# --- PDF ---------------------------------------------------------------------


def test_pdf_one_section_per_page_with_titles() -> None:
    data = make_pdf_pages([["Alpha page, prices apply."], ["Beta: second page."]])
    pages = parse_pdf(data, "offer.pdf", limits(parse_limits_settings()))
    assert [page.title for page in pages] == ["offer.pdf — Page 1", "offer.pdf — Page 2"]
    assert "Alpha" in pages[0].text
    assert pages[0].sections[0].heading is None


def test_pdf_page_cap_rejected() -> None:
    data = make_pdf_pages([["x"]] * 4)
    with pytest.raises(ParseError, match="maximum is 2"):
        parse_pdf(data, "huge.pdf", limits(parse_limits_settings(max_pdf_pages=2)))


def test_scanned_pdf_is_rejected_without_ocr() -> None:
    with pytest.raises(ParseError, match="No extractable text"):
        parse_pdf(make_scanned_pdf(), "scan.pdf", limits(parse_limits_settings()))


def test_corrupt_pdf_is_rejected() -> None:
    with pytest.raises(ParseError, match="corrupt"):
        parse_pdf(make_corrupt_pdf(), "broken.pdf", limits(parse_limits_settings()))


def test_pdf_nul_bytes_stripped() -> None:
    data = make_pdf_pages([["Price: 100\x00 USD"]])
    pages = parse_pdf(data, "nul.pdf", limits(parse_limits_settings()))
    assert "\x00" not in "".join(page.text for page in pages)


def test_pdf_glyph_codepoints_fold_to_plain_letters() -> None:
    # Presentation-form Arabic (as pypdf returns it from many exports) and a Latin ligature.
    glyphs = "\ufe8e\ufedf\ufe8e\ufeb3\ufe98\ufeae\ufe8e\ufea9 \ufb00ective"
    folded = normalise_pdf_text(glyphs)
    assert "\u0627\u0644\u0627\u0633\u062a\u0631\u0627\u062f" in folded
    assert folded.endswith("ffective")
    assert normalise_pdf_text("Plain text 100 USD") == "Plain text 100 USD"


# --- DOCX --------------------------------------------------------------------


def test_docx_heading_sections_and_tables() -> None:
    data = make_docx_with_table(
        "Return policy", [["Item", "Window"], ["Shoes", "14 days"], ["Boots", "30 days"]]
    )
    page = parse_docx(data, "policy.docx", limits(parse_limits_settings()))[0]
    assert any(section.heading == "Return policy" for section in page.sections)
    assert any("Item: Shoes — Window: 14 days" in section.text for section in page.sections)
    assert any("Item: Boots — Window: 30 days" in section.text for section in page.sections)


def test_docx_arabic_content() -> None:
    data = make_docx([("الأسئلة الشائعة", ["نحن نعمل من الأحد إلى الخميس."])])
    page = parse_docx(data, "arabic.docx", limits(parse_limits_settings()))[0]
    assert page.sections[0].heading == "الأسئلة الشائعة"
    assert "الأحد" in page.sections[0].text


def test_docx_zip_bomb_rejected() -> None:
    with pytest.raises(ParseError, match="zip bomb|decompresses"):
        parse_docx(make_zip_bomb_docx(), "bomb.docx", limits(parse_limits_settings()))


def test_docx_empty_rejected() -> None:
    with pytest.raises(ParseError, match="no readable text"):
        parse_docx(make_docx([]), "empty.docx", limits(parse_limits_settings()))


# --- TXT / MD ----------------------------------------------------------------


def test_md_front_matter_and_headings() -> None:
    data = (FIXTURES / "skill-output" / "pages" / "001-services.md").read_bytes()
    page = parse_text(data, "001-services.md")[0]
    assert page.title == "Services overview"
    assert page.source_url == "https://acme-services.example.com/services"
    assert page.language == "en"
    assert page.page_type == "services"
    headings = [section.heading for section in page.sections]
    assert "Services" in headings and "Pricing" in headings


def test_md_non_http_source_url_dropped() -> None:
    data = b"---\ntitle: X\nsource_url: javascript:alert(1)\n---\n\nbody"
    page = parse_text(data, "x.md")[0]
    assert page.source_url is None


def test_txt_no_headings_splits_at_blank_lines() -> None:
    data = b"first paragraph\nsecond line\n\nsecond paragraph"
    page = parse_text(data, "notes.txt")[0]
    assert [section.text.split("\n")[0] for section in page.sections] == [
        "first paragraph",
        "second paragraph",
    ]
    assert all(section.heading is None for section in page.sections)


def test_txt_latin1_fallback() -> None:
    page = parse_text(b"caf\xe9 is open", "legacy.txt")[0]  # latin-1 é
    assert "café" in page.text


def test_arabic_md_fixture_language_detection() -> None:
    data = (FIXTURES / "skill-output" / "pages" / "002-faq-ar.md").read_bytes()
    page = parse_text(data, "002-faq-ar.md")[0]
    assert page.language == "ar"  # front matter override wins
    assert any(section.heading == "ساعات العمل" for section in page.sections)


# --- chunking (docs/14 §4) -----------------------------------------------------


def test_short_document_is_single_chunk() -> None:
    assert split_text("A short policy text.", 1500, 200) == ["A short policy text."]


def test_long_text_splits_and_never_loses_content() -> None:
    text = "\n\n".join(f"paragraph {number} " + "content words " * 60 for number in range(1, 9))
    chunks = split_text(text, 1500, 200)
    assert len(chunks) > 1
    assert all(len(chunk) <= 1500 for chunk in chunks)
    joined = "".join(chunks)
    for number in range(1, 9):
        assert f"paragraph {number}" in joined


def test_chunk_overlap_present() -> None:
    text = " ".join(f"word{number}" for number in range(1, 400))
    chunks = split_text(text, 1500, 200)
    assert len(chunks) >= 2
    # The next chunk starts with the tail of the previous one (overlap 200).
    assert chunks[1].startswith(chunks[0][-200:])


def test_arabic_paragraph_split() -> None:
    text = "سؤال واحد؟ " * 600
    chunks = split_text(text, 1500, 200)
    assert len(chunks) > 1 and all(len(chunk) <= 1500 for chunk in chunks)


def test_giant_word_hard_sliced_without_loss() -> None:
    chunk = split_text("x" * 4000, 1500, 200)
    assert len(chunk) >= 3 and chunk[-1][-1] == "x"


# --- language + Arabic normalisation (docs/14 §2) -------------------------------


def test_detect_language_rules() -> None:
    assert detect_language("Hello world") == "en"
    assert detect_language("مرحبا كيف حالك") == "ar"
    assert detect_language("مرحبا hello") == "ar"  # arabic >= latin (tie → ar)
    assert detect_language("12345 !!! ...") is None


def test_arabic_normalisation_map_and_strip() -> None:
    assert normalise_text("مُحَمَّد") == "محمد"  # diacritics stripped
    assert normalise_text("أإآ") == "ااا"  # hamza forms collapse to plain alef
    assert normalise_text("ى") == "ي"  # alef maqsura → ya
    assert "ـــ" not in normalise_text("وـــالساعة")  # tatweel removed
    assert normalise_text("ABC") == "abc"


def test_content_hash_is_sha256_of_normalised_text() -> None:
    import hashlib

    normalised = normalise_text("سؤال واحد")
    assert content_hash(normalised) == hashlib.sha256(normalised.encode("utf-8")).hexdigest()


# --- Q&A CSV (docs/14 §3) ------------------------------------------------------


def test_qa_template_has_required_columns() -> None:
    result = parse_qa_csv(qa_template_csv())
    assert result.valid_rows == 1  # one example row


def test_qa_csv_valid_rows_and_blank_skipping() -> None:
    data = (
        b"\xef\xbb\xbfQUESTION,ANSWER, Topic, priority\n"  # BOM + case-insensitive
        b"What is the return window?,14 days with the invoice.,returns,7\n"
        b",,\n"
        b"Q2,A2,,\n"
    )
    result = parse_qa_csv(data)
    assert result.total_rows == 3  # one blank row skipped
    assert result.valid_rows == 2
    assert result.rows[0].priority == 7
    assert result.rows[1].priority == 0  # default


def test_qa_csv_row_level_errors() -> None:
    data = (
        b"Question,Answer,Topic,Priority\n"
        b",missing question,,\n"
        b"No answer,,,\n"
        b"Bad priority,x,,9.5\n"
        b"Good one,y,gen,3\n"
    )
    result = parse_qa_csv(data)
    assert [(error["row"], error["reason"]) for error in result.errors] == [
        (2, "missing question"),
        (3, "missing answer"),
        (4, "priority must be an integer 0-10, got '9.5'"),
    ]
    assert result.valid_rows == 1


def test_qa_csv_missing_columns_rejected() -> None:
    with pytest.raises(CsvStructureError, match="Missing required column"):
        parse_qa_csv(b"question\nonly the question\n")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__]))
