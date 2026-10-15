# Execution checkpoint

## 2026-10-14 — P7-03 Playwright repair and fictional demo seed

Built: `registerOwner` verifies register 201 and the tenant bots landing; all eight specs reuse the provisioned bot, with Starter assigned through staff API for dashboard editor second-bot/seats and knowledge's 10 MB limit. Invite signup blocks compared unchanged; owner's conversations bubble re-open fix preserved and committed. Guarded offline demo seed + 21 tests added, with four DB-dependent regressions; no product UI changed, no phase sign-off, push or deployment.
Tested: `.\.venv\Scripts\python.exe -m ruff check apps/api/scripts apps/api/tests/test_seed_demo.py`, `.\.venv\Scripts\python.exe -m ruff format --check apps/api/scripts apps/api/tests/test_seed_demo.py`, `.\.venv\Scripts\python.exe -m mypy --strict --follow-imports=silent apps/api/scripts apps/api/tests/test_seed_demo.py`, `.\.venv\Scripts\python.exe -m compileall -q apps/api/scripts apps/api/tests/test_seed_demo.py`, `npm.cmd run lint --workspace apps/web`, `npm.cmd run typecheck --workspace apps/web` - all EXIT 0. `npx.cmd prettier --check apps/web/tests/e2e-helpers.ts apps/web/tests/staff-helpers.ts apps/web/tests/contacts.spec.ts apps/web/tests/dashboard.spec.ts apps/web/tests/install.spec.ts apps/web/tests/knowledge.spec.ts apps/web/tests/overview.spec.ts apps/web/tests/platform.spec.ts apps/web/tests/playground.spec.ts apps/web/tests/widget.spec.ts apps/web/tests/conversations.spec.ts` - EXIT 0. `$env:PYTHONPATH='apps/api'; .\.venv\Scripts\python.exe -m pytest --noconftest -p no:cacheprovider apps/api/tests/test_seed_demo.py -k 'guard or password_default' -q` - EXIT 0, 17 passed / 4 deselected. Earlier guard run passed 17 with a pytest cache-permission warning; final run disables cache and has no warning. `git diff --check -- apps/api/scripts apps/api/tests/test_seed_demo.py` - EXIT 0.
Unverified: `Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue; Remove-Item Env:TEST_DATABASE_URL -ErrorAction SilentlyContinue; .\.venv\Scripts\python.exe -m pytest -p no:cacheprovider apps/api/tests/test_seed_demo.py -q -x` - EXIT 1 at fixture setup: no DATABASE_URL/TEST_DATABASE_URL; no DB tests executed. Playwright/Docker/seed CLI writes were not run. No browser behavior is verified until the owner runs each affected spec and the full suite; owner commands are provided in the completion report. Local commits: helper `d08fe3f`, specs + preserved handoff edit `6a8879f`; seed is the commit containing this checkpoint.

## 2026-10-14 — P5 close-out part 1 (handoff widget and ECONNRESET)

Built: API regression now polls the actual widget endpoint with the visitor token and `since` cursor after an agent reply; handoff copy is generic in EN/AR; opt-in `?debugWidget=1` records poll status/count/sender types only. Trace found no API sender filter, token/scope mismatch, handoff polling stop, or selector mismatch. ECONNRESET cause is still unknown because no failing request/stack was supplied; startup already gates API on `/health` and Playwright on the Next server URL.
Tested: `ruff check` / `ruff format --check` for the changed API files, strict mypy, Python compileall, web ESLint, `next typegen && tsc --noEmit`, and Prettier on the changed widget file all EXIT 0. `git diff --check` reports one pre-existing trailing blank line in `implementation/AGENT-PROMPTS.md` (not changed here). API integration needs the owner's disposable PostgreSQL DB and was not run; Playwright is unavailable in this sandbox.
Unverified: Browser handoff and `widget.spec:146` remain unverified until the owner runs Playwright. `widget.spec:146` diagnostic rerun: add `&debugWidget=1` to the widget sample URL and inspect browser console for `[widget-debug]` poll status/rows/failure. P5-03, P5-05, and sign-off remain unticked.

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

## 2026-10-14 — P4 audit attempt and close-out

Audit: `implementation/PHASE-04/AUDIT.md`. Review covered A1–A9. Static source/test review found no confirmed security defect. The checklist currently contains one P4 row per deliverable, one unticked owner gate, and one P5 header; `docs/phase4report.md` is now a one-line pointer to the canonical implementation report. Checklist diff reviewed: changes are confined to P4-05/P4-06 evidence rows, the two-site evidence row, and the report/owner line; P1–P3 and P5–P7 are unchanged.

