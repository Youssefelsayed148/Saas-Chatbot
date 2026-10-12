# Phase P2 task register — Knowledge (P2-00 → P2-04)

| Ticket | Scope | Status | Report |
|---|---|---|---|
| P2-00 | P1 carry-overs: security headers (next.config + test + live curl), invitation double-accept race test (with a row-lock fix) | Done, evidence recorded | P2-00-REPORT.md |
| P2-01 | Migrations: sources, source_pages, documents, knowledge_revisions (bots.published_revision_id), chunks (generated GIN tsvector), jobs; DB queue (claim/lease/retry/backoff/cancel) + `python -m app.worker` + Compose worker service | Done, evidence recorded | P2-01-REPORT.md |
| P2-02 | Upload endpoint (multipart, streaming size caps, magic-byte sniffing), storage interface (local disk), PDF/DOCX/TXT/MD parsers, Q&A CSV import (template + row-level report), chunking (§4), language detection + Arabic normalisation (§2), YAML front matter, upload hardening incl. zip-bomb / page-count / parse-timeout caps; CSRF + limits verified through the Next proxy | Done, evidence recorded | P2-02-REPORT.md |
| P2-03 | Indexing pipeline job (parse → chunk → dedupe → draft revision), no-op re-ingest, publish/rollback atomic pointer swap, failed-job isolation, two-tenant non-sharing | Done, evidence recorded | P2-03-REPORT.md |
| P2-04 | Knowledge UI (upload, Q&A report, jobs with Retry/Cancel, document/chunk preview, publish/rollback, role restrictions) + Playwright E2E (fixture file, real API + real worker) | Done, evidence recorded | P2-04-REPORT.md |

Verification gates: every new knowledge endpoint has a tenant A/B guessed-UUID 404 test and a viewer-write-denied test (test_knowledge_uploads.py + test_knowledge_pipeline.py). Phase verification lives in PHASE-REPORT.md.
