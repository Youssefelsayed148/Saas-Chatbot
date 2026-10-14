# P4 implementation audit

Date: 2026-10-14 · Branch: `feat/p1-01-foundation`

This audit checks the present worktree. PASS means the cited source or runtime evidence was checked; UNVERIFIED means the requested evidence could not be produced. No FAIL was confirmed. P5 starts only after the P4 verification recorded below; this does not sign off P4.

## A1 — Fresh verification

| Item | Result | Evidence |
|---|---|---|
| Ruff lint, format, strict mypy, full pytest (expected 216) | PASS | Ran the current worktree in `saas-chats-ai-api-checks:p4` against the local Postgres service, with its source mounted at `/workspace` and `DATABASE_URL` runtime-derived from the service environment. Output: `All checks passed!`; `118 files already formatted`; `Success: no issues found in 114 source files`; `216 passed, 1 warning in 89.08s`. The only warning is Starlette's `httpx` TestClient deprecation. |
| Web lint | PASS | `npm run lint` from repository root exited 0 (`eslint . --max-warnings 0`). |
| Web format | PASS after correction | Initial `npx prettier --check app lib tests` from `apps/web` identified three files. Ran `npx prettier --write 'app/platform/clients/[clientId]/page.tsx' app/platform/page.tsx lib/api.ts`; reran the check, which reported all matched files use Prettier style. |
| Web typecheck | PASS | `npx tsc --noEmit` from `apps/web` exited 0. `npm run typecheck` could not initialize Next SWC because its cache path under the user profile is not writable in this sandbox; direct TypeScript check passed against the generated route types. |
| Full Playwright suite (expected 20) | PASS | `npm run build -- --webpack` succeeded. Then `npm test` from `apps/web` ran against the real API and worker containers on the isolated E2E database: `20 passed (2.0m)`. The Playwright config's webServer command was temporarily changed to start the already-built bundle, then restored. The normal Turbopack build path is unavailable on this Windows install because its native SWC binding is missing. |
| Alembic revisions 0001–0006 up and down | PASS | Full pytest ran `tests/test_migrations.py::test_migrations_up_down_cycle`, which upgraded the empty disposable DB to head (0001–0006), downgraded to base, then upgraded to head again. |

## A2 — P4-00 carry-overs

| Item | Result | Evidence |
|---|---|---|
| Cross-script translation, including first message and fake model tests | PASS | `apps/api/app/chat/service.py:116`; `apps/api/tests/test_cross_script.py:76,108,131` cover first-message translate-once, provider-failure fallback, and same-language no-op. Execution in this audit is unverified under A1. |
| Production startup refusal with stub model | PASS | `apps/api/app/core/config.py:93`; `apps/api/tests/test_startup_guard.py:22,36`. Execution in this audit is unverified under A1. |
| Added evaluation cases, including injection inside uploaded documents | PASS | `implementation/PHASE-04/P4-00-REPORT.md` records 25 cases and document-borne injection cases; `implementation/PHASE-03/EVAL-REPORT.md` records stub results. Live rerun is UNVERIFIED here. |
| Real-key evaluation rerun | UNVERIFIED (no key) | No key was provided per `implementation/PHASE-03/EVAL-REPORT.md`; no paid API call was attempted. The prompt permits recording the honest no-key result. |

## A3 — Public widget surface

