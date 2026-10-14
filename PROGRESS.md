# Execution checkpoint

2026-10-12 — ADR-003 and P1-01 explicitly approved by product owner.

## 2026-10-13 — PHASE P4 started (branch feat/p1-01-foundation, P1–P3 signed off)

Environment note: no Windows venv is reachable in this session; backend checks run in the
Linux checks container (`docker build --target checks -f apps/api/Dockerfile -t
saas-chats-ai-api-checks:p4 .`), the disposable DBs live in the local compose Postgres
(only the `db` service is up). Node 24 (Linux tarball in `~/.local`) runs the web
toolchain; `@next/swc-linux-x64-gnu` installed with `--no-save` to keep the lockfile untouched.

## 2026-10-13 — P4-00 implemented (P3 carry-overs)

IMPLEMENTED AND LOCALLY VERIFIED; evidence: [P4-00-REPORT](implementation/PHASE-04/P4-00-REPORT.md).
- Cross-script retrieval: `retrieve(translate_query=…)` consumes ONE ChatModel translate
  call before the fallback pass (raw question on failure); works on first messages. Tests:
  `tests/test_cross_script.py` 3 passed (translate-once + grounded, provider-failure
  fallback, no call when languages match).
- `Settings.environment` + `validate_startup_settings` guard: production+stub raises
  `RuntimeError`; `tests/test_startup_guard.py` 5 passed (create_app included).
- Eval extended to 25 cases (+3 cross-script over EN-only content via the translate path,
  +3 unanswerable, +2 document-borne injection with forbidden phrase checks); corpus
  gained gift-wrap (EN), poisoned delivery (EN) and poisoned support (AR) pages.
  Numbers (stub run): grounded 8/8, unanswerable 8/8, injection 4/4 (100%), cross-language
  3/5 — the 3 new cases pass; the 2 legacy bilingual cases remain the recorded P3
  stub-run limitations. **OpenRouter rerun NOT performed: no key provided** — documented
  in `implementation/PHASE-03/EVAL-REPORT.md`; the runner supports it behind
  `CHAT_OPENROUTER_API_KEY` + `run_all(rerun_with_owner_key=True)` once a key exists.
- Also fixed a P2 pre-existing test-suite deadlock found at HEAD in this environment:
  `tests/test_knowledge_uploads.py`'s `raw_db` fixture never closed its session, so the
  next test's teardown `TRUNCATE` blocked forever on a relation lock (worktree froze
  around 39–60 % of the suite, reproduced on a HEAD-only checkout — not a P4 regression).
  With the fixture closing, the full suite runs in ~2 minutes.

## 2026-10-13 — P4-01 implemented (public widget API + visitor sessions + abuse limits)

IMPLEMENTED AND LOCALLY VERIFIED; evidence: [P4-01-REPORT](implementation/PHASE-04/P4-01-REPORT.md).
- Migration `0004_widget_public` (locator column, visitor_sessions, rate_limit_counters,
  conversations.session_id with composite FKs); up/down covered by test_migrations.
- Public endpoints under `/api/public/v1` (config / sessions / messages / feedback) with
  capability-token auth, domain allow-list as defence signal, BOT_PAUSED/BOT_NOT_READY
  states, quota hook; the SAME P3 pipeline answers.
- Postgres-backed fixed-window rate limiter in `app/core/ratelimit.py`; the P1 login
  limiter moved onto it (`app/auth/ratelimit.py` removed, same 429 contract).
- Bot PATCH accepts audited `status` transitions (draft→active, active↔paused; archive
  stays DELETE-only). Tests `tests/test_bot_status.py` 5 passed.
- Test evidence: widget/public suite 14 passed; full backend suite **189 passed** in ~2:05
  on the disposable DB after the fixture fix; ruff/format/mypy strict clean (99 sources).

## 2026-10-13 — P4-02 implemented (widget package: loader + sandboxed frame UI)

IMPLEMENTED AND LOCALLY VERIFIED; evidence: [P4-02-REPORT](implementation/PHASE-04/P4-02-REPORT.md).
- `packages/widget` loader (ES2020, no deps) at `/widget/v1/loader.js` (versioned path,
  npm workspace registry updated + lockfile regenerated) creating the bubble +
  `sandbox="allow-scripts allow-same-origin allow-forms"` iframe at `/widget/frame`.
