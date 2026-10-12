# Prompts for the coding agent (Codex / Claude Code) — paste one at a time, in order
Specs for parsing, chunking, embeddings, retrieval and analytics are agreed with the owner first and written into `docs/14-AGREED-BUILD-SPECS.md`; paste the P2+ prompts only after the relevant rows are filled. Each prompt covers one PHASE and ends at its gate: the agent stops and reports; you review the checklist in `PHASE-CHECKLISTS.md` and sign off before pasting the next prompt.

## 0. Standing preamble (include at the top of every prompt)
```text
You are a senior engineer working in the clean repo at the current directory (modular monolith: apps/web Next.js, apps/api FastAPI, Postgres+pgvector, one Alembic history).
Read first: AGENTS.md, README_START_HERE.md, DECISIONS.md, implementation/MASTER-ROADMAP.md, implementation/PHASE-CHECKLISTS.md, docs/18-EXPECTED-BEHAVIOUR.md, docs/03, 04, 05, 06, docs/14-AGREED-BUILD-SPECS.md and the docs relevant to the phase.
Rules: work through the phase's tickets IN ORDER, one at a time; after each ticket run lint, format check, mypy, pytest, and (if UI touched) typecheck + Playwright, fix failures, then record exact commands and results in PROGRESS.md and tick the checklist ONLY with evidence. Never fabricate results; if a check cannot run say so. Tenant scope on every tenant-owned query; hidden resources return 404; tests for tenant A vs B with every tenant-owned endpoint. Use only a disposable test DB (name ends with _test). Do not push, deploy, spend money or call paid APIs. Build only what the docs and docs/14 specify; if a needed parameter is TBD, stop and ask. No unrelated refactors. If a decision marked OPEN in DECISIONS.md blocks you, stop and ask. Commit locally after each ticket with a clear message (no push).
At the end of the phase: write implementation/PHASE-0X/PHASE-REPORT.md (what was built, evidence, limitations, open risks), update PROGRESS.md, and STOP for owner sign-off.
```

## 1. Phase P1 — Foundation (P1-02 → P1-04)
```text
[preamble]
PHASE P1. P1-01 is done. Implement, in order:
P1-02 Schema + auth. Add SQLAlchemy 2 + Alembic (apps/api/alembic). Tables: users(citext email unique, password_hash, is_platform_staff default false, created_at), sessions(id hashed token, user_id, expires_at, revoked_at, created_at), tenants, memberships(tenant_id,user_id,role in owner/admin/editor/viewer,status,unique pair), bots(id,tenant_id,name,status draft/active/paused/archived,config_json,created_at,updated_at,unique(tenant_id,id)), audit_events. Use UUID PKs, indexes on (tenant_id, ...), composite FKs where a child references (tenant_id,id). Auth module: register/login/logout/me with Argon2id, server-side sessions in a HttpOnly SameSite cookie, rotation on login, CSRF protection for cookie-authenticated writes, rate limiting on login, no secrets/tokens in logs. Add the _test database guard for tests and a conftest that runs migrations on the disposable DB. Tests: migration up/down, constraints, session valid/invalid/expired/revoked, CSRF, wrong password, duplicate email.
P1-03 Tenants, roles, bots. Endpoints per docs/05 (POST/GET tenants, GET /me with memberships, bots CRUD with soft archive). One reusable dependency that resolves tenant from the path, checks membership + role, returns a TenantContext; services take that context. Audit privileged writes. Stable error format {error:{code,message,request_id}}. Tests: full role matrix, tenant A/B guessed-UUID isolation (404), validation, archive behaviour.
P1-04 Dashboard UI. Next.js pages: /register, /login, /app (org selector + create org), /app/[tenant]/bots (list/create), /app/[tenant]/bots/[id]/settings (edit/archive). Real API only (fetch via a typed client), loading/empty/error states, role-aware controls, session-expired redirect. Playwright E2E: register → create org → create bot → archive; plus a second user cannot reach the first user's org.
Then phase verification and PHASE-REPORT.md. STOP.
```

