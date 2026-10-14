# PHASE P4 REPORT — Widget (the website channel), per-bot dashboard, admin console

Date: 2026-10-13 · Branch: `feat/p1-01-foundation` (local commits only, no push/deploy/paid calls)
Status: P4-00 → P4-06 implemented and locally verified. This report is the evidence base for
`implementation/PHASE-CHECKLISTS.md` §P4. **The phase is NOT signed off** — the owner review
remains (checklist items include the two-sites E2E + phase-owner sign-off line).

## Environment note (recorded honestly)

No Windows venv existed on this machine this run: backend checks ran in the Linux checks
container (`docker build --target checks -f apps/api/Dockerfile -t saas-chats-ai-api-checks:p4 .`,
only the local Compose `db` service up, disposable `_test` databases only). Web checks ran
with Node 24 (Linux build; `@next/swc-linux-x64-gnu` installed `--no-save`, lockfile untouched
except the added `@chatbot/widget` workspace), and Chromium's system libraries were installed
USER-SPACE (`/tmp/opencode/debroot`, extracted `.deb`s — no root) to run Playwright. The
Playwright harness boots the REAL FastAPI + REAL worker + production Next server on
loopback 3000/3100/8000 with `CHAT_STUB_MODEL=1` (dev/test-EVAL only) on a disposable `_test` DB,
matching the P2/P3 discipline. Compose api/web/worker stayed down during E2E (the harness
refuses a foreign server on port 8000 unless forced).

## What was built, per ticket

### P4-00 — P3 carry-overs
1. **Cross-script retrieval**: `retrieve(translate_query=…)` — when the question-language
   pass is empty and the languages differ, exactly ONE ChatModel call translates the QUERY
   into the bot's primary language (failure keeps the raw question); works without history
   (first message: no condense call). Unit tests with a fake model: translate-once+grounded,
   provider-failure fallback, no call when languages match (`tests/test_cross_script.py`).
2. **`environment` setting** (`development|production|test`) +
   `validate_startup_settings` refused to start with `CHAT_STUB_MODEL` + production
   (`tests/test_startup_guard.py`, incl. `create_app` behaviour).
3. **Eval extension**: 25 cases (+3 AR-question/EN-content cross-language through the real
   translate path with a deterministic translation stand-in, +3 unanswerable, +2
   injections whose directive lives INSIDE an uploaded document with `forbidden` phrases;
   poisoned EN/AR corpus pages). Stub-run numbers: grounded 8/8, unanswerable 8/8,
   injection 4/4 (100%), cross-language 3/5 — the 3 new cases pass; the 2 legacy
   bilingual-corpus cases remain the recorded P3 stub-run limitation (AR questions sharing
   tokens with AR content never take the fallback path). **OpenRouter rerun NOT done — no
   key was provided** (checked env + repo `.env`); recorded in
   `implementation/PHASE-03/EVAL-REPORT.md`; the runner supports it behind
   `CHAT_OPENROUTER_API_KEY` so the real numbers can replace the stub-run note.

### P4-01 — Public widget API + visitor sessions + abuse limits
- Migration `0004_widget_public`: `bots.widget_locator` (opaque, unique, NOT a secret,
  assigned at creation), `visitor_sessions` (SHA-256 token hash only; composite FK
  `(tenant_id, bot_id)` → bots), `conversations.session_id` (composite FK), and the
  Postgres-backed `rate_limit_counters` (fixed windows that survive restarts);
  up/down verified (`tests/test_migrations.py`).
- Public endpoints (`/api/public/v1`, no dashboard cookie; authority = the capability
  token, never a caller-supplied tenant id): widget config (safe fields only: branding,
  welcome, opening questions, colour/position/avatar/language/`dir` — internal config like
  support contact/allowed domains/always-include ids never exposed), session creation
  (short-lived token, shown once; `BOT_PAUSED`/`BOT_NOT_READY`/`BOT_DISABLED` states;
  allowed-domain check on the PAGE origin as a defence signal), messages (the SAME P3
  pipeline: grounded answers, citations, needs_human; per-(IP, session) 20/min window;
  daily message cap per bot from real usage events → `QUOTA_EXCEEDED`), thread recovery
  (`GET messages`, retention-aware, `?since=` ready for P5 polling) and widget thumbs
  (idempotent per message+session).
- `app/core/ratelimit.py`: atomic `INSERT … ON CONFLICT` counters. **The P1 in-process
  login limiter was folded into it** (`app/auth/ratelimit.py` deleted; the increment
  commits in its own transaction so FAILED logins still count; same 429 contract).
- Bot lifecycle: `PATCH /bots/{id}` accepts audited `status` transitions (draft→active,
  active↔paused; archive stays DELETE-only) — `tests/test_bot_status.py`.
- Tests: `test_widget_public.py` (14), `test_bot_status.py` (5).

