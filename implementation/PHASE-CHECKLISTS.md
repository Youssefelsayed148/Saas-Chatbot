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
- [ ] P2-01: parsing, chunking, embedding and retrieval specs agreed and recorded in docs/14; ADR-005 (embeddings) decided
- [ ] P2-02: migrations for sources, documents, revisions, chunks, jobs; atomic job claim with lease/retry tested (two workers, one job)
- [ ] P2-03: PDF/DOCX/TXT/MD/CSV parsed and chunked from fixtures; oversize/unsupported/corrupt files rejected clearly
- [ ] P2-04: URL import bounded (pages, depth, bytes, time, redirects); private/loopback/metadata targets and redirects-to-internal blocked; prompt-injection text stored as data
- [ ] P2-05: embeddings stored; re-ingest idempotent (content hash); draft → publish → rollback atomic; failed job leaves published revision intact
- [ ] P2-05: two tenants ingest identical content → zero shared rows
- [ ] P2-06: Knowledge UI: upload, job status, errors/retry, preview, publish/rollback
- [ ] Phase report; owner sign-off

## P3 Chat
- [ ] P3-01: hybrid retrieval (keyword + semantic) returns only tenant + bot + published-revision chunks (test proves removing the filter fails)
- [ ] P3-02: LLMProvider interface with first free/Ollama provider; prompts versioned; citations validated; abstains when evidence is missing
- [ ] P3-02: Arabic, English and mixed questions answered in the question's language
- [ ] P3-03: conversations, messages, citations, usage events stored (idempotent)
- [ ] P3-04: Playground shows answer + citations + errors; "not ready" state when nothing published
- [ ] P3-05: eval suite committed (grounded / unanswerable / injection / Arabic) with thresholds recorded and met
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
- [ ] Independent security review (SSRF, CSRF, session, tenant isolation, prompt injection) closed
- [ ] Phase report; owner sign-off → ready for staging

## P6 (optional) ManyOsirisChat integration
- [ ] Separate design ADR approved · [ ] explicit tenant mapping · [ ] contract tests · [ ] canary + rollback plan
