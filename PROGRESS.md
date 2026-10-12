# Execution checkpoint

2026-10-12 — ADR-003 and P1-01 explicitly approved by product owner.

## 2026-10-12 — P1-02 implemented (schema + auth)

IMPLEMENTED AND LOCALLY VERIFIED; evidence: [P1-02 report](implementation/PHASE-01/P1-02-REPORT.md). Checklist P1-02 items ticked with that evidence.

- Alembic revision 0001_initial: users (citext email), sessions, tenants, memberships, bots, invitations, audit_events; UUID PKs; (tenant_id,id) anchor unique on bots; citext extension created/dropped by the migration.
- Auth: register/login/logout/me; Argon2id (argon2-cffi); server-side sessions (HttpOnly SameSite=Lax cookie; SHA-256 token hash stored); rotation on login; CSRF double-submit on cookie writes; login rate limit (in-process, 10/300s default); stable `{error:{code,message,request_id}}` everywhere; secrets never echoed.
- Tests: 40 passed on Windows host and in the Linux checks container against disposable DBs (`chatbot_dev_test`, `chatbot_dev_migration_test`); `_test`-guard unit test; migration up/down on an empty disposable DB; constraint tests; session lifecycle; CSRF; rate limit; duplicate email (case-insensitive).
- Exact commands and outcomes recorded in P1-02-REPORT.md: ruff/mypy/pytest clean; `alembic upgrade head` applied to dev `chatbot_dev`; live uvicorn smoke register→login→logout→401 verified with curl.
- Note: hosted CI still not run (no push authorization). Login limiter is single-process by design for P1.

Next: P1-03 (tenants, roles, bots, team invitations).

## 2026-10-12 — P1-03 implemented (tenants, roles, bots, team invitations)

IMPLEMENTED AND LOCALLY VERIFIED; evidence: [P1-03 report](implementation/PHASE-01/P1-03-REPORT.md). Checklist P1-03 items ticked with that evidence.

- Reusable TenantContext dependency resolves tenant from path, validates active membership, role-required helpers; hidden resources always 404.
- Tenants create (creator-owner, audited, unique slug), member-only tenant get; /me with memberships.
- Team: invitations via one-time link (SHA-256 hash stored, token shown once), accept with email match, expiry/revoke/resend; members list/role change/remove; last-owner + owner protections; all audited.
- Bots CRUD with validated config schema (docs/04 fields), soft archive (idempotent, config preserved, hidden from default list), tenant-scoped 404s; CSRF required on all writes; stable error codes.
- Tests: 61 passed — full role matrix, tenant A/B guessed-UUID isolation across bots/members/invitations, invitation lifecycle incl. expired/used/revoked/resend + stale token, last-owner protection, soft-archive behaviour, audits. Same result in the Linux checks container (docker run).
- Exact commands recorded in P1-03-REPORT.md.

## 2026-10-12 — P1-04 implemented (dashboard UI + Playwright E2E)

IMPLEMENTED AND LOCALLY VERIFIED; evidence: [P1-04 report](implementation/PHASE-01/P1-04-REPORT.md). P1-04 checklist items ticked with that evidence.

- Next.js dashboard pages: /register, /login, /app (org selector + create), /app/[tenant]/bots, /app/[tenant]/bots/[id]/settings (rename + validated config + archive), /app/[tenant]/settings/members (invite link shown once with copy, resend/revoke, role selects, remove, owner protection notes) and /accept-invite with return-path handling.
- Typed API client with same-origin rewrites proxy (no CORS), CSRF header automation, stable ApiError mapping, session-expired redirect (event-based, open-redirect-safe), role-aware controls, loading/empty/error states everywhere; no mocked data.
- Playwright: global setup boots the REAL FastAPI on a disposable chatbot_dev_e2e_test DB (alembic migrations; _test guard), 5 tests pass — register→org→bot→archive, second-user cross-tenant 404 surfacing, team invite/accept/editor rights, sign-out redirect, landing smoke.
- Web checks green (lint, format, typecheck, Playwright 5 passed); backend regression green (ruff/format/mypy strict/pytest 61 passed); Compose stack rebuilt healthy with the API proxy build arg; proxied register→me smoke 201/200 through the web origin.
- Exact commands recorded in P1-04-REPORT.md.

## 2026-10-12 — P1 phase complete: awaiting owner sign-off

PHASE-REPORT written (implementation/PHASE-01/PHASE-REPORT.md). All P1 checklist items ticked with evidence except the final owner sign-off line. Nothing pushed, merged or deployed; hosted CI still unrun (documented limitation). Local Compose is running for review on loopback 3000/8000/55432.