## 2. Phase P2 — Knowledge (P2-01 → P2-06)
```text
[preamble]
PHASE P2 (P1 signed off). Build from the specs in docs/14; a TBD row you need means stop and ask.
P2-01 Spec check (no feature code): confirm docs/14 rows for embeddings, parsing and chunking are filled and ADR-005 is approved. If not, STOP and list what the owner must decide.
P2-02 Migrations: sources, source_pages, documents, knowledge_revisions (draft/published/archived, bots.published_revision_id), chunks (vector(D) with the approved D, tsvector column + GIN, HNSW/IVFFlat index), jobs. Implement the DB job queue (atomic claim with FOR UPDATE SKIP LOCKED, lease, retry/backoff, cancel) and `python -m app.worker`; add worker to Compose. Tests: two workers never claim the same job; crash → lease expiry → retry; job re-validates tenant+bot.
P2-03 File upload endpoint (size/type limits, storage interface with local-disk impl) and parsing+chunking for PDF/DOCX/TXT/MD/CSV per docs/14. Job pipeline: parse → chunk → dedupe by content hash → draft revision. Tests with fixture files incl. Arabic text, corrupt and oversize files.
P2-04 URL import: guarded fetcher (http/https only; block private/loopback/link-local/metadata, revalidate resolved IP and every redirect; caps on pages, depth, bytes, time, redirects; robots policy per ADR-006 — propose then ask), HTML→clean text, sanitized. Tests incl. redirect-to-internal, DNS rebinding simulation, oversized response, prompt-injection text kept as data.
P2-05 Embeddings via the approved provider interface (EmbeddingProvider), batch indexing, idempotent re-ingest, publish/rollback with atomic pointer swap, failed job leaves published knowledge untouched. Tests incl. two tenants with identical content share no rows.
P2-06 Knowledge UI under /app/[tenant]/bots/[id]/knowledge: upload, add URL, job status with errors+retry, document/chunk preview, publish/rollback, role restrictions. Playwright E2E with a fixture file.
Phase verification + PHASE-REPORT.md. STOP.
```

## 3. Phase P3 — Chat (P3-01 → P3-05)
```text
[preamble]
PHASE P3 (P2 signed off). Follow the retrieval and answer-generation specs in docs/14 (stop and ask if TBD).
P3-01 Retrieval service: hybrid search = Postgres full-text + pgvector similarity with score fusion; ALWAYS filter tenant_id + bot_id + bots.published_revision_id. Tests that fail if any filter is removed; Arabic and English queries.
P3-02 Chat service: LLMProvider interface; first provider = free model or Ollama configured by env; versioned prompt files; context built only from retrieved chunks; untrusted text treated as data; citation validation; abstention when evidence is weak; answer language follows question. Streaming with graceful non-streaming fallback.
P3-03 Persist visitor-agnostic conversations/messages/citations (tables with tenant_id) and idempotent usage_events.
P3-04 Playground UI (/bots/[id]/playground): chat with citations, error and not-ready states.
P3-05 Evaluation suite in apps/api/tests/eval: grounded, unanswerable, prompt-injection and Arabic cases with a runnable script and recorded thresholds; report real numbers.
Phase verification + PHASE-REPORT.md. STOP.
```

## 4. Phase P4 — Widget and client experience (P4-01 → P4-05)
```text
[preamble]
PHASE P4 (P3 signed off). Follow docs/09-WIDGET-SPECIFICATION.md.
P4-01 Public API: widget config by opaque locator (safe fields only), visitor session creation (short-lived capability token, bound to bot), message endpoint, allowed-domain check as a defence signal (not auth), per-IP/session rate limits, bot paused/not-ready handling, quota hooks. Tests: invalid locator, expired session, disabled bot, cross-bot session misuse.
P4-02 packages/widget: compiled loader + sandboxed iframe chat UI, responsive, keyboard accessible, RTL, versioned asset URL, CSP-friendly. Serve from the web app.
P4-03 Appearance settings (colour, name, avatar, greeting, placement, language) + Install page with the real snippet and a "test on a sample page" helper.
P4-04 Conversations list/detail with citations; lead capture with explicit consent text, retention setting, deletion.
P4-05 Analytics (metrics per docs/14): volume over time, top questions, unanswered questions, citation/source usage, usage events. Only measured data.
E2E: two static test sites embedding two different tenants' bots; each answers only from its own knowledge. Phase verification + PHASE-REPORT.md. STOP.
```

## 5. Phase P5 — Platform admin, quotas, onboarding, hardening (P5-01 → P5-05)
```text
[preamble]
PHASE P5 (P4 signed off).
P5-01 /platform area guarded by users.is_platform_staff (server-validated, separate from tenant roles): tenant directory, bot/source/job health, retry job, pause bot; every support action requires a reason and writes an audit event; no impersonation.
P5-02 Plans as internal labels + enforceable quotas (bots, pages, ingestion runs, monthly messages, seats) with transactional counters; concurrency test at the boundary; clear errors in API/UI/widget.
P5-03 ProvisioningService used by BOTH self-service signup and staff-initiated onboarding (tenant + owner invite + bot + optional file/URL ingestion), durable request record, Idempotency-Key, concurrent retries create exactly one bot; staff path adds actor attribution only.
P5-04 Tenant data export and delete (verified, audited); audit review screen.
P5-05 Release readiness: backup + restore drill script and evidence, structured logs with request/tenant correlation (no PII), error tracking hook, health/readiness, rate limits review, runbook. Staging deployment ONLY after the owner approves hosting (ADR-007) — propose options and stop.
Security review against docs/06 (SSRF, CSRF, sessions, tenant isolation, prompt injection) with findings fixed or documented. PHASE-REPORT.md. STOP.
```
