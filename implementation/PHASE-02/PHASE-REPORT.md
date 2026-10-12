# PHASE-02 REPORT — Knowledge (P2-00 → P2-04)

Date: 2026-10-12. Status: ALL P2 TICKETS IMPLEMENTED AND LOCALLY VERIFIED. **STOPPED FOR OWNER SIGN-OFF.**

Branch: `feat/p1-01-foundation` (extended; see git log for the P2 commits). No push, no merge, no deployment, no paid APIs (the whole phase is local Postgres + local files; no external model/API calls were made — nothing in P2 calls any LLM).

## What a person can do now (owner-readable summary)

1. Open a bot → **Knowledge**. Upload PDF/DOCX/TXT/MD files (up to 20 at once, 10 MB each) or a Q&A CSV (template downloadable; bad rows reported with row numbers and reasons). Website content prepared by the staff `website-to-knowledge` skill (Markdown pages + qa.csv) uploads here — there is no URL box (ADR-006).
2. Press **Ingest files** and watch the job go pending → running → succeeded (processed by the real DB worker container, not the web process), or fail with a readable reason and a Retry button (Cancel available while queued/running).
3. Review what was learned: documents (per PDF page, per DOCX heading section, per markdown heading/paragraph, per CSV row `Q:…A:…`) with chunk counts, and the raw chunk preview per document. Each document carries its `source_url` from the markdown front matter — that is what citations will link to in P3.
4. Publish a draft; the bot's knowledge switches atomically; roll back to a previous revision with the same button semantics (Roll back). A failed ingest never changes what is published.
5. Uploading the same file twice does not duplicate content; re-ingesting an unchanged source changes nothing; two organizations with the same file share nothing (verified down to row identity).

## Verification evidence (final state)

| Check | Linux (checks container) | Windows host |
|---|---|---|
| `ruff check .` (apps/api) | All checks passed | All checks passed |
| `ruff format --check .` | 83 files formatted | same |
| `mypy` (strict, 71 sources) | Success — no issues | Success — no issues |
| `pytest -q` | **123 passed**, 1 warning (httpx deprecation, pre-existing) | **123 passed** |
| Alembic `upgrade head` / `downgrade 0001_initial` / re-`upgrade` on disposable DBs | OK (`chatbot_dev_test`, `chatbot_dev_migration_test`) | OK |
| `npm run format:check` / `lint` / `typecheck` (apps/web) | — | all green (Prettier clean incl. new files; eslint 0 warnings; typegen + `tsc`) |
| `npm test` (Playwright, real API + real worker, disposable `chatbot_dev_e2e_test`) | — | **9 passed** (≈1 min) |
| `docker compose --env-file .env -f infra/compose.yaml up --build -d --wait` | db + api + **worker** + web all healthy | — |
| Live loopback curl smoke (owner-usable proof) | register → tenant → bot → **multipart upload with CSRF through the 3000 proxy** (generated storage key `…/{tenant}/{bot}/{hash}.md`) → ingest job → `job: succeeded` → 1 document (`Opening hours`, `https://sample.example.com/hours`, 1 chunk) → publish 200 | — |
| Live security-header curl | `Referrer-Policy: no-referrer`, `X-Content-Type-Options: nosniff`, `Content-Security-Policy: frame-ancestors 'none'` on `/` and `/login` via port 3000 | — |

Ticket reports with the per-ticket evidence: `P2-00-REPORT.md` … `P2-04-REPORT.md`.

## Checklist status (`implementation/PHASE-CHECKLISTS.md`)

Every P2 item is ticked with the evidence pointer above/its ticket report. Remaining open item: **owner review and sign-off**.

## Status of docs/18 behaviours (after P2)

- Upload PDF/DOCX/TXT/MD + Q&A CSV with template and bad-row report ✅
- Staff skill output (page files + qa.csv) uploads and ingests ✅
- `source_url` stored and surfaced for citations (citations themselves are rendered in P3) ✅
- Job queued→running→done; failed with readable reason + Retry ✅
- Documents + chunks preview with counts and source attribution ✅
- Publish atomic; rollback works; failed ingest never changes published knowledge ✅
- Same-file re-upload does not duplicate; cross-org identical content shares nothing ✅
- No fake data on screen ✅

## Limitations and open risks (incl. the carried P1 items)

1. **Hosted CI has never run** (carried from P1): no remote push authorised; the workflow now also runs the same P2 checks but remains a config artifact only.
2. **Login rate limiter is the P1 in-process limiter** (carried): Postgres-backed counters arrive with the public widget phase (docs/14 §7).
3. **Security headers do not attach to the `/api` proxy responses** (external rewrite to uvicorn; Next `headers()` cannot override in-flight proxied headers). Documented in P2-00; in production the one gateway in front of web+api adds them (deployment design is ADR-007, still OPEN).
4. **Parse-timeout thread**: the bounded parse runs in a thread; a thread that ignores the timeout keeps running until finished (bounded by the size/expansion caps, so worst case is finite). A subprocess model could hard-kill it; deferred as harder to port between Windows/Linux for now.
5. **Multi-worker poll interval is 1 s** and jobs run one at a time per worker process; heavy ingest fan-out (many concurrent uploads) is throttled by the worker container count. Correctness (exclusive claim, idempotent retries) is what P2 promised; throughput tuning is a later ops concern.
6. **Local-disk storage** assumed shared between api and worker via a Compose volume (`/data/storage`); object storage lands with ADR-007.
7. **`source_pages` provenance for DOCX/CSV** is minimal (one pseudo-page per file); the `page_ref` text on documents is the durable citation breadcrumb.
8. **`Content-length`-only proxy guard**: the proxy can't inspect multipart boundaries; it caps the whole request (220 MB = 20×10 MB + overhead). Bodies **without** Content-Length (chunked) skip the proxy header check and rely on the API streaming cap — recorded as a known hardening gap for P7 review.
9. Nightly Windows-only UI fit-and-finish for RTL preview is functional but the visual polish of RTL chunk text was eyeballed in a browser, not pixel-tested.
10. Dev databases used and left behind: `chatbot_dev` (migrated to `0002_knowledge`, review stack running on loopback 3000/8000/55432), `chatbot_dev_test`, `chatbot_dev_e2e_test` (disposable, `_test`-guarded). Migration exploration mistakes during development were made against and reverted from `chatbot_dev` only via its own migration tooling (no non-test DB was ever touched by tests; the suite itself always derives disposable `_test` databases).

## Second-approval notes for the owner

- Scope guardrails kept: **no in-app URL import/crawler** (ADR-006) — the skill folder path is fully covered; **no embeddings/vector column/pgvector** (ADR-005); website content only via uploaded files.
- Nothing was pushed/merged/deployed; no paid services were contacted. Local Compose remains running for review: stop with `docker compose --env-file .env -f infra/compose.yaml down`.
- Next phase per roadmap after sign-off: P3 Chat (P3-01 → P3-05, skipping the optional P3-06 unless the owner approves it at the gate).