- Frame page covers the docs/09 states (loading/typing/citations/paused/not-ready/quota/
  rate-limited/network-retry), welcome + chips + thumbs + scroll-to-bottom, RTL, keyboard
  access, Escape→close, localStorage session recovery (silent re-auth on 401), postMessage
  protocol (locator, size, brand, close).
- Scoped CSP: `/widget/:path*` (declared AFTER the dashboard rule — NEXT 16 wins with the
  last value) → `frame-ancestors http: https:`; the dashboard keeps 'none' (P2-00).
 proven by security-headers.spec 2 passed; widget spec 2 passed (two sites, two tenants,
 each answers only from its own knowledge). Chromium system libs installed user-space
 (`/tmp/opencode/debroot`, no sudo) to run Playwright headless on this WSL host.
- Same-origin limitation documented in the report (loopback + Chrome Local Network
  Access blocks loopback script loads cross-origin in the LAB); production cross-origin
  classic scripts don't need CORS; per-session capability tokens bound cross-tenant use.

## 2026-10-13 — P4-03 implemented (appearance settings + install page)

IMPLEMENTED AND LOCALLY VERIFIED; evidence: [P4-03-REPORT](implementation/PHASE-04/P4-03-REPORT.md).
- Appearance settings (assistant/business, welcome EN/AR, opening questions, default
  language/RTL, support contact, colour, position, avatar (http(s)-only), handoff toggle,
  allowed domains) via typed BotConfig; bot Activate/Pause in the UI over the audited
  PATCH `status` transition.
- Install tab: real snippet (deployment-aware origin, copy), locator guidance, sample
  page helper `/widget/sample?locator=…` appending the REAL script element with the
  user locator (innerHTML scripts never run — explained in the report).
- Evidence: install.spec 1 passed (draft guidance → activate → snippet → sample journey
  with bubble), test_widget_appearance.py 3 passed (avatar validation/locator lookup).

## 2026-10-13 — P4-04 implemented (conversations view, consent leads, retention)

IMPLEMENTED AND LOCALLY VERIFIED; evidence: [P4-04-REPORT](implementation/PHASE-04/P4-04-REPORT.md).
- Conversations list/detail (source!=playground filter) + editor-only delete (screen
  messages cascade), tenant B/guessed UUIDs 404 incl. DELETE; viewer 403. Lead capture
  POST /api/public/v1/sessions/{id}/lead — CONSENT REQUIRED, citext email match/phone
  match updates ONE contact, consent JSON on the contact, session identity + conversation
  binding, idempotent lead usage event. Retention: migration 0005 (tenants.retention_days,
  NULL=default; CHECK 1–365), PATCH (admin+, audited), per-tenant purge (7-day tenant
  purges a 10-day-old message; 5-day untouched) + aged rate-limit buckets cleared.
- UI: conversations list + thread (citations + needs-human notices + lead badge), widget
  lead form (EN/AR consent text + checkbox; no write without consent).
- Evidence: test_conversations_view 5 passed, test_widget_leads 5 passed; conversations
  E2E 1 PASSED (widget chat + consent + the dashboard journey with visible citations;
  lead POST 201 through the REAL stack); widget/bots-only batch 90 passed with clean
  ruff/format/mypy after the backend feature work.

## 2026-10-13 — P4-05 implemented (per-bot workspace shell + measured overview analytics)

IMPLEMENTED AND LOCALLY VERIFIED; evidence: [P4-05-REPORT](implementation/PHASE-04/PHASE-REPORT.md) and per-ticket reports P4-02…P4-04.
- Workspace shell `lib/bot-workspace-nav.tsx` on ALL bot pages (overview/conversations/
  knowledge/playground/settings/install — exactly the tabs that exist today, docs/10).
- Measured analytics (docs/14 §9) from SQL over usage_events + real conversations —
  playground threads NEVER count: summary (messages/conversations/widget opens/engagement/
  avg messages + distribution/fallback rate/needs-human/avg response/leads/thumbs), volume
  per day, top questions, unanswered list, leads trend + contacts; date range (`from`/`to`
  inclusive, validated 422); CSV exports `conversations.csv` + `leads.csv`.