Exact verification commands and outcomes from this session:
- `docker version` — FAILED: permission denied connecting to `npipe:////./pipe/DockerDesktopLinuxEngine`.
- `python -m ruff check .` (from `apps/api`) — FAILED to start: `No module named ruff`.
- `npm run lint` (repository root) — EXIT 0; ESLint completed with `--max-warnings 0`.
- `npx prettier --check app lib tests` (from `apps/web`) — first EXIT 1; listed `app/platform/clients/[clientId]/page.tsx`, `app/platform/page.tsx`, and `lib/api.ts` as unformatted. Applied `npx prettier --write 'app/platform/clients/[clientId]/page.tsx' app/platform/page.tsx lib/api.ts`; rerun EXIT 0: all matched files use Prettier style.
- `npm run typecheck` (repository root) — Next SWC initialization blocked with `EPERM` creating `C:\Users\Youssef\AppData\Local\next-swc` (outside writable workspace).
- `npx tsc --noEmit` (from `apps/web`) — EXIT 0.
- `docker compose -f infra/compose.yaml ps` — not run successfully; Compose could not interpolate the required POSTGRES_USER/POSTGRES_PASSWORD/POSTGRES_DB values, and Docker daemon is unavailable.

No fresh disposable DB was created. Full backend lint/format/mypy/pytest (including the claimed 216 tests), migration 0001–0006 up/down, and the full Playwright suite (claimed 20 tests) are UNVERIFIED. No live model key was available and no paid call was made. Because those checks are required to close A1 and they could not be run here, P5 was not started. P4 owner sign-off remains unticked.

## 2026-10-14 — P4 fresh verification completed

This entry supersedes the earlier same-day note that Docker was unavailable to the sandbox. The sandbox was denied the Docker Desktop named pipe, while an approved out-of-sandbox Docker command showed the engine running (Docker Server 29.8.0). Used the existing healthy local Postgres container; the repository's API, web, and worker services were not running. Test-only containers and databases were isolated to `*_test`; temporary API/worker/checks containers were removed after verification. The existing Postgres service and its volumes were left untouched.

Exact verification and outcomes:
- Backend command: `docker run --name p4-audit-checks --network saas-chats-ai-dev_default -e DATABASE_URL=<runtime-derived from local Postgres> -v <repo>:/workspace -w /workspace/apps/api saas-chats-ai-api-checks:p4 sh -c 'ruff check . && ruff format --check . && mypy && pytest'` — EXIT 0. Output: `All checks passed!`; `118 files already formatted`; `Success: no issues found in 114 source files`; `216 passed, 1 warning in 89.08s` (Starlette/httpx deprecation).
- Migration cycle: included in the full run as `tests/test_migrations.py::test_migrations_up_down_cycle` — upgrade head from empty disposable migration DB (0001–0006), downgrade base, upgrade head again; PASS.
- `npm run lint` (repo root) — EXIT 0.
- `npx prettier --check app lib tests` (`apps/web`) — EXIT 0 after formatting the three reported files.
- `npx tsc --noEmit` (`apps/web`) — EXIT 0.
- `npm run build -- --webpack` (`apps/web`, escalated to allow Next worker processes) — EXIT 0, production build compiled and generated all pages. Default Turbopack build is unavailable because the Windows native SWC binding is missing.
- `npm test` (`apps/web`) — EXIT 0, **20 passed (2.0m)**. Used `E2E_REUSE_API=1` with the isolated API/worker and E2E DB; temporarily changed Playwright webServer to start the successfully built Webpack bundle without rebuilding, then restored `playwright.config.ts`.

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

## 2026-10-14 - P5-03 inbox UI and operator thread

Added the tenant inbox and conversation thread screens. The inbox exposes status, mode, channel, member/unassigned, tag, unread, and full-text filters; unread/assignment counts; live updates through the existing SSE stream; loading, empty, and error states. The thread renders visitor, AI, agent, and system events with citations, visitor feedback, and answer/handoff indicators, and offers editor-gated takeover, return-to-AI, resolve, assign, reply, tags, and read state. Internal notes are separately labeled system events and are audited; the widget polling regression assertion confirms notes do not reach visitors. Added Inbox to the shared app navigation.