### P4-02 — Widget package (`packages/widget` + `/widget/frame`)
- Loader ES2020 (no build deps) served versioned at `/widget/v1/loader.js`; creates the
  bubble + the sandboxed iframe (`allow-scripts allow-same-origin allow-forms`, documented)
  at `/widget/frame`. postMessage protocol: locator handover, auto-height, brand sync,
  Escape→close. Frame UI covers the docs/09 states (loading/typing/answer+citations/no-
  knowledge/paused/not-ready/quota/rate-limited/network-retry), welcome + opening-chips,
  thumbs per answer, scroll-to-bottom, RTL, keyboard accessibility, localStorage session
  recovery (silent re-auth on 401). The iframe talks to the public API same-origin (no
  CORS, no third-party cookies).
- Scoped CSP: `/widget/:path*` → `frame-ancestors http: https:` (declared AFTER the
  dashboard rule; Next 16 last-wins per header key, verified by live curl + tests) while
  the dashboard keeps `frame-ancestors 'none'` (P2-00).
- E2E: `security-headers.spec.ts` (2), `widget.spec.ts` (2: TWO TEST SITES each embedding
  a DIFFERENT tenant's bot through the real snippet; each answers only from its own
  knowledge). Evidence note: on a loopback-only lab the two "sites" are the sample-page
  helper pages (Chrome's Local Network Access blocks cross-origin script loads into
  127.0.0.1); real customer sites embed cross-origin from public hosts where classic
  `<script src>` needs no CORS. Session/message cross-tenant isolation is asserted at the
  API level (foreign session id/token ⇒ 401).

### P4-03 — Appearance settings + Install page
- Settings: assistant/business info, welcome EN/AR (greeting), opening questions, default
  language/RTL, support contact, colour, position, **avatar (http(s)-only, ≤500 chars)**,
  handoff toggle, allowed domains; bot Activate/Pause in the UI over the audited PATCH
  `status`; widget config exposes the avatar.
- Install tab: the REAL snippet (deployment-aware origin + locator), locator-is-public
  explainer, draft/paused guidance, and the **sample-page helper**
  (`/widget/sample?locator=…`) appending the REAL `<script src="/widget/v1/loader.js"
  data-locator="…">` element (innerHTML scripts never execute — documented).
- E2E `install.spec.ts` (1: draft guidance → activate → snippet → sample-page bubble →
  colour round-trip). API tests `test_widget_appearance.py` (3).

### P4-04 — Conversations view, consent leads, retention
- Dashboard read views: list (playground excluded) + thread with citations; explicit
  deletion (editor+) removes the thread AND its messages. Migration `0005_retention_leads`:
  `tenants.retention_days` (NULL = deployment default, CHECK 1–365); PATCH tenant (admin+,
  audited); the retention purge applies EACH tenant's own window and clears aged rate-limit
  buckets.
- Lead capture `POST /api/public/v1/sessions/{id}/lead`: **CONSENT REQUIRED** (422
  `CONSENT_REQUIRED` otherwise — no contact write ever happens without it); email/phone
  reachable channel required; creates/updates ONE tenant contact (citext email / phone
  match; website contacts refresh their display name), records
  `consent.website {granted_at, text_version}`, binds the session identity + conversation,
  idempotent `lead` usage event.
- Widget lead form (EN/AR consent text + checkbox). UI: conversations list + detail.
- Tests: `test_conversations_view.py` (5), `test_widget_leads.py` (5);
  Playwright `conversations.spec.ts` (1: chat → consent-required error → consent →
  dashboard thread with citations + lead badge).

### P4-05 — Per-bot workspace + measured overview analytics
- Bot workspace shell (`BotWorkspaceNav`): overview, conversations, knowledge, playground,
  settings, install — exactly the tabs that exist today, no placeholders (Inbox/Contacts/
  Channels arrive in P5/P6 per docs/10).
- Measured analytics per docs/14 §9 (SQL over `usage_events` + real conversations; playground
  excluded): summary (messages, conversations, widget opens, engagement rate, avg messages
  per conversation + distribution, unanswered/fallback rate, needs-human/handoffs, avg
  response ms, leads, thumbs), volume per day, top questions, unanswered-questions list,
  leads trend + captured contacts, date range (`from`/`to`, validated), CSV exports
  (`conversations.csv`, `leads.csv`).
- Endpoint guards: member reads (viewers included); wrong tenant/bot 404.
- Tests: `tests/test_analytics.py` (6 — counts, volume/top/unanswered/leads, playground
  exclusion, per-bot scoping + CSVs, role/date validation, window filtering).
