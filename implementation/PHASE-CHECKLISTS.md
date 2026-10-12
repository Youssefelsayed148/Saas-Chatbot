# Phase checklists — tick only with evidence (command + result in PROGRESS.md or the ticket report)
Legend: [ ] open · [x] done with evidence. Owner sign-off closes each phase.

## P1 Foundation
- [x] P1-01 toolchain, health/ready, Compose, CI config (evidence: P1-01-REPORT.md; hosted CI not yet run)
- [x] P1-02: `alembic upgrade head` from empty DB and `downgrade base` both succeed on a disposable DB (evidence: P1-02-REPORT.md — `test_migrations_up_down_cycle` on `chatbot_dev_migration_test`, Windows + Linux container)
- [x] P1-02: unique/FK/composite-FK constraints verified by tests (P1-02-REPORT.md; test_models_constraints.py 40 passed)
- [x] P1-02: register/login/logout/me work; wrong password, expired and revoked sessions rejected (P1-02-REPORT.md)
- [x] P1-02: passwords stored as Argon2id; cookie HttpOnly/SameSite; CSRF enforced on writes; no secrets in logs (P1-02-REPORT.md; Secure asserted in production-config unit test, live smoke over HTTPS pending later phase)
- [x] P1-02: test DB guard refuses non-`_test` databases (test_database_guard.py)
- [ ] P1-03: tenant create/list-mine/get; creator becomes owner
- [ ] P1-03: invitations by one-time link (hash stored, single use, expiry, revoke), accept flow, members list/role change/remove, last-owner protected; expired/used/revoked tokens and role escalation rejected
- [ ] P1-03: role matrix tested (owner/admin/editor/viewer × every endpoint)
- [ ] P1-03: tenant A cannot read/write tenant B bots by guessed UUID (404)
- [ ] P1-03: bot create/list/get/update/archive with validation; archive is soft; audit rows written
- [ ] P1-04: register → create org → create bot works in a real browser (Playwright E2E)
- [ ] P1-04: org switcher, role-aware buttons, loading/empty/error states; members page (invite link, pending, roles, remove) and accept-invite page
- [ ] P1-04: UI contains no mocked data; lint, typecheck, format, mypy, pytest, Playwright all green
- [ ] Phase report written; owner reviewed and signed off