Verification (exact commands and outcomes):
- `docker exec p5-01-e2e-api sh -lc 'ruff check . && ruff format --check . && mypy && pytest -q'` - EXIT 0: 225 passed, 1 existing Starlette/httpx deprecation warning (run before the final note-visibility assertion).
- `docker exec p5-01-e2e-api sh -lc 'ruff check app/inbox/router.py tests/test_handoff.py && ruff format --check app/inbox/router.py tests/test_handoff.py && pytest -q tests/test_handoff.py'` - EXIT 0: 4 passed, 1 existing Starlette/httpx deprecation warning; this includes note authorization, audit, visitor-polling exclusion, and inbox feedback display.\n- `docker exec p5-01-e2e-api sh -lc 'ruff check app/inbox/router.py tests/test_handoff.py && ruff format --check app/inbox/router.py tests/test_handoff.py && mypy app/inbox/router.py && pytest -q tests/test_handoff.py'` - EXIT 0: Ruff/mypy passed; 4 passed, 1 existing Starlette/httpx deprecation warning.
- `npm run typecheck` (`apps/web`) - EXIT 0.
- `npm run lint` (`apps/web`) - EXIT 0.
- `npx prettier --check app/app/'[tenant]'/inbox/page.tsx app/app/'[tenant]'/inbox/'[conversation]'/page.tsx lib/api.ts lib/app-header.tsx tests/conversations.spec.ts` (`apps/web`) - EXIT 0.
- `npm run build -- --webpack` (`apps/web`) - EXIT 0; Webpack production build completed using Next's WASM SWC fallback.
- `$env:E2E_REUSE_API='1'; npx playwright test tests/conversations.spec.ts -g 'inbox agent takes over'` (`apps/web`) - EXIT 1; latest attempt timed out at 180 s waiting for the organization `Name` field before the visitor flow. Earlier retries encountered duplicate sample-widget frames and an unauthenticated APIRequestContext 404. The requested end-to-end journey is added but is NOT verified.

The E2E failure occurs before the inbox interaction and no successful P5-03 browser journey is claimed. No `.env` edits, external services, deployments, or paid model calls.

## 2026-10-14 - P5-05 follow-ups and analytics; P5-03 final verification attempt

P5-05 implementation adds durable website follow-up scheduling/cancellation, a worker queue job, one-time display on the visitor's next widget history read, and tenant-scoped measured handoff analytics. No sentiment model job or cost cap was added: per owner direction, sentiment classification/cost caps are deferred to P7; P5 analytics only aggregates stored sentiment values.

P5-05 evidence and exact outcomes:
- Earlier focused disposable-container run: `pytest -q tests/test_followups_analytics.py` - EXIT 0, 2 passed, 1 existing Starlette/httpx deprecation warning.
- Current local `mypy` - EXIT 0, 134 source files. `ruff check` and `ruff format --check` - EXIT 0 after three import/style fixes.
- `npm.cmd run lint --workspace apps/web` - EXIT 0. `npm.cmd run typecheck --workspace apps/web` - EXIT 0. Prettier check on P5-05 and inbox files - EXIT 0.
- `npm.cmd run build --workspace apps/web` - EXIT 1: Turbopack unsupported with the available Windows WASM-only SWC. `npm.cmd run build --workspace apps/web -- --webpack` - EXIT 1: Next.js build failed with `spawn EPERM`.
- Current focused local `pytest -q tests/test_followups_analytics.py --basetemp=...` - EXIT 1, both test setups errored when knowledge fixtures attempted to write to configured local storage (`The upload could not be stored`, INTERNAL_ERROR). Full local `pytest -q` - EXIT 1: 106 passed, 5 failed, 118 errors; the local Windows run also hit denied cache/temp and knowledge storage paths. Five failures are in existing inbox listing tests. The earlier focused disposable-container pass remains valid; this later local full-suite run is not a pass.
- Follow-up Playwright browser journey failed earlier with HTTP 409 because the E2E bot was activated but had no published knowledge revision; production availability validation was not changed.

P5-03 last-run evidence and exact outcomes:
- Updated `apps/web/tests/conversations.spec.ts` to log registration HTTP status, assert 201, use unique lead emails, scope the widget to the first frame, and keep dashboard API calls on `page.request` (the authenticated browser context, with CSRF on writes).
- Fresh disposable DB `rate_limit_counters` query after the browser attempt returned `(total=0, registration_buckets=0, peak_count=0)`, so the suspected Postgres rate limiter was not hit in that DB. No production limit was weakened.
- `npm.cmd test --workspace apps/web -- --reporter=line` - EXIT 1 before tests launched: Playwright process spawn failed with `EPERM`. No successful P5-03 E2E is claimed.
- `apps/web/playwright.config.ts` remains temporarily set to start the existing build without rebuilding; restore it to `npm run build && npm run start -- --port 3100` before any later Playwright run.