| Item | Result | Evidence |
|---|---|---|
| Capability token lifetime, hash-at-rest, session binding | PASS | `apps/api/app/widget/service.py:56-64,198-199`; `apps/api/tests/test_widget_public.py:166,192,219`. |
| A session reads only its own messages | PASS | `apps/api/app/widget/router.py:192-216`; `apps/api/app/widget/service.py:290-322`; tests `test_widget_public.py:219` and `:492`. |
| Allowed-domain check is not authentication | PASS | `apps/api/app/widget/service.py:104-129`; capability check is independently required in `router.py:112-117`; defence-signal test `test_widget_public.py:292`. |
| Origin/CORS behavior | PASS (static contract review) | `apps/api/app/main.py:17-34` restricts dashboard credentialed CORS to local origins; the widget iframe calls its same-origin public API. Browser verification is UNVERIFIED under A1. |
| Postgres rate limits and login limiter migration | PASS (static contract review) | Atomic DB upsert in `apps/api/app/core/ratelimit.py:16-51`; login commits increments before auth result in `apps/api/app/auth/router.py:32-50`; widget rate limits in `widget/service.py:167-176,254-268`; tests `test_auth.py:257,277`, `test_widget_public.py:324,337`. Restart/multi-process behavior was not exercised in this audit. |
| Locator safe fields only | PASS | `apps/api/app/widget/service.py:131-164`; `apps/api/tests/test_widget_public.py:125`. |
| Paused, not-ready, expired handling | PASS | `apps/api/app/widget/service.py:56-98`; `apps/api/tests/test_widget_public.py:192,251`. |
| Iframe sandbox attributes | PASS (source review) | `packages/widget/src/loader.js` creates the iframe with the documented sandbox flags; browser recheck is UNVERIFIED under A1. |
| Scoped headers and dashboard/widget frame policy | PASS (prior evidence only) | `apps/web/next.config.ts` has dashboard `frame-ancestors 'none'` and a later widget-specific rule; prior curl/E2E evidence is cited in `implementation/PHASE-04/PHASE-REPORT.md`. Not rerun here. |
| HTML knowledge text and citation URLs | PASS (source review) | React renders message text as text in `apps/web/app/widget/frame/page.tsx`; `apps/api/app/knowledge/front_matter.py` restricts source URLs to HTTP(S), and `test_widget_appearance.py:55` rejects `javascript:` avatar URLs. No dedicated widget `javascript:` citation regression test was found; dynamic rendering verification is UNVERIFIED. |
| PII/tokens in logs | PASS (source review) | No logging or `print` calls found under `apps/api/app/widget`, `platform`, `provisioning`, or `analytics`; this does not substitute for runtime log inspection. |

## A4 — Leads and conversations

| Item | Result | Evidence |
|---|---|---|
| Consent enforced server-side | PASS | `apps/api/app/widget/router.py:239-272`; `apps/api/tests/test_widget_leads.py:58`. |
| Contact create/update idempotency | PASS | `apps/api/app/widget/service.py:335-455`; tests `test_widget_leads.py:77,130,157`. |
| Retention setting and purge delete data | PASS (source/test coverage) | `apps/api/app/chat/conversations.py:372-407`; `apps/api/tests/test_conversations_view.py:170` and `test_conversations.py:311,325`. Execution in this audit is unverified under A1. |
| Playground excluded from operator conversations and analytics | PASS | Conversation filter `apps/api/app/conversations/router.py:51-65,101-115`; analytics aggregation filters in `apps/api/app/analytics/service.py`; tests `test_conversations_view.py:97` and `test_analytics.py:131`. |

## A5 — Analytics

| Item | Result | Evidence |
|---|---|---|
| Three headline numbers trace to stored events/SQL | PASS (source review) | `apps/api/app/analytics/service.py:38-157` aggregates conversation and usage-event rows; endpoint mapping is in `apps/api/app/analytics/router.py:32-45`. Existing data-backed tests: `apps/api/tests/test_analytics.py:80,164`. No seeded UI-to-SQL trace was rerun here. |
| No placeholder values; tenant/bot scoping | PASS (source/test coverage) | Services filter by tenant and bot; tests `test_analytics.py:164,192` cover bot scoping/viewer read access. Runtime verification unverified under A1. |

## A6 — Admin console