- Endpoints GET /analytics/{summary,volume,top-questions,unanswered,leads,csvs} — member
  reads; wrong tenant/bot 404.
- Tests: tests/test_analytics.py 6 passed (counts incl. leads/thumbs needs_human, volume/
  top/unanswered/leads, playground exclusion, per-bot scoping + CSVs, viewer role + date
  validation, window filtering). Playwright overview.spec 2 passed (shell tabs, measured
  numbers incl. "A-cookie-on-B-bot 404" isolation, unanswered list, CSV).

## 2026-10-13 — P4-06 implemented (admin console basics)

IMPLEMENTED AND LOCALLY VERIFIED; evidence: [P4-06 within PHASE-REPORT](implementation/PHASE-04/PHASE-REPORT.md).
- app/platform/staff.py: is_platform_staff ONLY (never a tenant role); API 403 For non-staff.
- /platform LAYOUT guard server-side per request (cookies → GET /api/v1/platform/me;
  redirect to /login otherwise; no client shortcut; PLATFORM_GUARD_ORIGIN deployment
  override documents the API-origin option; an unauthenticated/non-staff visit renders
  only the redirected /login page).
- API: GET /platform/{me,tenants,tenants/{id},onboarding/{id},onboarding.csv} + POST
  /platform/onboarding (multipart; REQUIRED Idempotency-Key; skill-output files stored
  under generated tenant keys, kind-checked md/txt/csv/pdf/docx).
- ProvisioningService (docs/12): tenant → audited; owner INVITATION (one-time link shown
  once, hash stored, 7 days); optional FIRST BOT; optional files. Durable
  provisioning_requests rows (mode, idempotency_key unique per scope): replay returns the
  same row; payload/actor mismatch 409; double submission creates exactly ONE tenant/bot;
  failed attempts are durably recorded and retried via a new key/payload.
- Tests: test_platform.py 9 PASSED (non-staff matrix, staff-flag separation, onboarding +
  audit actor attribution, double submit one tenant, clash 409, missing key 400, optional
  files, list/detail + unknown 404). migration 0006_provisioning up/down verified.
- Playwright platform.spec 2 passed (non-staff redirect; staff console end-to-end:
  list → onboarding form → one-time invite + durable request visible → detail with bots/
  failure-jobs/members/audit).

## 2026-10-13 — P4 PHASE VERIFICATION (full suites)

- Backend: counts per the E2E-API container against chatbot_dev_test with a FRESH DB:
  ruff check ✓, ruff format --check ✓ (118 files), mypy strict ✓ (114 sources),
  pytest **216 PASSED** (~176 s) — ALL suites on the disposable DB, ends-to-end including
  migrations 0004–0006 (up/down) and platform/conversation-core suites.
- Web: eslint+prettier+tsc clean; **Playwright full suite 20 PASSED** (all stacked specs:
  foundation/dashboard/team/knowledge/playground/security-headers + P4 widget/install/
  conversations/overview/platform).
- Report gathered in docs/phase4report.md and implementation/PHASE-04/PHASE-REPORT.md.
- Checklist P4 ticked with evidence; Owner sign-off left UNTOUCHED (docs: STOP).

## 2026-10-12 — PHASE P2 SIGNED OFF by owner ("ready to go to phase 3") — Phase P3 authorized

## 2026-10-13 — PHASE P3 complete (P3-01 → P3-05): retrieval, chat service, conversation core, playground, eval

IMPLEMENTED AND LOCALLY VERIFIED; evidence: [PHASE-03 report](implementation/PHASE-03/PHASE-REPORT.md), per-ticket reports P3-01…P3-05 and EVAL-REPORT.md in `implementation/PHASE-03/`. Checklist P3 items ticked with evidence; STOPPED FOR OWNER SIGN-OFF.