The P5-03 E2E checklist remains unticked. P5-05 checklist lines remain open because the full suite/browser evidence did not complete and sentiment is carried to P7. No owner sign-off is ticked. No `.env` or key was read, printed, or logged; the E2E harness retains `CHAT_STUB_MODEL=1`.

## 2026-10-14 — P5 close attempt and verification gate

The inbox listing failures recorded by the earlier Windows run were investigated in a clean Linux API container. No failure reproduced there. The five inbox-list tests passed against a fresh fixture-created `_test` database, and the full API suite passed. Added a cross-feature regression assertion that a follow-up delivered from the visitor history is listed once as the inbox's latest message. `apps/web/playwright.config.ts` was verified restored to `npm run build && npm run start -- --port 3100`.

Exact commands and outcomes:
- `docker run --rm --name p5-close-inbox --network saas-chats-ai-dev_default -e DATABASE_URL=<temporary disposable PostgreSQL URL; password redacted> -e STORAGE_ROOT=/tmp/p5-test-storage -v "${PWD}:/workspace" -w /workspace/apps/api saas-chats-ai-p5-close-checks sh -lc 'pytest -q tests/test_inbox_list.py --tb=short'` — EXIT 0, `5 passed, 1 warning in 5.92s` (Starlette/httpx deprecation).
- `docker run --rm --name p5-close-api-full --network saas-chats-ai-dev_default -e DATABASE_URL=<temporary disposable PostgreSQL URL; password redacted> -e STORAGE_ROOT=/tmp/p5-test-storage -v "${PWD}:/workspace" -w /workspace/apps/api saas-chats-ai-p5-close-checks sh -lc 'ruff check . && ruff format --check . && mypy && pytest -q'` — EXIT 0; Ruff passed; 138 files formatted; mypy passed for 134 source files; `228 passed, 1 warning in 117.02s`.
- `docker run --rm --name p5-close-regression --network saas-chats-ai-dev_default -e DATABASE_URL=<temporary disposable PostgreSQL URL; password redacted> -e STORAGE_ROOT=/tmp/p5-test-storage -v "${PWD}:/workspace" -w /workspace/apps/api saas-chats-ai-p5-close-checks sh -lc 'pytest -q tests/test_inbox_list.py tests/test_followups_analytics.py --tb=short'` — EXIT 0, `7 passed, 1 warning in 8.54s`.
- `npm.cmd run lint --workspace apps/web` — EXIT 0.
- `npx.cmd prettier --check app lib tests` (from `apps/web`) — EXIT 0.
- `npm.cmd run typecheck --workspace apps/web` — EXIT 0; Next used WASM SWC fallback.
- `npm.cmd run format:check` — EXIT 1; repository-wide Prettier reports existing `package.json` formatting. The web-only formatting check passed.
- `npm.cmd run build --workspace apps/web -- --webpack` — EXIT 1 before build completion: Windows `spawn EPERM` during Next compilation.
- With `DATABASE_URL` set to the disposable base DB, `STORAGE_ROOT` set under the workspace, and `CHAT_STUB_MODEL=1`, `npm.cmd test --workspace apps/web -- --reporter=line` — EXIT 1 before browser startup: Playwright `spawn EPERM`.

Gate status: **STOP before Part 2.** The full Playwright suite, including the P5-03 handoff journey, remains unverified. The owner must run the PowerShell command block in `implementation/PHASE-05/PHASE-REPORT.md` from an unrestricted terminal. P5-03/P5-05 and phase owner sign-off remain unticked. The owner decision moving sentiment classification/cost caps to P7-02 is recorded in `DECISIONS.md`; P5 analytics shows “Sentiment not measured yet” when the aggregate is empty. No `.env` or API key value was read, printed, or logged; temporary database credentials are omitted here.

## 2026-10-14 — P5 owner Playwright failures corrected

