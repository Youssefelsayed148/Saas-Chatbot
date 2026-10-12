# P2-02 REPORT — Upload endpoint, parsers, chunking, Q&A CSV

Date: 2026-10-12. Status: DONE, locally verified.

New dependencies pinned in `pyproject.toml` + both lockfiles (+ Dockerfile reinstalls them): `pypdf==6.20.1`, `python-docx==1.2.0`, `PyYAML==6.0.3`, `python-multipart==0.0.32`, dev `types-PyYAML==6.0.12.20260906`.

## Storage interface (`app/knowledge/storage.py`)

- ABC `Storage` with `save/open/delete`; local-disk `LocalStorage` rooted at `Settings.storage_root` (Compose: `/data/storage` shared by api and worker).
- Files stored under **generated** tenant/bot-namespaced keys `{tenant_id}/{bot_id}/{uuid}.ext` — the user-supplied filename is never a path component (defence-in-depth check rejects `..`/absolute/\\ in keys); SHA-256 + size recorded on the sources row. Files are never served raw — no download endpoint exists; only parsed content reaches the UI.
- Windows fix validated by test: write with `O_BINARY` so DOCX/PDF bytes survive exactly (`tests/test_knowledge_pipeline.py::test_docx_sections_tables_and_headings` failed on Windows before the fix and passes after).

## Upload endpoint (`app/knowledge/service.py`, `app/knowledge/router.py`)

`POST /api/v1/tenants/{tenant}/bots/{bot}/sources/files` (editor+ CSRF):
- Batch is **atomic**: every file is validated first; any rejection stores nothing (files deleted if a later failure happens).
- Streaming size cap: reads 256 KB chunks, aborts > 10 MB per file with 413 `FILE_TOO_LARGE`; ≤ 20 files per batch (422); empty files rejected.
- **Magic-byte sniffing** (`parsers.detect_and_validate`): `%PDF-` → pdf; `PK\x03\x04` zip → docx (zip must actually contain `word/document.xml`); NUL byte → binary junk rejected; textual → txt/md/qa_csv by extension with a clear mislabelled-content error (`The file content is a PDF but the name suggests .md.`). Content-Type headers are never trusted.
- Q&A CSV validated at upload: required columns, per-row report (row number + reason); valid rows counted; **all-invalid CSVs are rejected 422 with the first reasons**; partial-validity CSVs are stored with the row report on the source (`row_errors`, `valid_rows`, `total_rows`).

## Proxy limits

- `apps/web/proxy.ts` (Next 16 proxy convention, matcher `/api/:path*`): rejects bodies with `content-length` > 220 MB (= 20 files × 10 MB + overhead) with 413 before anything is forwarded.
- `experimental.proxyClientMaxBodySize: "220mb"` in `next.config.ts`: discovers Next 16's proxy buffered-body default (10 MB) — without it a legitimate 20-file 200 MB batch gets truncated by the proxy (`Request body exceeded 10MB…` warning, backend socket hang-up observed live); raised to match the API's batch cap while the API keeps its own per-file streaming cap.
- **CSRF + limits verified through the same-origin Next proxy** (Playwright, port 3100 → FastAPI): big-file upload (10 MB + 1 byte) → 413 rendered in the UI with "Files may be at most 10 MB" and **no source stored** (`knowledge.spec.ts` oversize test, passed); every successful upload in the E2E carries the `X-CSRF-Token` header through the proxy; missing CSRF is 403 `CSRF_MISSING` (API test).

## Parsers (`app/knowledge/parsers.py`, `tests/fixtures_factory.py` helpers)

- PDF (pypdf): one section per page, title `<file> — Page N`, NUL stripping; page-count cap (`max_pdf_pages=300` → clear message); encrypted PDFs rejected; **scanned** PDFs (no extractable text) rejected with "No extractable text found… use a text-based PDF"; corrupt PDFs rejected.
- DOCX (python-docx): sections split at Heading styles (title = heading), table rows become text lines; `iter_inner_content` keeps document order; **zip-bomb guard**: total uncompressed size and expansion ratio caps (`_check_docx_zip` before parsing).
- TXT/MD: UTF-8 with latin-1 fallback; **YAML front matter** (`front_matter.py`, PyYAML safe_load): `title`, `source_url` (http/https only — non-http URLs silently dropped), `language` (`en|ar`, anything else ignored), `page_type`, `captured_at`; markdown files split at headings, files without headings at blank-line paragraphs.
- Q&A CSV (`csv_qa.py`): case-insensitive columns, BOM tolerated, priority 0–10 (default 0), blank rows skipped; downloadable template (`qa_template_csv`, `GET …/sources/qa-template`, editor+) with the exact columns; every valid row becomes ONE chunk `Q: … A: …` — never split; row-level error report surfaced in the upload response, the Files list and persisted on the source.

## Chunking + language (`chunking.py`, `language.py`) — docs/14 §2/§4

- Recursive splitter: 1500/200, separators `"\n\n","\n",". ","! ","? ","؟ ","، "," ",""`; separators preserved with pieces so words/sentences stay intact; overlap is never allowed to drop content; a document ≤ 1500 chars is ONE chunk; unbreakable tokens are hard-sliced with overlap so no character is lost; Arabic (`؟ `, `، `) separators covered (Arabic paragraph split test).
- Language detection: Arabic-script letters ≥ Latin letters → `ar`; no letters → fallback (front matter > bot default > `en`).
- Arabic normalisation for `text_norm` (and later queries): strip diacritics + tatweel, `أ إ آ → ا`, `ى → ي`; `content_hash` = SHA-256 of normalised text (dedupe key).

## Parse in the worker with a timeout

`ingest.parse_source` runs `_parse_sync` in a ThreadPoolExecutor with `Settings.parse_timeout_seconds` (120 s default); a timeout yields the actionable error "Parsing timed out…" for the source while the job keeps running. Runaway threads are bounded by the size/expansion caps (noted limitation in PHASE-REPORT.md).

## Fixtures and tests (26 parser tests + 17 upload/endpoint tests, all green on Linux + Windows)

- Committed fixtures: `tests/fixtures/skill-output/` (pages `001-services.md` EN with front matter, `002-faq-ar.md` Arabic, `qa.csv`, `coverage.md`) — the sample staff skill output folder uploads and ingests **end to end** (`test_skill_output_folder_uploads_end_to_end`, front matter `source_url`s present on the documents).
- Runtime builders: minimal valid PDFs (incl. Arabic-safe WinAnsi), scanned PDFs, corrupt PDFs, zip-bomb DOCX, mislabelled files (PDF→.md, DOCX→.pdf), binary junk, oversize blob.
- Endpoint behaviour: tenant B cannot upload to/list tenant A's bot (404 for guessed ids); viewer write-denied on upload/ingestion/cancel/retry/publish (403); editor publish denied; archived bot 409; upload requires CSRF; >20 files 422; oversize 413; empty 422; all-invalid CSV 422 with reasons.

## Exact commands

Linux checks image: `ruff check .`, `ruff format --check .`, `mypy`, `python -m pytest -q` — green (123 passed). Windows host: identical — green. Compose live curl smoke through the 3000 proxy (multipart with CSRF, generated storage key shown in response): recorded in PHASE-REPORT.md.