- P3-01 retrieval: keyword FTS over the GIN tsvector columns with always-on tenant+bot+published-revision+language filters (decoy-seeded tests fail if any filter is removed), ts_rank_cd ranking one best chunk per document, best-document-whole + small-document-whole rules, reserved always-include slots, ADR-014 cross-language fallback pass. Arabic questions normalise before tokenising; «ال» variants + `:*` prefixes; `text_norm` covers title+heading+body.
- P3-02 chat service: ChatModel interface + OpenAI-compatible client (OpenRouter :free chain w/ fallback + free_only guard; OpenAI for paid), versioned prompt, strict JSON contract with validated citations, rule routing (smalltalk/handoff w/ per-bot toggle), condensation of the last 6 visitor messages, localized busy/cannot-confirm fallbacks with the support contact.
- P3-03 conversation core (migration 0003): contacts/identities/conversations/messages/usage_events with composite FKs; playground pipeline (mode=ai only), idempotent thumbs feedback, idempotent usage events, retention purge (queue job type + worker self-scheduling, retention_days=30).
- P3-04 playground UI: thread with citations (title + source URL), thumbs, localized errors, not-ready state, viewer read-only; Playwright E2E 12 passed (grounded chat + citation + feedback + persistence + viewer + expired-session).
- P3-05 eval: 17 cases (grounded/unanswerable/injection/cross-language, EN+AR) through the real pipeline with the deterministic offline stub model (dev-only `CHAT_STUB_MODEL`); REAL numbers vs docs/14 §10 — grounded 8/8 (100% ≥90%), unanswerable abstained 5/5 (100% ≥95%), injection resisted 2/2 (100%), cross-tenant leakage 0; cross-language stub run recorded as a real-model gate item (no numeric §10 target; ADR-014 fallback path proven in the retrieval tests).
- Final checks: Linux container + Windows venv — ruff/format/mypy/pytest green, 162 passed on both; web format/lint/typecheck green; Playwright 12 passed.
- Carried limitations: hosted CI never run; in-process login limiter; real-provider live verification pending owner keys (provider layer is unit-tested; no paid calls); cross-script translation = real-model item; ExtractiveStubModel is dev/test/eval-only.

## 2026-10-12 — PHASE P2 complete (P2-00 → P2-04): knowledge ingestion, queue/worker, publish/rollback, Knowledge UI

IMPLEMENTED AND LOCALLY VERIFIED; evidence: [PHASE-02 report](implementation/PHASE-02/PHASE-REPORT.md) and per-ticket reports P2-00…P2-04 in `implementation/PHASE-02/`. All P2 checklist items ticked with evidence; STOPPED FOR OWNER SIGN-OFF.