Owner-reported full browser run: 21 passed, 3 failed. Applied fixes for the three reported failures: the inbox header exposes `data-testid="inbox-status"` with human-readable state; the follow-up journey now shares the bot setup that ingests and publishes knowledge before opening a widget session; platform staff promotion uses the exact `E2E_DATABASE_URL` exported by global setup. The unanswered-twice visitor copy currently uses the same orders/accounts/payments message as other handoff reasons; this is documented as a docs/14 §15 copy limitation.

Removed `.env` reads from both Playwright and API test setup. Playwright now requires `DATABASE_URL` explicitly, exports the derived URL to `E2E_DATABASE_URL`, and the API pytest fixture requires `TEST_DATABASE_URL` or `DATABASE_URL`. A targeted source search of `apps/api/tests` and `apps/web/tests` found no remaining `.env` file reads. No `.env` file or key was opened or printed.

Verification (commands and exact outcomes):
- `npm.cmd run lint --workspace apps/web` — EXIT 0.
- `npx.cmd prettier --check app lib tests` (from `apps/web`) — EXIT 0, all matched files formatted.
- `npm.cmd run typecheck --workspace apps/web` — EXIT 0, Next route types generated and TypeScript passed.
- `docker run --rm --name p5-fix-api --network saas-chats-ai-dev_default -e DATABASE_URL=<temporary disposable PostgreSQL URL; password omitted> -e STORAGE_ROOT=/tmp/p5-fix-storage -v "${PWD}:/workspace" -w /workspace/apps/api saas-chats-ai-p5-close-checks sh -lc 'ruff check . && ruff format --check . && mypy && pytest -q'` — EXIT 0; Ruff passed; 138 files formatted; mypy passed for 134 source files; `228 passed, 1 warning in 126.76s` (Starlette/httpx deprecation). The fixture created only `*_test` databases.
- Full Playwright rerun after these changes: NOT RUN. The owner will rerun it using the PowerShell command in `implementation/PHASE-05/PHASE-REPORT.md`, with an explicitly entered disposable `DATABASE_URL` and `CHAT_STUB_MODEL=1`.

## 2026-10-14 - Inbox handoff locator and mode indicator

Inspected the owner's saved Playwright artifact at `apps/web/test-results/conversations-inbox-agent--b6981-plies-then-returns-it-to-AI-chromium/error-context.md`. The rendered conversation controls show `website · Open · Human mode`, followed by `Return to AI`; the thread and `Reply and notes` region are present. The Reply and Internal note textboxes have those accessible names. Before a value is entered, `Send reply` and `Add note` are correctly disabled. The failure occurred because the mode text shared a combined inline element with the channel and status, so exact text matching could not find an independent `Human mode` node.

Added `data-testid="inbox-mode"` to the mode indicator and asserted the mode and status after takeover and return to AI. Reviewed the full journey against the page markup: exact textbox and button locators match; the widget uses `widget-ai-msg` for all non-visitor turns, so the visitor assertion now filters for the agent's exact reply; after returning to AI, the test waits for one new assistant message. The visitor-visible agent reply and the post-return assistant response assertions remain active. No Playwright rerun was performed in this session; the saved owner artifact is the rendered-page evidence.

Exact verification commands and outcomes:
- `npm.cmd run lint --workspace apps/web` - EXIT 0 (previous locator-fix turn) and EXIT 0 (this turn).
- `npm.cmd run typecheck --workspace apps/web` - EXIT 0 (previous locator-fix turn) and EXIT 0; Next route types generated and TypeScript passed (this turn).
- `npx.cmd prettier --check app lib tests` (from `apps/web`) - EXIT 0 (previous locator-fix turn) and EXIT 0; all matched files use Prettier style (this turn).
- `npx.cmd prettier --write 'app/app/[tenant]/inbox/[conversation]/page.tsx' tests/conversations.spec.ts` (from `apps/web`) - EXIT 0; page formatted, test unchanged.
- `docker version --format '{{.Server.Version}}'` - unavailable; permission denied connecting to `npipe:////./pipe/dockerDesktopLinuxEngine`. No local Linux-container/browser rerun was possible.
- No `.env` or key was read.

## 2026-10-14 — P5 browser gate deferred; bounded widget/API check

P5 browser gate open: handoff journey widget step; widget.spec:146 flaky ECONNRESET once; 22/24

