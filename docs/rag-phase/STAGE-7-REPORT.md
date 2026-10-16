# Stage 7 — private metering and configurable limits

2026-10-16. Parent `fa1baff`; implementation hash recorded at final gate.
Provider requests: **0**. Owner explicitly authorized the export privacy fix and
configurable caps with unset values uncapped.

- Fixed the Stage 4 privacy regression: client exports now remove AI ledger rows
  and strip operational usage payloads; staff exports retain traces/cost data.
  Added export regression before proceeding with other work.
- Added optional deployment plan defaults and staff bot overrides for documents,
  chunks, stored bytes, monthly AI replies/tokens, embedding tokens and OCR pages.
  Durable serialized reservations enforce configured monthly caps before provider
  work; unknown/failed usage keeps conservative accounting. Storage/ingest checks
  preserve existing data. No numeric defaults/currency ceiling invented.
- Separate ingest/query embedding, rewrite, translation and generation usage,
  model, channel, tokens and measured cost. Unknown cost stays unknown. Staff
  analytics UI shows per-bot/channel costs and edits bot caps. New cost route is
  staff-only; exact matrix **82 = 82**. Details: `LIMITS-AND-METERING.md`.
- Additive migration `0015_rag_metering`; no existing data rewritten. Downgrade
  refuses populated RAG limits/metering. No OCR path added.

Affected checks: export regression **1 passed**; new limits/metering **8 passed**;
matrix/migrations **7 passed**; embedding/hybrid **17 passed**; ingestion/export/
traces **14 passed**. **46 unique affected API tests** (export test overlaps the
later file run). Final measured-cost check **1 passed**, 7 deselected.
All existing Starlette warning only. Backfill kill/resume and vector isolation
passed; no new privacy failures. Initial type checks found two new JSON integer
narrowing issues, corrected. Final mypy **176 source files**, affected Ruff/format,
web lint/typecheck passed. Repo Ruff still has exactly the same **9** old findings.

Affected browser roles-control/playground: **5 passed (1.3m)**, ECONNRESET **0**.
Staff saves/resets caps, clients see no panel, playground trace behavior preserved.
Exact commands/results in `PROGRESS.md`. Full suites reserved for the final gate.

Files: optional bot caps/event constraint + migration; quota contracts, reservation
ledger and provider wrappers; runtime ingestion/retrieval/chat wiring; staff RAG
routes/role metadata; export redaction; affected/new API tests; staff analytics
panel/API client/browser spec; reports/overrides/PROGRESS.

UNVERIFIED: production-scale ledger load, provider usage accuracy, real semantic
quality, real paid-provider calls. Conservative reservations can reject early.
OCR and LLM judge deferred. No dotenv reads, real calls, full-suite reruns, merge,
push, deployment or Compose.