| Item | Result | Evidence |
|---|---|---|
| `/platform` server-side staff authorization | PASS (source/test coverage) | `apps/api/app/platform/staff.py:21-40`; server-rendered guard in `apps/web/app/platform/layout.tsx`; `apps/api/tests/test_platform.py:50,72`. |
| Staff flag separate from tenant roles; no self-promotion path | PASS (source/test coverage) | User creation defaults `is_platform_staff=False` in `apps/api/app/auth/service.py:61`; staff-only dependency in `platform/staff.py`; test `test_platform.py:72`. No staff-promotion endpoint is registered in `platform/router.py`. |
| Idempotency-Key semantics | PASS (source/test coverage) | `apps/api/app/platform/router.py:262-291`; `apps/api/app/provisioning/service.py:42-102`; tests `test_platform.py:138,166,180`. |
| Owner invite shown once and stored hashed | PASS (source/test coverage) | `apps/api/app/provisioning/service.py:190-214,332`; test `test_platform.py:94`. |
| Audit actor attribution; no impersonation | PASS (source/test coverage) | Provisioning service records actor in audit writes; test `test_platform.py:94`; no impersonation route/UI found in `platform/router.py` and `apps/web/app/platform`. |

## A7 — Tenant and viewer route coverage

| Route family | Result | Evidence |
|---|---|---|
| Public widget config/session/messages/history/feedback | PASS (test coverage) | `apps/api/tests/test_widget_public.py:159,192,219,292,492`; no tenant role applies to these public capability-token routes. |
| Public lead capture | PASS (test coverage) | Consent and idempotency tests plus tenant isolation at `apps/api/tests/test_widget_leads.py:58,130,177`. |
| Bot status/settings writes | PASS (test coverage) | `apps/api/tests/test_bot_status.py:62,89`; bot routes also use shared tenant context and role enforcement. |
| Conversations list/detail/delete | PASS (test coverage) | `apps/api/tests/test_conversations_view.py:117,142`; viewer reads and cannot delete. |
| Analytics read routes and CSV exports | PASS (test coverage) | `apps/api/tests/test_analytics.py:164,192`; all routes use `TenantContextDep` and validate the bot before query. |
| Platform routes | PASS (test coverage) | Global staff-only surface; `apps/api/tests/test_platform.py:50,211` covers non-staff denial and staff tenant detail/404. |
| Full route-by-route rerun | UNVERIFIED | The above is source and test inventory; no endpoint tests ran during this audit because the DB-backed suite could not start. |

## A8 — Pilot-readiness gaps (no deployment)

- ADR-007 remains OPEN: hosting, object storage, retention defaults, and data residency are undecided (`DECISIONS.md`, ADR-007).
- Current uploads and knowledge files use local-disk storage; a public multi-instance pilot needs durable shared object storage and a migration/backup plan (`implementation/PHASE-04/PHASE-REPORT.md`, P2/P4 carried limitations).
- Production gateway must terminate HTTPS, route web/API consistently, set and sanitize forwarded headers (especially `X-Forwarded-For`), and set `PLATFORM_GUARD_ORIGIN`; `apps/api/app/core/ratelimit.py:83-88` trusts the first forwarded IP value.
- Production secrets need a managed secret source and rotation procedure; this audit did not inspect any secret values.
- Backup/restore evidence, monitoring, alerting, and operational runbooks are not yet built (P7-05 scope in `implementation/AGENT-PROMPTS.md`).
- Hosted CI has never run; deployment and a real HTTPS two-site pilot are not verified.

## A9 — Docs and checklist hygiene

| Item | Result | Evidence |
|---|---|---|
| Duplicate P4 checklist rows / duplicate P5 header | PASS (current worktree) | `implementation/PHASE-CHECKLISTS.md` has one P4 row for each ticket item, one P4 phase report/owner line, and one `## P5` header. The worktree diff changes only P4-05/P4-06 evidence rows, adds the two-site evidence row, and updates the report line; no other checklist sections are altered. |
| Duplicate phase report | PASS | `docs/phase4report.md` is now a one-line pointer to `implementation/PHASE-04/PHASE-REPORT.md`. |

## Close-out decision

No code security defect was confirmed by source review. The initial web formatting failure was corrected and the formatting check now passes. The backend suite, migration cycle, and all 20 Playwright tests were freshly verified against disposable test databases. Remaining UNVERIFIED item: the real-provider evaluation, because no key was supplied. This audit contains no open FAIL. P5 may proceed under the user's pasted authorization; the P4 owner sign-off line remains unticked and unchanged.