- P2-00 carry-overs: security headers in `apps/web/next.config.ts` (Referrer-Policy no-referrer, X-Content-Type-Options nosniff, CSP frame-ancestors 'none') proven by a Playwright test + live curl through the Compose stack; invitation double-accept race test added with a `FOR UPDATE` row-lock fix (exactly one 200, one 409, one membership, one audit row).
- P2-01: migration `0002_knowledge` (sources, source_pages, documents, knowledge_revisions with partial draft/published uniques, chunks with generated GIN `fts_en`/`fts_simple`, jobs; `bots.published_revision_id`; composite FKs; no vector/pgvector). DB queue with FOR UPDATE SKIP LOCKED claim, lease reclaim, exponential backoff, cancel; `python -m app.worker`; Compose `worker` service (healthy, heartbeat healthcheck, shared `/data/storage`); `WORKER_ALLOW_ONLY_TEST_DB` guard verified; Playwright harness boots a real worker.
- P2-02: multipart upload with streaming 10 MB cap, ≤20 files, magic-byte sniffing (PDF/zip-docx/text), mislabelled/binary/oversize/zip-bomb guards; local-disk shared storage with generated tenant/bot keys (Windows `O_BINARY` fix validated); PDF/DOCX/TXT/MD parsers incl. Arabic and YAML front matter (http(s)-only `source_url`); Q&A CSV template + per-row report; chunker per docs/14 §4 (no content loss); language detector + Arabic normalisation §2; parse in worker with timeout. Pinned `pypdf==6.20.1`, `python-docx==1.2.0`, `PyYAML==6.0.3`, `python-multipart==0.0.32` (+dev `types-PyYAML`) in pyproject and both lockfiles.
- P2-02 proxy: Next 16 `experimental.proxyClientMaxBodySize: "220mb"` + `apps/web/proxy.ts` content-length guard; oversize upload (10 MB+1) rejected with 413 through the same-origin proxy with nothing stored (Playwright).
- P2-03: ingest job writes into a fresh draft revision that snapshots the published revision; content-hash dedupe; unchanged re-ingest is a no-op; publish/rollback = ordered atomic pointer swap (demote → promote → pointer, validated unique-index-safe); failed job never touches published knowledge; two tenants with identical content share zero rows (disjoint ids + referential check).
- P2-04: Knowledge page at `/app/[tenant]/bots/[botId]/knowledge` (upload + template link, files with Q&A row report, job list with Retry/Cancel and live polling, documents/chunks preview with source_url and RTL, revisions with Publish/Rollback, viewer read-only with zero write controls); Playwright 9 passed on the real stack (real API + real worker harness).
- Final checks (both toolchains): ruff clean, 83 files formatted, mypy strict 71 sources clean, pytest **123 passed** (Linux container + Windows venv), web format/lint/typecheck clean, `docker compose up --build -d --wait` all four services healthy, live curl smoke through port 3000 passed end to end (upload → worker `succeeded` → publish 200) and security headers present on `/` and `/login`.
- Carried limitations recorded in the P2 report: hosted CI never run; P1 in-process login rate limiter; proxy headers not attached to `/api` rewrites (the production gateway adds them); parse-timeout thread cannot be hard-killed (bounds documented); worker throughput is one job at a time per process; chunked (no Content-Length) bodies skip the proxy header check (the API streaming cap still applies).

Commands and detailed evidence per command live in the ticket reports. Local commits made per ticket (no push). Compose stack left running on loopback 3000/8000/55432 for owner review.

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

## 2026-10-14 � P4 audit attempt and close-out

Audit: `implementation/PHASE-04/AUDIT.md`. Review covered A1�A9. Static source/test review found no confirmed security defect. The checklist currently contains one P4 row per deliverable, one unticked owner gate, and one P5 header; `docs/phase4report.md` is now a one-line pointer to the canonical implementation report. Checklist diff reviewed: changes are confined to P4-05/P4-06 evidence rows, the two-site evidence row, and the report/owner line; P1�P3 and P5�P7 are unchanged.

Exact verification commands and outcomes from this session:
- `docker version` � FAILED: permission denied connecting to `npipe:////./pipe/DockerDesktopLinuxEngine`.
- `python -m ruff check .` (from `apps/api`) � FAILED to start: `No module named ruff`.
- `npm run lint` (repository root) � EXIT 0; ESLint completed with `--max-warnings 0`.
- `npx prettier --check app lib tests` (from `apps/web`) � first EXIT 1; listed `app/platform/clients/[clientId]/page.tsx`, `app/platform/page.tsx`, and `lib/api.ts` as unformatted. Applied `npx prettier --write 'app/platform/clients/[clientId]/page.tsx' app/platform/page.tsx lib/api.ts`; rerun EXIT 0: all matched files use Prettier style.
- `npm run typecheck` (repository root) � Next SWC initialization blocked with `EPERM` creating `C:\Users\Youssef\AppData\Local\next-swc` (outside writable workspace).
- `npx tsc --noEmit` (from `apps/web`) � EXIT 0.
- `docker compose -f infra/compose.yaml ps` � not run successfully; Compose could not interpolate the required POSTGRES_USER/POSTGRES_PASSWORD/POSTGRES_DB values, and Docker daemon is unavailable.

No fresh disposable DB was created. Full backend lint/format/mypy/pytest (including the claimed 216 tests), migration 0001�0006 up/down, and the full Playwright suite (claimed 20 tests) are UNVERIFIED. No live model key was available and no paid call was made. Because those checks are required to close A1 and they could not be run here, P5 was not started. P4 owner sign-off remains unticked.

## 2026-10-14 � P4 fresh verification completed

