"""File parsers (docs/14 §3): PDF (pypdf), DOCX (python-docx), TXT/MD, Q&A CSV.

All parsers run inside the ingest worker with a wall-clock timeout (docs/06).
Uploaded files are untrusted input: sizes are capped in the API, DOCX zip
expansion is measured before parsing, PDF page counts are capped, NUL bytes
are stripped, and every text extracted from a document is DATA (never a
system instruction later).
"""

import io
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import PurePosixPath

import pypdf
from docx import Document as DocxDocument
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.knowledge.front_matter import split_front_matter
from app.knowledge.parsing import ParsedPage, ParsedSection, ParseError

# Parsing settings live on Settings; these are passed in explicitly to keep
# the parsers pure and easy to test.


@dataclass
class ParseLimits:
    max_pdf_pages: int
    max_docx_uncompressed_bytes: int
    max_docx_zip_ratio: int


def strip_nuls(text: str) -> str:
    """Postgres text cannot hold NUL bytes; PDF streams often leak them."""
    return text.replace("\x00", "")


def clean_extracted(text: str) -> str:
    """Normalise the extracted text: strip NULs, trailing spaces per line."""
    stripped = strip_nuls(text)
    lines = [line.rstrip() for line in stripped.split("\n")]
    # Collapse a run of blank lines to one.
    cleaned: list[str] = []
    for line in lines:
        if line == "" and cleaned and cleaned[-1] == "":
            continue
        cleaned.append(line)
    return "\n".join(cleaned).strip()


# --- PDF ---------------------------------------------------------------------


def normalise_pdf_text(text: str) -> str:
    """Fold PDF glyph codepoints back to the letters they stand for.

    Many PDFs (Arabic exports above all) put presentation forms (U+FB50-FEFF)
    and Latin ligatures (U+FB00-FB06) in the text layer. NFKC maps them to the
    plain letters, so search terms and the stored ``text_norm`` match what
    visitors type; plain text is unchanged.
    """
    return unicodedata.normalize("NFKC", text)


def parse_pdf(data: bytes, original_name: str, limits: ParseLimits) -> list[ParsedPage]:
    """One section per page (docs/14 §3); scanned PDFs are rejected — no OCR in MVP."""
    try:
        reader = pypdf.PdfReader(io.BytesIO(data), strict=False)
    except Exception as error:  # noqa: BLE001 - pypdf raises many error types
        raise ParseError("The PDF file is corrupt and could not be parsed.") from error
    if getattr(reader, "encrypted", False):
        raise ParseError("Encrypted PDF files are not supported.")
    page_count = len(reader.pages)
    if page_count == 0:
        raise ParseError("The PDF file has no pages.")
    if page_count > limits.max_pdf_pages:
        raise ParseError(f"The PDF has {page_count} pages; the maximum is {limits.max_pdf_pages}.")
    pages: list[ParsedPage] = []
    for index, page in enumerate(reader.pages, start=1):
        try:
            extracted = normalise_pdf_text(page.extract_text() or "")
        except Exception:  # noqa: BLE001 - untrusted input
            extracted = ""
        text = clean_extracted(extracted)
        if not text:
            # Scanned (image-only) page: no extractable text.
            text = ""
        pages.append(
            ParsedPage(
                page_number=index,
                title=f"{original_name} — Page {index}",
                text=text,
                sections=[ParsedSection(heading=None, text=text)],
            )
        )
    if all(page.text == "" for page in pages):
        raise ParseError(
            "No extractable text found (the PDF looks scanned). "
            "Scanned documents are not supported — use a text-based PDF."
        )
    return pages


# --- DOCX --------------------------------------------------------------------