STOP — awaiting owner sign-off before P2.

P1-01: IMPLEMENTED AND LOCALLY VERIFIED; awaiting owner acceptance. Evidence: [P1-01 report](implementation/PHASE-01/P1-01-REPORT.md).

- Initialized Git on feat/p1-01-foundation; original handoff retained. No commits/remote/push/merge/deployment.
- Next.js 16.4.0 / React 19.3.0 / TypeScript 6.0.3; FastAPI 0.143.0 / Pydantic 2.14.1; PostgreSQL 17.11 with pgvector 0.8.7 available. No application schema or extension installation.
- Frontend Prettier/ESLint/typecheck passed. Final Playwright run: 1 passed (27.7s).
- Linux backend checks: Ruff lint/format passed, strict mypy passed for 9 files, pytest 6 passed with one httpx deprecation warning. Windows pytest also passed; Windows mypy blocked by Application Control and verified via Linux instead.
- Final Compose build/start succeeded; db/api/web healthy. Live smoke: API /health and /ready 200; frontend 200 and 8 static assets served.
- Failure test: stopped only local development DB; /health stayed 200, /ready safely returned 503; DB restored and readiness passed.
- Host Next.js dev and Uvicorn reload commands started and served expected responses; temporary processes stopped. Compose remains running locally on loopback 3000/8000/55432.
- Production npm audit: zero vulnerabilities. Development lint chain: five high entries from one unpatched braces advisory; tracked in report, tooling excluded from standalone runtime.
- GitHub Actions configured; hosted CI NOT RUN because no remote push is authorized.

All P1-02 through P1-09 tickets remain NOT STARTED. No authentication, tenant schema, bots, ingestion, RAG, widgets, billing, ManyOsirisChat integration or reference code was implemented/imported. Phase 1 as a whole is not complete.

Next action: owner reviews P1-01 evidence. P1-02 requires separate explicit approval and relevant schema/isolation decisions. Stop here.

## 2026-10-12 — Plan simplified (docs only, no code change)
Roadmap reduced to 5 vertical-slice phases; ADR-004/009/010/011/012 approved; ADR-005 later resolved (see below). Added docs/18-EXPECTED-BEHAVIOUR.md, implementation/PHASE-CHECKLISTS.md, implementation/AGENT-PROMPTS.md; rewrote roadmap, Phase 1 spec/register, reuse matrix, architecture, AGENTS.md, README_START_HERE.md. P1-01 committed locally. Next: P1-02 (paste prompt 1 from AGENT-PROMPTS.md).

## 2026-10-12 — Reference repos removed from the plan
No Retrivo/Rabbit Hole inspection step in the build. Retrieval/ingestion/analytics specs are agreed with the owner and recorded in docs/14-AGREED-BUILD-SPECS.md (all TBD for now). ADR-012 retired.

## 2026-10-12 — Design review of Rabbit Hole and Retrivo
Both repos were read together with the owner. Result recorded in docs/14-AGREED-BUILD-SPECS.md: keyword-first retrieval (ADR-005 resolved), free-model chain with OpenAI for paid plans (ADR-013), same-language-first retrieval (ADR-014), static HTML URL import (ADR-006 partly). P2 reduced to 5 tickets without embeddings; P3-06 semantic upgrade is optional and eval-gated. No code changed.

## 2026-10-12 — In-app scraper replaced by staff skill
ADR-006 resolved: no in-app crawler in MVP; website content comes from the website-to-knowledge skill (docs/14 §13) as Markdown pages with source URLs + Q&A CSV. P2 is now 4 tickets. No code changed.

## 2026-10-12 — Re-scoped as a Mojeeb-style website product
Owner clarified: this SaaS serves website clients; ManyOsirisChat provides the Meta connections. Roadmap is now 7 phases (P5 inbox/handoff/CRM, P6 ManyOsirisChat channel contract, P7 platform/quotas/hardening); ADR-002 revised, ADR-015/016/017 added; docs/14 gained §14–§18; docs/17 rewritten as the channel contract; checklists, prompts and expected-behaviour guide updated. First sellable cut = end of P5. No code changed. Next: P1-02 (prompt 1 in AGENT-PROMPTS.md).

## 2026-10-12 — Two dashboards (ADR-018)
Client dashboard per chatbot (docs/10) and platform admin console (docs/11) are now named deliverables. Basic admin console + staff onboarding moved into P4 (new ticket P4-06); P7-01/P7-03 narrowed to advanced operations and self-service hardening. Roadmap, checklists, prompts, API routes, FRs and behaviour guide updated. No code changed.