- The existing Linux API regression test `apps/api/tests/test_handoff.py::test_handoff_state_cycle_viewer_tenant_and_widget_scope` creates an agent reply in human mode, GETs `/api/public/v1/sessions/{session_id}/messages` with that session's capability token, asserts the agent message ID/text is present, and asserts internal notes are absent. This covers the requested API-level behavior.
- `apps/web/app/widget/frame/page.tsx` restores session history and polls the same endpoint; every non-visitor turn renders with `data-testid="widget-ai-msg"`. `conversations.spec.ts` filters that element by the agent's exact text, so the locator matches the renderer; no product bug or locator correction was indicated by code inspection.
- Linux container rerun could not be performed: `docker version --format '{{.Server.Version}}'` exited 1 with permission denied connecting to `npipe:////./pipe/dockerDesktopLinuxEngine`. No test result is claimed for this turn.
- Owner deferred the browser gate. P5-03, both P5-05 items, and phase sign-off remain unticked. Execution plan is P5 → all P7-01..P7-05 → P6. Full green Playwright is mandatory in P7-05 and before P6.
- No `.env` was read.

## 2026-10-14 — P7 scope correction and P7-01

P7 scope is corrected across `implementation/MASTER-ROADMAP.md`, `implementation/AGENT-PROMPTS.md`, `implementation/PHASE-CHECKLISTS.md`, `docs/11-PLATFORM-ADMIN.md`, `docs/18-EXPECTED-BEHAVIOUR.md`, and `README_START_HERE.md`: P7-01 admin operations, P7-02 quotas plus sentiment job, P7-03 self-service signup, P7-04 export/delete plus audit, and P7-05 release readiness all precede P6. Only Many-dependent channel integration/operations are in P6. No sign-off was ticked.

P7-01 implemented: plan labels persist on tenants; staff can inspect job health, retry/cancel jobs with required reason and actor audit, assign plans with a reason/audit, pause bots with a reason/audit, read measured aggregate/per-client usage analytics, search audit events, and use a new operations UI. AI cost is intentionally not reported: the current model does not retain provider token usage or rate inputs, so a numeric estimate would be fabricated. Many delivery and connection health remain P6-specific.

Exact checks and outcomes:
- `python -m pytest -q apps/api/tests/test_platform_ops.py --tb=short` — EXIT 1, Python did not have pytest installed.
- `.venv\Scripts\python.exe -m pytest -q apps/api/tests/test_platform_ops.py --tb=short` — EXIT 1, 4 setup errors because no explicit `DATABASE_URL`/`TEST_DATABASE_URL` was supplied; no `.env` was read.
- Ruff check and format check on the six changed API source/test/migration files — EXIT 0. Strict mypy on router, model, provisioning service, and P7-01 tests — EXIT 0 (4 sources).
- `npm run lint --workspace apps/web` — EXIT 0; Prettier check on touched web files — EXIT 0; `npm run typecheck --workspace apps/web` — EXIT 0.
- Database migration upgrade/downgrade, API integration tests, and browser UI remain unverified until an explicit disposable test DB and browser-capable environment are available. No deploy. No `.env` was read.

## 2026-10-14 — P7-01 commit and known issue inventory

Built: Committed P7-01 migration, platform API/service changes, operations UI, and owner test fixes as `58ed96d`; created the OPEN issue inventory.
Tested: Owner verified `test_platform_ops.py` — 4 passed on a disposable DB (reported by owner; not rerun here).
Unverified: P7-01 operations UI browser check remains unverified; P7-02 blocked because approved docs specify no quota/cost-cap values.

## 2026-10-14 — P7-02 quotas and sentiment queue

Built: Central PLACEHOLDER plan table, tenant scoped counters/enforcement, 80% warnings, reason-audited staff overrides, measured provider token recording, friendly widget quota response, and resolved-conversation sentiment jobs.
Tested: `python -m compileall -q app/quotas app/knowledge/ingest.py app/knowledge/service.py app/tenants/service.py app/platform/router.py app/widget/service.py app/chat/providers.py app/chat/conversations.py app/inbox/router.py` — EXIT 0; web lint/typecheck/Prettier — EXIT 0.
Unverified: `python -m pytest -q tests/test_quotas.py tests/test_platform_ops.py --tb=short` — Python has no pytest installed. Owner command (run from `apps/api`) after installing project dev dependencies and setting a disposable plain URL: `$env:TEST_DATABASE_URL='postgresql://<user>:<password>@<host>/<base_db>'; python -m pytest -q tests/test_quotas.py tests/test_platform_ops.py --tb=short`. Ruff/mypy unavailable in that Python environment; no browser suite run.

## 2026-10-14 — P7-03 self-service signup