- Playwright `overview.spec.ts` (2: shell tabs + measured numbers incl. lead/thumbs, CSV;
  unanswered list shows the unconfirmed question; per-bot scoping — bot B's summary is 0).

### P4-06 — Admin console basics (docs/11, ADR-018)
- Staff guard `app/platform/staff.py`: `users.is_platform_staff` only — SEPARATE from
  tenant roles; non-staff API → 403; the `/platform` LAYOUT guard runs server-side every
  request (cookies → `/api/v1/platform/me`; redirects to /login otherwise; there is no
  client-side shortcut and no impersonation path). `PLATFORM_GUARD_ORIGIN` deployment
  override documents how to point the guard at the API process (default = request host).
- Client list (plan label, status, search/filter, bot/seat counts, messages this month,
  last activity), client detail (bots + published state, failed jobs, members, recent
  audit, usage), durable request views (`GET /onboarding/{id}` + `onboarding.csv`).
- Staff onboarding form → SHARED `ProvisioningService` (docs/12): tenant + owner one-time
  invite link (shown once; token hash stored; NO email provider) + optional bot + optional
  skill-output files stored under generated tenant/bot keys (kind-checked). REQUIRED
  `Idempotency-Key`: replay returns the SAME durable request; payload/actor mismatch = 409;
  double submission creates exactly ONE tenant; failure path records a durable `failed`
  row. Actor attribution audit rows on every step.
- Tests: `tests/test_platform.py` (9: non-staff 403 matrix, staff-flag separation,
  onboarding + invite, double submit = one tenant, payload clash 409, missing key 400,
  optional files, list/detail + 404, tenant isolation readings) + migration 0006 up/down.

## Full-suite evidence (phase verification)

Exact commands (recorded in `PROGRESS.md`):
- Backend (`docker run … saas-chats-ai-api-checks:p4 sh -c "ruff check . && ruff format
  --check . && mypy && pytest"`) — fresh disposable DB, `pytest` collects full suite,
  final counts recorded at the end of this report.
- Web: `npm run lint && npm run typecheck && npx prettier --check app lib tests` then
  `npm test` (Playwright full suite incl. dashboard/knowledge/playground from P1–P3 on the
  real stack, `PLATFORM_GUARD_ORIGIN=http://127.0.0.1:8000` set for the guard).

### Independent audit rerun (2026-10-14)

`implementation/PHASE-04/AUDIT.md` records the A1–A9 review. The fresh backend run against disposable `*_test` databases passed Ruff, format check (118 files), strict mypy (114 sources), and the full suite (**216 passed**, one Starlette/httpx deprecation warning). `tests/test_migrations.py::test_migrations_up_down_cycle` exercised migration 0001–0006 upgrade, downgrade to base, and re-upgrade. Web lint, Prettier, and `npx tsc --noEmit` passed. The full Playwright suite passed (**20 passed**).

The Windows install does not include Next's native SWC binding. Its default Turbopack build failed, so the production bundle was built with `npm run build -- --webpack`; Playwright then started that bundle against the isolated API/worker and E2E database. The temporary Playwright config change that skipped rebuilding was restored after the run. No confirmed P4 FAIL remains. The real-provider eval remains unrun because no key was supplied; no paid call was made. P5 is authorized by the user's pasted prompt, but P4's owner sign-off remains unticked.

## Known limitations / open risks (carried forward)

1. **Real-model eval rerun** still pending owner key (P4-00 above) — the cross-script
   translation path is unit-tested with fakes; the deterministic stub numbers are recorded.
2. Two legacy bilingual cross-language eval cases still fail on the stub run (same-root
   limitation: those questions share content tokens with in-language content or carry
   preposition-prefixed words the AL-variant builder does not split) — real-model rerun
   decides them.
3. The E2E "two sites" use the sample-page helper on one origin (loopback lab constraint:
   Chrome Local Network Access); real cross-origin embeds need no CORS for classic scripts
   (documented in `packages/widget/README.md`).
4. Hosted CI still never run (no push authorization). Windows venv unavailable this run —
   Linux container + Linux Node only (previous phases ran both toolchains).
5. The `/platform` layout self-fetches `/api/v1/platform/me` on the request host;
   `PLATFORM_GUARD_ORIGIN` exists for deployments that prune self-connections. The
   redirect surfaces the guard reason (`guard=status-…`) for diagnosis.
6. Widget conversations = ONE per visitor session (retention purge applies); per-contact
   conversation history binding arrives with P5 CRM (docs/14 §14/§16).
7. **Hosted CI has never run** (no push authorization); local success does not replace hosted CI evidence.
8. **Parser timeout uses a worker thread**: a timed-out parser thread cannot be forcibly killed; limits bound the operation, but a pathological parser may continue consuming worker resources until it exits.
9. **Chunked uploads without `Content-Length`** do not pass through the Next proxy's early body-size guard. The API streaming cap still applies; production gateway limits should also be configured.
10. **Storage is local disk** under the shared app-data volume. This is suitable for the current single-host Compose setup, not a durable multi-host public pilot; object storage and backup/restore remain undecided/unfinished.
