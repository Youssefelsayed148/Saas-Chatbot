"""Q&A CSV import (docs/14 §3, docs/14 §19 template contract).

Columns ``question, answer, topic, priority`` (case-insensitive, UTF-8 BOM
allowed); priority integer 0–10, default 0; blank rows skipped. Invalid rows
produce a row-level error report (row number, reason). Every valid row
becomes ONE chunk "Q: … A: …", never split.
"""

import csv
import io
from dataclasses import dataclass, field

REQUIRED_COLUMNS = {"question", "answer"}
KNOWN_COLUMNS = {"question", "answer", "topic", "priority"}


class CsvStructureError(Exception):
    """The CSV does not have the required columns."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass
class QaRow:
    question: str
    answer: str
    topic: str | None
    priority: int


@dataclass
class QaParseResult:
    rows: list[QaRow] = field(default_factory=list)
    errors: list[dict[str, str | int]] = field(default_factory=list)
    total_rows: int = 0

    @property
    def valid_rows(self) -> int:
        return len(self.rows)


def qa_template_csv() -> bytes:
    """The downloadable template (docs/05 qa-template contract)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["question", "answer", "topic", "priority"])
    writer.writerow(
        ["What are your opening hours?", "We are open 9:00-17:00, Sun-Thu.", "hours", "5"]
    )
    return buffer.getvalue().encode("utf-8")


def parse_qa_csv(data: bytes) -> QaParseResult:
    """Parse and validate a Q&A CSV; collects a per-row error report."""
    # UTF-8 (BOM tolerated); latin-1 fallback mirrors text-file handling.
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("latin-1")
    if "\x00" in text:
        raise CsvStructureError("The CSV is not a plain-text Q&A file.")

    reader = csv.reader(io.StringIO(text))
    try:
        header_row = next(reader)
    except StopIteration as error:
        raise CsvStructureError("The CSV file is empty.") from error
    header = [cell.strip().lower() for cell in header_row]
    missing = REQUIRED_COLUMNS - set(header)
    if missing:
        raise CsvStructureError("Missing required column(s): " + ", ".join(sorted(missing)) + ".")
    result = QaParseResult()

    for offset, row in enumerate(reader, start=2):
        result.total_rows += 1

        def column(name: str, current_row: list[str] = row) -> str:
            try:
                index = header.index(name)
            except ValueError:
                return ""
            return current_row[index].strip() if index < len(current_row) else ""

        if all(cell.strip() == "" for cell in row):
            continue  # blank rows are skipped, silently

        question = column("question")
        answer = column("answer")
        reason = ""
        if not question:
            reason = "missing question"
        elif not answer:
            reason = "missing answer"
        else:
            priority_text = column("priority")
            if priority_text == "":
                priority = 0
            else:
                try:
                    priority = int(priority_text)
                except ValueError:
                    priority = -1
                if not 0 <= priority <= 10:
                    reason = f"priority must be an integer 0-10, got {priority_text!r}"
                    priority = 0
        if reason:
            result.errors.append({"row": offset, "reason": reason})
            continue
        result.rows.append(
            QaRow(
                question=question,
                answer=answer,
                topic=column("topic") or None,
                priority=priority,
            )
        )
    return result