Built: Registration now creates a Free PLACEHOLDER tenant, direct owner membership, and first bot through the shared ProvisioningService; deterministic per-user idempotency handles concurrent retries.
Tested: Python compileall — EXIT 0; web lint, typecheck, and Prettier — EXIT 0.
Unverified: `python -m pytest -q tests/test_self_service_signup.py --tb=short` — Python has no pytest installed. Owner command (run from `apps/api`) with a disposable plain URL: `$env:TEST_DATABASE_URL='postgresql://<user>:<password>@<host>/<base_db>'; python -m pytest -q tests/test_self_service_signup.py --tb=short`.

## 2026-10-14 — P7-04 tenant data and audit review

Built: Added admin-only JSON export (including raw uploaded source bytes, parsed knowledge, contacts, identities, conversations, messages, usage, and audit), owner-only reason/confirmation tenant deletion, tenant audit search, and the data screen.
Tested: Python compileall — EXIT 0; web lint, typecheck, and Prettier — EXIT 0.
Unverified: `python -m pytest -q tests/test_tenant_data.py --tb=short` — Python has no pytest installed. Owner command (run from `apps/api`) with a disposable plain URL: `$env:TEST_DATABASE_URL='postgresql://<user>:<password>@<host>/<base_db>'; python -m pytest -q tests/test_tenant_data.py --tb=short`. Local storage cleanup remains best-effort on OS unlink errors (see KNOWN-ISSUES.md).

## 2026-10-14 — P2 ingestion hardening carryovers

Built: Replaced interruptible-thread parser timeout with a spawned subprocess that is terminated at the wall-clock limit; added timeout and chunked multipart upload regressions; routed knowledge/provisioning/data file access through the `Storage` factory; fixed concurrent signup error import and typed measured-token extraction; added `expire_all()` before DB assertions reading API-updated rows.
Tested: Ruff check and format check — EXIT 0; strict mypy on six affected API modules — EXIT 0; `python -m compileall -q` on affected app/test modules — EXIT 0.
Unverified: the root-invoked API pytest command could not initialize because no disposable DB URL is configured. Owner command (run from `apps/api`): `$env:TEST_DATABASE_URL='postgresql://<user>:<password>@<host>/<base_db>'; python -m pytest -q tests/test_knowledge_parsers.py tests/test_knowledge_uploads.py tests/test_quotas.py tests/test_platform_ops.py --tb=short`.

## 2026-10-14 — P7-05 release readiness review package

Built: Added draft runbook, backup/restore procedure, monitoring/alert definitions, security review record, and ADR-007 hosting options; all unresolved choices and verification gaps are explicit.
Tested: Documentation cross-checked against open ADR-007, P7 checklist, current Storage interface, and P6 channel boundary; no deploy or database restore was performed.
Unverified: Disposable backup/restore drill, independent security review, production alert delivery, and full Playwright run remain open. Full suite owner command after ADR-007/environment review: `npm.cmd test --workspace apps/web`; full API owner command (run from `apps/api`) requires a disposable plain URL: `$env:TEST_DATABASE_URL='postgresql://<user>:<password>@<host>/<base_db>'; python -m pytest -q --tb=short`. Existing browser failures were not chased, and no phase sign-off was ticked.


## 2026-10-15 — UI redesign characterization baseline

Command: `npm.cmd run test --workspace apps/web -- ui-characterization.spec.ts` with isolated loopback PostgreSQL on 55439, disposable `ui_redesign_test`, API on 8019 and offline model. Result: 5 passed, 1 failed (1.5m). Owner deletion validation, data-role presentation, platform operations, client mutation payloads and inbox viewer matrix passed. Widget 429 verbatim assertion failed: existing UI discards server text and substitutes a local fallback. The assertion remains exact; a frontend-only prerequisite fix follows in a separate commit. No redesign code changed before this baseline. An initial root npm argument-forwarding attempt failed with spawn EPERM; corrected workspace invocation used approved process permissions. No .env or credentials read.

## 2026-10-15 — UI prerequisite: preserve widget server errors

Frontend-only correction retains server message strings for session/message failures and lead errors; error codes still control existing behavior. Sandbox, CSP, postMessage and API contracts unchanged. Failed-spec-only command: `npm.cmd run test --workspace apps/web -- ui-characterization.spec.ts -g 'widget 429'` on disposable test instance: 1 passed (57.2s). Full gate sequence deferred to end per latest run policy. Characterization assertions were not weakened. The initial baseline could not be wholly green because the required verbatim behavior was already broken; recorded failing test separately before correction.

