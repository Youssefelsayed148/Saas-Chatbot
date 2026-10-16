# Stage 5 — parsing limits and staff ingestion status

2026-10-16. Parent `85dbe92`; implementation hash follows next checkpoint.
Provider requests: **0**.

- DOCX tables retain the first row and repeat its labels on every data row.
  CSV/FAQ stays one record per retrieval document/chunk. Text PDFs/docs parse
  directly; arbitrary PDF table structure/reading order remains UNVERIFIED.
- Every parser runs in an isolated process. POSIX cleanup kills its owned process
  group, including nested helpers, on timeout and after output. Windows uses
  `taskkill /PID ... /T /F` without a shell; descendant behavior there is UNVERIFIED.
- Existing approved caps retained: per-plan file sizes 5/10/20/25 MiB;
  per-bot pages 25/150/600/2,000 (existing placeholder plans), PDF max 300 pages
  per source, DOCX expansion max 100 MiB/ratio 200, timeout 120 seconds, batch 20.
  Added parser-side input byte check aligned with the scoped plan upload cap.
- Derived document parsed status, chunk counts and warnings appear only through
  existing staff knowledge API/UI. No schema changes or new routes.
- No OCR engine/path exists. Scanned PDFs remain safely rejected; async OCR and
  its metering are **UNVERIFIED/deferred**, as the prompt permits.

Verification: **57 unique affected API tests passed**: parsers 29, pipeline 9,
uploads 19. Review caught and corrected a potential global-size-cap regression;
final pipeline recheck **9 passed**, 31.45s. Actual timeout test starts a nested
Python helper, then verifies it is absent/dead after the parser timeout.
Mypy **167 source files** passed; affected Ruff/format and web lint/typecheck
passed. Knowledge Playwright: **4 passed (1.1m)**, ECONNRESET **0**.
Exact commands/results: `PROGRESS.md`. No isolation/privacy failures.

Files: knowledge ingestion/parser/schema/router; parser/pipeline tests; typed web
document contract and knowledge page; checkpoint docs and PROGRESS.

Not done: OCR, Windows process-tree integration test, PDF visual-table validation,
full suites, real calls, dotenv reads, merge, push, deploy or Compose.
