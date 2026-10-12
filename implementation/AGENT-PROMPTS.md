# Prompts for the coding agent (Codex / Claude Code) — paste one at a time, in order
The detailed specs the prompts refer to (parsing, chunking, retrieval, answer contract, analytics) are agreed with the owner and live in `docs/14-AGREED-BUILD-SPECS.md`. Each prompt covers one PHASE and ends at its gate: the agent stops and reports; you review the checklist in `PHASE-CHECKLISTS.md` and sign off before pasting the next prompt.

## 0. Standing preamble (include at the top of every prompt)
```text
You are a senior engineer working in the clean repo at the current directory (modular monolith: apps/web Next.js, apps/api FastAPI, Postgres, one Alembic history; product = Mojeeb-style website AI agent + inbox/handoff + light CRM; Meta channels come only through the ManyOsirisChat contract in P6 — never Meta APIs directly).
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

## 2. Phase P2 — Knowledge (P2-01 → P2-04)
```text
[preamble]
PHASE P2 (P1 signed off). Build exactly what docs/14-AGREED-BUILD-SPECS.md §1, §3, §4, §5, §13 specify. There is NO in-app URL import/crawler (ADR-006); website content arrives as uploaded Markdown page files + a Q&A CSV. No embeddings, no vector column, no pgvector extension (ADR-005).
P2-01 Migrations: sources, source_pages, documents, knowledge_revisions (draft/published/archived; bots.published_revision_id), chunks (tenant_id, bot_id, revision_id, document_id, title, heading, text, text_norm, language, priority, content_hash, generated tsvector columns fts_en/fts_simple with GIN indexes, composite FK to bots), jobs. DB job queue: atomic claim with FOR UPDATE SKIP LOCKED, lease, retry/backoff, cancel; `python -m app.worker` using the same codebase; add the worker service to Compose. Tests: two workers never claim one job; crash → lease expiry → retry; job re-validates tenant + bot.
P2-02 File upload endpoint (multipart; size/type limits; storage interface with local-disk implementation) and parsers for PDF (pypdf, per page), DOCX (python-docx, heading sections, tables as text), TXT/MD, plus Q&A CSV import (template download, row-level error report). Chunking per §4 with the language detector and Arabic normalisation of §2. Parse optional YAML front matter in .md/.txt (title, source_url, language, page_type); store source_url per document and use it for citations (http/https only). Tests with fixtures incl. Arabic, scanned/corrupt/oversize files, bad CSV rows, and a sample skill output folder.
P2-03 Indexing pipeline job: parse → chunk → dedupe by content hash → write chunks into a draft revision; publish/rollback with atomic pointer swap; failed job never touches published knowledge; unchanged re-ingest is a no-op. Tests incl. two tenants with identical content share no rows.
P2-04 Knowledge UI at /app/[tenant]/bots/[id]/knowledge: multi-file upload, Q&A CSV with template + error report, job status with errors + retry, document/chunk preview, publish/rollback, role restrictions. Playwright E2E with a fixture file.
Phase verification + PHASE-REPORT.md. STOP.
```

## 3. Phase P3 — Chat (P3-01 → P3-05)
```text
[preamble]
PHASE P3 (P2 signed off). Build exactly docs/14-AGREED-BUILD-SPECS.md §1, §2, §5, §6, §7, §10.
P3-01 Retrieval service: language-aware full-text search on the indexed columns, filters tenant + bot + published revision + language, cross-language fallback, ts_rank_cd ranking, one best chunk per document, small-document expansion, always-include documents. Tests that fail if any filter is removed; Arabic and English queries; Arabic normalisation/prefix cases.
P3-02 Chat service: ChatModel interface with OpenAI-compatible client (OpenRouter free chain with fallback models and free_only guard; OpenAI model option from config); versioned prompt template; strict JSON answer contract and citation validation; follow-up condensation; rule-based routing (smalltalk, order/account handoff); localized fallback/busy replies with the bot's support contact; answers in the visitor's language. Unit tests with fake providers (including invalid JSON, bad citations, rate-limit errors).
P3-03 Persist the channel-agnostic conversation core of docs/14 §14: contacts, contact_identities, conversations (channel, connection_id, mode, status, assigned_user_id, handoff_reason), messages (sender_type, delivery_status, can_answer, needs_human, response_ms) and citations; the chat pipeline runs only when mode=ai; every table tenant-scoped with composite FKs; thumbs feedback endpoint; idempotent usage_events; retention purge job.
P3-04 Playground UI (/bots/[id]/playground): chat with citations, feedback buttons, error and not-ready states.
P3-05 Evaluation suite in apps/api/tests/eval: EN + AR fixture corpora and eval.jsonl (grounded / unanswerable / injection / cross-language), runnable script, deterministic checks plus optional judge; report real numbers against the docs/14 §10 targets.
Phase verification + PHASE-REPORT.md. STOP. (P3-06 semantic upgrade is NOT started unless the owner approves after reading the eval report.)
```

## 4. Phase P4 — Widget and client experience (P4-01 → P4-05)
```text
[preamble]
PHASE P4 (P3 signed off). Follow docs/09-WIDGET-SPECIFICATION.md.
P4-01 Public API: widget config by opaque locator (safe fields only), visitor session creation (short-lived capability token, bound to bot), message endpoint, allowed-domain check as a defence signal (not auth), per-IP/session rate limits, bot paused/not-ready handling, quota hooks. Tests: invalid locator, expired session, disabled bot, cross-bot session misuse.
P4-02 packages/widget: compiled loader + sandboxed iframe chat UI, responsive, keyboard accessible, RTL, versioned asset URL, CSP-friendly. Serve from the web app.
P4-03 Appearance settings (colour, name, avatar, greeting, placement, language) + Install page with the real snippet and a "test on a sample page" helper.
P4-04 Conversations list/detail with citations; lead capture with explicit consent text that creates or updates a contact (docs/14 §14, §16), retention setting, deletion.
P4-05 Analytics per docs/14 §9: summary metrics, volume per day, top questions, unanswered-questions list, leads trend, thumbs feedback, CSV export. Only measured data.
E2E: two static test sites embedding two different tenants' bots; each answers only from its own knowledge. Phase verification + PHASE-REPORT.md. STOP.
```

## 5. Phase P5 — Inbox, handoff and light CRM (P5-01 → P5-05)
```text
[preamble]
PHASE P5 (P4 signed off). Build exactly docs/14 §14–§17, ADR-015/016, docs/09 (handoff in the widget), docs/05 inbox routes. No Meta or ManyOsirisChat code in this phase.
P5-01 Conversation state machine and handoff: mode ai|human, status open|waiting_human|resolved; automatic handoff triggers (§15, configurable thresholds, EN/AR keyword lists); endpoints takeover / return-to-ai / resolve / assign with 409 on a lost takeover race; agent reply endpoint (editor+); system messages and audit rows; widget polling endpoint GET /public/v1/sessions/{id}/messages?since= so agent replies appear within ~3 s (plain text only); a new visitor message reopens a resolved conversation in AI mode. Tests: state-transition matrix, race, viewer 403, tenant A/B, widget cannot read another session.
P5-02 Inbox API + live updates: list with filters (status, mode, channel, assignee, tag, unread) and full-text search; per-user unread counters; SSE stream backed by a DB cursor poll (~2 s) with Last-Event-ID resume that works with two API processes; in-app notification counts. Tests with two app instances, reconnect, tenant isolation.
P5-03 Inbox UI at /app/[tenant]/inbox and /inbox/[conversation]: list + filters, thread (citations, feedback, notes, system events), reply box, take over / return / resolve / assign, tags, notes, unread badges, role-aware controls, empty/loading/error states. Playwright E2E of the full journey: visitor asks an unanswerable question → waiting_human → agent takes over and replies → widget shows it → agent returns chat to the bot.
P5-04 Contacts and light CRM: contacts CRUD, identities, stage (default new/qualified/customer/lost, editable names), tags, custom fields (≤20), consent per channel, timeline, explicit audited merge, CSV export, erasure; widget lead form creates/updates contacts; pages /contacts and /contacts/[id].
P5-05 Follow-ups and analytics: follow-up scheduling (user or simple rule), job-based sending (website: pending message shown on next visit; no Meta sends in this phase), sentiment job using ChatModel (cost-capped, aggregate use only), analytics for handoff rate, time to first human reply, per-channel counts, resolved/open, sentiment distribution, agent workload. Measured data only.
Phase verification + PHASE-REPORT.md. STOP — the website product is now sellable; owner decides whether to start P6 now.
```

## 6. Phase P6 — ManyOsirisChat channel (P6-01 → P6-05)
```text
[preamble]
PHASE P6 (P5 signed off; owner has confirmed the Many-side endpoints/delegated mode exist or will exist). Build exactly docs/17 and docs/14 §18, ADR-002/017. Never call Meta APIs or store Meta tokens; Many is reached only through the signed contract. Do not modify the Many repo.
P6-01 channel_connections + channel_events tables; staff-created connections (tenant+bot+channel+many_base_url); per-connection secret generated, shown once, stored encrypted, rotatable; HMAC-SHA256 sign/verify helpers (timestamp + "." + raw body, 5-minute window, constant-time compare); POST /api/channels/manyosiris/events returns 202 and enqueues a job; dedupe on (connection_id, event_id); paused/revoked connections rejected. Tests: bad signature, old timestamp, replay, wrong connection, paused connection.
P6-02 Inbound processing job: message.received → contact_identity (unique per tenant+connection+external_id) → conversation (channel, external_conversation_id) → the SAME chat/handoff pipeline as the widget; unsupported types get the localized text-only reply and a human flag; duplicate and out-of-order events harmless. Tests: tenant A connection cannot write to tenant B; idempotency; ordering.
P6-03 Outbound delivery job: POST {many_base_url}/api/saas/messages keyed by message_id for AI replies, agent replies and handoff messages, retry with exponential backoff; message.status events update delivery_status monotonically; window_closed / template_required / recipient_unreachable shown in the inbox and not blindly retried; Many-down visible and recovers. Inbox shows channel badge and per-message delivery state.
P6-04 Follow-ups and broadcasts through Many: only to contacts with recorded opt-in for that channel, only with an approved template_ref outside the window; campaign record with per-recipient delivery status; STOP and ask the owner before any real send.
P6-05 Contract test suite against a fake Many server run in CI; write docs/17 "Many-side requirements" handover (exact endpoints, payloads, error codes); canary + rollback plan (pause connection); Playwright E2E with the fake Many.
Phase verification + PHASE-REPORT.md. STOP. The real staging test with a test WhatsApp number needs owner approval.
```

## 7. Phase P7 — Platform admin, quotas, onboarding, hardening (P7-01 → P7-05)
```text
[preamble]
PHASE P7 (P6 signed off, or P5 if the owner skips Meta for now).
P7-01 /platform area guarded by users.is_platform_staff (server-validated, separate from tenant roles): tenant directory, bot/source/job health, Many connection health + secret rotation, retry job, pause bot/connection; every support action requires a reason and writes an audit event; no impersonation.
P7-02 Plans as internal labels + enforceable quotas (bots, seats, monthly messages, channel connections, contacts, sentiment runs, ingestion runs, pages) with transactional counters; concurrency test at the boundary; clear errors in API/UI/widget.
P7-03 ProvisioningService used by BOTH self-service signup and staff-initiated onboarding (tenant + owner invite + bot + optional file ingestion + optional channel connection request), durable request record, Idempotency-Key, concurrent retries create exactly one bot; staff path adds actor attribution only.
P7-04 Tenant data export and delete (contacts, conversations, identities, knowledge; verified, audited); audit review screen.
P7-05 Release readiness: backup + restore drill script and evidence, structured logs with request/tenant correlation (no PII), alerts for failed deliveries and stuck jobs, health/readiness, rate limits review, runbook. Staging deployment ONLY after the owner approves hosting (ADR-007) — propose options and stop.
Security review against docs/06 (upload hardening, CSRF, sessions, tenant isolation, prompt injection, HMAC channel endpoint, SSE) with findings fixed or documented. PHASE-REPORT.md. STOP.
```
