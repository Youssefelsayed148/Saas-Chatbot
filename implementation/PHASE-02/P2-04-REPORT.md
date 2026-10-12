# P2-04 REPORT — Knowledge UI + Playwright E2E

Date: 2026-10-12. Status: DONE, locally verified. Nothing on screen is mocked — every list comes from the real FastAPI via the typed client.

## Page `/app/[tenant]/bots/[botId]/knowledge` (`apps/web/app/app/[tenant]/bots/[botId]/knowledge/page.tsx`)

- **Upload**: multi-file input (PDF/DOCX/TXT/MD/CSV accepting), per-batch submit through the same-origin proxy with the CSRF header; success notice tells how many files were stored and the Q&A **template link** (direct download of the editor-only template).
- **Files list**: name, kind badge, size, status (`stored/queued/ingested/failed`), valid/total rows for Q&A CSVs, per-source errors, and the **row-level error report** ("Row 3: missing answer") rendered from the stored `row_errors`.
- **"Ingest files"** button starts the ingest job (disabled with a title when nothing is stored); a **2.5 s poll** refreshes sources/jobs while any job is pending or running, so the queue visibly moves queued → running → done.
- **Jobs list**: newest first with status, time, attempt count, error text, **Retry** (finished jobs, editor+) and **Cancel** (pending/running, editor+).
- **Documents & chunks preview**: a View switch (`Published knowledge` / `Draft (latest ingest)`), document rows with title, heading, `page_ref`, `source_url`, language (RTL `dir` for Arabic chunks), chunk count, char count and a text excerpt; clicking a document expands the **chunk preview** (ordinal + text) fetched from `GET /documents/{id}/chunks`.
- **Revisions**: status, document/chunk counts, timestamps, `current` marker; admin+ can **Publish** a draft or **Roll back to this revision** (archived ones).
- **Role restrictions** (server-enforced too): viewer gets the read-only notice, no template link, disabled file input, and **no Upload/Ingest/Retry/Cancel/Publish buttons at all**; editors cannot publish (admin+ per docs/06). Link from the bot settings page and back-links.

`lib/api.ts` gained the typed knowledge client (sources/upload multipart/ingestion/jobs/documents/chunks/revisions/publish) reusing the session/CSRF/401-redirect plumbing.

## Playwright E2E (`apps/web/tests/knowledge.spec.ts`, real API + real worker)

Harness: `tests/e2e-api-setup.ts` now also spawns the DB worker (P2-01) with the `WORKER_ALLOW_ONLY_TEST_DB=1` guard; teardown stops `[e2e] API + worker`.

1. `upload, ingest through the worker, preview, publish` — register → org → bot → knowledge; template download verified (`question,answer,topic,priority`); upload of the fixture `tests/fixtures/knowledge-sample.md` (front-matter `source_url: https://sample.example.com/hours`); "Ingest files" → job reaches **`succeeded` processed by the real worker**; draft documents show the title from front matter, the source_url and the chunk list (`#0 …`); Publish → success notice + published revision row; the published view shows the documents (default view is the published revision).
2. `oversize uploads are rejected through the same-origin proxy with 413` — a 10 MB + 1 byte `big.md` through the proxy renders "Files may be at most 10 MB" and stores nothing (needs `experimental.proxyClientMaxBodySize` ≥ the batch cap, see P2-02).
3. `viewer is read-only on knowledge` — owner invites a viewer (one-time link, accept flow reused from P1); the viewer opens knowledge and gets the read-only notice, disabled file input, zero upload/ingest/publish/retry/cancel buttons and no template link.

Final Playwright run: **9 passed** (3 knowledge + 5 dashboard/foundation + 1 security-headers), real API (disposable `chatbot_dev_e2e_test`, Alembic, `_test` guard) and real worker spawned by the harness.

Web checks: `npm run format:check` (all files Prettier-clean incl. the new files), `npm run lint` (0 warnings), `npm run typecheck` (next typegen + `tsc --noEmit` clean).