def _check_docx_zip(data: bytes, limits: ParseLimits) -> None:
    """Zip-bomb guard: cap the uncompressed size and the expansion ratio."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos = archive.infolist()
    except zipfile.BadZipFile as error:
        raise ParseError("The DOCX file is corrupt (not a valid Office file).") from error
    uncompressed = sum(info.file_size for info in infos)
    compressed = sum(info.compress_size for info in infos) or 1
    if uncompressed > limits.max_docx_uncompressed_bytes:
        raise ParseError("The DOCX file decompresses to more than the allowed size.")
    if uncompressed / compressed > limits.max_docx_zip_ratio:
        raise ParseError("The DOCX file looks like a zip bomb (excessive expansion).")


def parse_docx(data: bytes, original_name: str, limits: ParseLimits) -> list[ParsedPage]:
    """Heading sections; table rows become lines of text (docs/14 §3)."""
    _check_docx_zip(data, limits)
    try:
        document = DocxDocument(io.BytesIO(data))
    except Exception as error:  # noqa: BLE001 - python-docx raises several types
        raise ParseError("The DOCX file could not be parsed.") from error

    sections: list[ParsedSection] = []
    heading: str | None = None
    buffer: list[str] = []

    def flush() -> None:
        text = clean_extracted("\n".join(buffer))
        if text:
            sections.append(ParsedSection(heading=heading, text=text))
        buffer.clear()

    for item in document.iter_inner_content():
        if isinstance(item, Paragraph):
            style_name = (item.style.name or "") if item.style is not None else ""
            if style_name.startswith("Heading"):
                flush()
                heading = item.text.strip() or heading
            else:
                if item.text.strip():
                    buffer.append(item.text)
        elif isinstance(item, Table):
            # Keep the header line and repeat its labels in every data row, so
            # chunks retain column meaning when a large table crosses a boundary.
            rows = [[cell.text.strip() for cell in row.cells] for row in item.rows]
            headers = rows[0] if rows else []
            if any(headers):
                buffer.append(" — ".join(headers))
            for cells in rows[1:]:
                pairs = []
                for index, cell in enumerate(cells):
                    label = headers[index] if index < len(headers) else ""
                    if cell:
                        pairs.append(f"{label or f'Column {index + 1}'}: {cell}")
                line = " — ".join(pairs)
                if line:
                    buffer.append(line)
    flush()

    if not sections:
        raise ParseError("The DOCX file contains no readable text.")
    return [
        ParsedPage(
            page_number=None,
            title=original_name,
            text="\n\n".join(section.text for section in sections),
            sections=sections,
        )
    ]


# --- TXT / MD ----------------------------------------------------------------

_HEADING_PREFIXES = tuple("#" * level + " " for level in range(1, 7))


def decode_text(data: bytes) -> str:
    """UTF-8 with a latin-1 fallback (docs/14 §3)."""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def parse_text(data: bytes, original_name: str) -> list[ParsedPage]:
    """Parse TXT/MD: front matter, then markdown headings or blank-line paragraphs."""
    raw = decode_text(data)
    front, body = split_front_matter(raw)
    sections = _split_sections(body)
    if not sections:
        raise ParseError("The file contains no readable text.")
    # The page text keeps the body (front matter is metadata, not content).
    return [
        ParsedPage(
            page_number=None,
            title=front.title or original_name,
            text=body.strip(),
            sections=sections,
            source_url=front.source_url,
            page_type=front.page_type,
            language=front.language,
        )
    ]


def _has_heading(body: str) -> bool:
    return any(line.lstrip().startswith(_HEADING_PREFIXES) for line in body.split("\n"))


def _split_sections(body: str) -> list[ParsedSection]:
    """Split at markdown headings; when the file has none, at blank-line paragraphs."""
    if _has_heading(body):
        return _split_at_headings(body)
    return _split_at_blank_lines(body)


def _split_at_headings(body: str) -> list[ParsedSection]:
    sections: list[ParsedSection] = []
    heading: str | None = None
    buffer: list[str] = []

    def flush() -> None:
        text = clean_extracted("\n".join(buffer))
        if text:
            sections.append(ParsedSection(heading=heading, text=text))
        buffer.clear()

    for line in body.split("\n"):
        stripped = line.lstrip()
        if stripped.startswith(_HEADING_PREFIXES):
            flush()
            heading = stripped.lstrip("#").strip() or heading
        else:
            buffer.append(line)
    flush()
    return sections


def _split_at_blank_lines(body: str) -> list[ParsedSection]:
    sections: list[ParsedSection] = []
    buffer: list[str] = []

    def flush() -> None:
        text = clean_extracted("\n".join(buffer))
        if text:
            sections.append(ParsedSection(heading=None, text=text))
        buffer.clear()

    for line in body.split("\n"):
        if line.strip() == "":
            flush()
        else:
            buffer.append(line)
    flush()
    return sections


# --- upload sniffing (docs/06 hardening) --------------------------------------


# Extension aliases accepted for upload; content must agree with the extension.
_TEXTUAL_EXTENSIONS = {"txt", "md", "csv"}


def sniff_kind(head: bytes) -> str | None:
    """Magic-byte sniffing: 'pdf', 'zip' or 'text' (never trusts Content-Type)."""
    if head.startswith(b"%PDF-"):
        return "pdf"
    if head.startswith(b"PK\x03\x04") or head.startswith(b"PK\x05\x06"):
        return "zip"
    if b"\x00" in head:
        return None  # binary content of an unknown flavour
    return "text"


def docx_is_real(data: bytes) -> bool:
    """A valid DOCX is a zip whose central directory holds ``word/document.xml``."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            return "word/document.xml" in archive.namelist()
    except zipfile.BadZipFile:
        return False


def detect_and_validate(filename: str | None, data: bytes) -> str:
    """Return the source kind ('pdf'|'docx'|'txt'|'md'|'qa_csv') or reject.

    Sniffs content and enforces extension/content agreement so a renamed
    PDF/DOCX cannot slip through as text (mislabelled files are rejected).
    """
    head = data[:512]
    detected = sniff_kind(head)
    extension = PurePosixPath((filename or "").replace("\\", "/")).suffix.lstrip(".").lower()

    if detected == "pdf":
        if extension and extension != "pdf":
            raise ValueError(f"The file content is a PDF but the name suggests .{extension}.")
        return "pdf"
    if detected == "zip":
        if extension and extension != "docx":
            raise ValueError(
                f"The file content is a zip archive but the name suggests .{extension}."
            )
        if not docx_is_real(data):
            raise ValueError("The file is a zip archive but not a Word document.")
        return "docx"
    if detected == "text":
        if extension == "csv":
            return "qa_csv"
        if extension in ("", "txt", "markdown"):
            return "txt" if extension in ("", "txt") else "md"
        if extension == "md":
            return "md"
        supported = "txt, md or csv"
        raise ValueError(
            f"The file looks like text but .{extension or 'txt'} is not supported; use {supported}."
        )
    raise ValueError("Unsupported file type. Only PDF, DOCX, TXT, MD and CSV files are accepted.")
