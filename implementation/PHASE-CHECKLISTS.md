# Phase checklists — tick only with evidence (command + result in PROGRESS.md or the ticket report)
Legend: [ ] open · [x] done with evidence. Owner sign-off closes each phase.

## P1 Foundation
- [x] P1-01 toolchain, health/ready, Compose, CI config (evidence: P1-01-REPORT.md; hosted CI not yet run)
- [ ] P1-02: `alembic upgrade head` from empty DB and `downgrade base` both succeed on a disposable DB
- [ ] P1-02: unique/FK/composite-FK constraints verified by tests
- [ ] P1-02: register/login/logout/me work; wrong password, expired and revoked sessions rejected
- [ ] P1-02: passwords stored as Argon2id; cookie HttpOnly/SameSite; CSRF enforced on writes; no secrets in logs
- [ ] P1-02: test DB guard refuses non-`_test` databases
- [ ] P1-03: tenant create/list-mine/get; creator becomes owner
- [ ] P1-03: role matrix tested (owner/admin/editor/viewer × every endpoint)
- [ ] P1-03: tenant A cannot read/write tenant B bots by guessed UUID (404)
- [ ] P1-03: bot create/list/get/update/archive with validation; archive is soft; audit rows written
- [ ] P1-04: register → create org → create bot works in a real browser (Playwright E2E)
- [ ] P1-04: org switcher, role-aware buttons, loading/empty/error states
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
- [ ] P3-03: conversations, messages, citations, thumbs feedback, usage events stored (idempotent); retention purge works
- [ ] P3-04: Playground shows answer + citations + errors; "not ready" state when nothing is published
- [ ] P3-05: eval suite committed (grounded / unanswerable / injection / cross-language, EN + AR) with real numbers against docs/14 §10 targets
- [ ] P3-06 (optional): only started if evals show recall gaps — separate approval
- [ ] Phase report; owner sign-off

## P4 Widget and client experience
- [ ] P4-01: public config + session endpoints; locator is not a secret; short-lived session capability; rate limits; allowed-domain check
- [ ] P4-02: widget loads from one script tag; iframe sandbox; mobile, keyboard, screen-reader labels, RTL
- [ ] P4-03: appearance settings saved and reflected; install page shows correct snippet
- [ ] P4-04: conversations view; leads captured only with consent; retention setting works
- [ ] P4-05: analytics show measured numbers only (matches stored events)
- [ ] Two test websites + two tenants: each answers only from its own knowledge; paused bot and expired session handled
- [ ] Phase report; owner sign-off

## P5 Platform admin, quotas, onboarding, hardening
- [ ] P5-01: /platform area for `is_platform_staff` only; tenant/bot/job health; actions audited with reason; no impersonation
- [ ] P5-02: quotas enforced and race-tested (concurrent requests at the limit)
- [ ] P5-03: ProvisioningService used by both self-service and staff paths; idempotency key; concurrent retries create one bot
- [ ] P5-04: tenant export/delete verified; audit review screen
- [ ] P5-05: backup + restore drill done; health/monitoring/alerts defined; staging deploy only after ADR-007 approval
- [ ] Independent security review (upload hardening, CSRF, session, tenant isolation, prompt injection) closed
- [ ] Phase report; owner sign-off → ready for staging

## P6 (optional) ManyOsirisChat integration
- [ ] Separate design ADR approved · [ ] explicit tenant mapping · [ ] contract tests · [ ] canary + rollback plan