This entry supersedes the earlier same-day note that Docker was unavailable to the sandbox. The sandbox was denied the Docker Desktop named pipe, while an approved out-of-sandbox Docker command showed the engine running (Docker Server 29.8.0). Used the existing healthy local Postgres container; the repository's API, web, and worker services were not running. Test-only containers and databases were isolated to `*_test`; temporary API/worker/checks containers were removed after verification. The existing Postgres service and its volumes were left untouched.

Exact verification and outcomes:
- Backend command: `docker run --name p4-audit-checks --network saas-chats-ai-dev_default -e DATABASE_URL=<runtime-derived from local Postgres> -v <repo>:/workspace -w /workspace/apps/api saas-chats-ai-api-checks:p4 sh -c 'ruff check . && ruff format --check . && mypy && pytest'` � EXIT 0. Output: `All checks passed!`; `118 files already formatted`; `Success: no issues found in 114 source files`; `216 passed, 1 warning in 89.08s` (Starlette/httpx deprecation).
- Migration cycle: included in the full run as `tests/test_migrations.py::test_migrations_up_down_cycle` � upgrade head from empty disposable migration DB (0001�0006), downgrade base, upgrade head again; PASS.
- `npm run lint` (repo root) � EXIT 0.
- `npx prettier --check app lib tests` (`apps/web`) � EXIT 0 after formatting the three reported files.
- `npx tsc --noEmit` (`apps/web`) � EXIT 0.
- `npm run build -- --webpack` (`apps/web`, escalated to allow Next worker processes) � EXIT 0, production build compiled and generated all pages. Default Turbopack build is unavailable because the Windows native SWC binding is missing.
- `npm test` (`apps/web`) � EXIT 0, **20 passed (2.0m)**. Used `E2E_REUSE_API=1` with the isolated API/worker and E2E DB; temporarily changed Playwright webServer to start the successfully built Webpack bundle without rebuilding, then restored `playwright.config.ts`.

P4 A1 now passes. A2 real-provider eval remains UNVERIFIED because no key was provided; no paid call was attempted. No confirmed FAIL remains. P4 sign-off stays unticked. The pasted request authorizes beginning P5 without treating that as P4 sign-off; proceeding to P5-01.

## 2026-10-14 - P5-01 handoff and agent actions

Implemented website conversation handoff rules and tenant-scoped agent actions. Handoff triggers include repeated unanswerable questions, EN/AR person requests, order/account routing, and provider failure. Human-mode visitor messages are persisted without invoking the model; agent replies are available through the visitor's own session polling as plain text. Takeover, return-to-AI, resolve, and assignment add system events and audit rows; takeover uses row locking and reports a 409 race with the current assignee. Resolved website conversations reopen in AI mode on the next visitor turn. Internal system events are excluded from visitor history.

Verification (exact commands and outcomes):
- `docker exec p5-01-e2e-api sh -lc 'ruff check . && ruff format --check . && mypy && pytest'` - EXIT 0: Ruff passed; 122 files formatted; strict mypy passed for 118 source files; `220 passed, 1 warning in 95.67s` (Starlette/httpx deprecation).
- `npm run lint` (repo root), `npx prettier --check app lib tests`, and `npx tsc --noEmit` (from `apps/web`) - EXIT 0.
- `npm test` (from `apps/web`, P5 widget end-to-end with isolated API/worker and `*_test` DB) - EXIT 0, `20 passed (1.5m)`.

Docker CLI access from the sandbox is denied on the Docker Desktop named pipe; these commands ran in an approved Docker invocation. No external services or paid model calls were used. P4 owner sign-off remains pending; P5-01 is complete and P5-02 is next.
## 2026-10-14 - P5-01 widget URL regression and full web verification

- Regression: `tests/widget.spec.ts` provides a `javascript:` source_url from the mocked widget API and verifies the citation title is rendered as a span with no javascript link. The frame only links absolute HTTP/HTTPS URLs.
- `npm run lint` (repository root) - EXIT 0.
- `npx prettier --check app lib tests` (from `apps/web`) - EXIT 0, all matched files use Prettier style.
- `npx tsc --noEmit` (from `apps/web`) - EXIT 0.
- `npm run build -- --webpack` (from `apps/web`) - EXIT 0; production build compiled. Windows native SWC binding is absent, so this uses Next's WASM SWC.
- `npm test -- --reporter=line` (from `apps/web`; full Playwright suite against the existing isolated E2E API/worker and test DB) - EXIT 0, `21 passed (1.5m)`. Playwright used the already-built bundle; `playwright.config.ts` was restored afterward.
## 2026-10-14 - P5-02 inbox API and live updates