## 2026-10-15 — UI S1 tokens, theme and navigation

Shared semantic tokens, system-default viewer-local theme, responsive sidebar/drawer/top bar, workspace context, separate platform accent and navigation-only keyboard palette. No dependencies, API contract or platform guard changes. New presentation tests written, execution deferred. `npm.cmd run typecheck`: exit 0; `npm.cmd run lint`: exit 0. No stage build or Playwright run. All original routes/destinations retained; Overview navigation now targets the approved tenant root (implemented S2). Screenshots and full gates deferred to final sequence.

## 2026-10-15 — UI S2 auth and tenant Overview

Added read-only `/app/[tenant]` Overview using existing endpoints only; separate Bots destination remains unchanged. Counts, recent rows, quota meters and a first-current-bot checklist use returned data. Installation detection omitted. Auth/picker/landing/invitation presentation, show/hide password, skeleton/error/empty/shared confirmation surfaces added; auth/provisioning logic unchanged. `npm.cmd run typecheck`: exit 0; `npm.cmd run lint`: exit 0. Added read-only-route test; all new presentation tests await final browser gate. Zero dependencies. No stage build/Playwright.

## 2026-10-15 — UI S3 bots and knowledge

Bot tables/forms retained with archive confirmation dialogs, human status labels/raw attributes, clearer bot-tab purposes, knowledge source/job/revision cards and true indeterminate ingestion progress. No simulated percentage or ETA. Existing tests now assert raw status attributes and explicitly confirm archive; all assertions retained. `npm.cmd run typecheck`: exit 0; `npm.cmd run lint`: exit 0. No stage build/Playwright. Zero dependencies or contract changes. Screenshot/full browser verification deferred.

## 2026-10-15 — UI S4 inbox and conversations

Shared inbox list on existing list/detail routes, desktop split pane/mobile stacked navigation, explicit filter layout/removal chips, contact lookup through existing contacts endpoint, unread/snippet/status/channel/time rows, chat bubbles and expandable returned citations. Existing stream and mutation logic retained; raw mode/status remain available. New Arabic/unread/filter test written. Initial lint found an unused import; corrected. Final `npm.cmd run typecheck`: exit 0; `npm.cmd run lint`: exit 0. No stage build/Playwright. No dependencies/backend changes.

## 2026-10-15 — UI S5 people, tenant governance and platform

Restyled contacts/profile/follow-ups, team, handoff analytics, tenant data/audit and platform clients/detail/operations. Tenant deletion keeps exact-name/reason guards and adds a cancelable final dialog; contact erasure explicitly preserves the existing optional message-erasure payload. Server guards/permissions unchanged. Characterization specs cover sensitive current behavior. `npm.cmd run typecheck`: exit 0; `npm.cmd run lint`: exit 0. No stage build/Playwright. Zero dependencies. Stored-sentiment empty state and PLACEHOLDER disclosures retained.

## 2026-10-15 — UI S6 widget and sample

Widget/frame/launcher/lead/error/handoff/typing surfaces restyled with canonical tokens; sample polished. Standalone loader token definitions are generated by `node packages/widget/scripts/sync-loader.mjs` from tokens.css; both copies byte-identical. Config-driven brand gets contrast-aware ink. Server messages remain verbatim (including configuration/message/session/lead errors when supplied). Initial sandbox/origin line-comparison failed on Prettier-only line wrapping/trailing commas; original security-sensitive formatting restored in S7 and exact comparison passed; CSP/proxy files unchanged. `npm.cmd run typecheck`: exit 0; `npm.cmd run lint`: exit 0. No stage build/Playwright. No dependencies or API config fields added.

## 2026-10-15 — UI S7 responsive, RTL and verification preparation

Added logical spacing, self-directed user text, palette combobox/listbox semantics, mobile/contrast refinements, tenant-deletion cancellation assertion and screenshot harness (26 routes × 2 themes × 2 viewports). Manual test updated only for requested commands/labels/flows and redesigned UI checks. Seed range already contained valid UTF-8 and no `runon` occurrence existed in the current file; those replacements were unnecessary. Initial S6 boundary comparison was a formatting-only false mismatch, now corrected and verified against baseline. `npm.cmd run typecheck`: exit 0; `npm.cmd run lint`: exit 0; `git diff --check`: exit 0. Source count: 35 browser tests (all original 25 retained). No stage browser/build run. Final sequential gates and screenshot execution follow.