## P2 Knowledge
- [ ] P2-01: migrations for sources, documents, revisions, chunks (generated GIN-indexed tsvector columns), jobs; no vector column
- [ ] P2-01: atomic job claim (FOR UPDATE SKIP LOCKED) with lease/retry/cancel — two workers never run one job; crash → lease expiry → retry; job re-validates tenant + bot
- [ ] P2-02: PDF/DOCX/TXT/MD parsed per docs/14 §3 from fixtures (incl. Arabic text); scanned/corrupt/oversize/unsupported files rejected with clear messages
- [ ] P2-02: Q&A CSV import works with template download and row-level error report (bad priority, empty question/answer, missing columns)
- [ ] P2-02: chunking matches docs/14 §4 (1500/200, titles kept, short docs = one chunk)
- [ ] P2-02: Markdown front matter (title, source_url, language, page_type) parsed; non-http(s) source_url dropped; citations show the source_url
- [ ] P2-02: a sample skill output folder (pages/*.md + qa.csv) uploads end-to-end
- [ ] P2-03: dedupe by content hash; re-ingest of unchanged source is a no-op; draft → publish → rollback is atomic; failed job leaves published revision intact
- [ ] P2-03: two tenants ingest identical content → zero shared rows
- [ ] P2-04: Knowledge UI: upload (multi-file), Q&A CSV with template/error report, job status with errors + Retry, document/chunk preview, publish/rollback, role restrictions
- [ ] Phase report; owner sign-off

## P3 Chat
- [ ] P3-01: retrieval per docs/14 §2, §5: tenant + bot + published-revision + language filters (a test fails if any filter is removed); cross-language fallback; small-document expansion; Arabic normalisation + prefix matching
- [ ] P3-02: ChatModel interface; free OpenRouter chain + OpenAI option via config; strict JSON contract; invalid JSON or invalid/missing citation → fallback; can_answer=false → needs_human
- [ ] P3-02: smalltalk and order/account routing work without model calls; replies follow the visitor's language
- [ ] P3-03: channel-agnostic contacts, conversations (channel, mode, status) and messages (sender_type, delivery_status) per docs/14 §14; citations, thumbs feedback, usage events stored (idempotent); retention purge works; pipeline runs only in mode=ai
- [ ] P3-04: Playground shows answer + citations + errors; "not ready" state when nothing is published
- [ ] P3-05: eval suite committed (grounded / unanswerable / injection / cross-language, EN + AR) with real numbers against docs/14 §10 targets
- [ ] P3-06 (optional): owner decides at the P3 gate from the eval report (Arabic/dialect cases included); separate approval
- [ ] Phase report; owner sign-off

## P4 Widget — the website channel
- [ ] P4-01: public config + session endpoints; locator is not a secret; short-lived session capability; rate limits; allowed-domain check
- [ ] P4-02: widget loads from one script tag; iframe sandbox; mobile, keyboard, screen-reader labels, RTL
- [ ] P4-03: appearance settings saved and reflected; install page shows correct snippet
- [ ] P4-04: conversations view; leads captured only with consent and create/update a contact; retention setting works
- [ ] P4-05: per-bot dashboard shell (nav: overview, knowledge, playground, conversations, settings, install; no placeholder or fake items for later phases); overview shows measured numbers only (matches stored events) with date range
- [ ] P4-06: /platform guarded by is_platform_staff (server-validated): client list (plan label, status, bots, last activity, search/filter), client detail (bots, knowledge/job status, members, recent audit)
- [ ] P4-06: staff onboarding via ProvisioningService (tenant + owner one-time invite link, no email + bot + optional file upload); Idempotency-Key; double submit creates one tenant; actor attributed in audit; no impersonation
- [ ] Two test websites + two tenants: each answers only from its own knowledge; paused bot and expired session handled
- [ ] Phase report; owner sign-off

## P5 Inbox, handoff and light CRM (first sellable cut)
- [ ] P5-01: handoff triggers per docs/14 §15 (2x can_answer=false, asks for a person EN/AR, order/account, provider failure, staff keyword) set waiting_human with localized message
- [ ] P5-01: take over / return to AI / resolve / assign work; AI silent in human mode; two-agent takeover race → 409; resolved conversation reopens in AI mode on a new visitor message; audit rows + system messages
- [ ] P5-01: agent reply is visible in the widget within ~3 s (polling) and rendered as plain text; viewer cannot reply (API 403)
- [ ] P5-02: inbox list API with filters (status, mode, channel, assignee, tag, unread) and full-text search; tenant A/B isolation test on every endpoint
- [ ] P5-02: SSE stream tenant-scoped, resumes from Last-Event-ID, works with two API processes; in-app notification counts correct
- [ ] P5-03: inbox UI: list, filters, thread with citations/notes/system events, reply box, take over/return/resolve/assign, tags, notes; role-aware; loading/empty/error states; Playwright E2E of the full handoff journey (visitor → bot → agent → back to bot)
- [ ] P5-04: contacts CRUD, identities, stage, tags, custom fields (≤20), timeline, explicit merge (audited), CSV export, erasure removes identities and messages
- [ ] P5-04: widget lead form → contact (consent recorded)
- [ ] P5-05: follow-ups scheduled by user or rule and sent by a job; website follow-up shown on next visit; no send without recorded opt-in (Meta channels)
- [ ] P5-05: sentiment job (cost-capped) and analytics: handoff rate, time to first human reply, per-channel counts, sentiment distribution, agent workload — all match stored data
- [ ] Phase report; owner sign-off → website product is sellable

## P6 ManyOsirisChat channel (WhatsApp, Messenger, Instagram)
- [ ] Prerequisite: Many-side endpoints/delegated mode agreed and available (separate workstream); owner confirms the delegated-mode assumption (ADR-017)
- [ ] P6-01: channel connections created explicitly (staff); per-connection secret shown once, stored encrypted, rotatable; HMAC verify with constant-time compare, 5-minute window; bad signature/old timestamp/paused connection → rejected; channel_events dedupe by (connection_id, event_id)
- [ ] P6-02: message.received → contact identity (unique per tenant+connection+external_id) → conversation → same chat/handoff pipeline; unsupported media gets the text-only reply and a human flag; duplicate and out-of-order events harmless; a tenant-A connection can never write into tenant B
- [ ] P6-03: outbound via POST to Many keyed by message_id with retry/backoff; message.status updates delivery_status monotonically (sent < delivered < read); window_closed/template_required shown in the inbox and not blindly retried; Many-down is visible and recovers
- [ ] P6-04: follow-ups/broadcasts through Many only with recorded opt-in and approved template_ref; owner-approved before first real send
- [ ] P6-05: contract tests against a fake Many (signature, replay, duplicates, ordering, errors) in CI; Many-side requirements doc handed over; canary plan with one test number in staging; rollback = pause connection
- [ ] Staging end-to-end: a message from a test WhatsApp number is answered by the bot, handed off, replied to by an agent from the inbox, with delivery status shown
- [ ] Phase report; owner sign-off

## P7 Platform admin, quotas, onboarding, hardening
- [ ] P7-01: admin console advanced: job/delivery health, Many connection health and secret rotation, plan assignment, platform analytics (messages, tenants, bots, handoff rate, AI usage per client), pause bot/connection; actions audited with reason; no impersonation
- [ ] P7-02: quotas enforced and race-tested (bots, seats, monthly messages, channel connections, contacts, sentiment runs)
- [ ] P7-03: self-service signup uses the same ProvisioningService as staff onboarding; concurrent retries create exactly one tenant/bot
- [ ] P7-04: tenant export/delete verified (includes contacts, conversations, identities); audit review screen
- [ ] P7-05: backup + restore drill done; health/monitoring/alerts defined (including failed deliveries and stuck jobs); staging deploy only after ADR-007 approval
- [ ] Independent security review (upload hardening, CSRF, session, tenant isolation, prompt injection, HMAC channel endpoint, SSE) closed
- [ ] Phase report; owner sign-off → ready for staging