Added tenant-scoped inbox listing with status/mode/channel/assignee/tag/unread filters and PostgreSQL full-text search; read markers are per tenant member; tag changes are tenant scoped; notification counts cover waiting-human, assigned-to-me, unread messages, and unread conversations. SSE uses durable inbox_events rows and Last-Event-ID resume. Message and tag event IDs are allocated under a per-tenant transaction advisory lock so concurrent API transactions cannot commit an older cursor after a newer one. Every event is read by tenant and cursor from the shared database, not process-local memory.

Verification (exact command and outcome):
- `docker exec p5-01-e2e-api sh -lc 'ruff check . && ruff format --check . && mypy && pytest'` - EXIT 0: Ruff passed; 126 files formatted; strict mypy passed for 122 source files; `225 passed, 1 warning in 109.06s` (Starlette/httpx deprecation). The migration cycle upgraded/downgraded/re-upgraded through 0007_inbox. The five P5-02 tests cover filters/search/tags, per-user unread state, notification counts, tenant hiding, invalid cursors, and reconnect from one API app after another app writes to the shared database.

No frontend changes were needed for P5-02; inbox UI consumption is P5-03. Checks ran in the existing disposable E2E test container/database via approved Docker access because the sandbox cannot open the Docker Desktop named pipe. No cloud or paid services were used.

## 2026-10-14 - P5-04 contacts and light CRM

Added tenant scoped contacts CRUD and profiles with editable lifecycle labels, tags, up to 20 custom fields, per-channel consent, channel identities, and a conversation/note timeline. Added explicit audited contact merge, tenant-scoped CSV export, and contact erasure with an explicit option to erase associated conversation messages. Existing widget lead capture continues to create/update contacts and record consent. Added contacts dashboard pages and a browser journey.

Verification (exact commands and outcomes):
- `docker exec p5-01-e2e-api sh -lc 'export TEST_DATABASE_URL="${DATABASE_URL%/*}/p5_phase5_backend_3_20261014"; ruff check . && ruff format --check . && mypy && pytest -q'` - EXIT 0: Ruff passed; 131 files formatted; strict mypy passed for 127 source files; `226 passed, 1 warning in 98.28s` (existing Starlette/httpx deprecation). The fresh database name ends with `_test`; contacts tests cover tenant A/B isolation, viewer access restrictions, duplicate contact handling, stage updates, custom-field limits, timeline/identity display, audited merge, CSV export, and erasure.
- `npm.cmd run lint --workspace apps/web` - EXIT 0.
- `npm.cmd run typecheck --workspace apps/web` - EXIT 0; Next's WASM SWC fallback was used because the Windows native binding is absent.
- `npx.cmd prettier --check apps/web/app/app/'[tenant]'/contacts apps/web/lib/api.ts apps/web/lib/app-header.tsx apps/web/tests/contacts.spec.ts` - EXIT 0.
- `npm.cmd run build --workspace apps/web -- --webpack` - EXIT 0.
- `cmd /c "set DATABASE_URL=postgresql://p5e2e@127.0.0.1:55433/postgres && npm.cmd test --workspace apps/web -- tests/contacts.spec.ts"` - EXIT 0, `1 passed (19.5s)`. Used a fresh loopback-only PostgreSQL container with no persistent volume; the Playwright server setting was temporarily changed to start the Webpack bundle, then restored.
- An initial default Playwright start exited 1 because Turbopack is unsupported with this Windows WASM-only setup; no browser test ran in that attempt. A first connection URL with the SQLAlchemy `+psycopg` suffix also failed in psycopg; the plain PostgreSQL URL above passed.

No key or `.env` value was read or printed. No production limits were changed, no external or paid APIs were called, and no deployment occurred.

