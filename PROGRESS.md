# Execution checkpoint

## 2026-10-26 - stale-test fixes, two bug fixes, production deploy stack (branch fix/stale-tests-and-baseline, from main)

Disposable DB: pgvector container on 127.0.0.1:55462 (`TEST_DATABASE_URL=.../fixrun`, derived `fixrun_test`). Each pytest ran one file at a time. No full-suite rerun, no push, no paid or Meta calls.

Code fixes: (1) `_merge_config` stored `[]` for an empty always_include list instead of clearing it; (2) an aborted streamed turn left the visitor message and inbox event behind because `reserve()` commits the session, now removed explicitly and tenant-scoped (`_discard_unanswered_message`); (3) `scripts/create_platform_staff.py` refused every non-`_dev`/`_demo` database, so no production admin could be created: new production path (ENVIRONMENT=production, PostgreSQL only) with a test; (4) `ingest.py` uses `sys.platform` so mypy passes on Windows.
Stale tests fixed: staff_members (field names now allowed in 422, values must not echo), rag_gate provider chain (3 requests = one per model, no retries), knowledge_hygiene cross-tenant check (platform staff may act on any tenant by design), route matrix (PUT routes, count 90, replace upload), bot_names_migration (tenants has no updated_at), rag_stage0 baseline (`preview` kwarg), utf-8 file read in rag_gate.
Lint: ruff now clean (per-file E501 ignore for tests and old migrations; four app lines wrapped; `ruff format` applied); `mypy` strict: Success, 244 files.

Results (exact, one file each): hygiene 12 passed; bot_names_migration 1; staff_members 28; rag_gate + rag_stage0_baseline 45 (with PYTHONUTF8=1, then the utf-8 read fix); route matrix + rag_gate 37; chat_streaming disconnect test 1 passed (full file earlier: 20 passed, 1 failed = this bug); chat 26; conversations 13; widget_public 17; handoff 5; chat_streaming_unit 34; create_platform_staff 3. playground_parity: still running when committed. NOT run: Playwright (13 known failures untouched), embedding/hybrid/RAG-evaluation files.

Follow-up (same branch): playground_parity `test_messages_of_returns_the_newest_100_in_order` failed in the single-file run. Cause: `append_message` used `datetime.now()` per message; equal timestamps (Windows clock) were tie-broken by random uuid, flipping history order. Fix: created_at is strictly increasing within a conversation. After the fix: playground_parity 8 passed, conversations 13, handoff 5, chat 26, widget_public 17 (one file each).

Retrieval on pgvector 0.8.7 (one file each): embedding_readiness 6, hybrid_retrieval 11, embedding_foundation 17, rag_evaluation 12 (after the UTF-8 fix, commit b0fa06a). Hybrid retrieval was never failing in code; the old failures were a test database without real pgvector.
Playwright (ONLY the 12 failing specs, never the full suite; each first build stopped at the Next.js advisory notice and was retried, Next.js version unchanged): all stale tests, no product bugs. Widget now streams (`/messages/stream`) and polls with `?since=`; specs waited for `/messages` and mocked without the query; UI redesign renamed the membership link ("Open <name>"), moved bot status to `.status-card`, made bots a card list; mocks lacked quota usage keys and job fields (`source_ids`, `max_attempts`, `cancel_requested`); always-include is a controlled checkbox (click then toBeChecked); the staff-only sample page needs a staff session on each host. Result: group-a-operator 2, group-c-polish 1, install 1, overview 2, widget-polling 2, widget-streaming 1, knowledge:199, widget-domain:230, conversations:69 all passed in targeted runs. `widget.spec.ts:285` does not exist in the repo. Web eslint, tsc and prettier on the edited specs: exit 0.

Deploy: `compose.prod.yaml`, `deploy/Caddyfile`, `deploy/backup.sh`, `.env.production.example`, `scripts/deploy.sh`, `DEPLOY.md`. `docker compose config` valid (only 80/443 published); api and web images built; local smoke test with fake keys and no Caddy (project saasprodsmoke, torn down afterwards): db, migrate, staff, api, worker, web all healthy; admin login 200 with Secure cookies; /platform anonymous 307 to login; widget loader 200. Caddy/HTTPS untested until a real domain.

## 2026-10-22 — A2 widget embedding & domain enforcement batch (branch fix/a2-widget-embedding, created from main)

Commits (local only, no push/tag/merge): 5493fbb A2.1 loader host forwarding +
`_host_of` bare-hostname support; 69cd2d0 A2.2 per-bot `frame-ancestors` via
proxy; fbe4b7f A2.3 defaults (hello_default welcome, bottom-right position);
e3f9f19 A2.4 Playwright domain-enforcement spec. All commit messages carry the
required trailer.

Implementation choices:
- A2.1: `packages/widget/src/loader.js` (canonical) was edited and both copies
  regenerated with `node packages/widget/scripts/sync-loader.mjs`; the frame URL
  now carries `host=<location.hostname of the EMBEDDING page>`. The frame page
  (`apps/web/app/widget/frame/page.tsx`) reads `host` from its own query and
  posts it as `page_origin` (API field existed, max 300 kept).
- A2.2: `headers()` in next.config is static and a page cannot set its own
  response headers, so the per-bot value is computed where the pipeline can:
  the existing `apps/web/proxy.ts` was extended with the `/widget/frame` matcher
  and fetches the new locator-addressed endpoint
  `GET /api/public/v1/widgets/{locator}/frame-ancestors` (compiled CSP value
  only; a bot's unknown locator 404s). This is the smallest change: no route
  split, no restructuring of the (client) frame page, no config contract change
  — the endpoint exposes exactly the value the frame HTTP header shows any
  browser anyway. Empty list → permissive `http: https:`; non-empty → listed
  hosts in http+https plus subdomains (matching `origin_allowed` semantics);
  `localhost` gets `:<port-wildcard>` outside production. Unknown locator /
  API outage → falls back to the static permissive rule while the session
  endpoint still denies unlisted page origins. Dashboard CSP untouched, the
  sandbox attribute unchanged, and the security position is unchanged: the
  `host`/`page_origin` value is a spoofable defence signal sent by the page —
  NOT authentication — and `frame-ancestors` is what stops browsers from
  framing the widget on unlisted sites.

Verification environment: Windows venv (`.venv/Scripts/python.exe`, driven from
WSL, as in earlier sessions) and Windows node (`node.exe`, `cmd.exe`).

Commands and outcomes:
- `cmp apps/web/public/widget/v1/loader.js packages/widget/src/loader.js` after
  `node packages/widget/scripts/sync-loader.mjs` → identical, `diff` exit 0;
  both copies gained the same 6 lines (host param + comment).
- `python -m ruff check` on every touched API file per commit — All checks
  passed!; `python -m ruff format --check` on the touched test files, service
  and router — formatted (one PRE-EXISTING formatting drift remains in
  `app/widget/router.py` at the old `ai_message=(...)` block, flagged by
  `--check` on HEAD before this batch too; left untouched per batch scope).
- `python -m mypy --follow-imports=silent app/widget/service.py
  app/widget/router.py` — Success, no issues.
- `cmd.exe /c npm run typecheck` (next typegen + tsc --noEmit), `eslint` on
  `proxy.ts`, the frame page, the settings page and `widget-domain.spec.ts`
  with `--max-warnings 0` — clean.
- `cmd.exe /c npm run build` (Next 16.4.0) — succeeded, Proxy(Middleware)
  compiled; `cmd.exe /c npm run check:public-asset` — OK.
- Header behaviour verified WITHOUT the disposable DB: the web build ran on
  127.0.0.1:3100 against a THROWAWAY stub API (local Python script on
  127.0.0.1:8004, no containers, since the owner's dev API listens on 8000 and
  was left alone; both processes were closed afterwards):
  `/widget/frame?locator=…` → single header
  `content-security-policy: frame-ancestors http://localhost:* https://localhost:* …`;
  `/widget/frame` without locator and with an UNKNOWN locator → falls back to
  `frame-ancestors http: https:`; `/login` keeps `frame-ancestors 'none'`.

NOT verified (blocked, no fabrication):
- Disposable test DB `saas-test-db` on 127.0.0.1:55462 kept refusing/timing out
  connections (psycopg ConnectionTimeout, two runs: 23 errors / 44 errors, ALL
  at session-scoped fixture setup, zero assertion failures). NO pytest and NO
  Playwright run completed in this session. Written-but-unverified tests:
  `tests/test_allowed_domains.py` `test_host_of` cases,
  `tests/test_widget_public.py` bare-hostname + frame-ancestors tests,
  `tests/test_widget_appearance.py` hello_default fallback test, the Playwright
  spec `tests/widget-domain.spec.ts`, and the real end-to-end CSP enforcement
  inside Chrome. Owner reruns:
  `cd apps/api && TEST_DATABASE_URL=postgresql://test:test@127.0.0.1:55462/postgres ENVIRONMENT=test PYTHONUTF8=1 python -m pytest tests/test_allowed_domains.py tests/test_widget_public.py tests/test_widget_appearance.py`
  then `cd apps/web && TEST_DATABASE_URL=… npx playwright test`.
- A2.4 runtime risk tracked for that run: Chrome treats a missing port in a CSP
  host-source as the scheme's default port only, which is why the spec pins the
  ALLOWED site to `localhost` (emitted as `localhost:*` outside production) and
  the DENIED site to 127.0.0.1.
- Known pre-existing behaviour observed but NOT changed (outside batch scope,
  for the owner): `restoreSession` keys the widget session in the frame's own
  localStorage, so a token minted on an allowed site survives a later load
  behind `allow-same-origin` even if the unlisted site's homepage would
  otherwise be denied; with A2.2 that site cannot frame the widget at all, so
  the reuse path is unreachable for foreign sites in browser clients.


## 2026-10-20 — S3 staff Bots (backend/static verification complete)

Branch `feature/staff-bots` initially stacked on S2 `df826b5`, then incorporated
S2's markup follow-up `691382c` and final documentation status `5bbd9cd` by local
rebase. It remains isolated in
`.worktrees/staff-bots`. S2 completed 75 targeted passes, identical full runs
437 passed/1 skipped, and 7 standalone startup-guard passes before S3 began.
No branches were merged or pushed; S1/main/Phase 6 source checkouts are untouched.

Implemented a single `app/bots/factory.py::create_bot_record` for every runtime
API/provisioning bot creation path. It trims/validates the name, locks an active
tenant, enforces the existing bot quota, creates the draft/default config and
public widget locator, and records the caller's audit action in the transaction.
BotService, the existing staff tenant-bot endpoint, the new global endpoint and
ProvisioningService._make_bot delegate to it. The latter is the only change to
ProvisioningService, as approved to reconcile the prompt's single-factory rule
with its instruction to preserve self-service provisioning.

Added staff-only typed global bot list/create with search/organization filter,
tenant-and-bot-scoped source/job/revision summaries, and shared summary rendering
for organization detail. Existing strict update contracts reject organization
changes, verified for both organization_id and tenant_id. Added global Bots UI,
one shared creation form with a locked organization variant, Knowledge/Settings
links, read-only organization text in Settings, and preserved Pause controls.

Removed only staff onboarding POST/UI/client function/unused interface/styles;
historical GET status and CSV remain and are tested. Historical owner/admin
audit labels and fixtures remain because they still describe immutable records.
The old workspace link now targets the real organization creation section.

Regression replacements: staff setup and widget reachability use the real new
organization/user/invitation/bot endpoints. Durable duplicate-submit/conflict,
legacy fingerprint/result translation, and optional historical file staging
exercise the retained service directly, with actual service results/exceptions;
no fake HTTP responses. The retired missing-header HTTP case now verifies 404/405.
Platform browser setup uses organization and shared bot forms plus user/invitation
API calls; search/detail/audit/access/deletion assertions remain. The old durable
request UI assertion is replaced by actual creation feedback; durable behavior
remains covered in service regressions. No existing test was deleted.

Targeted command in apps/api (per-process owner test URL, ENVIRONMENT=test,
PYTHONUTF8=1, both model stubs=true; TEMP/TMP root `.test-storage-s3/t`):
`python -u -m pytest -q --tb=short -p no:cacheprovider tests/test_staff_bots.py
tests/test_platform.py tests/test_group_c_polish.py tests/test_self_service_signup.py
tests/test_tenant_route_matrix.py tests/test_quotas.py tests/test_staff_members.py
tests/test_staff_members_migration.py --basetemp=<workspace>/.test-storage-s3/q
--junitxml=../../.test-storage-s3/targeted.xml`.
Exit 0; raw tail: `77 passed, 1 warning in 173.29s (0:02:53)` (0 failed/0 skipped).
Includes S2's schema upgrade/downgrade test. Log: `.test-storage-s3/targeted.log`.

Static commands:
- `python -m ruff check` on changed backend files: initial import/line-length
  findings fixed before testing; final exit 0, `All checks passed!`.
- `python -m mypy --follow-imports=silent app/bots/factory.py app/bots/service.py
  app/bots/router.py app/platform/bots.py app/platform/router.py app/main.py
  app/provisioning/service.py tests/test_staff_bots.py tests/test_platform.py
  tests/test_group_c_polish.py`: exit 0, no issues in 10 source files.
- apps/web `npm.cmd run lint`, `npm.cmd run typecheck`: exit 0.
- apps/web `npm.cmd run test -- --list`: exit 0, **68 tests in 22 files**.
  Browser execution remains deferred to one combined run after S4.
- Root `python -m unittest discover -s scripts -p test_dev_compose.py`: exit 0,
  raw tail `Ran 7 tests in 0.006s` / `OK`. Static Compose/seed wiring only.
  The seed uses deterministic fixtures and existing RAG endpoints, never the
  removed onboarding endpoint, so seed source is unchanged. No Docker/seed run.

The full backend pair uses this identical command in separate processes:
`python -u -m pytest -q --tb=short -p no:cacheprovider
--ignore=tests/test_startup_guard.py --basetemp=<workspace>/.test-storage-s3/f
--junitxml=../../.test-storage-s3/full.xml` with the same per-process environment.
Run 1 exited 0; raw tail:
`449 passed, 1 skipped, 1 warning in 1335.63s (0:22:15)` (0 failed).
The skip is the existing POSIX process-group parser integration on Windows.
Run 2 exited 0 with identical counts; raw tail:
`449 passed, 1 skipped, 1 warning in 1335.95s (0:22:15)` (0 failed).
Logs: `.test-storage-s3/full-1.log` and `full-2.log`.
Standalone startup guard removed BOTH stub variables before launching its own
Python process, with the owner test URL and PYTHONUTF8=1:
`python -u -m pytest -q --tb=short -p no:cacheprovider tests/test_startup_guard.py
--basetemp=<workspace>/.test-storage-s3/s`: exit 0,
raw tail `7 passed, 1 warning in 0.66s` (0 failed/0 skipped).
No paid API calls, credential-file reads or safety-guard edits occurred.

Final markup follow-up aligns the new pages with the existing main wrapper.
`git diff df826b5 691382c -- apps/api` is empty: the S2 follow-up changes only
Members markup and review records, so backend source remained identical during
both full runs and final restacking. Only S3's own generated evaluation timestamp
was restored. Final Ruff/mypy checks still pass on all 10 changed Python files;
final web lint/typecheck/list run after restacking exited 0: **68 tests in 22
files** listed, no browser execution. The last restack from 691382c to 5bbd9cd
changed documentation only (`git diff 691382c 5bbd9cd -- apps` is empty).
The documentation-only rebase conflict retained both S3 history and S2's verified
status heading. Final source/test guards are unchanged, with no conflict markers.
S2 and S3 are complete for backend/static review; the one combined Playwright
execution remains deferred until S4. No merge, push, tag, deployment or Docker run.

## 2026-10-20 — S2 staff members (backend/static verification complete)

Owner authorized working before S1 verification finishes and reviewing S1/S2/S3
together. Isolated branch `feature/staff-members` initially started at S1 commit
`49710c7` instead of merged main, then rebased onto finalized S1 `bb2e847` after
its verification commits arrived. S1's checkout and Phase 6 worktree are untouched. Worktree:
`.worktrees/staff-members`. Its ignored local `apps/web/node_modules` junction
reuses existing dependencies; no dependencies or lockfiles were changed.

Implemented account phone/is_active migration, staff account lifecycle endpoints,
session revocation and shared login eligibility, existing-user-only invitations,
Members screens and organization membership controls. Typed passwords are not
returned by the API; the UI shows its submitted password once. Generated passwords
are returned once and kept only in component state. Staff user endpoints send
`Cache-Control: no-store`; tenant response schemas expose no phone.

Regression setup adaptations: invitation helpers provision existing accounts
before invitation creation; logged_in can log in to such an account; direct
invitation and route-matrix fixtures create prerequisite users. Assertions are
retained. The closed-registration regression removes its fixture account to
represent a legacy outstanding invitation and preserve registration assertions.
Browser invitation fixtures provision accounts first; the dashboard journey
signs in rather than registering the already-provisioned invitee. These setup
changes are necessary for the requested existing-users-only contract.

Commands run from the isolated worktree (Python is the root
`.venv/Scripts/python.exe`):

- `npm.cmd run typecheck` in apps/web: initially failed resolving @types/node;
  Next's automatic install attempt failed offline. Reusing installed dependencies
  resolved this. A subsequent run found an optional invitation link type, fixed
  before repeating. Final run exit 0, route generation and TypeScript successful.
- `npm.cmd run lint` in apps/web: exit 0, no warnings.
- `npm.cmd run test -- --list` in apps/web: exit 0, **66 tests in 21 files**;
  no browser tests executed. One combined Playwright execution remains deferred
  until after S4, per owner instruction.
- `python -m ruff check` over changed backend files: initial formatting/import
  findings fixed; subsequent checks exit 0, `All checks passed!`.
- `python -m mypy --follow-imports=silent app/platform/users.py app/auth/service.py
  app/tenants/service.py tests/test_staff_members.py
  tests/test_staff_members_migration.py`: exit 0, no issues in five source files.
- With the owner-supplied TEST_DATABASE_URL set per process, `python -m pytest
  --collect-only -q -p no:cacheprovider tests/test_staff_members.py
  tests/test_staff_members_migration.py`: exit 0, **15 tests collected in 0.27s**
  at that checkpoint; additional cases have since been added. Collection did not
  execute database fixtures. Existing Starlette/httpx deprecation warning only.
- After adding validation, atomic rollback, filtering and concurrent revocation
  cases, the same collection command with
  `tests/test_staff_member_revocation_race.py` appended exited 0:
  **31 tests collected in 0.25s**. No database tests have executed yet.

Database execution began only after elevated process checks confirmed that S1's
pytest processes had exited, then confirmed no new run after a 30-second wait.
The originally prescribed disposable database URL is used. The optional request
to use a separate database was not acted on. No safety guard was changed.

S2 targeted command in apps/api (per-process TEST_DATABASE_URL supplied, ENVIRONMENT=test,
CHAT_STUB_MODEL=true, EMBEDDING_TEST_STUB=true):
`python -u -m pytest -q --tb=short -p no:cacheprovider tests/test_staff_members.py
tests/test_staff_members_migration.py tests/test_staff_member_revocation_race.py
tests/test_staff_member_errors.py tests/test_invitations.py tests/test_self_service_signup.py
tests/test_auth.py tests/test_tenant_route_matrix.py tests/test_quotas.py
--basetemp=../../.test-storage-s2/targeted-host
--junitxml=../../.test-storage-s2/targeted-host.xml`.

- Initial sandbox run used `--basetemp=../../.test-storage-s2/targeted` without
  JUnit output. Exit 1: progress showed failures/errors, then pytest session cleanup
  crashed with WinError 5 reading its own temporary directory. There is no reliable
  final passed/failed/skipped summary for this run. Raw output: targeted.log.
- Corrected the NEW migration test's raw INSERT to supply required created_at.
  No existing test assertions or safety guards were removed to address this.
- Repeated with host permissions and JUnit output to get complete diagnostics:
  exit 1, raw tail `1 failed, 74 passed, 1 warning in 47.10s`.
  Failure: existing platform route-matrix check reported missing x-minimum-role
  metadata on the nested users router. Authorization checks themselves passed.
- Registered the users router through the existing top-level application path,
  so the unchanged metadata assignment covers it. Startup validation and all
  permission checks remain intact. Added safe handling of database statement
  errors so bound phone/password-hash parameters cannot escape into tracebacks.
- Final targeted repeat: exit 0, raw tail:
  `75 passed, 1 warning in 49.85s` (0 failed, 0 skipped).
  Raw output: `.test-storage-s2/targeted-final.log`; JUnit: targeted-host.xml.
- The subsequent full backend run is in progress, using
  `python -u -m pytest -q --tb=short -p no:cacheprovider
  --ignore=tests/test_startup_guard.py --basetemp=../../.test-storage-s2/full-host
  --junitxml=../../.test-storage-s2/full-host.xml` with the same per-process
  environment. Log: `.test-storage-s2/full-1.log`. No full-suite result yet.

The owner's later "dont stop" instruction is applied to repairing S2's failures;
S3 remains gated on successful S2 verification. Both initial failures and fixes
are retained in this record rather than represented as an initially green run.

Initial full S2 result: exit 1, **434 passed, 3 failed, 1 skipped**, one existing
warning, 1374.94s. Raw tail:
`3 failed, 434 passed, 1 skipped, 1 warning in 1374.94s (0:22:54)`.
Two failures were cp1252 UnicodeDecodeError in the existing Arabic evaluation
tests. The third was FileNotFoundError saving a fixture under the long nested
worktree temp path (over the classic Windows path limit). New S2 cases passed.
The skipped case is tests/test_knowledge_parsers.py:52 (POSIX process groups,
Windows unverified). Raw log: `.test-storage-s2/full-1.log`.

After that run, incorporated S1's finalized commits (only its verification notes,
platform analytics label and browser tab locator changed since the original base).
S1's newly committed notes document PYTHONUTF8=1 for these existing Windows
encoding failures. No tests or guards were changed to fix the runtime environment.
Per-process UTF-8 plus a shorter root-workspace temp directory resolved all three:
`python -u -m pytest -q --tb=short -p no:cacheprovider
tests/test_rag_evaluation.py::test_two_mode_retrieval_eval_is_entirely_offline
tests/test_rag_gate.py::test_stage0_raw_fts_gate_measurements
tests/test_rag_stage0_baseline.py::test_real_fts_pipeline_checkpoints_and_never_replays
--basetemp=<workspace>/.test-storage-s2/encoding`: exit 0,
raw tail `3 passed, 1 warning in 8.49s`. Log: encoding-proof.log.

The required pair of full runs now uses PYTHONUTF8=1 with the same test/stub
environment, TEMP and TMP pointing at `<workspace>/.test-storage-s2/t`, and this
identical Python command in both processes:
`python -u -m pytest -q --tb=short -p no:cacheprovider
--ignore=tests/test_startup_guard.py
--basetemp=<workspace>/.test-storage-s2/f
--junitxml=../../.test-storage-s2/full-utf8.xml`.
Both corrected full runs exited 0 with identical counts:

```text
437 passed, 1 skipped, 1 warning in 1425.32s (0:23:45)
437 passed, 1 skipped, 1 warning in 1335.86s (0:22:15)
```

The one skip is the existing POSIX process-group parser integration on Windows;
there are no new skipped cases. Logs: full-utf8-1.log and full-utf8-2.log.
Standalone startup command removed both stub variables before launching its own
Python process, with the same explicit test URL and PYTHONUTF8=1:
`python -u -m pytest -q --tb=short -p no:cacheprovider tests/test_startup_guard.py
--basetemp=<workspace>/.test-storage-s2/s`: exit 0,
raw tail `7 passed, 1 warning in 0.63s` (0 failed, 0 skipped).
No test/worker/startup/database-name guards were modified.

Final Ruff check over all 15 changed Python files: exit 0, `All checks passed!`.
`python -m mypy --follow-imports=silent` over the same 15 files: exit 0,
`Success: no issues found in 15 source files`. Final web lint, typecheck and
Playwright --list also exit 0 (66 tests in 21 files, browser execution deferred).
Only the evaluation timestamp regenerated by S2's own suite was restored to HEAD;
the original S1 checkout was not altered. S2 backend/static verification is green.
S3 may now be built stacked on this branch; no merge/push/deployment performed.
Final UI consistency follow-up: Members list/detail now use the existing page
main landmark/wrapper. This is markup only; backend/test source is unchanged.
Repeated web lint/typecheck both exit 0. S3 will incorporate this local follow-up
before its final review report; backend verification counts above remain applicable.

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

## 2026-10-15 — UI final-gate corrections (before final successful sequence)

- First final sequence: `npm.cmd run typecheck`, `npm.cmd run lint`, `npm.cmd run build` all exit 0. `npm.cmd run test`: 29 failed, 6 passed (5.5m). All 29 failures shared broad Password selectors matching the new show-password button. Field selectors now use exact accessible names; assertions unchanged. `npm.cmd run test --workspace apps/web -- contacts.spec.ts`: 1 passed (46.3s).
- Corrected PowerShell-to-Python character conversion in newly introduced icons/copy using explicit Unicode escapes; existing server-returned messages were not rewritten. Removed a false success notice on read-only platform loading. Restarted lint caught six unescaped JSX apostrophes; corrected typography and reran lint successfully.
- Restarted typecheck, lint and build: all exit 0. `npm.cmd run test`: 2 failed, 33 passed (3.5m). Follow-up selector matched hidden contact-erasure copy; platform operation selector still expected raw pending as display text after readable badge mapping. Added explicit Conversation label, exact follow-up selectors and a raw data-status hook for operation rows.
- Failed-spec-only reruns: `npm.cmd run test --workspace apps/web -- followups.spec.ts`: 1 passed (49.0s); `npm.cmd run test --workspace apps/web -- ui-characterization.spec.ts -g 'platform operations:'`: 1 passed (48.6s). No skipped/deleted tests, changed retries, weaker assertions or timeout inflation.
- Tightened configured widget brand ink to pure black/white for AA contrast, with a new both-theme mid-tone/light/dark color test (suite now 36 cases). Loader copies regenerated from canonical tokens.
- Safe test environment: isolated local PostgreSQL cluster in the OS temporary directory, listening only on 127.0.0.1:55439; disposable database ui_redesign_test, API 8019, web 3100, offline stub model. No existing database credentials or .env were read. Native process permissions required approved escalation. No API pytest, backend source, migrations or infrastructure edits.
- Command output logs are local and uncommitted under `.test-storage/ui-redesign/`. Initial/restarted failed full runs remain in `test-run-1.log` and `test-final-1.log`; focused reruns have separate logs. The final sequence uses `typecheck-final.log`, `lint-final.log`, `build-final.log`, and `test-36-run-1.log` / `test-36-run-2.log`.

## 2026-10-15 — UI final revision and boundary review

An intermediate complete suite passed 36/36 (2.9m). A final mobile spacing correction keeps left/right embedded frames inside a 360px viewport; a reachable header close control reuses the existing close message, returns launcher focus, and preserves origin strictness. Added explicit widget language/close-form labels. Screenshot harness now includes open embeds as well as launchers (108 planned images). Final suite source count: 37; every original test retained.

AST comparison against baseline 1bea650 passed for all iframe sandbox values, event-origin comparisons and postMessage arguments in loader/frame. The first Node-based comparison could not spawn git (EPERM); using a read-only Python baseline export and Node AST parsing succeeded. API contracts, CSP/proxy configuration, backend/migrations/infra, dependency manifests/lockfile and protected docs were separately checked unchanged. Both loader copies are identical.

Final revision: `npm.cmd run typecheck` exit 0; `npm.cmd run lint` exit 0; `npm.cmd run build` exit 0. `npm.cmd run test` final 37-case run 1: 37 passed (2.9m), exit 0, no retries/skips. Run 2 and screenshot results follow in the completion entry. Final logs: `.test-storage/ui-redesign/test-37-run-1.log` and `test-37-run-2.log`.

## 2026-10-15 — UI characterization teardown race

The first final 37-case run passed 37/37 (2.9m). The consecutive second run finished 36 passed / 1 failed (3.0m): the 429 assertion itself succeeded, but an in-flight auth/me proxy handler from the preceding viewer characterization errored during page teardown. This was a test-harness race, not a swallowed product failure. Replaced proxy callbacks with an authenticated session snapshot (explicitly assert the tenant membership first) and added `page.unrouteAll({behavior:'wait'})` cleanup. No ignored errors, retries, skipped tests or weaker assertions. Failed-spec-only command `npm.cmd run test --workspace apps/web -- ui-characterization.spec.ts`: 6 passed (1.0m), exit 0. Restarted final typecheck and lint both exit 0. The fresh full-run logs will be `test-37-final-1.log` and `test-37-final-2.log`; earlier run logs remain unchanged.

## 2026-10-15 — UI visual review refinement

The frozen revision after the teardown fix passed two consecutive complete `npm.cmd run test` runs: 37 passed (2.9m), then 37 passed (2.9m), exit 0 both, no skips/retries. `npm.cmd run test --workspace apps/web -- --config playwright.screenshots.config.ts` then passed 1 capture workflow (40.6s), producing 108 PNGs / 11,779,148 bytes in implementation/ui-screens. Horizontal page overflow assertions passed across captured app routes/viewports. Inspected dark desktop Overview, light mobile conversation/auth, staff detail, inbox and embedded widget.

Visual inspection found the expanded inbox filter stack pushed its list below the desktop fold. Refined presentation only: Search and Status remain visible; all five other existing filters are in native More filters disclosure with Escape support; active chips remain visible. Compact counts keep rows visible. Extended the existing Arabic/filter test with mode-request and disclosure keyboard assertions; no test was removed. Quota warning keys now use the shared readable-label mapper, not server-error rewriting. `npm.cmd run typecheck`: exit 0; `npm.cmd run lint`: exit 0. Repeating full final sequence and regenerating screenshots for this visual refinement. Prior consecutive green logs retained as test-37-final-1.log / test-37-final-2.log; reviewed revision logs use test-37-reviewed-1.log / test-37-reviewed-2.log.

## 2026-10-15 — UI advanced-filter selector correction

Reviewed compact-filter full run: 36 passed / 1 failed (3.0m). The extended filter test matched both the Mode select and the active Remove mode filter chip after a successful mode request. Added explicit inbox-mode-filter test ID and targeted that control; assertions unchanged. Failed-case-only command `npm.cmd run test --workspace apps/web -- ui-redesign.spec.ts -g 'Arabic inbox'`: 1 passed (47.6s). Restarted `npm.cmd run typecheck` and `npm.cmd run lint`: exit 0 both. Final compact revision logs use test-37-delivery-1.log / test-37-delivery-2.log and screenshots-delivery.log; earlier logs remain available.

## 2026-10-15 — UI raw handoff inspection hook

The compact inbox delivery revision passed two complete runs (37 passed, 2.9m each), then refreshed all 108 screenshots successfully (1 capture workflow passed, 41.1s; 13,285,101 bytes). Visual inspection confirmed rows visible within the desktop viewport. Final inspection added the missing raw handoff reason to title/data-handoff-reason while preserving its readable label; extended the existing Arabic row assertion to cover this requirement. No action or request changed. `npm.cmd run typecheck` and `npm.cmd run lint`: exit 0. Repeating the final sequence for this metadata-only correction; final handoff logs use test-37-handoff-1.log / test-37-handoff-2.log and screenshots-handoff.log. The same disposable local database was restarted for this verification only.

## 2026-10-15 — UI redesign completion

Final revision verified in the requested strict sequence, one heavy command at a time:

1. `npm.cmd run typecheck` — exit 0.
2. `npm.cmd run lint` — exit 0.
3. `npm.cmd run build` — exit 0; all original routes plus approved read-only /app/[tenant] generated.
4. `npm.cmd run test` — 37 passed (2.9m), exit 0.
5. `npm.cmd run test` — 37 passed (2.9m), exit 0, consecutively on unchanged source.
6. `npm.cmd run test --workspace apps/web -- --config playwright.screenshots.config.ts` — 1 capture workflow passed (40.5s), exit 0; production build reused.

Evidence: `.test-storage/ui-redesign/typecheck-final.log`, `lint-final.log`, `build-final.log`, `test-37-handoff-1.log`, `test-37-handoff-2.log`, `screenshots-handoff.log`. Original 25 browser tests retained; total now 37; retries 0, no skipped/deleted/weakened assertions. Earlier failures, the one observed harness teardown race and all focused reruns are recorded above, not hidden. No command was killed for memory. API pytest was not run per frontend-only scope.

Artifacts: `implementation/ui-screens/` contains 108 full-page PNGs (13,733,221 bytes): 26 routes plus open embedded-widget state, each in dark/light at 1440x900 and 360x800 viewports. PNG widths/group completeness verified. Capture workflow's horizontal-overflow assertions passed. Visually inspected representative dark/light desktop/mobile Overview, inbox/thread, auth, platform and widget images; final compact inbox rows are visible within the desktop viewport. Screenshots remain uncommitted; original Stage 0 plan remains uncommitted/untouched.

Decisions: zero dependencies and system fonts; native dialogs/disclosure and navigation-only palette; system-default viewer-local theme; separate read-only tenant Overview while preserving existing entry/org-switch destinations; first-current-bot knowledge checklist; existing contacts endpoint for row names; shared inbox list across existing list/thread routes; More filters keeps Search/Status and active chips visible; explicit optional contact-message erasure; canonical loader tokens with contrast-aware ink; mobile close reuses existing protocol; safe isolated disposable PostgreSQL/offline model; exact selectors/raw attributes and awaited test route cleanup.

Skipped because existing API supplies no reliable data: installation detection/status, numeric ingestion percentage/ETA, actual token-stream rendering. No fabricated values. PLACEHOLDER plan disclosures and final-pricing/limits-TBD note retained. No staging/pricing ADR decision made.

Final scope review: no backend source, migrations, infra, API contract, dependency manifest/lockfile, CSP/proxy, README or protected docs edits. Only requested MANUAL-TEST changes under existing implementation docs. Sandbox/origin/postMessage arguments match baseline AST; loader copies identical. No .env/key read, push, merge, deploy, paid API calls or cloud resources. Test API/worker/web processes stopped by harness; dedicated local PostgreSQL stopped via pg_ctl, data retained only in its temporary test cluster. Generated next-env.d.ts is restored to the pre-task tracked version.

Limits: Chromium/local fixtures and automated keyboard/contrast/RTL/layout verification; manual screen-reader, other browsers and real customer-host embedding were not exercised. No production deployment approval implied. All authorized implementation and required verification are complete; no known blocking failure remains.
# 2026-10-16 — Product cycle 1

Branch: `feat/product-cycle-1`, based on local `main`; local commits only.
No `.env` or credential files were read. API tests used `ENVIRONMENT=test` and a disposable local PostgreSQL cluster (`postgres_test`, `postgres_e2e_test`).

Changed API specs, run one file at a time with `python -m pytest -q tests/<file>.py --tb=short -p no:cacheprovider`:

- `test_self_service_signup.py`: 3 passed, 1 Starlette `httpx` deprecation warning (1.41s).
- `test_bots.py`: 4 passed, 1 warning (1.99s).
- `test_members.py`: 8 passed, 1 warning (3.37s).
- `test_quotas.py`: 10 passed, 1 warning (4.39s).
- `test_analytics.py`: 6 passed, 1 warning (49.04s).
- `test_contacts.py`: 1 passed, 1 warning (7.43s); updated fixture to use a directly seeded test bot and owner/admin export assertions.
- `test_knowledge_pipeline.py`: 9 passed, 1 warning (34.93s).
- `test_knowledge_uploads.py`: 19 passed, 1 warning (38.43s); test fixture seeds bots without calling the now-forbidden tenant bot endpoint.
- `test_tenant_data.py`: 2 passed, 1 warning (1.70s).
- `test_followups_analytics.py`: 2 passed, 1 warning (24.43s).
- `test_tenant_route_matrix.py`: 1 passed, 1 warning (5.14s); enumerates OpenAPI tenant routes, calls as viewer/editor/admin/owner, and probes foreign tenant IDs. The open-ended SSE route is exercised through its foreign-tenant authorization check.

Web verification:

- `npm run build`: passed; TypeScript and Next production build completed.
- First `npm test -- --reporter=line`: 37 passed, 1 failed because `ui-redesign.spec.ts` expected the removed TBD wording. Updated the assertion to the current provisional plan copy.
- Final `npm test -- --reporter=line`: 38 passed (4.1m), exit 0.
- After removing the remaining Archive control from the bot Settings UI, reran `npm test -- --reporter=line`: 37 passed, 1 failed (5.8m). `knowledge.spec.ts` timed out while the web proxy logged `ECONNRESET` to the local API; it failed filling `Organization name` during owner registration. This was a test infrastructure failure; the full suite result for the preceding source revision was 38/38.
- After removing remaining visible PLACEHOLDER copy and updating the accessible quota label assertion, focused `npm test -- --grep 'platform client mutations preserve plan' --reporter=line`: 1 passed (59.1s). Final `npm run typecheck`: exit 0.

One ordinary in-sandbox pytest attempt hit restricted Windows temp-directory access; the same affected API specs were rerun successfully outside the sandbox against the disposable database. A test run interrupted while exercising the endless SSE stream; the route matrix was updated to verify its foreign-tenant rejection before streaming, then passed.


## 2026-10-16 ? Phase 1 roles and operator control verification

Scope: explicit owner change note; three client roles, operator-only bot control, migration 0013, last-admin locking, invite-only registration guard, soft-delete ledger/worker purge and admin change requests with attachments/operator triage. Local work only; no push/deploy, environment-file or credential reads, paid calls or channel implementation. APIs use the guarded disposable local PostgreSQL cluster on loopback.

Intermediate verification (before the file-by-file logs below):
- First test_members.py attempt inadvertently ran the previous test file after a path-writing error: 6 failed / 2 passed (obsolete owner/transfer assertions). Corrected file: `../../.venv/Scripts/python.exe -m pytest -q tests/test_members.py --tb=short -p no:cacheprovider` from apps/api: 5 passed, 1 warning, 2.30s.
- test_tenant_route_matrix.py: initial ordinary run failed at temp setup (4 errors, Windows sandbox permissions); explicit workspace basetemp also failed with WinError 5. Subsequent disposable-DB runs outside sandbox: 1 passed / 3 failed (fixture payload/state); then 3 passed / 1 failed for an already-ingested source; then 3 passed / 1 failed for a staff assignment fixture FK; then 3 passed / 1 failed when probing unrequested membership-free inbox actions. The matrix now asserts all client routes and checks membership-free staff success for every operator-only route. It does not skip a tenant/client-role combination or accept 422/404 as an allowed role's success. SSE transport alone is bounded with a finite test generator, retaining the real endpoint/dependencies.
- First test_tenant_data.py: 1 passed / 1 failed because requested_at and grace deadline used separate clocks; schedule now uses one timestamp. Corrected run is below.
- Initial web typecheck found duplicate install imports and stale role labels; fixed. Initial lint found hook dependencies; fixed. Final pre-suite `npm.cmd run typecheck` and `npm.cmd run lint`: exit 0.
- Changed-file Ruff initially reported formatting/import issues; fixed. Full-source Ruff also reports pre-existing untouched violations (for example quotas/sentiment.py and platform/router.py). Final changed-file check is recorded separately.
- Focused mypy command `../../.venv/Scripts/python.exe -m mypy app/tenants/changes.py app/tenants/deletion.py app/db/models/operations.py app/core/permissions.py app/core/tenancy.py --follow-imports=silent`: mypy 2.4.0 INTERNAL ERROR, exit 1. Retrying with --no-incremental and an isolated --cache-dir produced the same internal error; no typecheck success claimed.

Related tests and final full-suite file-by-file commands/results:

- From `apps/api`: `../../.venv/Scripts/python.exe -m pytest -q tests/test_self_service_signup.py --tb=short -p no:cacheprovider \'--basetemp=D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai\.test-storage\roles-control\tmp-1792112650788005700\'` — exit 0; 4 passed, 1 warning in 2.13s. Log: `.test-storage/roles-control/test_self_service_signup-1792112650788005700.log`.

- From `apps/api`: `../../.venv/Scripts/python.exe -m pytest -q tests/test_change_requests.py --tb=short -p no:cacheprovider \'--basetemp=D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai\.test-storage\roles-control\tmp-1792112655436147200\'` — exit 0; 1 passed, 1 warning in 1.30s. Log: `.test-storage/roles-control/test_change_requests-1792112655436147200.log`.

- From `apps/api`: `../../.venv/Scripts/python.exe -m pytest -q tests/test_tenant_data.py --tb=short -p no:cacheprovider \'--basetemp=D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai\.test-storage\roles-control\tmp-1792112657772958900\'` — exit 0; 2 passed, 1 warning in 2.41s. Log: `.test-storage/roles-control/test_tenant_data-1792112657772958900.log`.

- From `apps/api`: `../../.venv/Scripts/python.exe -m pytest -q tests/test_tenant_route_matrix.py --tb=short -p no:cacheprovider \'--basetemp=D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai\.test-storage\roles-control\tmp-1792112662370247400\'` — exit 0; 4 passed, 1 warning in 42.28s. Log: `.test-storage/roles-control/test_tenant_route_matrix-1792112662370247400.log`.

- From `apps/api`: `../../.venv/Scripts/python.exe -m pytest -q tests/test_migrations.py --tb=short -p no:cacheprovider \'--basetemp=D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai\.test-storage\roles-control\tmp-1792112706879674400\'` — exit 0; 1 passed, 1 warning in 4.69s. Log: `.test-storage/roles-control/test_migrations-1792112706879674400.log`.

- From `apps/api`: `../../.venv/Scripts/python.exe -m pytest -q tests/eval/test_eval.py --tb=short -p no:cacheprovider \'--basetemp=D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai\.test-storage\roles-control\tmp-1792113028383492400\'` — exit 0; 2 passed, 1 warning in 12.93s. Log: `.test-storage/roles-control/test_eval-1792113028383492400.log`.

- From `apps/api`: `../../.venv/Scripts/python.exe -m pytest -q tests/test_analytics.py --tb=short -p no:cacheprovider \'--basetemp=D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai\.test-storage\roles-control\tmp-1792113044356797800\'` — exit 0; 6 passed, 1 warning in 84.35s (0:01:24). Log: `.test-storage/roles-control/test_analytics-1792113044356797800.log`.

- From `apps/api`: `../../.venv/Scripts/python.exe -m pytest -q tests/test_auth.py --tb=short -p no:cacheprovider \'--basetemp=D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai\.test-storage\roles-control\tmp-1792113131100782500\'` — exit 0; 15 passed, 1 warning in 7.39s. Log: `.test-storage/roles-control/test_auth-1792113131100782500.log`.

Mypy diagnosis: repeating the focused command with `--no-incremental --show-traceback --cache-dir ../../.test-storage/roles-control/mypy-final` failed because importing ast_serialize raised `ImportError: DLL load failed ... An Application Control policy has blocked this file.` OS security control was not bypassed. Python static typing remains UNVERIFIED.

- From `apps/api`: `../../.venv/Scripts/python.exe -m pytest -q tests/test_bot_status.py --tb=short -p no:cacheprovider \'--basetemp=D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai\.test-storage\roles-control\tmp-1792113140928986200\'` — exit 0; 5 passed, 1 warning in 54.37s. Log: `.test-storage/roles-control/test_bot_status-1792113140928986200.log`.

- From `apps/api`: `../../.venv/Scripts/python.exe -m pytest -q tests/test_bots.py --tb=short -p no:cacheprovider \'--basetemp=D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai\.test-storage\roles-control\tmp-1792113197520681600\'` — exit 1; 1 failed, 3 passed, 1 warning in 2.21s. Log: `.test-storage/roles-control/test_bots-1792113197520681600.log`.

- From `apps/api`: `../../.venv/Scripts/python.exe -m pytest -q tests/test_change_requests.py --tb=short -p no:cacheprovider \'--basetemp=D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai\.test-storage\roles-control\tmp-1792113201339635400\'` — exit 0; 1 passed, 1 warning in 1.39s. Log: `.test-storage/roles-control/test_change_requests-1792113201339635400.log`.

- From `apps/api`: `../../.venv/Scripts/python.exe -m pytest -q tests/test_chat.py --tb=short -p no:cacheprovider \'--basetemp=D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai\.test-storage\roles-control\tmp-1792113203738112300\'` — exit 0; 15 passed, 1 warning in 145.42s (0:02:25). Log: `.test-storage/roles-control/test_chat-1792113203738112300.log`.

- From `apps/api`: `../../.venv/Scripts/python.exe -m pytest -q tests/test_contacts.py --tb=short -p no:cacheprovider \'--basetemp=D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai\.test-storage\roles-control\tmp-1792113351568409000\'` — exit 0; 1 passed, 1 warning in 11.86s. Log: `.test-storage/roles-control/test_contacts-1792113351568409000.log`.

- From `apps/api`: `../../.venv/Scripts/python.exe -m pytest -q tests/test_conversations.py --tb=short -p no:cacheprovider \'--basetemp=D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai\.test-storage\roles-control\tmp-1792113365648329200\'` — exit 1; 1 failed, 12 passed, 1 warning in 142.33s (0:02:22). Log: `.test-storage/roles-control/test_conversations-1792113365648329200.log`.

- From `apps/api`: `../../.venv/Scripts/python.exe -m pytest -q tests/test_conversations_view.py --tb=short -p no:cacheprovider \'--basetemp=D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai\.test-storage\roles-control\tmp-1792113509276410000\'` — exit 0; 5 passed, 1 warning in 59.99s. Log: `.test-storage/roles-control/test_conversations_view-1792113509276410000.log`.

- From `apps/api`: `../../.venv/Scripts/python.exe -m pytest -q tests/test_cross_script.py --tb=short -p no:cacheprovider \'--basetemp=D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai\.test-storage\roles-control\tmp-1792113571579058100\'` — exit 0; 3 passed, 1 warning in 30.20s. Log: `.test-storage/roles-control/test_cross_script-1792113571579058100.log`.

- From `apps/api`: `../../.venv/Scripts/python.exe -m pytest -q tests/test_database_guard.py --tb=short -p no:cacheprovider \'--basetemp=D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai\.test-storage\roles-control\tmp-1792113603706451200\'` — exit 0; 5 passed, 1 warning in 0.81s. Log: `.test-storage/roles-control/test_database_guard-1792113603706451200.log`.

- From `apps/api`: `../../.venv/Scripts/python.exe -m pytest -q tests/test_followups_analytics.py --tb=short -p no:cacheprovider \'--basetemp=D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai\.test-storage\roles-control\tmp-1792113605429904100\'` — exit 0; 2 passed, 1 warning in 22.03s. Log: `.test-storage/roles-control/test_followups_analytics-1792113605429904100.log`.

- From `apps/api`: `../../.venv/Scripts/python.exe -m pytest -q tests/test_handoff.py --tb=short -p no:cacheprovider \'--basetemp=D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai\.test-storage\roles-control\tmp-1792113628779954500\'` — exit 0; 5 passed, 1 warning in 48.48s. Log: `.test-storage/roles-control/test_handoff-1792113628779954500.log`.

- From `apps/api`: `../../.venv/Scripts/python.exe -m pytest -q tests/test_health.py --tb=short -p no:cacheprovider \'--basetemp=D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai\.test-storage\roles-control\tmp-1792113679284126600\'` — exit 0; 6 passed, 1 warning in 1.16s. Log: `.test-storage/roles-control/test_health-1792113679284126600.log`.

- From `apps/api`: `../../.venv/Scripts/python.exe -m pytest -q tests/test_inbox_list.py --tb=short -p no:cacheprovider \'--basetemp=D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai\.test-storage\roles-control\tmp-1792113681472639400\'` — exit 0; 5 passed, 1 warning in 16.76s. Log: `.test-storage/roles-control/test_inbox_list-1792113681472639400.log`.

- From `apps/api`: `../../.venv/Scripts/python.exe -m pytest -q tests/test_invitations.py --tb=short -p no:cacheprovider \'--basetemp=D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai\.test-storage\roles-control\tmp-1792113699168942100\'` — exit 0; 6 passed, 1 warning in 2.83s. Log: `.test-storage/roles-control/test_invitations-1792113699168942100.log`.

- From `apps/api`: `../../.venv/Scripts/python.exe -m pytest -q tests/test_jobs.py --tb=short -p no:cacheprovider \'--basetemp=D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai\.test-storage\roles-control\tmp-1792113702857747300\'` — exit 0; 8 passed, 1 warning in 1.34s. Log: `.test-storage/roles-control/test_jobs-1792113702857747300.log`.

- From `apps/api`: `../../.venv/Scripts/python.exe -m pytest -q tests/test_knowledge_parsers.py --tb=short -p no:cacheprovider \'--basetemp=D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai\.test-storage\roles-control\tmp-1792113705342054900\'` — exit 0; 27 passed, 1 warning in 13.64s. Log: `.test-storage/roles-control/test_knowledge_parsers-1792113705342054900.log`.

- From `apps/api`: `../../.venv/Scripts/python.exe -m pytest -q tests/test_knowledge_pipeline.py --tb=short -p no:cacheprovider \'--basetemp=D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai\.test-storage\roles-control\tmp-1792113720916312700\'` — exit 1; 2 failed, 7 passed, 1 warning in 31.63s. Log: `.test-storage/roles-control/test_knowledge_pipeline-1792113720916312700.log`.

- From `apps/api`: `../../.venv/Scripts/python.exe -m pytest -q tests/test_knowledge_uploads.py --tb=short -p no:cacheprovider \'--basetemp=D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai\.test-storage\roles-control\tmp-1792113754675675700\'` — exit 1; 1 failed, 18 passed, 1 warning in 35.96s. Log: `.test-storage/roles-control/test_knowledge_uploads-1792113754675675700.log`.

- From `apps/api`: `../../.venv/Scripts/python.exe -m pytest -q tests/test_members.py --tb=short -p no:cacheprovider \'--basetemp=D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai\.test-storage\roles-control\tmp-1792113792904465600\'` — exit 0; 5 passed, 1 warning in 2.86s. Log: `.test-storage/roles-control/test_members-1792113792904465600.log`.

- From `apps/api`: `../../.venv/Scripts/python.exe -m pytest -q tests/test_migrations.py --tb=short -p no:cacheprovider \'--basetemp=D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai\.test-storage\roles-control\tmp-1792113797904304600\'` — exit 1; 1 failed, 1 warning in 19.41s. Log: `.test-storage/roles-control/test_migrations-1792113797904304600.log`.

- From `apps/api`: `../../.venv/Scripts/python.exe -m pytest -q tests/test_models_constraints.py --tb=short -p no:cacheprovider \'--basetemp=D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai\.test-storage\roles-control\tmp-1792113818955511600\'` — exit 0; 13 passed, 1 warning in 1.48s. Log: `.test-storage/roles-control/test_models_constraints-1792113818955511600.log`.

- From `apps/api`: `../../.venv/Scripts/python.exe -m pytest -q tests/test_platform.py --tb=short -p no:cacheprovider \'--basetemp=D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai\.test-storage\roles-control\tmp-1792113821326688200\'` — exit 1; 1 failed, 8 passed, 1 warning in 103.13s (0:01:43). Log: `.test-storage/roles-control/test_platform-1792113821326688200.log`.

- From `apps/api`: `../../.venv/Scripts/python.exe -m pytest -q tests/test_platform_ops.py --tb=short -p no:cacheprovider \'--basetemp=D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai\.test-storage\roles-control\tmp-1792113926676420800\'` — exit 0; 4 passed, 1 warning in 2.43s. Log: `.test-storage/roles-control/test_platform_ops-1792113926676420800.log`.

- From `apps/api`: `../../.venv/Scripts/python.exe -m pytest -q tests/test_quotas.py --tb=short -p no:cacheprovider \'--basetemp=D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai\.test-storage\roles-control\tmp-1792113931255073500\'` — exit 1; 1 failed, 9 passed, 1 warning in 16.30s. Log: `.test-storage/roles-control/test_quotas-1792113931255073500.log`.

- From `apps/api`: `../../.venv/Scripts/python.exe -m pytest -q tests/test_retrieval.py --tb=short -p no:cacheprovider \'--basetemp=D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai\.test-storage\roles-control\tmp-1792113949920426300\'` — exit 0; 9 passed, 1 warning in 89.37s (0:01:29). Log: `.test-storage/roles-control/test_retrieval-1792113949920426300.log`.

- From `apps/api`: `../../.venv/Scripts/python.exe -m pytest -q tests/test_seed_demo.py --tb=short -p no:cacheprovider \'--basetemp=D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai\.test-storage\roles-control\tmp-1792114041608127100\'` — exit 1; 2 failed, 19 passed, 1 warning in 8.77s. Log: `.test-storage/roles-control/test_seed_demo-1792114041608127100.log`.

- From `apps/api`: `../../.venv/Scripts/python.exe -m pytest -q tests/test_self_service_signup.py --tb=short -p no:cacheprovider \'--basetemp=D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai\.test-storage\roles-control\tmp-1792114052276019000\'` — exit 0; 4 passed, 1 warning in 1.87s. Log: `.test-storage/roles-control/test_self_service_signup-1792114052276019000.log`.

- From `apps/api`: `../../.venv/Scripts/python.exe -m pytest -q tests/test_startup_guard.py --tb=short -p no:cacheprovider \'--basetemp=D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai\.test-storage\roles-control\tmp-1792114055075277100\'` — exit 0; 5 passed, 1 warning in 0.97s. Log: `.test-storage/roles-control/test_startup_guard-1792114055075277100.log`.

- From `apps/api`: `../../.venv/Scripts/python.exe -m pytest -q tests/test_tenant_data.py --tb=short -p no:cacheprovider \'--basetemp=D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai\.test-storage\roles-control\tmp-1792114056971979100\'` — exit 0; 2 passed, 1 warning in 2.28s. Log: `.test-storage/roles-control/test_tenant_data-1792114056971979100.log`.

- From `apps/api`: `../../.venv/Scripts/python.exe -m pytest -q tests/test_tenant_route_matrix.py --tb=short -p no:cacheprovider \'--basetemp=D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai\.test-storage\roles-control\tmp-1792114060598413500\'` — exit 0; 5 passed, 1 warning in 38.76s. Log: `.test-storage/roles-control/test_tenant_route_matrix-1792114060598413500.log`.

- From `apps/api`: `../../.venv/Scripts/python.exe -m pytest -q tests/test_tenants.py --tb=short -p no:cacheprovider \'--basetemp=D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai\.test-storage\roles-control\tmp-1792114101551945100\'` — exit 0; 6 passed, 1 warning in 2.07s. Log: `.test-storage/roles-control/test_tenants-1792114101551945100.log`.

- From `apps/api`: `../../.venv/Scripts/python.exe -m pytest -q tests/test_widget_appearance.py --tb=short -p no:cacheprovider \'--basetemp=D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai\.test-storage\roles-control\tmp-1792114104631754500\'` — exit 0; 3 passed, 1 warning in 31.03s. Log: `.test-storage/roles-control/test_widget_appearance-1792114104631754500.log`.

- From `apps/api`: `../../.venv/Scripts/python.exe -m pytest -q tests/test_widget_leads.py --tb=short -p no:cacheprovider \'--basetemp=D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai\.test-storage\roles-control\tmp-1792114137796461700\'` — exit 0; 5 passed, 1 warning in 60.06s (0:01:00). Log: `.test-storage/roles-control/test_widget_leads-1792114137796461700.log`.

- From `apps/api`: `../../.venv/Scripts/python.exe -m pytest -q tests/test_widget_public.py --tb=short -p no:cacheprovider \'--basetemp=D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai\.test-storage\roles-control\tmp-1792114200043130400\'` — exit 1; 1 failed, 13 passed, 1 warning in 155.09s (0:02:35). Log: `.test-storage/roles-control/test_widget_public-1792114200043130400.log`.

- From `apps/api`: `../../.venv/Scripts/python.exe -m pytest -q tests/test_bots.py --tb=short -p no:cacheprovider \'--basetemp=D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai\.test-storage\roles-control\tmp-1792114435276233000\'` — exit 0; 4 passed, 1 warning in 1.79s. Log: `.test-storage/roles-control/test_bots-1792114435276233000.log`.

- From `apps/api`: `../../.venv/Scripts/python.exe -m pytest -q tests/test_members.py --tb=short -p no:cacheprovider \'--basetemp=D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai\.test-storage\roles-control\tmp-1792114438039204000\'` — exit 0; 5 passed, 1 warning in 3.11s. Log: `.test-storage/roles-control/test_members-1792114438039204000.log`.

- From `apps/api`: `../../.venv/Scripts/python.exe -m pytest -q tests/test_migrations.py --tb=short -p no:cacheprovider \'--basetemp=D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai\.test-storage\roles-control\tmp-1792114443108854100\'` — exit 0; 1 passed, 1 warning in 3.34s. Log: `.test-storage/roles-control/test_migrations-1792114443108854100.log`.

- From `apps/api`: `../../.venv/Scripts/python.exe -m pytest -q tests/test_seed_demo.py --tb=short -p no:cacheprovider \'--basetemp=D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai\.test-storage\roles-control\tmp-1792114448141929100\'` — exit 0; 21 passed, 1 warning in 6.11s. Log: `.test-storage/roles-control/test_seed_demo-1792114448141929100.log`.

- From `apps/api`: `../../.venv/Scripts/python.exe -m pytest -q tests/test_quotas.py --tb=short -p no:cacheprovider \'--basetemp=D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai\.test-storage\roles-control\tmp-1792114456150207300\'` — exit 0; 10 passed, 1 warning in 15.87s. Log: `.test-storage/roles-control/test_quotas-1792114456150207300.log`.

- From `apps/api`: `../../.venv/Scripts/python.exe -m pytest -q tests/test_knowledge_pipeline.py --tb=short -p no:cacheprovider --basetemp=D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai\.test-storage\roles-control\tmp-1792114474275536100` — exit 1; 1 failed, 8 passed, 1 warning in 31.09s. Log: `.test-storage/roles-control/test_knowledge_pipeline-1792114474275536100.log`.

- From `apps/api`: `../../.venv/Scripts/python.exe -m pytest -q tests/test_knowledge_uploads.py --tb=short -p no:cacheprovider --basetemp=D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai\.test-storage\roles-control\tmp-1792114507348328000` — exit 0; 19 passed, 1 warning in 35.52s. Log: `.test-storage/roles-control/test_knowledge_uploads-1792114507348328000.log`.

- From `apps/api`: `../../.venv/Scripts/python.exe -m pytest -q tests/test_tenant_route_matrix.py --tb=short -p no:cacheprovider --basetemp=D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai\.test-storage\roles-control\tmp-1792114544775828400` — exit 0; 5 passed, 1 warning in 41.88s. Log: `.test-storage/roles-control/test_tenant_route_matrix-1792114544775828400.log`.

- From `apps/api`: `../../.venv/Scripts/python.exe -m pytest -q tests/test_conversations.py --tb=short -p no:cacheprovider --basetemp=D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai\.test-storage\roles-control\tmp-1792114589182428100` — exit 0; 13 passed, 1 warning in 147.42s (0:02:27). Log: `.test-storage/roles-control/test_conversations-1792114589182428100.log`.

Final web static checks after role/UI wiring: `npm.cmd run lint` ? exit 0; `npm.cmd run typecheck` ? exit 0. Changed-file `ruff check` ? all checks passed (see `.test-storage/roles-control/ruff-final.log`). Migration rollback limit: downgrade does not restore owner roles or the retired demo-owner login; no non-test migration was applied.

- From `apps/api`: `../../.venv/Scripts/python.exe -m pytest -q tests/test_platform.py --tb=short -p no:cacheprovider --basetemp=D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai\.test-storage\roles-control\tmp-1792114739034219600` — exit 0; 9 passed, 1 warning in 97.74s (0:01:37). Log: `.test-storage/roles-control/test_platform-1792114739034219600.log`.

- From `apps/api`: `../../.venv/Scripts/python.exe -m pytest -q tests/test_widget_public.py --tb=short -p no:cacheprovider --basetemp=D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai\.test-storage\roles-control\tmp-1792114838887423000` — exit 0; 14 passed, 1 warning in 142.42s (0:02:22). Log: `.test-storage/roles-control/test_widget_public-1792114838887423000.log`.

- From `apps/api`: `../../.venv/Scripts/python.exe -m pytest -q tests/test_knowledge_pipeline.py --tb=short -p no:cacheprovider --basetemp=D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai\.test-storage\roles-control\tmp-1792115057389502400` — exit 0; 9 passed, 1 warning in 32.91s. Log: `.test-storage/roles-control/test_knowledge_pipeline-1792115057389502400.log`.

- Owner clarification: viewers retain read-only contact lists and profiles. Contact writes remain editor+, and merge/delete/stage configuration remains admin.
- Full API file-by-file sweep and affected-file rechecks complete: latest results total 278 passed across 37 files. The initial sweep was not wholly green; failures and rechecks are recorded above.
- Full Playwright command from `apps/web`: `$env:ENVIRONMENT='test'; $env:DATABASE_URL='postgresql://postgres@127.0.0.1:55439/postgres'; $env:E2E_API_PORT='18135'; $env:API_PROXY_TARGET='http://127.0.0.1:18135'; npm.cmd test -- --reporter=line` (log `.test-storage/roles-control/playwright-full.log`); result pending.

- Final changed-file Python Ruff check: exit 0, all checks passed. Final `git diff --check`: exit 0. The final API retry test recheck passed (9 tests); forced test retries use a past timestamp, with production scheduling unchanged.

- Full Playwright run: exit 1; **37 passed, 3 failed (7.2m)**. Failed specs/tests: `overview.spec.ts` workspace/scoping (caller fixture was staff, so foreign tenant read correctly returned 200), `playground.spec.ts` expired session (new client-side role guard prevented the old protected fetch, so no redirect), `roles-control.spec.ts` change triage (test selected visible label while control had explicit accessible name). Corrected isolation fixture to assert as a client admin; centralized protected-page 401 redirect in session refresh; corrected test selector.
- Deferred ECONNRESET observed during `overview.spec.ts`, test `unanswered list shows the question the bot could not confirm`: Next proxy `/api/v1/auth/me` read reset. That test passed; no flake behavior changed.
- Scoped browser recheck from `apps/web`, same disposable environment as full run: `npm.cmd test -- tests/overview.spec.ts tests/playground.spec.ts tests/roles-control.spec.ts tests/dashboard.spec.ts --reporter=line` (log `.test-storage/roles-control/playwright-related.log`); result pending. These are affected specs and related session coverage only.
- Scoped ESLint after these fixes: `node_modules/.bin/eslint.cmd lib/session.tsx tests/staff-helpers.ts tests/overview.spec.ts tests/roles-control.spec.ts --max-warnings 0` ? exit 0.

- Session redirect recheck exposed an over-broad initial condition: the public `/accept-invite` landing page must remain available before authentication. Narrowed automatic initial-session redirect to `/app` and `/platform` only; existing expired-session event behavior is retained. Invitation UI journeys will receive a focused recheck on the final build.
- TypeScript after session/test-helper fixes: `npm.cmd run typecheck` ? exit 0.

- Scoped browser recheck: exit 1; **10 passed, 2 failed (3.2m)**. All three original failures now pass; the two invitation journeys failed due to the initial session redirect including the public invite landing page. That condition was already narrowed during the run; built output required a focused final recheck.
- Final invitation recheck from `apps/web`, same environment: `npm.cmd test -- tests/dashboard.spec.ts tests/playground.spec.ts --grep 'team management|viewer is read-only' --reporter=line`; log `.test-storage/roles-control/playwright-invitations.log`, result pending.

- From `apps/api`: `../../.venv/Scripts/python.exe -m pytest -q tests/test_tenant_data.py --tb=short -p no:cacheprovider --basetemp=D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai\.test-storage\roles-control\tmp-1792115859147402500` — exit 0; 2 passed, 1 warning in 2.02s. Log: `.test-storage/roles-control/test_tenant_data-1792115859147402500.log`.

- Final invitation browser recheck: exit 0; **2 passed (1.1m)**. All 40 browser scenarios have a passing latest result across the full sweep and scoped rechecks; no second full browser sweep was run.
- Final purge review preserved prior cleanup of tenant visitor message-rate counters, moved to delayed purge. `tests/test_tenant_data.py` recheck passed 2 tests in 2.02s, including removal of that counter and preservation of an unrelated counter. Ruff for the two touched Python files passed.
- Restored generated `next-env.d.ts` and timestamp-only `PHASE-03/EVAL-REPORT.md` output; neither is part of this change. Full changed-file list, 77-route matrix, per-file API/browser results, and unverified checks are in `implementation/PHASE-01/ROLES-OPERATOR-REPORT.md`.

- Final session ESLint check from `apps/web`: `node_modules/.bin/eslint.cmd lib/session.tsx --max-warnings 0` ? exit 0. Final `git diff --check` ? exit 0. Verification complete; committing locally only. No push/deployment performed.

- Phase 1 verification: docker exec -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/phase1verify phase1-verification-api python -m pytest -q tests/test_tenant_data.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1-test_tenant_data — exit 0. 2 passed, 1 warning in 7.07s Log: .test-storage/phase1-verification/test_tenant_data-typing.log

- Phase 1 verification: docker exec -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/phase1verify phase1-verification-api python -m pytest -q tests/test_members.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1-test_members — exit 0. 5 passed, 1 warning in 6.41s Log: .test-storage/phase1-verification/test_members-typing.log

- Phase 1 verification: docker exec -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/phase1verify phase1-verification-api python -m pytest -q tests/test_migrations.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1-test_migrations — exit 0. 1 passed, 1 warning in 7.35s Log: .test-storage/phase1-verification/test_migrations-typing.log

- Phase 1 verification: docker exec -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/phase1verify phase1-verification-api python -m pytest -q tests/test_bots.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1-test_bots — exit 0. 4 passed, 1 warning in 6.62s Log: .test-storage/phase1-verification/test_bots-typing.log

- Phase 1 verification: docker exec -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/phase1verify phase1-verification-api python -m pytest -q tests/test_self_service_signup.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1-test_self_service_signup — exit 0. 4 passed, 1 warning in 4.86s Log: .test-storage/phase1-verification/test_self_service_signup-typing.log

- Phase 1 verification: docker exec -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/phase1verify phase1-verification-api python -m pytest -q tests/test_startup_guard.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1-test_startup_guard — exit 0. 5 passed, 1 warning in 3.14s Log: .test-storage/phase1-verification/test_startup_guard-typing.log

- Phase 1 verification: docker exec -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/finalverify phase1-verification-api python -m pytest -q tests/test_auth.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1-final-test_auth — exit 0. 15 passed, 1 warning in 6.57s Log: .test-storage/phase1-verification/test_auth-final.log

- Phase 1 verification: docker exec -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/finalverify phase1-verification-api python -m pytest -q tests/test_bot_status.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1-final-test_bot_status — exit 0. 5 passed, 1 warning in 90.54s (0:01:30) Log: .test-storage/phase1-verification/test_bot_status-final.log

- Phase 1 verification: docker exec -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/phase1verify phase1-verification-api python -m pytest -q tests/test_widget_public.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1-test_widget_public — exit 0. 14 passed, 1 warning in 302.14s (0:05:02) Log: .test-storage/phase1-verification/test_widget_public-typing.log

- Phase 1 verification: docker exec -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/finalverify phase1-verification-api python -m pytest -q tests/test_conversations.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1-final-test_conversations — exit 0. 13 passed, 1 warning in 239.26s (0:03:59) Log: .test-storage/phase1-verification/test_conversations-final.log

- Phase 1 verification: docker exec -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/finalverify phase1-verification-api python -m pytest -q tests/test_handoff.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1-final-test_handoff — exit 0. 5 passed, 1 warning in 65.10s (0:01:05) Log: .test-storage/phase1-verification/test_handoff-final.log


## 2026-10-16 Phase 1 verification of e5e3761

- Starting HEAD: e5e376159b028c022f20fb03609de675816bd1b0. No push, deployment, cloud resources, paid model calls, direct .env/key-content inspection or printed secret values. Initial `docker compose ps --format json` was denied but may have internally parsed root dotenv; no-implicit-dotenv-read guarantee is UNVERIFIED. All subsequent container commands use plain Docker and explicit test settings. Isolated local PostgreSQL container on 127.0.0.1:55447; API checks container has current source mounted read-only, ENVIRONMENT=test. All pytest invocations run one file each; disposable databases only.
- Docker status initially sandbox-denied; approved Docker access showed no running containers. First disposable DB container attempt on port 55439 failed because the host port was in use; switched to 55447 without touching the existing listener.
- Initial host pytest from apps/api: `ENVIRONMENT=test DATABASE_URL=postgresql://postgres@127.0.0.1:55447/phase1verify ../../.venv/Scripts/python.exe -m pytest -q tests/test_tenant_route_matrix.py --tb=short -p no:cacheprovider --basetemp=../../.test-storage/phase1-verification/matrix-baseline` ? exit 1; EEEE. plus WinError 5 on basetemp. Moved pytest execution into the isolated API container, without bypassing OS controls.
- `docker exec -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/phase1verify phase1-verification-api python -m pytest -q tests/test_self_service_signup.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1-signup` ? exit 0; 4 passed, 1 warning in 5.81s.
- `docker exec -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/matrixverify phase1-verification-api python -m pytest -q tests/test_tenant_route_matrix.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1-matrix-expanded` ? exit 0; 5 passed, 1 warning in 32.07s. Staff no longer skipped on ordinary tenant routes; target-tenant membership asserted absent. Subsequent final file rerun records the added per-request assertion.
- `docker exec -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/concurrencyverify phase1-verification-api python -m pytest -q tests/test_members.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1-concurrent` ? exit 0; 8 passed, 1 warning in 7.91s, including synchronized DELETE/DELETE, PATCH/PATCH and DELETE/PATCH requests.
- `docker exec phase1-verification-api python -m mypy --no-incremental --cache-dir /tmp/phase1-mypy` ? baseline exit 1: 13 errors in 7 files (154 checked). First fix iteration: 6 Settings kwargs errors in 1 file. Final invocation exit 0: Success: no issues found in 154 source files (.test-storage/phase1-verification/mypy-final.log).
- From apps/web, `ENVIRONMENT=test DATABASE_URL=postgresql://postgres@127.0.0.1:55447/phase1verify E2E_API_PORT=18147 API_PROXY_TARGET=http://127.0.0.1:18147 npm.cmd test -- --reporter=line` ? first sandbox launch exit 1 spawn EPERM before tests; approved full run exit 0: 40 passed (4.7m). No ECONNRESET. Two ignored SSE cleanup connection-closed tracebacks under ui-redesign.spec.ts; no proxy or worker behavior changed. Log .test-storage/phase1-verification/playwright-full.log.
- Full Playwright repeated after owner-label cleanup, same command except DATABASE_URL=postgresql://postgres@127.0.0.1:55447/phase1final ? exit 0: 40 passed (4.1m), zero ECONNRESET/Failed-to-proxy/Traceback matches. Log .test-storage/phase1-verification/playwright-final-full.log. Neither run scoped tests or used retries.
- From root `npm.cmd run lint` then `npm.cmd run typecheck` ? both exit 0. Extra broad root Ruff invocation (`.venv/Scripts/python.exe -m ruff check --no-cache apps/api/app apps/api/tests apps/api/alembic`) found 13 pre-existing import/line-length errors; no lint-clean claim for the whole API. Container Ruff initially could not write its cache/read-only source; source checks use --no-cache or local Ruff. No unrelated formatting rewrite performed.
- Owner scan: `git grep -n -i -E 'owner|transfer-ownership|transfer_ownership|demo-owner' -- . ':!*.lock' ':!*.env*' ':!*key*'` plus tracked/untracked filename inventory. All authored source covered; inaccessible ignored temp/caches unverified. Complete per-hit classification and 77-route table: implementation/PHASE-01/VERIFICATION-e5e3761.md. Historical signed reports, legacy migrations/rejection tests, human product-owner wording, onboarding compatibility names and historical audit event identifiers intentionally retained.
- ECONNRESET investigation only: installed proxy 30s timeout, shared httpxy keep-alive agents, Uvicorn 5s idle timeout, client-disconnect destruction, /health vs /ready, migration subprocess handling, separate worker process and bounded DB pool reviewed. Historical overview /auth/me reset found; precise cause and historic widget/knowledge socket/load data remain UNVERIFIED. No network-path behavior changed.

- Phase 1 verification: docker exec -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/finalverify phase1-verification-api python -m pytest -q tests/test_inbox_list.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1-final-test_inbox_list — exit 0. 5 passed, 1 warning in 15.20s Log: .test-storage/phase1-verification/test_inbox_list-final.log

- Phase 1 verification: docker exec -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/finalverify phase1-verification-api python -m pytest -q tests/test_knowledge_uploads.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1-final-test_knowledge_uploads — exit 0. 19 passed, 1 warning in 8.52s Log: .test-storage/phase1-verification/test_knowledge_uploads-final.log

- Phase 1 verification: docker exec -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/finalverify phase1-verification-api python -m pytest -q tests/test_models_constraints.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1-final-test_models_constraints — exit 0. 13 passed, 1 warning in 1.03s Log: .test-storage/phase1-verification/test_models_constraints-final.log

- Phase 1 verification: docker exec -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/finalverify phase1-verification-api python -m pytest -q tests/test_platform.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1-final-test_platform — exit 0. 9 passed, 1 warning in 136.05s (0:02:16) Log: .test-storage/phase1-verification/test_platform-final.log

- Phase 1 verification: docker exec -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/finalverify phase1-verification-api python -m pytest -q tests/test_platform_ops.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1-final-test_platform_ops — exit 0. 4 passed, 1 warning in 4.22s Log: .test-storage/phase1-verification/test_platform_ops-final.log

- Phase 1 verification: docker exec -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/finalverify phase1-verification-api python -m pytest -q tests/test_quotas.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1-final-test_quotas — exit 0. 10 passed, 1 warning in 9.11s Log: .test-storage/phase1-verification/test_quotas-final.log

- Phase 1 verification: docker exec -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/finalverify phase1-verification-api python -m pytest -q tests/test_seed_demo.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1-final-test_seed_demo — exit 0. 21 passed, 1 warning in 3.52s Log: .test-storage/phase1-verification/test_seed_demo-final.log

- Phase 1 verification: docker exec -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/finalverify phase1-verification-api python -m pytest -q tests/test_tenants.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1-final-test_tenants — exit 0. 6 passed, 1 warning in 3.34s Log: .test-storage/phase1-verification/test_tenants-final.log

- Phase 1 verification: docker exec -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/finalverify phase1-verification-api python -m pytest -q tests/test_tenant_data.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1-final-test_tenant_data — exit 0. 2 passed, 1 warning in 4.79s Log: .test-storage/phase1-verification/test_tenant_data-final.log

- Phase 1 verification: docker exec -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/finalverify phase1-verification-api python -m pytest -q tests/test_tenant_route_matrix.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1-final-test_tenant_route_matrix — exit 0. 5 passed, 1 warning in 28.68s Log: .test-storage/phase1-verification/test_tenant_route_matrix-final.log

- Phase 1 verification: docker exec -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/finalverify phase1-verification-api python -m pytest -q tests/test_knowledge_pipeline.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1-final-test_knowledge_pipeline — exit 0. 9 passed, 1 warning in 36.31s Log: .test-storage/phase1-verification/test_knowledge_pipeline-final.log

- Phase 1 verification: docker exec -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/finalverify phase1-verification-api python -m pytest -q tests/test_jobs.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1-final-test_jobs — exit 0. 8 passed, 1 warning in 4.15s Log: .test-storage/phase1-verification/test_jobs-final.log

- Third full browser run after adding ordinary non-staff admin snippet assertions: from apps/web `ENVIRONMENT=test DATABASE_URL=postgresql://postgres@127.0.0.1:55447/phase1snippet E2E_API_PORT=18147 API_PROXY_TARGET=http://127.0.0.1:18147 npm.cmd test -- --reporter=line` ? exit 0; 40 passed (4.8m), no ECONNRESET or Failed-to-proxy matches. Four ignored SSE generator cleanup connection-closed tracebacks; no failures. Log .test-storage/phase1-verification/playwright-admin-full.log. No scoped rechecks.
- Final API total for this verification: 185 passed across 22 unique test files (latest result per file); this is targeted coverage, not a full 37-file API rerun. Every pytest invocation used one file. Full per-file output table is in the verification report.
- Changed Python implementation/test-file Ruff check ? exit 0, All checks passed. Exact file list is the changed core/config, main, tenants/deletion, widget/service, scripts/seed_demo and all changed Python test files; full API lint has pre-existing failures recorded above. Final API-container mypy ? exit 0; Success: no issues found in 154 source files.
- OpenAPI equality check inside API container via stdin Python (`create_app().openapi()` compared to `TENANT_ROUTE_ROLES`) ? exit 0: Actual tenant operations: 77; Declared operations: 77; Missing declarations: set(); Unused declarations: set(). First `python -c` attempt hit Windows quote stripping/SyntaxError, then stdin preserved source correctly.
- New browser test lint: initial direct root ESLint call exit 1 (no root eslint.config); rerun from apps/web `node_modules/.bin/eslint.cmd tests/roles-control.spec.ts --max-warnings 0` ? exit 0. Root npm lint/typecheck already passed; latest full browser run rebuilt the web app successfully.
- All fixes remain local commits, separately grouped by verification item. No merge, push, deployment or non-test database changes. Detailed result: implementation/PHASE-01/VERIFICATION-e5e3761.md.

- Phase 1 follow-up affected: `docker exec -e ENVIRONMENT=test -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/p1followaffected phase1-verification-api python -m pytest -q tests/test_tenant_route_matrix.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1follow-affected-test_tenant_route_matrix` ? exit 0; 6 passed, 1 warning in 26.30s. Log: `.test-storage/phase1-followup/affected-test_tenant_route_matrix.log`.

- Phase 1 follow-up affected: `docker exec -e ENVIRONMENT=test -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/p1followaffected phase1-verification-api python -m pytest -q tests/test_knowledge_pipeline.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1follow-affected-test_knowledge_pipeline` ? exit 0; 9 passed, 1 warning in 33.68s. Log: `.test-storage/phase1-followup/affected-test_knowledge_pipeline.log`.

- Phase 1 follow-up affected: `docker exec -e ENVIRONMENT=test -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/p1followaffected phase1-verification-api python -m pytest -q tests/test_knowledge_uploads.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1follow-affected-test_knowledge_uploads` ? exit 0; 19 passed, 1 warning in 10.43s. Log: `.test-storage/phase1-followup/affected-test_knowledge_uploads.log`.

- Phase 1 follow-up affected: `docker exec -e ENVIRONMENT=test -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/p1followaffected phase1-verification-api python -m pytest -q tests/test_bots.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1follow-affected-test_bots` ? exit 0; 4 passed, 1 warning in 4.56s. Log: `.test-storage/phase1-followup/affected-test_bots.log`.

- Phase 1 follow-up affected: `docker exec -e ENVIRONMENT=test -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/p1followaffected phase1-verification-api python -m pytest -q tests/test_members.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1follow-affected-test_members` ? exit 0; 8 passed, 1 warning in 5.53s. Log: `.test-storage/phase1-followup/affected-test_members.log`.

- Phase 1 follow-up affected: `docker exec -e ENVIRONMENT=test -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/p1followaffected phase1-verification-api python -m pytest -q tests/test_conversations_view.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1follow-affected-test_conversations_view` ? exit 1; 1 warning, 5 errors in 30.15s. Log: `.test-storage/phase1-followup/affected-test_conversations_view.log`.

- Phase 1 follow-up affected: `docker exec -e ENVIRONMENT=test -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/p1followaffected phase1-verification-api python -m pytest -q tests/test_widget_public.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1follow-affected-test_widget_public` ? exit 1; 1 passed, 1 warning, 13 errors in 71.72s (0:01:11). Log: `.test-storage/phase1-followup/affected-test_widget_public.log`.

- Phase 1 follow-up affected: `docker exec -e ENVIRONMENT=test -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/p1followaffected phase1-verification-api python -m pytest -q tests/test_tenant_data.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1follow-affected-test_tenant_data` ? exit 0; 2 passed, 1 warning in 4.16s. Log: `.test-storage/phase1-followup/affected-test_tenant_data.log`.

- Phase 1 follow-up affected-fix: `docker exec -e ENVIRONMENT=test -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/p1followaffected-fix phase1-verification-api python -m pytest -q tests/test_conversations_view.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1follow-affected-fix-test_conversations_view` ? exit 0; 5 passed, 1 warning in 79.08s (0:01:19). Log: `.test-storage/phase1-followup/affected-fix-test_conversations_view.log`.

## Phase 1 follow-up implementation (2026-10-16)
- Owner authorized local merge/tag/merged-branch cleanup; no push, deployment, cloud resources, paid calls, environment-file contents or Docker Compose used in this follow-up. Explicit ENVIRONMENT=test prevents Python dotenv loading; no web-directory .env filenames found. Plain Docker restarted only phase1-verification-db-2 and phase1-verification-api. Test source is mounted read-only; all databases are disposable and guarded by _test suffixes.
- Eight knowledge GET permissions changed to platform_staff_only. Bot status list/detail remain readable while config/locator are redacted for every client role; no separate snippet API exists. All client knowledge/install pages and nav hidden. Visitor and client thread citations redacted; client export excludes knowledge/config/citations while preserving client operational exports. Stored citations and staff review remain intact. No migrations required.
- Existing platform-linked deletion popup confirmed: preview counts, exact typed name, reason, cancel, immediate disablement. Added real browser coverage using an onboarded client with no staff membership; initial assertion expected 200 but actual successful DELETE is 204, corrected.
- From apps/web: `ENVIRONMENT=test npm.cmd run typecheck` and `npm.cmd run lint`: both exit 0. Next generated next-env.d.ts now references production route types consistently with the production E2E build.
- Initial `docker exec -e ENVIRONMENT=test phase1-verification-api python -m ruff check ...` and format attempt failed before linting: cache on read-only /app. Used --no-cache afterwards; no permissions bypass. Host `python -m ruff check apps/api/app apps/api/tests --no-cache` reported 9 issues (3 import order, 6 long lines, existing unrelated files); host formatter applied only changed files. Pinned container ruff check --no-cache on every changed API file then exit 0 (ruff-affected.log). API `docker exec -e ENVIRONMENT=test phase1-verification-api python -m mypy --no-incremental --cache-dir /tmp/p1follow-mypy`: exit 0, no issues in 154 source files.
- From apps/web: `ENVIRONMENT=test DATABASE_URL=postgresql://postgres@127.0.0.1:55447/p1followaffected E2E_API_PORT=18147 API_PROXY_TARGET=http://127.0.0.1:18147 npm.cmd test -- knowledge.spec.ts install.spec.ts roles-control.spec.ts platform.spec.ts widget.spec.ts --reporter=line`: exit 1; 11 passed, 2 failed (2.4m). Failures were new platform assertion expecting 200 vs 204 and old widget expectation that a source label remains a SPAN. Corrected both assertions. Log: .test-storage/phase1-followup/playwright-affected.log.
- From apps/web: same command with DATABASE_URL base p1followaffectedfix and only platform.spec.ts widget.spec.ts: exit 0; 6 passed (1.1m). Log: .test-storage/phase1-followup/playwright-affected-fix.log. Final affected spec coverage: knowledge 4, install 1, roles-control 2, platform 2, widget 4 = 13 passed. No full browser suite has run during implementation.
- Initial affected API conversation-view and widget-public files failed fixture setup because publish_draft still read revisions as admin. Changed shared knowledge_helpers.py to use staff; rechecks run one file at a time (affected-fix logs). Initial outcomes retained above, never overwritten.
- Full merge gate is reserved for main: exactly one recursive 37-file API pass (including tests/eval/test_eval.py), each pytest command has one file, plus exactly one unscoped Playwright run. No rerun for reporting.

- Phase 1 follow-up affected-fix: `docker exec -e ENVIRONMENT=test -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/p1followaffected-fix phase1-verification-api python -m pytest -q tests/test_widget_public.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1follow-affected-fix-test_widget_public` ? exit 0; 14 passed, 1 warning in 199.90s (0:03:19). Log: `.test-storage/phase1-followup/affected-fix-test_widget_public.log`.

- Affected checks complete: 67 passed across 8 unique API files (latest result per file); 13 passed across 5 affected browser specs. Explicit final file results remain recorded above. Source review confirms 77 exact tenant routes and no new endpoint. Untracked inventory: none; no untracked/ignored content deleted. .test-storage, Playwright output and inaccessible generated pytest temp directories are ignored.

- Phase 1 follow-up gate: `docker exec -e ENVIRONMENT=test -e EVAL_REAL_RERUN=0 -e REPO_IMPL_DIR=/tmp/p1follow-gate-eval -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/p1followgate phase1-verification-api python -m pytest -q tests/eval/test_eval.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1follow-gate-test_eval` ? exit 0; 2 passed, 1 warning in 12.92s. Log: `.test-storage/phase1-followup/gate-test_eval.log`.

- Phase 1 follow-up gate: `docker exec -e ENVIRONMENT=test -e EVAL_REAL_RERUN=0 -e REPO_IMPL_DIR=/tmp/p1follow-gate-eval -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/p1followgate phase1-verification-api python -m pytest -q tests/test_analytics.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1follow-gate-test_analytics` ? exit 0; 6 passed, 1 warning in 116.79s (0:01:56). Log: `.test-storage/phase1-followup/gate-test_analytics.log`.

- Phase 1 follow-up gate: `docker exec -e ENVIRONMENT=test -e EVAL_REAL_RERUN=0 -e REPO_IMPL_DIR=/tmp/p1follow-gate-eval -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/p1followgate phase1-verification-api python -m pytest -q tests/test_auth.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1follow-gate-test_auth` ? exit 0; 15 passed, 1 warning in 4.43s. Log: `.test-storage/phase1-followup/gate-test_auth.log`.

- Phase 1 follow-up gate: `docker exec -e ENVIRONMENT=test -e EVAL_REAL_RERUN=0 -e REPO_IMPL_DIR=/tmp/p1follow-gate-eval -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/p1followgate phase1-verification-api python -m pytest -q tests/test_bot_status.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1follow-gate-test_bot_status` ? exit 0; 5 passed, 1 warning in 78.69s (0:01:18). Log: `.test-storage/phase1-followup/gate-test_bot_status.log`.

- Phase 1 follow-up gate: `docker exec -e ENVIRONMENT=test -e EVAL_REAL_RERUN=0 -e REPO_IMPL_DIR=/tmp/p1follow-gate-eval -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/p1followgate phase1-verification-api python -m pytest -q tests/test_bots.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1follow-gate-test_bots` ? exit 0; 4 passed, 1 warning in 2.96s. Log: `.test-storage/phase1-followup/gate-test_bots.log`.

- Phase 1 follow-up gate: `docker exec -e ENVIRONMENT=test -e EVAL_REAL_RERUN=0 -e REPO_IMPL_DIR=/tmp/p1follow-gate-eval -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/p1followgate phase1-verification-api python -m pytest -q tests/test_change_requests.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1follow-gate-test_change_requests` ? exit 0; 1 passed, 1 warning in 3.31s. Log: `.test-storage/phase1-followup/gate-test_change_requests.log`.

- Merge gate on main, merge commit fde670f83c0f5e67e0ffe597a519f0ddd8d6c62b (parents 60745a7 and 4f5a00f), no conflicts. UI redesign 51bafec and foundation 1bea650 already ancestors of main; no duplicate merges.
- Single full unscoped browser gate from apps/web: `ENVIRONMENT=test DATABASE_URL=postgresql://postgres@127.0.0.1:55447/p1followgate E2E_API_PORT=18147 API_PROXY_TARGET=http://127.0.0.1:18147 npm.cmd test -- --reporter=line`: exit 0; 40 passed, 0 failed (3.3m), zero ECONNRESET. Log .test-storage/phase1-followup/playwright-gate.log. No browser rerun after this result.

- Phase 1 follow-up gate: `docker exec -e ENVIRONMENT=test -e EVAL_REAL_RERUN=0 -e REPO_IMPL_DIR=/tmp/p1follow-gate-eval -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/p1followgate phase1-verification-api python -m pytest -q tests/test_chat.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1follow-gate-test_chat` ? exit 0; 15 passed, 1 warning in 181.76s (0:03:01). Log: `.test-storage/phase1-followup/gate-test_chat.log`.

- Phase 1 follow-up gate: `docker exec -e ENVIRONMENT=test -e EVAL_REAL_RERUN=0 -e REPO_IMPL_DIR=/tmp/p1follow-gate-eval -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/p1followgate phase1-verification-api python -m pytest -q tests/test_contacts.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1follow-gate-test_contacts` ? exit 0; 1 passed, 1 warning in 14.88s. Log: `.test-storage/phase1-followup/gate-test_contacts.log`.

- Phase 1 follow-up gate: `docker exec -e ENVIRONMENT=test -e EVAL_REAL_RERUN=0 -e REPO_IMPL_DIR=/tmp/p1follow-gate-eval -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/p1followgate phase1-verification-api python -m pytest -q tests/test_conversations.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1follow-gate-test_conversations` ? exit 0; 13 passed, 1 warning in 190.28s (0:03:10). Log: `.test-storage/phase1-followup/gate-test_conversations.log`.

- Phase 1 follow-up gate: `docker exec -e ENVIRONMENT=test -e EVAL_REAL_RERUN=0 -e REPO_IMPL_DIR=/tmp/p1follow-gate-eval -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/p1followgate phase1-verification-api python -m pytest -q tests/test_conversations_view.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1follow-gate-test_conversations_view` ? exit 0; 5 passed, 1 warning in 77.42s (0:01:17). Log: `.test-storage/phase1-followup/gate-test_conversations_view.log`.

- Phase 1 follow-up gate: `docker exec -e ENVIRONMENT=test -e EVAL_REAL_RERUN=0 -e REPO_IMPL_DIR=/tmp/p1follow-gate-eval -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/p1followgate phase1-verification-api python -m pytest -q tests/test_cross_script.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1follow-gate-test_cross_script` ? exit 0; 3 passed, 1 warning in 36.68s. Log: `.test-storage/phase1-followup/gate-test_cross_script.log`.

- Phase 1 follow-up gate: `docker exec -e ENVIRONMENT=test -e EVAL_REAL_RERUN=0 -e REPO_IMPL_DIR=/tmp/p1follow-gate-eval -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/p1followgate phase1-verification-api python -m pytest -q tests/test_database_guard.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1follow-gate-test_database_guard` ? exit 0; 5 passed, 1 warning in 0.63s. Log: `.test-storage/phase1-followup/gate-test_database_guard.log`.

- Phase 1 follow-up gate: `docker exec -e ENVIRONMENT=test -e EVAL_REAL_RERUN=0 -e REPO_IMPL_DIR=/tmp/p1follow-gate-eval -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/p1followgate phase1-verification-api python -m pytest -q tests/test_followups_analytics.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1follow-gate-test_followups_analytics` ? exit 0; 2 passed, 1 warning in 32.00s. Log: `.test-storage/phase1-followup/gate-test_followups_analytics.log`.

- Phase 1 follow-up gate: `docker exec -e ENVIRONMENT=test -e EVAL_REAL_RERUN=0 -e REPO_IMPL_DIR=/tmp/p1follow-gate-eval -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/p1followgate phase1-verification-api python -m pytest -q tests/test_handoff.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1follow-gate-test_handoff` ? exit 0; 5 passed, 1 warning in 62.50s (0:01:02). Log: `.test-storage/phase1-followup/gate-test_handoff.log`.

- Phase 1 follow-up gate: `docker exec -e ENVIRONMENT=test -e EVAL_REAL_RERUN=0 -e REPO_IMPL_DIR=/tmp/p1follow-gate-eval -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/p1followgate phase1-verification-api python -m pytest -q tests/test_health.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1follow-gate-test_health` ? exit 0; 6 passed, 1 warning in 1.77s. Log: `.test-storage/phase1-followup/gate-test_health.log`.

- Phase 1 follow-up gate: `docker exec -e ENVIRONMENT=test -e EVAL_REAL_RERUN=0 -e REPO_IMPL_DIR=/tmp/p1follow-gate-eval -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/p1followgate phase1-verification-api python -m pytest -q tests/test_inbox_list.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1follow-gate-test_inbox_list` ? exit 0; 5 passed, 1 warning in 13.30s. Log: `.test-storage/phase1-followup/gate-test_inbox_list.log`.

- Phase 1 follow-up gate: `docker exec -e ENVIRONMENT=test -e EVAL_REAL_RERUN=0 -e REPO_IMPL_DIR=/tmp/p1follow-gate-eval -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/p1followgate phase1-verification-api python -m pytest -q tests/test_invitations.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1follow-gate-test_invitations` ? exit 0; 6 passed, 1 warning in 6.20s. Log: `.test-storage/phase1-followup/gate-test_invitations.log`.

- Phase 1 follow-up gate: `docker exec -e ENVIRONMENT=test -e EVAL_REAL_RERUN=0 -e REPO_IMPL_DIR=/tmp/p1follow-gate-eval -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/p1followgate phase1-verification-api python -m pytest -q tests/test_jobs.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1follow-gate-test_jobs` ? exit 0; 8 passed, 1 warning in 2.75s. Log: `.test-storage/phase1-followup/gate-test_jobs.log`.

- Phase 1 follow-up gate: `docker exec -e ENVIRONMENT=test -e EVAL_REAL_RERUN=0 -e REPO_IMPL_DIR=/tmp/p1follow-gate-eval -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/p1followgate phase1-verification-api python -m pytest -q tests/test_knowledge_parsers.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1follow-gate-test_knowledge_parsers` ? exit 0; 27 passed, 1 warning in 3.43s. Log: `.test-storage/phase1-followup/gate-test_knowledge_parsers.log`.

- Phase 1 follow-up gate: `docker exec -e ENVIRONMENT=test -e EVAL_REAL_RERUN=0 -e REPO_IMPL_DIR=/tmp/p1follow-gate-eval -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/p1followgate phase1-verification-api python -m pytest -q tests/test_knowledge_pipeline.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1follow-gate-test_knowledge_pipeline` ? exit 0; 9 passed, 1 warning in 31.68s. Log: `.test-storage/phase1-followup/gate-test_knowledge_pipeline.log`.

- Phase 1 follow-up gate: `docker exec -e ENVIRONMENT=test -e EVAL_REAL_RERUN=0 -e REPO_IMPL_DIR=/tmp/p1follow-gate-eval -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/p1followgate phase1-verification-api python -m pytest -q tests/test_knowledge_uploads.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1follow-gate-test_knowledge_uploads` ? exit 0; 19 passed, 1 warning in 9.28s. Log: `.test-storage/phase1-followup/gate-test_knowledge_uploads.log`.

- Phase 1 follow-up gate: `docker exec -e ENVIRONMENT=test -e EVAL_REAL_RERUN=0 -e REPO_IMPL_DIR=/tmp/p1follow-gate-eval -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/p1followgate phase1-verification-api python -m pytest -q tests/test_members.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1follow-gate-test_members` ? exit 0; 8 passed, 1 warning in 4.29s. Log: `.test-storage/phase1-followup/gate-test_members.log`.

- Phase 1 follow-up gate: `docker exec -e ENVIRONMENT=test -e EVAL_REAL_RERUN=0 -e REPO_IMPL_DIR=/tmp/p1follow-gate-eval -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/p1followgate phase1-verification-api python -m pytest -q tests/test_migrations.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1follow-gate-test_migrations` ? exit 0; 1 passed, 1 warning in 6.40s. Log: `.test-storage/phase1-followup/gate-test_migrations.log`.

- Phase 1 follow-up gate: `docker exec -e ENVIRONMENT=test -e EVAL_REAL_RERUN=0 -e REPO_IMPL_DIR=/tmp/p1follow-gate-eval -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/p1followgate phase1-verification-api python -m pytest -q tests/test_models_constraints.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1follow-gate-test_models_constraints` ? exit 0; 13 passed, 1 warning in 1.08s. Log: `.test-storage/phase1-followup/gate-test_models_constraints.log`.

- Phase 1 follow-up gate: `docker exec -e ENVIRONMENT=test -e EVAL_REAL_RERUN=0 -e REPO_IMPL_DIR=/tmp/p1follow-gate-eval -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/p1followgate phase1-verification-api python -m pytest -q tests/test_platform.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1follow-gate-test_platform` ? exit 0; 9 passed, 1 warning in 127.57s (0:02:07). Log: `.test-storage/phase1-followup/gate-test_platform.log`.

- Phase 1 follow-up gate: `docker exec -e ENVIRONMENT=test -e EVAL_REAL_RERUN=0 -e REPO_IMPL_DIR=/tmp/p1follow-gate-eval -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/p1followgate phase1-verification-api python -m pytest -q tests/test_platform_ops.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1follow-gate-test_platform_ops` ? exit 0; 4 passed, 1 warning in 3.39s. Log: `.test-storage/phase1-followup/gate-test_platform_ops.log`.

- Phase 1 follow-up gate: `docker exec -e ENVIRONMENT=test -e EVAL_REAL_RERUN=0 -e REPO_IMPL_DIR=/tmp/p1follow-gate-eval -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/p1followgate phase1-verification-api python -m pytest -q tests/test_quotas.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1follow-gate-test_quotas` ? exit 0; 10 passed, 1 warning in 5.55s. Log: `.test-storage/phase1-followup/gate-test_quotas.log`.

- Phase 1 follow-up gate: `docker exec -e ENVIRONMENT=test -e EVAL_REAL_RERUN=0 -e REPO_IMPL_DIR=/tmp/p1follow-gate-eval -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/p1followgate phase1-verification-api python -m pytest -q tests/test_retrieval.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1follow-gate-test_retrieval` ? exit 0; 9 passed, 1 warning in 123.62s (0:02:03). Log: `.test-storage/phase1-followup/gate-test_retrieval.log`.

- Phase 1 follow-up gate: `docker exec -e ENVIRONMENT=test -e EVAL_REAL_RERUN=0 -e REPO_IMPL_DIR=/tmp/p1follow-gate-eval -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/p1followgate phase1-verification-api python -m pytest -q tests/test_seed_demo.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1follow-gate-test_seed_demo` ? exit 0; 21 passed, 1 warning in 2.61s. Log: `.test-storage/phase1-followup/gate-test_seed_demo.log`.

- Phase 1 follow-up gate: `docker exec -e ENVIRONMENT=test -e EVAL_REAL_RERUN=0 -e REPO_IMPL_DIR=/tmp/p1follow-gate-eval -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/p1followgate phase1-verification-api python -m pytest -q tests/test_self_service_signup.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1follow-gate-test_self_service_signup` ? exit 0; 4 passed, 1 warning in 3.38s. Log: `.test-storage/phase1-followup/gate-test_self_service_signup.log`.

- Phase 1 follow-up gate: `docker exec -e ENVIRONMENT=test -e EVAL_REAL_RERUN=0 -e REPO_IMPL_DIR=/tmp/p1follow-gate-eval -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/p1followgate phase1-verification-api python -m pytest -q tests/test_startup_guard.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1follow-gate-test_startup_guard` ? exit 0; 5 passed, 1 warning in 1.15s. Log: `.test-storage/phase1-followup/gate-test_startup_guard.log`.

- Phase 1 follow-up gate: `docker exec -e ENVIRONMENT=test -e EVAL_REAL_RERUN=0 -e REPO_IMPL_DIR=/tmp/p1follow-gate-eval -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/p1followgate phase1-verification-api python -m pytest -q tests/test_tenant_data.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1follow-gate-test_tenant_data` ? exit 0; 2 passed, 1 warning in 3.77s. Log: `.test-storage/phase1-followup/gate-test_tenant_data.log`.

- Phase 1 follow-up gate: `docker exec -e ENVIRONMENT=test -e EVAL_REAL_RERUN=0 -e REPO_IMPL_DIR=/tmp/p1follow-gate-eval -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/p1followgate phase1-verification-api python -m pytest -q tests/test_tenant_route_matrix.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1follow-gate-test_tenant_route_matrix` ? exit 0; 6 passed, 1 warning in 26.36s. Log: `.test-storage/phase1-followup/gate-test_tenant_route_matrix.log`.

- Phase 1 follow-up gate: `docker exec -e ENVIRONMENT=test -e EVAL_REAL_RERUN=0 -e REPO_IMPL_DIR=/tmp/p1follow-gate-eval -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/p1followgate phase1-verification-api python -m pytest -q tests/test_tenants.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1follow-gate-test_tenants` ? exit 0; 6 passed, 1 warning in 3.57s. Log: `.test-storage/phase1-followup/gate-test_tenants.log`.

- Phase 1 follow-up gate: `docker exec -e ENVIRONMENT=test -e EVAL_REAL_RERUN=0 -e REPO_IMPL_DIR=/tmp/p1follow-gate-eval -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/p1followgate phase1-verification-api python -m pytest -q tests/test_widget_appearance.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1follow-gate-test_widget_appearance` ? exit 0; 3 passed, 1 warning in 43.63s. Log: `.test-storage/phase1-followup/gate-test_widget_appearance.log`.

- Phase 1 follow-up gate: `docker exec -e ENVIRONMENT=test -e EVAL_REAL_RERUN=0 -e REPO_IMPL_DIR=/tmp/p1follow-gate-eval -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/p1followgate phase1-verification-api python -m pytest -q tests/test_widget_leads.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1follow-gate-test_widget_leads` ? exit 0; 5 passed, 1 warning in 80.10s (0:01:20). Log: `.test-storage/phase1-followup/gate-test_widget_leads.log`.

- Phase 1 follow-up gate: `docker exec -e ENVIRONMENT=test -e EVAL_REAL_RERUN=0 -e REPO_IMPL_DIR=/tmp/p1follow-gate-eval -e DATABASE_URL=postgresql://postgres@host.docker.internal:55447/p1followgate phase1-verification-api python -m pytest -q tests/test_widget_public.py --tb=short -p no:cacheprovider --basetemp=/tmp/p1follow-gate-test_widget_public` ? exit 0; 14 passed, 1 warning in 189.12s (0:03:09). Log: `.test-storage/phase1-followup/gate-test_widget_public.log`.

- Final single API gate on main: 282 passed, 0 failed across all 37 files, each invoked once individually. Full per-file table: implementation/PHASE-01/FOLLOW-UP-MERGE-REPORT.md. Offline eval report copied with `docker cp phase1-verification-api:/tmp/p1follow-gate-eval/implementation/PHASE-03/EVAL-REPORT.md .test-storage/phase1-followup/eval-gate.md` (exit 0); historical tracked eval report unchanged.
- Local cleanup commands, all exit 0: `git tag phase-1-complete fde670f83c0f5e67e0ffe597a519f0ddd8d6c62b`; `git branch -d feat/p1-01-foundation feat/product-cycle-1 feat/ui-redesign`; `git worktree prune`. Deleted tips: 1bea650, 4f5a00f, 51bafec, all merged into main. One worktree retained on main; no secondary worktree removal. Untracked inventory before cleanup: empty. Ignored files/logs/storage retained; no force, push, reset or clean operation. No unmerged local branches remain.
- Evidence-only report commit follows the tested merge. No source changed after the merge gate, and no full or affected tests were rerun for reporting. Whole-repository host Ruff has 9 existing findings; changed-file pinned Ruff, web lint/typecheck and full API mypy passed. Hosted CI/live providers/production remain unverified.

## 2026-10-16 RAG Phase 2 — Stage 0 checkpoint

Scope: Stage 0 only. Report: `implementation/RAG-PHASE-02/STAGE-0-REPORT.md`. The live baseline stopped at its first HTTP 429; Stage 0 remains pending owner disposition. No automatic retries, waiting for quota, model rotation, or Stage 1 work.

Setup commands and outcomes:

- `git log --oneline phase-1-complete..HEAD` on initial main: only `946f2cb docs: record Phase 1 merge gate and safe cleanup`.
- `git merge-base --is-ancestor phase-1-complete HEAD`: exit 0. Tag points to `fde670f83c0f5e67e0ffe597a519f0ddd8d6c62b`; initial HEAD `946f2cb16989379a4d0996db6434932e5feda18d`.
- `git switch -c feat/rag-phase-2`: initially sandbox-denied writing refs; approved retry exit 0.
- `git add -- docs/RAG-PLAN-v2.md docs/RAG-PHASE-PROMPT-v2.md`; `git commit -m "docs(rag): record approved Phase 2 plan and execution gates"`: exit 0, first commit `0c70c5b`. Corrected the filename reference in the prompt.
- Process-environment presence checks, including elevated execution: both required variables not set, model count 0; no values printed. Owner then explicitly allowed scoped `.env` loading. Both entries were set there; chain was non-JSON comma-separated text with 3 candidates, not all passing the `:free` guard.
- `.venv/Scripts/python.exe .test-storage/rag-stage-0/configure-chain.py`: first invocation exit 1, single public catalog lookup succeeded but same-model zero-priced `:free` variants were absent for positions 1 and 3; no mutation. After explicit owner approval to replace unavailable entries, same command exit 0 using only cached catalog: retained one entry, replaced two, updated only the chain to JSON with 3 verified zero-priced `:free` IDs. Key unchanged. No key/model values displayed. Exactly 1 catalog request overall; no model smoke tests. `.env` remains ignored and unstaged.
- Owner explicitly approved raw FTS plus at most one generation call, disabling rewrite/translation model calls for this baseline. This is an eval-only budget choice; production chat is unchanged.

Disposable infrastructure, plain Docker only:

```powershell
docker run --detach --name rag-stage0-postgres --publish 127.0.0.1:55461:5432 --env POSTGRES_HOST_AUTH_METHOD=trust --env POSTGRES_DB=rag_stage0_base_test postgres:17
docker run --detach --name rag-stage0-checks --env ENVIRONMENT=test --mount 'type=bind,source=D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai\apps\api,target=/app,readonly' --workdir /app saas-chats-ai-p5-close-checks:latest sleep infinity
```

Both exit 0. No running containers initially. Test trust authentication is restricted to the disposable container's loopback-published port. No existing application database was used. The checks mount intentionally stays read-only.

Affected Playwright commands, from `apps/web` (three scheduled runs, no retries):

```powershell
$env:ENVIRONMENT='test'; $env:DATABASE_URL='postgresql://postgres@127.0.0.1:55461/rag_stage0_run1_test'; $env:E2E_API_PORT='18161'; $env:API_PROXY_TARGET='http://127.0.0.1:18161'; $env:STORAGE_ROOT='D:/Projects/Work Projects/The Osiris Labs/SAAS-chats-ai/.test-storage/rag-stage-0/storage-run1'; npm.cmd test -- tests/widget.spec.ts tests/knowledge.spec.ts tests/overview.spec.ts --reporter=line 2>&1 | Tee-Object -FilePath '../../.test-storage/rag-stage-0/playwright-run1.log'; exit $LASTEXITCODE
$env:ENVIRONMENT='test'; $env:DATABASE_URL='postgresql://postgres@127.0.0.1:55461/rag_stage0_run2_test'; $env:E2E_API_PORT='18161'; $env:API_PROXY_TARGET='http://127.0.0.1:18161'; $env:STORAGE_ROOT='D:/Projects/Work Projects/The Osiris Labs/SAAS-chats-ai/.test-storage/rag-stage-0/storage-run2'; npm.cmd test -- tests/widget.spec.ts tests/knowledge.spec.ts tests/overview.spec.ts --reporter=line 2>&1 | Tee-Object -FilePath '../../.test-storage/rag-stage-0/playwright-run2.log'; exit $LASTEXITCODE
$env:ENVIRONMENT='test'; $env:DATABASE_URL='postgresql://postgres@127.0.0.1:55461/rag_stage0_run3_test'; $env:E2E_API_PORT='18161'; $env:API_PROXY_TARGET='http://127.0.0.1:18161'; $env:STORAGE_ROOT='D:/Projects/Work Projects/The Osiris Labs/SAAS-chats-ai/.test-storage/rag-stage-0/storage-run3'; npm.cmd test -- tests/widget.spec.ts tests/knowledge.spec.ts tests/overview.spec.ts --reporter=line 2>&1 | Tee-Object -FilePath '../../.test-storage/rag-stage-0/playwright-run3.log'; exit $LASTEXITCODE
```

- Run 1: exit 0, 10 passed (1.8m).
- Run 2: exit 1, 9 passed and 1 failed (2.2m). `overview.spec.ts:127` expected Messages: 2, got 1. Existing helper accepted an old AI bubble and navigated before the new POST completed. Preserved trace `.test-storage/rag-stage-0/run2-overview-trace.zip` shows POST statuses 201 then -1. Added explicit wait for the new POST 201, without weakening any message-count assertion.
- Run 3 after synchronization fix: exit 0, 10 passed (1.6m).
- All three logs: 0 ECONNRESET, 0 Failed-to-proxy, 0 Traceback matches. PowerShell Tee logs are UTF-16; the first UTF-8 log-reading attempt failed with UnicodeDecodeError and was corrected to UTF-16 without rerunning tests. An earlier local raw-answer summary failed with a Windows console UnicodeEncodeError; rerendered as UTF-8. Neither error came from the widget/API or caused provider calls.
- Initial Uvicorn default probe had a PowerShell/native quoting SyntaxError; corrected stdin-based probe verified default 5 seconds. Same API socket test before/after 6 seconds idle: HTTP 200 both times, socket identity unchanged, exit 0. Log `.test-storage/rag-stage-0/keep-alive-socket.log`. The socket check used Python `http.client.HTTPConnection('127.0.0.1', 18161, timeout=10)`, read `/health`, saved the socket, slept 6 seconds, read `/health` again, and asserted both statuses and socket identity. No model calls.
- Retained 65-second keep-alive in Dockerfile, stack command and E2E launcher. ECONNRESET root cause remains UNVERIFIED; it did not reproduce. Latest instruction's affected-spec-only rule takes precedence over the original prompt's three-full-suite wording. No full suites run.

Affected API budget/checkpoint tests (only this new file; all HTTP mocked):

```powershell
docker exec -e DATABASE_URL=postgresql://postgres@host.docker.internal:55461/rag_stage0_checks -e ENVIRONMENT=test rag-stage0-checks python -m pytest -q tests/test_rag_stage0_baseline.py --tb=short -p no:cacheprovider --basetemp=/tmp/rag-stage0-budget
docker exec -e DATABASE_URL=postgresql://postgres@host.docker.internal:55461/rag_stage0_checks -e ENVIRONMENT=test rag-stage0-checks python -m pytest -q tests/test_rag_stage0_baseline.py --tb=short -p no:cacheprovider --basetemp=/tmp/rag-stage0-budget-final
docker exec -e DATABASE_URL=postgresql://postgres@host.docker.internal:55461/rag_stage0_checks -e ENVIRONMENT=test rag-stage0-checks python -m pytest -q tests/test_rag_stage0_baseline.py --tb=short -p no:cacheprovider --basetemp=/tmp/rag-stage0-budget-passed
```

- Initial: exit 0, 12 passed, 1 existing Starlette warning (1.52s); `budget-tests.log`.
- Added real-FTS/replay integration test: exit 1, 12 passed, 1 failed (1.72s); `budget-tests-final.log`. Found current `RetrievalResult.candidates` is never populated. Corrected eval instrumentation to observe the existing ranked SQL function, without extra retrieval queries or production changes.
- Final: exit 0, **13 passed**, 1 existing warning (1.44s); `budget-tests-passed.log`. Tests cover immediate quota/auth stop, no retries, one fallback maximum, preprocessing skipped without requests, checkpoint/redaction, disposable DB guard, real FTS expected-ID hit and replay prevention.

Static checks:

- `npm.cmd run lint` and `npm.cmd run typecheck` from root: exit 0 initially and after the overview synchronization fix.
- `node node_modules/prettier/bin/prettier.cjs --check apps/web/tests/e2e-api-setup.ts infra/compose.yaml`: initially reported harness formatting; formatted only the touched harness. After editing overview, changed-file check reported overview formatting; formatted only that touched spec. Final `node node_modules/prettier/bin/prettier.cjs --check apps/web/tests/e2e-api-setup.ts apps/web/tests/overview.spec.ts infra/compose.yaml`: exit 0.
- `docker exec rag-stage0-checks python -m ruff check --no-cache app tests`: exit 1; **9 pre-existing findings**, unchanged (full list in Stage 0 report; log `ruff-existing.log`). No broad fixes.
- Initial `docker exec rag-stage0-checks python -m ruff check --no-cache --fix scripts/rag_stage0_baseline.py tests/test_rag_stage0_baseline.py`: could not write on read-only mount. Used host Ruff only for these two new files. Initial checks found import/format/line-length issues and B023 capture; fixed. Initial expanded mypy found a test-only implicit-reexport reference; corrected. These initial failures are not represented as passing checks.
- Final `docker exec rag-stage0-checks python -m ruff check --no-cache scripts/rag_stage0_baseline.py tests/test_rag_stage0_baseline.py`: exit 0, all checks passed.
- Final `docker exec rag-stage0-checks python -m ruff format --no-cache --check scripts/rag_stage0_baseline.py tests/test_rag_stage0_baseline.py`: exit 0, 2 files already formatted.
- Final `docker exec rag-stage0-checks python -m mypy --no-incremental --cache-dir /tmp/rag-stage0-passed-mypy app tests alembic scripts/rag_stage0_baseline.py`: exit 0, no issues in **156 source files**. Earlier pre-script baseline mypy passed for 154 files; intermediate `app tests scripts/...` invocation passed 142; first complete 156-file check failed only on the corrected test reference.
- `git diff --check`: passed before report updates; final check recorded below. No tests are rerun for documentation/reporting.

Fixture validation: `.venv/Scripts/python.exe -` with an inline AST/JSON check verified 32 unique case IDs, all five types, 10 unanswerable cases, the first 20 cases in Arabic/mixed/unanswerable buckets, and expected source keys present in seed_demo.FAQS. No eval/provider request. Synthetic `Settings(_env_file=None)` checks via `../../.venv/Scripts/python.exe -` from apps/api accepted JSON-array whitespace, preserved inside-string whitespace, and rejected comma/space-separated non-JSON input. No real dotenv/key reads in those synthetic checks.

Single live eval command, from `apps/api`:

```powershell
$env:ENVIRONMENT='test'; $env:DATABASE_URL='postgresql://postgres@127.0.0.1:55461/rag_stage0_baseline_test'; Remove-Item Env:CHAT_STUB_MODEL -ErrorAction SilentlyContinue; ../../.venv/Scripts/python.exe -m scripts.rag_stage0_baseline --database-url postgresql://postgres@127.0.0.1:55461/rag_stage0_baseline_test --cases ../../implementation/RAG-PHASE-02/stage-0-eval.jsonl --output ../../.test-storage/rag-stage-0/baseline --scoped-dotenv ../../.env 2>&1 | Tee-Object -FilePath '../../.test-storage/rag-stage-0/baseline-run.log'; exit $LASTEXITCODE
```

Exit **2**, immediate stop at first HTTP 429 on `mixed-booking`; **9/32 completed**, 1 quota-stopped, 22 unattempted. **5 completion requests** (HTTP statuses: four 200, one 429), **1 catalog request** overall. The quota-stopped question used its primary attempt and one allowed fallback; no requests followed 429. No rerun or resume. Results/journal are UTF-8, flushed and fsynced per attempted question, under `.test-storage/rag-stage-0/baseline/`.

Partial metrics on completed cases only: hit@8 **3/9 (33.3%)**, wrong refusals **6/9 (66.7%)**, returned citations valid **3/3**, internal-marker matches **0/9**. Arabic 0/6 hits with six wrong refusals; mixed 3/3 completed hits and correct prices/hours. Unanswerable refusal correctness, paraphrases, follow-ups, complete-set quality and exhaustive widget/API error safety remain UNVERIFIED. Partial metrics are not full-set results. Owner was immediately asked to keep Stage 0 pending or accept the partial baseline at STOP 0. One Stage 0 implementation commit is deferred pending that answer; only first docs commit exists so far.

- Final `git diff --check` after the report/progress update: exit 0. No test reruns for docs/reporting.
- `docker stop rag-stage0-checks rag-stage0-postgres`: exit 0. Only these disposable containers stopped; data and raw checkpoints preserved for an explicitly approved continuation. No removal or destructive cleanup.

## 2026-10-16 Whole-phase continuation — Stage 0

Owner changed numbered STOP gates to checkpoints and persistent quota stops to
chat-only PENDING states; explicitly retained minimal client bot navigation
fields while hiding all operator data. Overrides: `docs/rag-phase/EXECUTION-OVERRIDES.md`.
Latest no-dotenv instruction supersedes the earlier scoped permission. Process
checks: both required variables not set, chain length 0. No new provider calls.

- `docker start rag-stage0-postgres rag-stage0-checks`: exit 0, preserved disposable containers only.
- `docker exec -e DATABASE_URL=postgresql://postgres@host.docker.internal:55461/rag_stage0_checks -e ENVIRONMENT=test rag-stage0-checks python -m pytest -q tests/test_rag_stage0_baseline.py --tb=short -p no:cacheprovider --basetemp=/tmp/rag-stage0-resume`: exit 0, **14 passed**, 1 existing warning, 3.72s. Log `.test-storage/rag-stage-0/budget-tests-resume.log`.
- `docker exec rag-stage0-checks python -m ruff check --no-cache scripts/rag_stage0_baseline.py tests/test_rag_stage0_baseline.py`: exit 0.
- `docker exec rag-stage0-checks python -m ruff format --no-cache --check scripts/rag_stage0_baseline.py tests/test_rag_stage0_baseline.py`: exit 0, two files formatted.
- `docker exec rag-stage0-checks python -m mypy --no-incremental --cache-dir /tmp/rag-stage0-commit-mypy app tests alembic scripts/rag_stage0_baseline.py`: exit 0, **156 source files**.
- From apps/api, with ENVIRONMENT=test, DATABASE_URL=postgresql://postgres@127.0.0.1:55461/rag_stage0_baseline_test, CHAT_STUB_MODEL unset: `../../.venv/Scripts/python.exe -m scripts.rag_stage0_baseline --database-url postgresql://postgres@127.0.0.1:55461/rag_stage0_baseline_test --cases ../../implementation/RAG-PHASE-02/stage-0-eval.jsonl --output ../../.test-storage/rag-stage-0/baseline --retrieval-only`: exit 0, all **32** cases, **0 chat/embedding requests**. Existing live artifacts unchanged. Expected-source hits: Arabic 0/6, mixed 4/4, paraphrase 3/8, follow-up 2/4; answerable total 9/22. Unanswerable empty evidence 6/10; generation/refusal correctness for remaining cases PENDING.
- Reused the already completed three affected Playwright runs, without rerunning for reporting. Full suites remain reserved for the final exit gate.

## 2026-10-16 RAG Stage 1 — embedding foundation

Stage 0 implementation committed locally as `ba7ffa0`. Stage 1 adds the fixed
1024-dim schema, three provider adapters, staff-only settings/backfill routes,
ingestion scheduling, and resumable/fenced job processing. See
`docs/rag-phase/STAGE-1-REPORT.md`. Chat requests used: **0**. Real OpenAI calls:
**0**. Ollama probe unavailable; deterministic test-only vectors, no model pull.

Infrastructure: `docker run --detach --name rag-phase2-postgres --publish 127.0.0.1:55462:5432 --env POSTGRES_HOST_AUTH_METHOD=trust --env POSTGRES_DB=rag_phase2_base_test pgvector/pgvector:pg17` — exit 0. Preserved Stage 0 database on port 55461 untouched by the vector migration. First native-quoted Ollama probe had a SyntaxError; corrected stdin-based HTTPX probe to `http://host.docker.internal:11434/api/tags` reported unavailable. No retry/model pull/provider credential used.

Exact affected API commands (all run with mocked provider HTTP/test vectors and
ENVIRONMENT=test in the checks container; each database is disposable):

```text
docker exec -e DATABASE_URL=postgresql://postgres@host.docker.internal:55462/rag_stage1 -e ENVIRONMENT=test rag-stage0-checks python -m pytest -q tests/test_embedding_foundation.py --tb=short -p no:cacheprovider --basetemp=/tmp/rag-stage1-foundation
docker exec -e DATABASE_URL=postgresql://postgres@host.docker.internal:55462/rag_stage1 -e ENVIRONMENT=test rag-stage0-checks python -m pytest -q tests/test_embedding_foundation.py --tb=short -p no:cacheprovider --basetemp=/tmp/rag-stage1-foundation-fixed
docker exec -e DATABASE_URL=postgresql://postgres@host.docker.internal:55462/rag_stage1 -e ENVIRONMENT=test rag-stage0-checks python -m pytest -q tests/test_embedding_foundation.py --tb=short -p no:cacheprovider --basetemp=/tmp/rag-stage1-foundation-final
docker exec -e DATABASE_URL=postgresql://postgres@host.docker.internal:55462/rag_stage1_pipeline -e ENVIRONMENT=test rag-stage0-checks python -m pytest -q tests/test_knowledge_pipeline.py --tb=short -p no:cacheprovider --basetemp=/tmp/rag-stage1-pipeline
docker exec -e DATABASE_URL=postgresql://postgres@host.docker.internal:55462/rag_stage1_pipeline -e ENVIRONMENT=test rag-stage0-checks python -m pytest -q tests/test_knowledge_pipeline.py --tb=short -p no:cacheprovider --basetemp=/tmp/rag-stage1-pipeline-fixed
docker exec -e DATABASE_URL=postgresql://postgres@host.docker.internal:55462/rag_stage1_matrix -e ENVIRONMENT=test rag-stage0-checks python -m pytest -q tests/test_tenant_route_matrix.py --tb=short -p no:cacheprovider --basetemp=/tmp/rag-stage1-matrix
docker exec -e DATABASE_URL=postgresql://postgres@host.docker.internal:55462/rag_stage1_migrations -e ENVIRONMENT=test rag-stage0-checks python -m pytest -q tests/test_migrations.py --tb=short -p no:cacheprovider --basetemp=/tmp/rag-stage1-migrations
docker exec -e DATABASE_URL=postgresql://postgres@host.docker.internal:55462/rag_stage1_jobs -e ENVIRONMENT=test rag-stage0-checks python -m pytest -q tests/test_jobs.py --tb=short -p no:cacheprovider --basetemp=/tmp/rag-stage1-jobs
docker exec -e DATABASE_URL=postgresql://postgres@host.docker.internal:55462/rag_stage1_startup -e ENVIRONMENT=test rag-stage0-checks python -m pytest -q tests/test_startup_guard.py --tb=short -p no:cacheprovider --basetemp=/tmp/rag-stage1-startup
```

Outcomes in command order: foundation initial 9 passed/1 failed (unflushed test
setup pointer), fixed 10 passed, final with new lease-fence test **11 passed**
(9.68s); pipeline initial 6 passed/3 failed (old single-job assumptions), fixed
**9 passed** (32.15s); matrix **6 passed** (23.58s); migrations **1 passed**
(4.83s); jobs **8 passed** (3.60s); startup **5 passed** (1.82s). Each has the
existing Starlette warning. Logs: `.test-storage/rag-stage-0/stage1-*.log`.

Static commands:

- `docker exec rag-stage0-checks python -m mypy --no-incremental --cache-dir /tmp/rag-stage1-first-mypy`: initial exit 1, three object/counter typing errors; fixed with explicit integer narrowing. Intermediate and final checks passed.
- Final `docker exec rag-stage0-checks python -m mypy --no-incremental --cache-dir /tmp/rag-stage1-commit-mypy`: exit 0, **161 source files**.
- `docker exec rag-stage0-checks python -m ruff check --no-cache app/embeddings app/db/models/types.py app/db/models/core.py app/core/config.py app/jobs/runner.py app/main.py app/core/permissions.py alembic/versions/0014_rag_embeddings.py tests/test_tenant_route_matrix.py tests/test_embedding_foundation.py tests/test_knowledge_pipeline.py`: exit 0 after initial new-file line/import formatting fixes.
- Same file scope with `python -m ruff format --no-cache --check`: exit 0, **14 files** formatted.
- `docker exec rag-stage0-checks python -m ruff check --no-cache --output-format concise app tests`: exactly **9 pre-existing findings**, exit 1; no new findings. Subsequent combined command's overall exit 0 came from the successful format check, not a repo-wide Ruff pass.
- `npm.cmd run lint`; `npm.cmd run typecheck`: exit 0. Changed E2E launcher Prettier check exit 0.

Affected browser command from apps/web:

```powershell
$env:ENVIRONMENT='test'; $env:DATABASE_URL='postgresql://postgres@127.0.0.1:55462/rag_stage1_browser_test'; $env:E2E_API_PORT='18162'; $env:API_PROXY_TARGET='http://127.0.0.1:18162'; $env:STORAGE_ROOT='D:/Projects/Work Projects/The Osiris Labs/SAAS-chats-ai/.test-storage/rag-stage-0/stage1-browser-storage'; npm.cmd test -- tests/widget.spec.ts tests/knowledge.spec.ts tests/overview.spec.ts --reporter=line 2>&1 | Tee-Object -FilePath '../../.test-storage/rag-stage-0/stage1-browser.log'; exit $LASTEXITCODE
```

Exit 0: **10 passed (1.7m)**. No ECONNRESET reported. No full API/Playwright run,
real embedding generation, dotenv reads, push, merge, deploy or destructive cleanup.


## 2026-10-16 RAG Stage 2 ? hybrid retrieval and isolation

Stage 1 implementation: `39e3888`. Stage 2 adds scoped parallel retrieval,
rank fusion, iterative HNSW scans and exact SQL underfill repair. Chat/real
embedding requests: 0. No isolation test returned foreign hits.

Exact affected test commands (disposable pgvector DBs, mocked/test providers):

```text
docker exec -e DATABASE_URL=postgresql://postgres@host.docker.internal:55462/rag_stage2_hybrid -e ENVIRONMENT=test rag-stage0-checks python -m pytest -q tests/test_hybrid_retrieval.py --tb=short -x -p no:cacheprovider --basetemp=/tmp/rag-stage2-hybrid
docker exec -e DATABASE_URL=postgresql://postgres@host.docker.internal:55462/rag_stage2_hybrid -e ENVIRONMENT=test rag-stage0-checks python -m pytest -q tests/test_hybrid_retrieval.py --tb=short -x -p no:cacheprovider --basetemp=/tmp/rag-stage2-hybrid2
docker exec -e DATABASE_URL=postgresql://postgres@host.docker.internal:55462/rag_stage2_hybrid -e ENVIRONMENT=test rag-stage0-checks python -m pytest -q tests/test_hybrid_retrieval.py --tb=short -x -p no:cacheprovider --basetemp=/tmp/rag-stage2-hybrid3
docker exec -e DATABASE_URL=postgresql://postgres@host.docker.internal:55462/rag_stage2_fts -e ENVIRONMENT=test rag-stage0-checks python -m pytest -q tests/test_retrieval.py tests/test_rag_stage0_baseline.py --tb=short -x -p no:cacheprovider --basetemp=/tmp/rag-stage2-fts
```

Outcomes: hybrid initial failed only log capture (Alembic disabled the imported
logger; isolation already passed); second failed only HNSW index-plan assertion
(tiny-fixture planner chose scoped B-tree + sort); third **6 passed** in 68.31s
with explicit test-only forced ANN planner settings. Existing retrieval **9** +
baseline **14** = **23 passed** in 113.29s. Existing Starlette warning only.
Saved raw EXPLAIN with:
`docker cp rag-stage0-checks:/tmp/rag-stage2-hybrid3/test_filtered_vector_isolation0/filtered-vector-explain.json docs/rag-phase/STAGE-2-EXPLAIN.json` (exit 0).

- `docker exec rag-stage0-checks python -m mypy --no-incremental --cache-dir /tmp/rag-stage2-mypy`: initial 3 test annotation/import errors; corrected.
- `docker exec rag-stage0-checks python -m mypy --no-incremental --cache-dir /tmp/rag-stage2-mypy2`: exit 0, **163 source files**.
- `docker exec rag-stage0-checks python -m ruff check --no-cache app/retrieval app/core/config.py tests/test_hybrid_retrieval.py`: exit 0.
- `.venv/Scripts/python.exe -m ruff format --check apps/api/app/retrieval apps/api/app/core/config.py apps/api/tests/test_hybrid_retrieval.py`: exit 0, **6 files** formatted.
- No browser changes or full suites. No real embedding/chat calls, dotenv reads,
  merge, push, Compose or deployment. Production chat integration belongs to
  Stage 3 alongside the relevance gate.

Owner clarification requested before Stage 3: whether either independent
relevance signal suffices versus requiring both, and approval for explicitly
untuned provisional cosine 0.50 / FTS rank 0.01 defaults without real embedding
scores. The plan does not resolve this threshold tradeoff; no Stage 3 code started.


## 2026-10-16 RAG Stage 3 ? relevance gate, rewrite, refusal

Owner approved cosine OR FTS, and explicitly untuned configurable bge-m3
cosine 0.50 / FTS ts_rank_cd 0.01 defaults. OpenAI calibration remains pending;
unknown model identities cannot pass on vectors without their own floor.
Stage 2 implementation hash: `8f163e9`. No real provider requests.

Affected API commands:

```text
docker exec -e DATABASE_URL=postgresql://postgres@host.docker.internal:55462/rag_stage3_gate -e ENVIRONMENT=test rag-stage0-checks python -m pytest -q tests/test_rag_gate.py --tb=short -x -p no:cacheprovider --basetemp=/tmp/rag-stage3-gate
docker exec -e DATABASE_URL=postgresql://postgres@host.docker.internal:55462/rag_stage3_chat -e ENVIRONMENT=test rag-stage0-checks python -m pytest -q tests/test_chat.py tests/test_cross_script.py --tb=short -x -p no:cacheprovider --basetemp=/tmp/rag-stage3-chat
docker exec -e DATABASE_URL=postgresql://postgres@host.docker.internal:55462/rag_stage3_conversations -e ENVIRONMENT=test rag-stage0-checks python -m pytest -q tests/test_conversations.py tests/test_handoff.py tests/test_analytics.py --tb=short -x -p no:cacheprovider --basetemp=/tmp/rag-stage3-conversations
docker exec -e DATABASE_URL=postgresql://postgres@host.docker.internal:55462/rag_stage3_baseline -e ENVIRONMENT=test rag-stage0-checks python -m pytest -q tests/test_rag_stage0_baseline.py --tb=short -x -p no:cacheprovider --basetemp=/tmp/rag-stage3-baseline
```

Gate/budget/all-case checks: **13 passed**, 1.83s; baseline compatibility:
**14 passed**, 1.96s. Existing Starlette warning only. Other file outcomes
recorded below when complete. Raw-FTS, translation/rewrite-off gate measurement:
32 cases, expected-source accepted hits 9/22; unanswerable rejected 6/10.
Four unanswerable questions still pass keyword relevance; this is not a claim
of generation/refusal correctness. Arabic 0/6, mixed 4/4, paraphrase 3/8,
follow-up 2/4 expected hits. Saved `docs/rag-phase/STAGE-3-GATE-RESULTS.json`.
Fixture copied verbatim to API tests/fixtures for portable container tests.
First artifact copy used a wrong truncated pytest directory; locate + corrected
copy succeeded without rerunning tests or spending requests.

- `docker exec rag-stage0-checks python -m mypy --no-incremental --cache-dir /tmp/rag-stage3-mypy`: exit 0, **165 source files**.
- `.venv/Scripts/python.exe -m ruff check apps/api/app/retrieval/gate.py apps/api/app/chat/service.py apps/api/app/chat/providers.py apps/api/app/chat/models.py apps/api/app/chat/prompts.py apps/api/app/core/config.py apps/api/tests/test_rag_gate.py apps/api/tests/test_chat.py`: exit 0.
- Same eight-file scope with `ruff format --check`: exit 0, **8 files**.

Affected browser command from apps/web (offline stubs/disposable DB):

```powershell
$env:ENVIRONMENT='test'; $env:DATABASE_URL='postgresql://postgres@127.0.0.1:55462/rag_stage3_browser_test'; $env:E2E_API_PORT='18162'; $env:API_PROXY_TARGET='http://127.0.0.1:18162'; $env:STORAGE_ROOT='D:/Projects/Work Projects/The Osiris Labs/SAAS-chats-ai/.test-storage/rag-stage-0/stage3-browser-storage'; npm.cmd test -- tests/widget.spec.ts tests/playground.spec.ts --reporter=line 2>&1 | Tee-Object -FilePath '../../.test-storage/rag-stage-0/stage3-browser.log'; exit $LASTEXITCODE
```

Exit 0: **7 passed (1.3m)**, ECONNRESET **0**. No full suites, live semantic
calibration, dotenv reads, paid calls, merge, push, deployment or Compose.

- Chat/cross-script: exit 0, **19 passed** (16 + 3), 249.76s.
- Conversations/handoff/analytics: exit 0, **24 passed** (13 + 5 + 6), 397.86s.
- Review found history included the current message and oldest turns. Corrected
  to recent prior visitor turns, scoped by tenant+bot, using configured window.
  `docker exec -e DATABASE_URL=postgresql://postgres@host.docker.internal:55462/rag_stage3_history -e ENVIRONMENT=test rag-stage0-checks python -m pytest -q tests/test_rag_gate.py -k rewrite_history --tb=short -p no:cacheprovider --basetemp=/tmp/rag-stage3-history`: exit 0, **1 passed**, 13 deselected, 1.59s.
- Final `docker exec rag-stage0-checks python -m mypy --no-incremental --cache-dir /tmp/rag-stage3-final-mypy`: exit 0, **165 files**.
- Final `ruff check` affected retrieval gate/chat/config/tests scope: exit 0;
  `ruff format --check` same scope including conversations.py: **9 files**, exit 0.
- Stage 3 total: **71 unique affected API tests**; **7 affected browser tests**.


## 2026-10-16 RAG Stage 4 ? grounded generation and private traces

Stage 3 committed `555ffc7`. Added per-bot model selection on playground/widget,
private JSON traces stored in existing message usage events, one staff-only
trace route (exact matrix now81), typed staff playground trace panel and
optional post-check callback hook. Existing strict citation validation kept.
OpenAI transport tested only with mocked HTTP. Real provider requests: 0.

```text
docker exec -e DATABASE_URL=postgresql://postgres@host.docker.internal:55462/rag_stage4_traces -e ENVIRONMENT=test rag-stage0-checks python -m pytest -q tests/test_rag_traces.py tests/test_rag_gate.py --tb=short -x -p no:cacheprovider --basetemp=/tmp/rag-stage4-traces
docker exec -e DATABASE_URL=postgresql://postgres@host.docker.internal:55462/rag_stage4_matrix -e ENVIRONMENT=test rag-stage0-checks python -m pytest -q tests/test_tenant_route_matrix.py --tb=short -x -p no:cacheprovider --basetemp=/tmp/rag-stage4-matrix
docker exec -e DATABASE_URL=postgresql://postgres@host.docker.internal:55462/rag_stage4_widget -e ENVIRONMENT=test rag-stage0-checks python -m pytest -q tests/test_widget_public.py --tb=short -x -p no:cacheprovider --basetemp=/tmp/rag-stage4-widget
docker exec -e DATABASE_URL=postgresql://postgres@host.docker.internal:55462/rag_stage4_citations -e ENVIRONMENT=test rag-stage0-checks python -m pytest -q tests/test_chat.py -k 'citation or invalid_json or provider_failure' --tb=short -x -p no:cacheprovider --basetemp=/tmp/rag-stage4-citations
```

First command **17 passed** (3 trace +14 gate),5.76s. Matrix **6 passed**,24.87s.
Other outcomes below. No cross-tenant/bot hits or client exposure in checks.
`docker cp rag-stage0-checks:/tmp/rag-stage4-traces/test_sample_traces_and_postche0/sample-traces.json docs/rag-phase/STAGE-4-SAMPLE-TRACES.json`:exit0.
Samples are mocked answerable/refusal/follow-up traces, not live quality evidence.

Initial mypy found2new test setup/narrowing errors; corrected. Final
`docker exec rag-stage0-checks python -m mypy --no-incremental --cache-dir /tmp/rag-stage4-mypy2`:exit0,**167 source files**.
`ruff check` and `ruff format --check` on app/chat, widget/service.py,
embeddings/router.py, core/permissions.py, tenant matrix +trace tests:exit0,
**14 files** formatted. Host Ruff fixed new-file formatting only.
`npm.cmd run lint` and `npm.cmd run typecheck`:exit0. Touched web files formatted.

Affected browser command from apps/web:

```powershell
$env:ENVIRONMENT='test'; $env:DATABASE_URL='postgresql://postgres@127.0.0.1:55462/rag_stage4_browser_test'; $env:E2E_API_PORT='18162'; $env:API_PROXY_TARGET='http://127.0.0.1:18162'; $env:STORAGE_ROOT='D:/Projects/Work Projects/The Osiris Labs/SAAS-chats-ai/.test-storage/rag-stage-0/stage4-browser-storage'; npm.cmd test -- tests/playground.spec.ts --reporter=line 2>&1 | Tee-Object -FilePath '../../.test-storage/rag-stage-0/stage4-browser.log'; exit $LASTEXITCODE
```

Exit0,**3 passed(1.1m)**,including trace panel and viewer restriction. No full
suites or new migration. No dotenv reads, real provider calls, merge,push,deploy.

- Widget public: exit0, **14 passed**,216.30s. Selected citation/error: exit0, **4 passed**,12 deselected,58.71s. Stage4 total **41 affected API tests**. Browser log checked as UTF-16: ECONNRESET0.


## 2026-10-16 RAG Stage 5 ? parsing and staff status

Stage4 commit `85dbe92`. DOCX table first row is retained as header and repeated
as labels for each subsequent row. Existing CSV records remain whole. Parser
subprocess owns a POSIX session/process group; cleanup kills the complete group
on timeout and after output, including helpers. Windows uses argument-vector
taskkill /T /F; Windows descendant behavior remains UNVERIFIED. Parser input
bytes are checked against the same existing per-plan upload cap. Existing PDF
page, DOCX expansion, source/page quotas and timeout remain enforced.
No OCR path found (`rg -n 'OCR|ocr' apps/api/app -g '*.py'`); scanned PDF rejection
retained, OCR deferred per prompt. Derived document parsed status/chunk count/
warnings are returned/rendered only on existing staff knowledge surfaces.

```text
docker exec -e DATABASE_URL=postgresql://postgres@host.docker.internal:55462/rag_stage5_parsers -e ENVIRONMENT=test rag-stage0-checks python -m pytest -q tests/test_knowledge_parsers.py --tb=short -x -p no:cacheprovider --basetemp=/tmp/rag-stage5-parsers
docker exec -e DATABASE_URL=postgresql://postgres@host.docker.internal:55462/rag_stage5_pipeline -e ENVIRONMENT=test rag-stage0-checks python -m pytest -q tests/test_knowledge_pipeline.py tests/test_knowledge_uploads.py --tb=short -x -p no:cacheprovider --basetemp=/tmp/rag-stage5-pipeline
docker exec -e DATABASE_URL=postgresql://postgres@host.docker.internal:55462/rag_stage5_pipeline -e ENVIRONMENT=test rag-stage0-checks python -m pytest -q tests/test_knowledge_pipeline.py --tb=short -x -p no:cacheprovider --basetemp=/tmp/rag-stage5-plan-cap
```

Parser **29 passed**,6.88s, including actual nested helper PID and bounded timeout;
pipeline/upload **28 passed** (9+19),36.19s. Final pipeline check follows below:
review found the initial global10MB guard would reject previously allowed
business/pro uploads, so parser settings now use the scoped tenant plan cap,
matching upload behavior. No failing test was hidden; this was found in review.

`docker exec rag-stage0-checks python -m mypy --no-incremental --cache-dir /tmp/rag-stage5-mypy`:exit0,**167 source files**.
Affected Ruff check and six-file format check passed after initial new-line/import
formatting fixes. `npm.cmd run lint` and `npm.cmd run typecheck`:exit0.

Affected browser command from apps/web:

```powershell
$env:ENVIRONMENT='test'; $env:DATABASE_URL='postgresql://postgres@127.0.0.1:55462/rag_stage5_browser_test'; $env:E2E_API_PORT='18162'; $env:API_PROXY_TARGET='http://127.0.0.1:18162'; $env:STORAGE_ROOT='D:/Projects/Work Projects/The Osiris Labs/SAAS-chats-ai/.test-storage/rag-stage-0/stage5-browser-storage'; npm.cmd test -- tests/knowledge.spec.ts --reporter=line 2>&1 | Tee-Object -FilePath '../../.test-storage/rag-stage-0/stage5-browser.log'; exit $LASTEXITCODE
```

Exit0:**4 passed(1.1m)**. Client knowledge denial retained. Provider requests0.
No full suites, OCR implementation, new schema, dotenv reads, merge,push,deploy.

- Final pipeline recheck:exit0,**9 passed**,31.45s. Final mypy `/tmp/rag-stage5-final-mypy`:exit0,167files. Final six-file Ruff/format checks:exit0. Browser ECONNRESET0.


## 2026-10-16 RAG Stage 6 ? eval and owner calibration tools

Stage5 `75ee690`. Added operator eval helpers/API runner and requested root
owner scripts. Neither root owner script executed (not even --help). Both AST
parsed; provider/budget helpers exercised only with mocked HTTP. No real calls.

```text
docker exec -e DATABASE_URL=postgresql://postgres@host.docker.internal:55462/rag_stage6_eval -e ENVIRONMENT=test rag-stage0-checks python -m pytest -q tests/test_rag_evaluation.py --tb=short -x -p no:cacheprovider --basetemp=/tmp/rag-stage6-eval
docker exec -e DATABASE_URL=postgresql://postgres@host.docker.internal:55462/rag_stage6_budget -e ENVIRONMENT=test rag-stage0-checks python -m pytest -q tests/test_rag_evaluation.py tests/test_rag_stage0_baseline.py -k 'not two_mode_retrieval_eval' --tb=short -x -p no:cacheprovider --basetemp=/tmp/rag-stage6-budget
```

First **6 passed**,5.98s, including one64-row offline FTS/hybrid comparison.
Final after usage/budget accounting review **20 passed**,1comparison deselected,
3.09s (6eval/budget +14baseline). **21 unique affected tests** overall, existing
Starlette warning only. No comparison rerun for reporting. Test vectors are
synthetic lexical vectors, not actual bge-m3. Hybrid candidate coverage22/22
versus FTS9/22 is trivial with4chunks andk8; Arabic accepted0/6 both modes.
Unanswerable gate refusals6/10 and answerable wrong refusals12/22 both. No
semantic improvement or generation-quality claim. Thresholds stay owner-approved
provisional0.50/0.01; real-model tuning pending owner, not inferred from fake data.

Artifacts copied without rerun:
`docker cp rag-stage0-checks:/tmp/rag-stage6-eval/test_two_mode_retrieval_eval_i0/summary.json docs/rag-phase/STAGE-6-COMPARISON.json`;
`docker cp rag-stage0-checks:/tmp/rag-stage6-eval/test_two_mode_retrieval_eval_i0/retrieval-results.jsonl docs/rag-phase/STAGE-6-RETRIEVAL-RESULTS.jsonl` (bothexit0).

Initial mypy on eval code found4annotation/narrowing errors; corrected.
Intermediate passed170files. Final
`docker exec rag-stage0-checks python -m mypy --no-incremental --cache-dir /tmp/rag-stage6-final-mypy app tests alembic scripts/rag_phase2_eval.py scripts/rag_stage0_baseline.py`:
exit0,**171 source files**. New-file Ruff/import/line formatting corrected;
root CLI broad exception guards intentionally redact unexpected diagnostics.
Affected six-file Ruff checks passed. Owner entrypoints parsed using ast.parse,
without importing/executing them. No UI changes/browser runs/full suites.

Review fixed BudgetModel's raw nested provider usage to satisfy its typed integer
counter contract, and records actual reserved requests rather than a blocked
attempt at cap40. Calibration batch usage logged once per batch. Safe error
boundaries prevent configuration/provider values in CLI diagnostics. Exact owner
commands in docs/rag-phase/OWNER-CHECKS.md. No dotenv reads, merge,push,deploy.


## 2026-10-16 RAG Stage 7 ? privacy fix, metering and caps

Owner approved export redaction first, then continued Stage7, and configurable
caps with unset values uncapped. Stage6 commit `fa1baff`. New fields/units/defaults
and conservative reservation behavior: docs/rag-phase/LIMITS-AND-METERING.md.
No real provider calls. All work on disposable local databases.

Exact affected API commands:

```text
docker exec -e DATABASE_URL=postgresql://postgres@host.docker.internal:55462/rag_stage7_privacy -e ENVIRONMENT=test rag-stage0-checks python -m pytest -q tests/test_tenant_data.py -k export_contains --tb=short -x -p no:cacheprovider --basetemp=/tmp/rag-stage7-privacy
docker exec -e DATABASE_URL=postgresql://postgres@host.docker.internal:55462/rag_stage7_limits -e ENVIRONMENT=test rag-stage0-checks python -m pytest -q tests/test_rag_limits.py --tb=short -x -p no:cacheprovider --basetemp=/tmp/rag-stage7-limits
docker exec -e DATABASE_URL=postgresql://postgres@host.docker.internal:55462/rag_stage7_matrix -e ENVIRONMENT=test rag-stage0-checks python -m pytest -q tests/test_tenant_route_matrix.py tests/test_migrations.py --tb=short -x -p no:cacheprovider --basetemp=/tmp/rag-stage7-matrix
docker exec -e DATABASE_URL=postgresql://postgres@host.docker.internal:55462/rag_stage7_embedding -e ENVIRONMENT=test rag-stage0-checks python -m pytest -q tests/test_embedding_foundation.py tests/test_hybrid_retrieval.py --tb=short -x -p no:cacheprovider --basetemp=/tmp/rag-stage7-embedding
docker exec -e DATABASE_URL=postgresql://postgres@host.docker.internal:55462/rag_stage7_pipeline -e ENVIRONMENT=test rag-stage0-checks python -m pytest -q tests/test_knowledge_pipeline.py tests/test_tenant_data.py tests/test_rag_traces.py --tb=short -x -p no:cacheprovider --basetemp=/tmp/rag-stage7-pipeline
docker exec -e DATABASE_URL=postgresql://postgres@host.docker.internal:55462/rag_stage7_limits -e ENVIRONMENT=test rag-stage0-checks python -m pytest -q tests/test_rag_limits.py -k measured_events --tb=short -x -p no:cacheprovider --basetemp=/tmp/rag-stage7-cost
```

Outcomes in order: export1passed(1deselected),3.06s; limits8passed,10.21s;
matrix6+migrations1=7passed,30.87s; embedding11+hybrid6=17passed,87.54s;
pipeline9+export2+traces3=14passed,44.12s; final explicit-cost-precedence check
1passed(7deselected),2.61s. **46 unique affected tests**, all passed. Existing
Starlette warning only; isolation/backfill/privacy/migration checks passed.

Initial mypy found two new JSON integer narrowing issues; corrected. Intermediate
mypy174filespassed. Final
`docker exec rag-stage0-checks python -m mypy --no-incremental --cache-dir /tmp/rag-stage7-final-mypy app tests alembic scripts/rag_phase2_eval.py scripts/rag_stage0_baseline.py`:
exit0,**176 files**. Affected Ruff checks passed. Broad inventory
`.venv/Scripts/python.exe -m ruff check --no-cache apps/api/app apps/api/tests --output-format concise`:
exit1, exactly9existingfindings. A broad formatting invocation touched unrelated
sentiment formatting; restored only that agent-created formatting from HEAD
before final checks/commit, preserving all9oldfindings. No user edits discarded.
Web `npm.cmd run lint` and `npm.cmd run typecheck`:exit0.

Affected browser command from apps/web:

```powershell
$env:ENVIRONMENT='test'; $env:DATABASE_URL='postgresql://postgres@127.0.0.1:55462/rag_stage7_browser_test'; $env:E2E_API_PORT='18162'; $env:API_PROXY_TARGET='http://127.0.0.1:18162'; $env:STORAGE_ROOT='D:/Projects/Work Projects/The Osiris Labs/SAAS-chats-ai/.test-storage/rag-stage-0/stage7-browser-storage'; npm.cmd test -- tests/roles-control.spec.ts tests/playground.spec.ts --reporter=line 2>&1 | Tee-Object -FilePath '../../.test-storage/rag-stage-0/stage7-browser.log'; exit $LASTEXITCODE
```

Exit0,**5passed(1.3m)**. Includes staff cap save/reset, all client-role panel hiding,
and playground tracing. No full suites before final gate. No real APIs, dotenv,
Compose,push,merge,deploy or destructive cleanup.

## 2026-10-16 RAG final exit gate (single run)

Stage 7 implementation commit: `e1d1c23`. Full API gate launched once with
`.venv/Scripts/python.exe .test-storage/rag-phase2-final/run_api.py`.
The runner enumerates all 44 test files, executes each separately in
`rag-stage0-checks` against its own disposable pgvector database, and saves exact
commands, counts and logs after each file to
`.test-storage/rag-phase2-final/api-results.json`. It refuses automatic replay.
No API gate failure observed at this checkpoint; final counts follow when done.

Single unscoped Playwright command from apps/web:

```powershell
$env:ENVIRONMENT='test'
$env:DATABASE_URL='postgresql://postgres@127.0.0.1:55462/rag_final_browser_test'
$env:E2E_API_PORT='18162'
$env:API_PROXY_TARGET='http://127.0.0.1:18162'
$env:STORAGE_ROOT='D:/Projects/Work Projects/The Osiris Labs/SAAS-chats-ai/.test-storage/rag-phase2-final/browser-storage'
npm.cmd test -- --reporter=line 2>&1 | Tee-Object -FilePath '../../.test-storage/rag-phase2-final/playwright-full.log'
```

Exit 0: **40 passed (3.5m)**. UTF-16 log scanned: ECONNRESET 0,
Failed to proxy 0, Python tracebacks 0. No browser rerun. Existing Next/Node
warnings do not fail the suite. API/worker stopped normally by the harness.

Final review corrected embedding accounting: missing/invalid usage must retain
unknown cost rather than compute OpenAI USD 0. Added five mocked cases before
`test_embedding_foundation.py` was first executed by the API gate. No real call
or suite restart. Initial mypy found one new test payload inference error;
explicit `dict[str, object]` corrected it. Final command:

```text
docker exec rag-stage0-checks python -m mypy --no-incremental --cache-dir /tmp/rag-final-cost-mypy2 app tests alembic scripts/rag_phase2_eval.py scripts/rag_stage0_baseline.py
```

Exit 0, **176 source files**. Host Ruff check/format of
`apps/api/app/embeddings/providers.py` and
`apps/api/tests/test_embedding_foundation.py` passed. No unrelated Ruff fixes.

Final API gate completed: **353 passed, 44/44 files**, all exit 0, counts {'failed': 0, 'skipped': 0, 'deselected': 0, 'error': 0}. Exact command per file, counts and timings copied without rerun to docs/rag-phase/FINAL-TEST-RESULTS.json. Embedding foundation16 includes all five final accounting regressions. Full Playwright40passed, ECONNRESET0. No new provider requests. Semantic multilingual improvement and complete live refusal quality remain unestablished; leave feature branch unmerged and untagged.

## 2026-10-16 Owner-approved local merge

Owner subsequently instructed "merge approved do it", after the pending quality
checks were reported. This overrides the earlier unmerged restriction. Record
the approval in the execution overrides and final report, preserve all phase
commits, merge into local `main`, then delete only the merged feature branch
using `git branch -d`. Working tree was clean at `b4c8d05`; main `946f2cb` is an
ancestor. No code changes or test reruns for this documentation/Git operation.
Existing results remain 353 API / 40 Playwright passed. Calibration and live
semantic/refusal quality remain PENDING; no completion tag, provider calls or push.


## 2026-10-16 Final RAG fixes before owner calibration

Owner scope: no real provider calls, merge or tag; affected checks only.
Default identity is now openai:text-embedding-3-large at 1024 dimensions;
OpenAI 0.50 OR FTS 0.01 is UNTUNED, pending owner calibration. Optional Ollama
retains its own row. Missing identities use FTS only. Added configurable minimum
matched content terms (default 1), computed per chunk against stored PostgreSQL
indexes in tenant/bot/revision-scoped SQL, including expanded/hybrid candidates.

Shared demo: 44 documents/chunks (36 EN, 8 AR), with close shop/workshop
distractors; eval: 76 cases (62 answerable, 14 gaps), covering every source.
Arabic FTS is simple on normalized fts_simple; English is english on fts_en.
Calibration plans the exact corpus before DB/provider activity, prints cost first,
rejects >2M tokens, caches embeddings, reports hit@3/MRR for both modes and
90 cosine/FTS/minimum-term settings with leaks/refusals/wrong-evidence accepts.
One calibration-results.json contains all paste-back evidence and recommendations.
The generation check optionally loads that recommendation for its run only.
Renumbered RAG ADR to unused ADR-019; deferred billing ADR-008 is unchanged.
FINAL-REPORT.md lists the complete client BotOut exception and exact two owner
commands. No schema/migration or client API contract changes.

Affected test commands from the repository root (all HTTP mocked/synthetic;
existing test container, only disposable local databases):

```powershell
docker exec -e DATABASE_URL=postgresql://postgres@host.docker.internal:55462/rag_calibration_fixes_test -e ENVIRONMENT=test rag-stage0-checks python -m pytest -q tests/test_rag_evaluation.py tests/test_rag_gate.py tests/test_seed_demo.py tests/test_embedding_foundation.py tests/test_hybrid_retrieval.py tests/test_retrieval.py tests/test_cross_script.py tests/test_rag_traces.py tests/test_rag_stage0_baseline.py --tb=short -x -p no:cacheprovider --basetemp=/tmp/rag-calibration-fixes
```

Exit 1: **99 passed, 1 failed**, 1 existing Starlette/httpx deprecation warning,
339.61s. Failure: test_real_fts_pipeline_checkpoints_and_never_replays expected
Arabic cannot_confirm from the old English-only demo. Actual expanded demo
correctly returns answer. Updated source label to pricing-ar, asserted Arabic
hit/citations and one mocked generation call; replay assertions still count
both mocked requests and forbid additional calls.

While this ran, added an end-to-end synthetic calibration report test, a
recommendation-loading test, and a direct PostgreSQL lexical isolation/stemming/
Arabic term-group test. Follow-up command:

```powershell
docker exec -e DATABASE_URL=postgresql://postgres@host.docker.internal:55462/rag_calibration_followup_test -e ENVIRONMENT=test rag-stage0-checks python -m pytest -q tests/test_rag_evaluation.py tests/test_retrieval.py::test_lexical_signal_count_uses_postgres_terms_and_tenant_scope tests/test_rag_stage0_baseline.py tests/test_chat.py tests/test_embedding_foundation.py::test_default_embedding_identity_and_optional_ollama --tb=short -x -p no:cacheprovider --basetemp=/tmp/rag-calibration-followup 2>&1 | Tee-Object -FilePath .test-storage/rag-owner-fixes/affected-followup.log; exit $LASTEXITCODE
```

Exit 1: **12 passed, 1 failed**, 1 existing warning, 38.57s. The new Arabic
lexical assertion used question marks after PowerShell's ASCII native-pipeline
encoding. Corrected its actual UTF-8 query plus two similarly affected new
Arabic gap questions, and added an assertion checking Arabic content in every
Arabic-labelled eval question. Existing Arabic data was preserved. Corrected run:

```powershell
docker exec -e DATABASE_URL=postgresql://postgres@host.docker.internal:55462/rag_calibration_followup_test -e ENVIRONMENT=test rag-stage0-checks python -m pytest -q tests/test_rag_evaluation.py tests/test_retrieval.py::test_lexical_signal_count_uses_postgres_terms_and_tenant_scope tests/test_rag_stage0_baseline.py tests/test_chat.py tests/test_embedding_foundation.py::test_default_embedding_identity_and_optional_ollama --tb=short -x -p no:cacheprovider --basetemp=/tmp/rag-calibration-followup-corrected 2>&1 | Tee-Object -FilePath .test-storage/rag-owner-fixes/affected-followup-corrected.log; exit $LASTEXITCODE
```

Corrected run exit 0: **44 passed**, 1 existing Starlette/httpx deprecation
warning, **260.74s**. Raw log:
`.test-storage/rag-owner-fixes/affected-followup-corrected.log`.
Together with the first run's unaffected passes, this covers **120 distinct
affected tests** (99 + 44 passes, with 23 repeated passing cases). Both failed
assertions were corrected and passed in the final run; no failures/skips remain
in affected coverage. No full-suite/browser rerun.

Type checks (exact container commands):

```text
docker exec rag-stage0-checks python -m mypy --no-incremental --follow-imports=silent app/core/config.py app/retrieval/evaluation.py app/retrieval/gate.py app/retrieval/hybrid.py app/retrieval/query.py app/retrieval/service.py scripts/demo_knowledge.py scripts/seed_demo.py scripts/rag_phase2_eval.py tests/test_rag_evaluation.py tests/test_rag_gate.py tests/test_seed_demo.py tests/test_embedding_foundation.py
```

Exit 1, mypy 2.4.0 INTERNAL ERROR with default cache. Used a writable temp cache:

```text
docker exec rag-stage0-checks python -m mypy --no-incremental --cache-dir /tmp/rag-calibration-mypy --show-traceback app/core/config.py app/retrieval/evaluation.py app/retrieval/gate.py app/retrieval/hybrid.py app/retrieval/query.py app/retrieval/service.py scripts/demo_knowledge.py scripts/seed_demo.py scripts/rag_phase2_eval.py tests/test_rag_evaluation.py tests/test_rag_gate.py tests/test_seed_demo.py tests/test_embedding_foundation.py
```

Exit 1: three errors (missing texts annotation; two direct _env_file test
constructor arguments rejected by Settings' static signature). Corrected these;
default-identity test now uses model_construct without reading dotenv.

```text
docker exec rag-stage0-checks python -m mypy --no-incremental --cache-dir /tmp/rag-calibration-mypy-final app/core/config.py app/retrieval/evaluation.py app/retrieval/gate.py app/retrieval/hybrid.py app/retrieval/query.py app/retrieval/service.py scripts/demo_knowledge.py scripts/seed_demo.py scripts/rag_phase2_eval.py tests/test_rag_evaluation.py tests/test_rag_gate.py tests/test_seed_demo.py tests/test_embedding_foundation.py tests/test_retrieval.py
```

Exit 0: **14 source files**.

```text
docker exec rag-stage0-checks python -m mypy --no-incremental --cache-dir /tmp/rag-calibration-mypy-last scripts/rag_phase2_eval.py tests/test_rag_evaluation.py tests/test_rag_stage0_baseline.py
```

Exit 0: **3 source files**, after runner/report/baseline updates.
Initial affected Ruff checks caught long literals/import order/loop closure
lint; all corrected. Final scoped Ruff/format and diff checks follow below.

No .env read, real provider call, merge, tag, push, deployment, production DB
mutation or new infrastructure. Existing active embedding identities remain
unchanged until an explicit backfill. Real multilingual quality/calibration and
phase completion remain pending the owner.


Final lint/format commands (repository root):

```powershell
.venv/Scripts/ruff.exe check apps/api/app/core/config.py apps/api/app/retrieval apps/api/scripts/demo_knowledge.py apps/api/scripts/seed_demo.py apps/api/scripts/rag_phase2_eval.py apps/api/tests/test_rag_gate.py apps/api/tests/test_rag_evaluation.py apps/api/tests/test_seed_demo.py apps/api/tests/test_embedding_foundation.py apps/api/tests/test_retrieval.py apps/api/tests/test_rag_stage0_baseline.py scripts/rag_calibrate.py
.venv/Scripts/ruff.exe format --check apps/api/app/core/config.py apps/api/app/retrieval apps/api/scripts/demo_knowledge.py apps/api/scripts/seed_demo.py apps/api/scripts/rag_phase2_eval.py apps/api/tests/test_rag_gate.py apps/api/tests/test_rag_evaluation.py apps/api/tests/test_seed_demo.py apps/api/tests/test_embedding_foundation.py apps/api/tests/test_retrieval.py apps/api/tests/test_rag_stage0_baseline.py scripts/rag_calibrate.py
git diff --check
```

All exit 0: Ruff clean, **17 files already formatted**, no diff whitespace errors.
Git printed only existing LF/CRLF conversion notices for .env.example and query.py.

## 2026-10-16 - Final review fixes (branch fix/rag-phase-2-final)

Fixed F-01, F-02, F-03, F-04, F-06, F-08, F-09, F-14, F-15 and added Arabic FTS
(migration 0016); others deferred (docs/rag-phase/DEFERRED-REVIEW.md). Commands
(disposable pgvector DB rag_final_fix_test on 127.0.0.1:55462, PYTHONUTF8=1, ENVIRONMENT=test):

```text
python -m pytest -q <each tests/test_*.py file, one invocation per file> -p no:cacheprovider --tb=short
```
Result: 377 passed across 44 files, 1 skipped (POSIX-only). First pass had 2 failing
files (test_conversations, test_rag_stage0_baseline); fixed (question matched only
1 of 2 terms; harness forwarded `channel`) and re-run: 13 and 14 passed.

```text
cd apps/web; npx playwright test    (DATABASE_URL=.../rag_final_pw)
```
Result: 40 passed (3.6m), exit 0, ECONNRESET 0.
No real provider call, push, tag or compose. Recall (Arabic and semantic) UNVERIFIED.

## 2026-10-16 - Development Compose stack (feat/compose-stack)

Owner authorized a branch from main, local commits, a `--no-ff` merge into main,
and deletion of the feature branch. No Docker command (including Compose config),
provider call, `.env` read, push, deployment, or database operation was performed.
ADR-007/008 remain unchanged and outside this local-development task.

Discovery: root `compose.yaml` included `infra/compose.yaml`. That definition covered
pgvector/Postgres 17, database health/persistence, API, worker, web, shared uploads,
and an optional demo-only seed. API startup owned migrations; the worker waited
for API readiness. Provider keys were optional and the seed did not create staff,
set premium, or request backfill. The PowerShell runners independently managed
plain Docker containers rather than using that Compose stack.

Changes:
- Replaced the include with one root development definition; removed
  `infra/compose.yaml`. Added a one-shot migration service and success dependencies
  for both API and worker. Web bakes `API_PROXY_TARGET=http://api:8000` into its build.
- API/web bind only `127.0.0.1:8000` / `127.0.0.1:3000`. PostgreSQL stays internal;
  `postgres_data` and shared `app_data` persist across `down`.
- Required OpenAI key/model interpolation names missing variables clearly. Keys
  are supplied only at runtime to API/worker. Explicit OpenAI embeddings and HTTP
  development cookies; optional OpenRouter/free chain remain supported.
- Added `apps/api/scripts/seed_dev_stack.py`: guarded existing demo/staff helpers,
  password from `PLATFORM_STAFF_PASSWORD`, authenticated CSRF-protected premium
  and backfill requests, logout, safe errors, staff email/web URL output. Backfill
  is queued asynchronously; no embedding-completion claim is made. Demo queries
  reuse the existing tenant-scoped helpers and returned tenant/bot IDs.
- Replaced `scripts/dev_up.ps1` / `scripts/dev_down.ps1` with Compose wrappers and
  added their shared `scripts/dev_compose.ps1` runner. It disables implicit `.env`
  loading and inherited `COMPOSE_ENV_FILES`, optionally selects user-created
  `.env.local`, propagates exit codes, and restores the caller's environment.
- `.gitignore` already ignored `.env`; explicitly added `.env.local`. Existing
  `.dockerignore` excludes dotenv files. No credential file was created or changed.
- Updated README startup commands, marked the old local guide as historical,
  corrected the API Dockerfile comment and npm formatter's Compose file path.
  Added seven static configuration contract tests in `scripts/test_dev_compose.py`.

Validation commands and outcomes (static only):

```powershell
# Repository root: YAML parse/contract assertions and Python AST syntax only.
.venv/Scripts/python.exe scripts/test_dev_compose.py -v
.venv/Scripts/ruff.exe check --config apps/api/pyproject.toml scripts/test_dev_compose.py
.venv/Scripts/ruff.exe format --check --config apps/api/pyproject.toml scripts/test_dev_compose.py
node node_modules/prettier/bin/prettier.cjs --check compose.yaml package.json
git diff --check
git check-ignore .env .env.local

# From apps/api:
../../.venv/Scripts/ruff.exe check scripts/seed_dev_stack.py
../../.venv/Scripts/ruff.exe format --check scripts/seed_dev_stack.py
../../.venv/Scripts/mypy.exe --follow-imports=silent scripts/seed_dev_stack.py
```

All final commands above exited 0: **7 static tests passed**, Ruff lint/format clean,
Prettier clean, mypy found no issues in the one new seed source file, no diff
whitespace errors, and both dotenv paths were confirmed ignored (names only).

PowerShell AST parsing (no wrapper execution), repository root:

```powershell
$parseFailed = $false
foreach ($scriptPath in @('scripts/dev_compose.ps1', 'scripts/dev_up.ps1', 'scripts/dev_down.ps1')) {
  $parseTokens = $null
  $parseErrors = $null
  [void][System.Management.Automation.Language.Parser]::ParseFile((Join-Path (Get-Location) $scriptPath), [ref]$parseTokens, [ref]$parseErrors)
  if ($parseErrors.Count -gt 0) {
    $parseFailed = $true
    $parseErrors | ForEach-Object { Write-Output $_.Message }
  } else {
    Write-Output "$scriptPath syntax OK"
  }
}
if ($parseFailed) { exit 1 }
```

Exit 0; all three scripts parsed without syntax errors.

Earlier validation iterations, subsequently corrected:
- Root `.venv/Scripts/ruff.exe check apps/api/scripts/seed_dev_stack.py scripts/test_dev_compose.py`
  found two E501 lines (exit 1). The corresponding `ruff.exe format --check` found
  both files unformatted (exit 1). Explicit API-config formatting corrected them:
  `.venv/Scripts/ruff.exe format --config apps/api/pyproject.toml apps/api/scripts/seed_dev_stack.py scripts/test_dev_compose.py` (exit 0).
- `node node_modules/prettier/bin/prettier.cjs --check compose.yaml package.json`
  initially reported package.json formatting (exit 1); the same paths with `--write`
  fixed it (exit 0).
- Root `.venv/Scripts/ruff.exe check --config apps/api/pyproject.toml apps/api/scripts/seed_dev_stack.py scripts/test_dev_compose.py`
  reported I001 for API import classification (exit 1). The final API check uses
  its established `apps/api` working directory and passes without an import rewrite.
- From apps/api, `../../.venv/Scripts/mypy.exe --follow-imports=silent scripts/seed_dev_stack.py`
  initially rejected `Settings(_env_file=None)` (exit 1). Reused the existing seed's
  explicit-env `Settings.model_construct` pattern, then rechecked successfully.

Owner commands (NOT EXECUTED), repository root. Set `CHAT_OPENAI_API_KEY`,
`CHAT_OPENAI_MODEL`, and `PLATFORM_STAFF_PASSWORD` in the host environment or create
`.env.local` yourself first; the wrappers choose that file when present:

```powershell
.\scripts\dev_up.ps1
.\scripts\dev_compose.ps1 --profile seed up seed
# Later: stop containers/network, retain database and uploads.
.\scripts\dev_down.ps1
```

Equivalent direct commands for host-environment values:

```powershell
$env:COMPOSE_DISABLE_ENV_FILE = '1'
Remove-Item Env:COMPOSE_ENV_FILES -ErrorAction SilentlyContinue
docker compose up --build -d --wait
docker compose --profile seed up seed
docker compose down
```

For user-created `.env.local`, after the same two environment setup lines:

```powershell
docker compose --env-file .env.local up --build -d --wait
docker compose --env-file .env.local --profile seed up seed
docker compose --env-file .env.local down
```

Web: `http://localhost:3000`; API: `http://127.0.0.1:8000`; default staff:
`staff@example.com`. Seed may incur OpenAI embedding costs when the owner runs it.
Old plain-Docker runner resources are not adopted/removed. Existing Compose database
volumes require matching original POSTGRES_* values; URL passwords must be URL-safe.
No volumes were deleted. **All runtime behaviour is UNVERIFIED**: builds, startup,
migrations, healthchecks, authentication, seeding, premium routing, queue execution,
embeddings, persistence, and shutdown require owner validation. No phase gate was signed off.

## 2026-10-17 — Group A operator fixes

Owner scope: `fix/group-a-operator` from main; small local commits; merge with
`--no-ff` and delete the branch only after checks pass. No push, tags, Docker,
credential-file reads, deployment or paid API calls. Owner approved separately
committing the pre-existing untracked feature inventory. Owner approved G4's
rule: non-staff with only revoked memberships in active organizations cannot
log in; another active organization and staff access remain valid. Outstanding
invitations for the removed membership's organization/email are revoked.

Changes: paginate the existing platform tenants API; shared staff organizations
for `/app` and the header, onboarding navigation and refresh; API-side active
member filtering for platform detail (Team already filters active members);
separate pending invitations; explicit read-only staff inbox, including staff
who also have a membership. Archived organizations open their platform detail.
Tenant A/B and revoked admin/editor/viewer regressions use test fixtures only.

Validation so far (PowerShell; paths relative to repository unless noted):
- `npm.cmd run lint` — exit 0.
- `npm.cmd run typecheck` — exit 0 (`next typegen && tsc --noEmit`).
- In `apps/api`: `../../.venv/Scripts/ruff.exe check app/auth/service.py app/platform/router.py app/tenants/service.py tests/test_group_a_operator.py` — exit 0.
- In `apps/api`: `../../.venv/Scripts/mypy.exe --follow-imports=silent app/auth/service.py app/platform/router.py app/tenants/service.py tests/test_group_a_operator.py` — exit 0.
- In `apps/api`: `../../.venv/Scripts/ruff.exe format --check app/auth/service.py app/tenants/service.py tests/test_group_a_operator.py` — exit 0.
- The initial `../../.venv/Scripts/mypy.exe app/auth/service.py app/tenants/service.py tests/test_group_a_operator.py` command reported three existing Windows-incompatible attributes in `app/knowledge/ingest.py`: `os.setsid`, `os.killpg`, `signal.SIGKILL` (exit 1).
- Initial Ruff found an unused test import and pre-existing import ordering/two long lines in the touched platform router; corrected, then the above checks passed.
- In `apps/api`, `$env:ENVIRONMENT='test'; $env:TEST_DATABASE_URL='postgresql://postgres@127.0.0.1:55437/group_a'; ../../.venv/Scripts/python.exe -m pytest tests/test_auth.py -q --tb=short` — exit 1, 15 setup errors: native PostgreSQL lacks pgvector.
- In `apps/api`, with the same environment: `../../.venv/Scripts/python.exe -m pytest -q --tb=short -x -p no:cacheprovider` — exit 1, first test blocked during Alembic `0014_rag_embeddings` (`CREATE EXTENSION vector`). Also encountered Windows temporary-directory cleanup permissions. Full log: `.test-storage-group-a/backend-full.log` (ignored).
- A fresh native PostgreSQL cluster was initialized under `.test-storage-group-a/pg`, started only on loopback port 55437; no existing database was modified. This installation has no pgvector. No migration was skipped or altered to get past that failure.
- In `apps/web`: `npm.cmd run test -- --config ../../.test-storage-group-a/operator.config.ts --reporter=line` — 4 isolated Playwright tests passed (55.0s) against a fresh production build. The ignored config reuses the normal Playwright configuration but disables API setup/teardown for these API-mocked tests. Earlier run: 2 passed/2 failed because the test mocked `/inbox/{id}` instead of the actual `/conversations/{id}` endpoint; corrected the fixture and reran. The later archived-navigation refinement requires another final run.
- From root, the first `npm.cmd test -- --config ../../.test-storage-group-a/operator.config.ts --reporter=line` invocation lost options through nested npm scripts and hit sandbox `spawn EPERM`; corrected by invoking the workspace script directly, with process execution approval.
- In `apps/web`, `$env:ENVIRONMENT='test'; $env:DATABASE_URL='postgresql://postgres@127.0.0.1:55437/group_a_browser_test'; $env:E2E_API_PORT='18137'; $env:API_PROXY_TARGET='http://127.0.0.1:18137'; npm.cmd run test -- --reporter=line` — stopped after migration setup failed for missing pgvector and the harness continued into repeated API 500 errors. Log: `.test-storage-group-a/frontend-full.log` (ignored). This was not a passing full run; the real member-visibility browser regression remains unverified.
- The owner started PostgreSQL; ports 55462/5432 now answer but require authentication. Awaiting a test-only connection without reading dotenv/key files. No merge has been performed while integration checks remain blocked.

Validation update after the owner supplied the throwaway test connection:
- Used only loopback port 55462, test-only credentials, `ENVIRONMENT=test`, `CHAT_STUB_MODEL=1`, `EMBEDDING_TEST_STUB=1`; no dotenv/key file reads. The backend harness derives `postgres_test`; browser tests have separate `group_a_browser*_test` databases.
- In `apps/api`: `../../.venv/Scripts/python.exe -m pytest tests/test_group_a_operator.py tests/test_auth.py tests/test_members.py tests/test_invitations.py tests/test_platform.py -q --tb=short -p no:cacheprovider --basetemp=../../.test-storage-group-a/targeted-tmp` — **44 passed**, 1 existing Starlette deprecation warning, 132.05s, exit 0.
- Final isolated operator browser command above rerun after archived navigation and complete workspace mocks: **4 passed**, 50.6s, exit 0 (`frontend-operator-final2.log`).
- Full backend command now running: `../../.venv/Scripts/python.exe -u -m pytest -q --tb=short -p no:cacheprovider --basetemp=../../.test-storage-group-a/full-tmp`.
- Full browser run on the authorized database was deliberately stopped at the existing inbox reply journey: its fixture used a staff account for replies, contrary to Group A's explicit read-only requirement. Changed only that test's fixture to revoke its temporary staff flag after bot setup, preserving the actual client-admin journey. Rerunning `npm.cmd run test -- --reporter=line` with `DATABASE_URL` pointing to a fresh `group_a_browser_final_test` on port 55462, `E2E_API_PORT=18137`, `API_PROXY_TARGET=http://127.0.0.1:18137`, `STORAGE_ROOT=<repo>/.test-storage-group-a/browser-final-storage`, `ENVIRONMENT=test`, `PYTHONUTF8=1`.

Final concurrency review and follow-up:
- Removal now invalidates outstanding invitations. To prevent a tenant/invitation lock inversion with simultaneous acceptance, acceptance consistently locks the tenant before the invitation; all validation still occurs under the locks.
- In `apps/api`, with the owner-supplied test-only connection on port 55462 (base name `group_a_lock`): `../../.venv/Scripts/python.exe -u -m pytest tests/test_group_a_operator.py tests/test_invitations.py tests/test_members.py -q --tb=short -p no:cacheprovider --basetemp=../../.test-storage-group-a/lock-tmp` — **21 passed**, 1 existing Starlette warning, 13.25s, exit 0. Includes concurrent removal/old-invite acceptance plus the existing double-accept race test.
- The authorized full browser rerun finished **44 passed, 1 failed**, 4.1m (exit 1). The only failure was the new member test expecting an exact standalone pending email, whereas the unchanged Team markup renders email and role together. Corrected the locator to assert the Pending invitations region contains the email and the Members region excludes the revoked email. No client product code changed. Running the member regression again before the final full rerun.
- Final frontend lint, typecheck and Prettier checks on all changed web files passed (exit 0); changed backend Ruff and mypy with `--follow-imports=silent` passed (exit 0).

Final frontend verification:
- `npm.cmd run test -- tests/group-a-members.spec.ts --reporter=line` against the real API and its own `group_a_member_check_test` database — **1 passed**, 53.5s, exit 0.
- `npm.cmd run test -- --reporter=line` against a fresh `group_a_browser_green_test` on authorized port 55462 — **45 passed**, 3.8m, exit 0. Same test environment/API port/proxy/storage isolation as above, with `STORAGE_ROOT=<repo>/.test-storage-group-a/browser-green-storage`. Full log: `.test-storage-group-a/frontend-full-green.log` (ignored).
- `npm.cmd run lint`, `npm.cmd run typecheck`, and Prettier checks for all changed frontend files — exit 0.
- In `apps/api`: `../../.venv/Scripts/mypy.exe --platform linux app/auth/service.py app/platform/router.py app/tenants/service.py tests/test_group_a_operator.py` — exit 0, no issues (including imported modules). Linux matches the API deployment target and resolves the earlier Windows-only attribute diagnostics without changing unrelated code.
- Stopped the temporary native PostgreSQL server started earlier; the owner's Docker resources were never managed by this agent. Restored only the test-generated timestamp in `implementation/PHASE-03/EVAL-REPORT.md`.

Full-suite diagnostics and minimal logging fix:
- The two sentiment-warning assertions passed alone: `../../.venv/Scripts/python.exe -m pytest tests/test_quotas.py::test_sentiment_is_skipped_and_logged_without_a_key tests/test_quotas.py::test_sentiment_model_failure_is_logged_and_skipped -q --tb=short -p no:cacheprovider --basetemp=../../.test-storage-group-a/sentiment-tmp` — **2 passed**, 0.67s, exit 0 (separate `group_a_sentiment_diagnostic_test` database).
- Alembic's default `fileConfig` disabled existing application loggers during migration tests. Added `disable_existing_loggers=False` and a regression in the existing migration-cycle test proving an application logger remains enabled. No migration/schema or client-role behavior changed.
- `../../.venv/Scripts/python.exe -m pytest tests/test_migrations.py tests/test_quotas.py::test_sentiment_is_skipped_and_logged_without_a_key tests/test_quotas.py::test_sentiment_model_failure_is_logged_and_skipped -q --tb=short -p no:cacheprovider --basetemp=../../.test-storage-group-a/logging-tmp` — **3 passed**, 7.20s, exit 0 (base `group_a_logging`, port 55462).
- The initial full command also forced `CHAT_STUB_MODEL=1` globally, conflicting with the production-settings guard test. Corrected the test command, clearing `CHAT_STUB_MODEL` and `EMBEDDING_TEST_STUB`; the suite supplies offline fixtures itself. Provider credential environment variables are cleared only inside the child test shell, without reading/printing their values or any credential files.
- With those command corrections, `../../.venv/Scripts/python.exe -m pytest tests/test_startup_guard.py -q --tb=short -p no:cacheprovider --basetemp=../../.test-storage-group-a/startup-tmp` — **7 passed**, 1.08s, exit 0.
- Final full backend rerun: `../../.venv/Scripts/python.exe -u -m pytest -q --tb=short -p no:cacheprovider --basetemp=../../.test-storage-group-a/green-tmp`, with the owner-supplied test-only connection on port 55462, base `group_a_backend_final`, `ENVIRONMENT=test`, `PYTHONUTF8=1`, no global stub flags/provider credentials. Log: `.test-storage-group-a/backend-full-green.log` (ignored).
- Changed backend Ruff lint/format and Linux-target mypy checks pass, including `alembic/env.py` and `tests/test_migrations.py` (6 source files, exit 0). The newly appended progress notes are normalized to UTF-8, preserving the historical file prefix.

The superseded full backend run was stopped at 92% after three observed failures
and one skip, once the causes were diagnosed. It was not recorded as a passing
run. The corrected full rerun uses the complete final source, including the
invitation race regression and logger-preservation assertion.

Files changed for Group A:
- API: `apps/api/app/auth/service.py`, `apps/api/app/platform/router.py`, `apps/api/app/tenants/service.py`, `apps/api/alembic/env.py`, `apps/api/tests/test_group_a_operator.py`, `apps/api/tests/test_migrations.py`.
- Web: `apps/web/app/app/page.tsx`, `apps/web/app/app/[tenant]/inbox/[conversation]/page.tsx`, `apps/web/app/platform/page.tsx`, `apps/web/app/platform/clients/[clientId]/page.tsx`, `apps/web/lib/api.ts`, `apps/web/lib/app-header.tsx`, `apps/web/lib/session.tsx`, `apps/web/tests/group-a-operator.spec.ts`, `apps/web/tests/group-a-members.spec.ts`, `apps/web/tests/conversations.spec.ts`.
- Evidence/record: `implementation/FEATURE-INVENTORY.md` (pre-existing user evidence, separately committed with approval), `PROGRESS.md`.

Final result and local integration readiness:
- Final full backend command recorded above exited **0**: **391 passed, 1 skipped, 1 existing Starlette deprecation warning**, 1579.98s (26m19s). Skip: `tests/test_knowledge_parsers.py:52`, POSIX process-group integration; Windows unverified. No Group A regression was skipped.
- Final full frontend: **45 passed**, exit 0; lint, typecheck and changed-file formatting checks passed. Changed backend Ruff lint/format and Linux-target mypy checks passed. Relevant final invitation/member, migration/logging and startup follow-ups also passed (21, 3 and 7 tests respectively).
- All runtime verification used disposable test databases. After the owner supplied the connection, only port 55462 was used. Model/provider behavior was mocked or fixture-controlled; no paid API calls, credential-file reads, Docker commands, push, tags or production deployment.
- No schema migration is required. Remaining verification limitation: the existing POSIX-only parser descendant-process cleanup test cannot execute on this Windows host.
- Restore the evaluation report's generated timestamp, commit this exact validation record, then perform the owner's authorized local `git merge --no-ff fix/group-a-operator` into `main` and `git branch -d fix/group-a-operator`. The merge commit records final integration; no phase/release or deployment sign-off is implied.

## 2026-10-17 — Group 0 inbox 500 regression

Owner scope: branch `fix/group-0-inbox-500` from clean `main`; small local
commits; merge with `--no-ff` and delete the branch after relevant checks pass.
Only task-related tests; no Docker, push, tags, deployment or paid providers.
Hosting/billing decisions and phase gates are outside this bug-fix scope.

Root cause: `_unread_count` nested read-marker scalar subqueries implicitly
introduced their own `conversations` FROM instead of correlating to the outer
conversation (two SELECT levels up). Multiple read markers for the same user
and tenant returned multiple rows and PostgreSQL rejected the scalar expression.
This is data-dependent, not an admin/editor permission failure: viewer/staff
without read state succeed. One marker also silently applied its cursor to
other conversations. Explicit `.correlate(Conversation)` on both marker queries
fixes the SQL scope without exception suppression, authorization changes or schema changes.

Baseline traceback (original `listing.py`, unmodified from `main`):
```text
tests/test_group_0_inbox.py:166 in test_inbox_multiple_read_cursors
    response = client.get(data.base + "/inbox")
app/inbox/listing.py:181 in list_inbox
    rows = context.db.execute(...)
sqlalchemy/engine/base.py:1969 in _exec_single_context
sqlalchemy/engine/default.py:952 in do_execute
    cursor.execute(statement, parameters)
psycopg/cursor.py:117 in execute
    raise ex.with_traceback(None)
psycopg.errors.CardinalityViolation: more than one row returned by a subquery used as an expression
sqlalchemy.exc.ProgrammingError: (psycopg.errors.CardinalityViolation) more than one row returned by a subquery used as an expression
```

Also found: `/inbox/events` crashes during its initial counts query for the same
admin/editor data; fixed by the shared helper. No other crash/5xx was found in
the four-role sidebar sweep. The actual thread API is `/conversations/{id}`;
`/inbox/{id}` is a web page and its API equivalent correctly returns 404.

Coverage: six website conversations spanning every status, assigned/unassigned,
AI/human mode, handoff, contacts, visitor/AI/agent/system messages, timestamp/UUID
ties, admin/editor read cursors, invitations and a change request. Independent
staff has no tenant membership. Tests assert per-user counts and filters,
read-marker updates, zero/one/multiple markers, tenant A/B isolation and explicit
200/403/404 statuses for 31 GETs per role. SSE HTTP transport is bounded to its
first event while retaining the real generator, SQL, authentication and serialization.

Database handling: only `127.0.0.1:55462` was contacted. Initially no connection
environment was set; a passwordless probe was rejected. The owner subsequently
allowed reading database fields in `.env.local`; both configured URL and
POSTGRES credentials were rejected on port 55462 (8 setup errors, then 1 setup
error with `-x`). No dev database was contacted or modified. The owner then
provided throwaway test credentials and prohibited further dotenv use. A local
credential-reading helper was deleted. Successful runs use only process-level
`TEST_DATABASE_URL` and `DATABASE_URL`, base database `group_0_inbox`; the harness
creates/migrates/cleans `group_0_inbox_test`. The plain `postgresql://` scheme is
required by the harness's direct psycopg maintenance connection. No connection
values were written to tracked files or dotenv files. `ENVIRONMENT=test` disables
dotenv loading. Providers remain fixture-controlled/offline.

Commands/results (PowerShell, API commands in `apps/api`; all pytest commands
use the process-only connection above plus `ENVIRONMENT=test`, `PYTHONUTF8=1`):
- Before the fix, `../../.venv/Scripts/python.exe -m pytest tests/test_group_0_inbox.py -k 'multiple_read_cursors or sidebar_get_sweep' -q --tb=short -p no:cacheprovider` — exit 1: **4 failed, 4 passed, 8 deselected**, 10.75s. Admin/editor regression and sweeps fail; viewer/staff pass. Log: `.test-storage-group-0/reproduction.log` (ignored).
- Before the fix, `../../.venv/Scripts/python.exe -m pytest tests/test_group_0_inbox.py::test_unread_zero_one_and_multiple_markers -q --tb=short -p no:cacheprovider` — exit 1: **2 failed, 1 passed**, 3.46s. Zero markers passes; one marker has wrong counts; two markers crashes. Log: `.test-storage-group-0/cursor-baseline.log`. An earlier version of this new assertion incorrectly counted the caller's own agent message as unread; corrected the expectation before this final baseline.
- After the fix, `../../.venv/Scripts/python.exe -m pytest tests/test_group_0_inbox.py -q --tb=short -p no:cacheprovider` — exit 0: **16 passed**, 15.61s, one existing Starlette deprecation warning. Log: `.test-storage-group-0/regression-green.log`.
- `../../.venv/Scripts/ruff.exe check --no-cache app/inbox/listing.py tests/test_group_0_inbox.py` — exit 0. Initial new-test formatting/import issues were corrected before the database runs.
- `../../.venv/Scripts/ruff.exe format --check --no-cache app/inbox/listing.py tests/test_group_0_inbox.py` — exit 0, both files formatted.
- `../../.venv/Scripts/mypy.exe --platform linux app/inbox/listing.py tests/test_group_0_inbox.py` — exit 0, no issues in 2 source files.
- In `apps/web`, `npm.cmd exec -- eslint lib/inbox-list.tsx lib/api.ts lib/session.tsx lib/app-header.tsx "app/app/[tenant]/inbox/page.tsx" "app/app/[tenant]/inbox/[conversation]/page.tsx" --max-warnings 0` — exit 0.
- In `apps/web`, `npm.cmd exec -- tsc --noEmit --incremental false` — exit 0. Direct TypeScript checking avoids Next's dotenv-loading setup commands.
- `../../.venv/Scripts/python.exe -m pytest tests/test_inbox_list.py tests/test_handoff.py -q --tb=short -p no:cacheprovider` — initial sandbox run exit 1: **5 failed, 1 passed, 4 setup errors**, 6.63s. Ingestion-dependent fixtures could not publish (`KNOWLEDGE_EMPTY`) before reaching inbox checks. Same targeted command rerunning with normal subprocess permissions; result to be recorded below. Logs: `.test-storage-group-0/existing-inbox-green.log`, `.test-storage-group-0/existing-inbox-green2.log`.

Final verification: the identical existing inbox/handoff command with normal
subprocess permissions exited **0: 10 passed**, 62.57s, one existing Starlette
warning. No product or fixture code was changed for that rerun. Together with
the new regression module, **26 relevant backend tests passed**. The four-role
sweep covers **124 GET/status checks**; no remaining 5xx/crashes were observed.
`git diff --check` also passed. Files touched: `apps/api/app/inbox/listing.py`,
`apps/api/tests/test_group_0_inbox.py`, `PROGRESS.md`. No migration is needed.
Frontend lint and TypeScript checks passed; no browser journey, production/demo
database, provider integration, or full suite was run (full suites explicitly
excluded by the owner). SSE long-lived behavior is covered by the existing
reconnection test, while the new role/data HTTP sweep checks its initial event.
Commit the fix/verification record, then perform the authorized local `--no-ff`
merge into main and delete the fix branch. No deployment/phase gate is implied.

## 2026-10-17 - Group B client visibility and role matrix

Owner scope: `fix/group-b-client-visibility` from merged, clean `main`; small
local commits, full checks once at the end, then authorized `--no-ff` merge and
branch deletion if green. No push, tags, Docker, paid calls or credential-file
reads. Hosting/billing OPEN decisions are outside this UI fix scope.

Step 0: owner rebuilt the stack and personally verified demo-admin and
demo-editor Overview and Inbox in the browser without errors; explicitly
instructed this agent to accept that evidence and skip another live M1 check.
No agent-run live/demo login check is claimed.

Changes: `implementation/ROLE-MATRIX.md`; client Overview landing and organization
links; direct default-bot Conversations sidebar destination with an empty/error
fallback; role-specific sidebar and command palette; pre-shell client redirects
for legacy Bots and operator-only bot routes; no client bot status/settings or
bot tabs; admin-only CSV links; read-only organization plan/usage with readable
labels and no client bot count, provisional notice or provider-token details.
Removed operator-only copy from client requests, Tenant data, and conversations.
Staff controls and Group A read-only staff Inbox behavior remain unchanged;
no API guard, schema, plan entitlement or backend source was modified.

Coverage: new four-role UI fixtures exercise sidebar/palette, hidden DOM text,
exports, contacts/follow-ups/merge/erase, conversation delete/retention, Inbox
controls, operator routes and settings; extra empty-list and unresolved-session
checks. Existing real-API role journeys now expect client Overview/redirects;
operator helpers explicitly enter the staff Bots list after fixture promotion.

Validation in progress (PowerShell; never writing DB connection values to files):
- Initial `npm.cmd run lint` and `npm.cmd run typecheck` launch attempts stopped
  before either check ran because NODE_OPTIONS parsed a backslash Windows path
  incorrectly (`MODULE_NOT_FOUND`). Corrected the preload path to forward slashes.
- `npm.cmd run lint` from root: exit 0. Log:
  `.test-storage-group-b/frontend-lint-final.log` (ignored).
- `npm.cmd run typecheck` from root: first actual check reported TS18047 for the
  nullable default-conversation sidebar state. Added an explicit non-null guard.
  Repeated the required check after that fix: exit 0, route types and TypeScript
  passed. Log: `.test-storage-group-b/frontend-typecheck-green.log` (ignored).
- Both Next commands use an ignored NODE_OPTIONS preload that replaces only
  `@next/env.loadEnvConfig` with the existing process environment, preventing
  automatic dotenv reads. No product configuration was changed for this.
- In `apps/api`: `../../.venv/Scripts/python.exe -u -m pytest -q --tb=short -p no:cacheprovider --basetemp=../../.test-storage-group-b/backend-tmp`
  is the single final full backend run. `ENVIRONMENT=test`, `PYTHONUTF8=1`;
  process-only TEST_DATABASE_URL/DATABASE_URL use the supplied throwaway account,
  normalized to plain postgresql for the harness's psycopg maintenance connection.
  Only `127.0.0.1:55462`, isolated `group_b_backend_test`; global stub flags and
  provider credential variables cleared in this child process, fixtures control
  offline providers. Log: `.test-storage-group-b/backend-full.log` (ignored).
- In `apps/web`: `npm.cmd run test -- --reporter=line` is the single final full
  browser run (51 tests), using its normal production build/API/worker harness,
  separate `group_b_browser_test` on port 55462, `E2E_API_PORT=18138`,
  `API_PROXY_TARGET=http://127.0.0.1:18138`, isolated ignored browser storage,
  `ENVIRONMENT=test`, `PYTHONUTF8=1`, the same dotenv-blocking Node preload and
  process-only database connection. Providers are stubbed by the existing browser
  harness. Log: `.test-storage-group-b/frontend-full.log` (ignored).
- Prettier formatted changed web files; `git diff --check` passed. Full suite
  outcomes will be appended after completion. No passing outcome is assumed.

Frontend verification completed:
- The single full browser command finished exit 1: **45 passed, 6 failed**, 5.2m.
  All 45 pre-existing cases passed. Five new cases had a DOM assertion that
  incorrectly treated the shared application theme button's "Appearance" label
  as a staff-only widget control. The sixth new case used an invalid mock cost
  response (`[]` instead of `{costs: []}`), causing the fixture-only staff page
  to error. Corrected only the new spec: match widget appearance/settings rather
  than the ordinary app theme button, and return the actual typed cost envelope.
  No product source was changed after the full browser run.
- In `apps/web`: `npm.cmd run test -- tests/group-b-client-visibility.spec.ts --config ../../.test-storage-group-b/visibility.config.ts --reporter=line`
  exited **0: 6 passed**, 32.4s. This is the only targeted follow-up, covering
  every new admin/editor/viewer/staff, empty-list and unresolved-session case.
  The ignored config reuses the existing production build and normal browser
  project but disables API setup/teardown because all six tests use API fixtures.
  Same dotenv-blocking Node preload; no database connection is needed for this
  targeted run. Log: `.test-storage-group-b/frontend-visibility.log` (ignored).
  Thus all **51 browser cases** have passing coverage on the final product;
  a second full-suite run was deliberately not performed, per owner instruction.
- In `apps/web`: `npm.cmd exec -- eslint lib/app-header.tsx tests/group-b-client-visibility.spec.ts --max-warnings 0`
  and `npm.cmd exec -- tsc --noEmit --incremental false`: both exit 0 after the
  final test-only corrections. Earlier full frontend lint and typecheck passed.
- The backend full suite is still running; no backend rerun has been started.

Files touched (paths below relative to `apps/web`, plus the two root records):
- Records: `implementation/ROLE-MATRIX.md`, `PROGRESS.md`.
- Navigation/entry: `app/app/layout.tsx`, `app/app/page.tsx`,
  `app/register/page.tsx`, `lib/app-header.tsx`, `lib/bot-workspace-nav.tsx`,
  `app/app/[tenant]/conversations/page.tsx`.
- Tenant views: `app/app/[tenant]/page.tsx`, `contacts/page.tsx`,
  `settings/data/page.tsx`, `settings/members/page.tsx`,
  `inbox/[conversation]/page.tsx` (last four relative to that tenant directory).
- Bot views under `app/app/[tenant]/bots/[botId]`: `settings/page.tsx`,
  `knowledge/page.tsx`, `install/page.tsx`, `playground/page.tsx`,
  `overview/page.tsx`, `conversations/[conversationId]/page.tsx`.
- Shared copy: `lib/labels.tsx`, `lib/change-requests.tsx`.
- Tests: `tests/group-b-client-visibility.spec.ts`, `tests/e2e-helpers.ts`,
  `tests/dashboard.spec.ts`, `tests/knowledge.spec.ts`,
  `tests/playground.spec.ts`, `tests/roles-control.spec.ts`,
  `tests/ui-redesign.spec.ts`.

Final backend and integration readiness:
- The single full backend command recorded above exited **0: 407 passed,
  1 skipped, 1 existing Starlette deprecation warning**, 1582.93s (26m22s).
  Skip: `tests/test_knowledge_parsers.py:52`, POSIX process-group integration;
  Windows behavior remains unverified. All API guard, tenant-isolation and
  Group 0 regression tests passed. No backend suite rerun was performed.
- Final frontend evidence: **45 existing browser cases passed** in the single
  full run, and **all 6 new Group B cases passed** after the documented test-only
  corrections in one isolated follow-up. Lint, TypeScript, changed-file Prettier
  check and `git diff --check` passed. No product source changed after the full
  browser production build/run; the isolated follow-up used that same build.
- Confirmed the generated evaluation report differs only by its run timestamp;
  restore that line to avoid unrelated changes. Final scope: 28 tracked files
  (26 web files plus ROLE-MATRIX and PROGRESS), no API/schema/migration changes.
- No Docker commands, credential-file reads, persisted connection values, paid
  API calls, push, tags or deployment. All DB runtime checks used only disposable
  databases on `127.0.0.1:55462`. Browser/API/worker harnesses stopped their owned
  processes. The OS-specific skip is the only remaining test limitation.
- All required Group B work is complete. Perform the owner's authorized local
  `git merge --no-ff fix/group-b-client-visibility` into `main`, then
  `git branch -d fix/group-b-client-visibility`; leave main clean. This does not
  imply production deployment or unrelated roadmap/hosting/billing sign-off.


## 2026-10-17 - Group C safety and polish

Authorization: Group B is merged at `4f0d01f`; work branch is
`fix/group-c-polish`, created from clean main. Owner explicitly authorizes
small local commits, a final `--no-ff` merge and branch deletion after checks.
No push, tags, Docker, production changes or paid provider calls authorized.
Hosting/billing OPEN decisions do not block this requested maintenance scope.

Verified before renaming: `ProvisioningService._provision` creates the onboarding
invitation with `role="admin"`; self-service membership also uses `admin`.
Acceptance is covered by the updated platform backend test, including refusal
of platform staff access for the invited admin.

Implemented admin API/frontend identifiers and new admin audit actions. Existing
audit rows stay untouched; both tenant/platform search and all three audit views
handle historical owner names. Historical provisioning fingerprints and replayed
result JSON remain compatible without a database column rename or migration.
GET data/export keeps its intentional audit write, with an explanatory comment.

Validation so far (PowerShell, repository root unless noted):
- `git status --short`, `git branch --show-current`, `git log -8 --oneline`:
  clean main with Group B merged. Initial sandbox `git switch -c
  fix/group-c-polish` could not write .git; the identical elevated command passed.
- First Node preload invocation failed before checks ran: path with spaces was
  not quoted. Corrected NODE_OPTIONS to a quoted absolute forward-slash path.
  The ignored `.test-storage-group-c/no-dotenv.cjs` disables only Next dotenv
  loading; no credential files were opened or configuration files changed.
- `npm.cmd run lint`, `npm.cmd run typecheck`: exit 0 (including route generation).
  Repeated after adding Group C fixtures: exit 0; logs in ignored
  `.test-storage-group-c/frontend-{lint,typecheck}.log`.
- `.venv/Scripts/python.exe -m ruff check --fix apps/api/tests/test_group_c_polish.py`:
  fixed import order; initially reported long lines. `ruff format` corrected them.
  Final changed-file Ruff check: exit 0.
- In apps/api, `../../.venv/Scripts/python.exe -u -m pytest -q --tb=short
  -p no:cacheprovider tests/test_group_c_polish.py tests/test_platform.py
  tests/test_self_service_signup.py tests/test_tenant_data.py
  tests/test_widget_appearance.py
  --basetemp=../../.test-storage-group-c/backend-targeted-tmp`:
  incomplete due to Windows sandbox temp-directory ACL errors, including pytest
  cleanup. Seven dots and thirteen setup errors were printed before the cleanup
  exception; this is not a passing suite result. Log: backend-targeted.log.
- In apps/api, `../../.venv/Scripts/python.exe -u -m pytest -q --tb=short
  -p no:cacheprovider --basetemp=../../.test-storage-group-c/backend-full-tmp`:
  full elevated run in progress. ENVIRONMENT=test, PYTHONUTF8=1, supplied test
  connection in child-process TEST_DATABASE_URL/DATABASE_URL only, normalized
  to plain postgresql for the harness's psycopg maintenance connection; only
  127.0.0.1:55462 and disposable postgres_test. Provider credentials and global
  stub flags cleared in the child environment. Log: backend-full.log.
- In apps/web, `npm.cmd run test -- --reporter=line`: full production build and
  62-test suite in progress with the dotenv-blocking preload, offline provider
  harness, isolated group_c_browser_test on the same authorized DB port,
  E2E_API_PORT=18148 and API_PROXY_TARGET=http://127.0.0.1:18148. All connection
  settings are child-process environment only. Log: frontend-full.log.

No live manual browser login verification was performed, per owner request.
Exact completed outcomes and final integration will be appended below.


Group C implementation and review notes:
- Reused the existing native-dialog ConfirmAction for all six requested action
  placements, retaining Cancel autofocus, Escape dismissal and focus restoration.
  Contact erase and organization-delete confirmations are unchanged.
- Retry is rendered only for failed jobs; Cancel only for pending (displayed as
  Queued) or running jobs, in both operations and knowledge lists.
- Appearance specs, checklist and UI now say Save settings applies changes live.
  The real install journey also checks the public widget config after saving.
- Added a shared React title component, SVG change-request icon, valid 32px ICO,
  and a server-side staff guard shared by platform and /widget/sample. Existing
  client-admin handoff coverage now uses the public widget frame for visitor
  turns; authenticated operator install/sample coverage remains.
- Encoding diagnosis: UTF-8 source in the contact detail page contained the
  actual U+00C2 U+00B7 sequence in the Conversation option and follow-up rows.
  Replaced it with U+00B7. No customer/production DB inspection or data rewrite
  was needed: the separator is a literal JSX string, not seed or DB content.
- The first browser build captured an initial Windows-script '?' in the newly
  added title strings. Source is corrected to literal UTF-8 middle dots; a final
  rebuild/run is required. Initial run also exposed the old non-staff sample
  handoff test and a new reset-test endpoint typo (/rag/limits vs actual /rag).
  Corrected the tests; no API endpoint behavior changed for these failures.
- Final review made legacy-name audit matching case-insensitive, with uppercase
  query coverage. This small follow-up requires a targeted backend run after
  the full suite (which had already imported the earlier helper/test version).

Additional static checks (not part of the owner's required backend test command):
- In apps/api, `../../.venv/Scripts/python.exe -m mypy`: exit 1, four pre-existing
  errors: knowledge/ingest.py POSIX-only os.setsid/os.killpg/signal.SIGKILL on
  Windows (3) and tests/test_rag_limits.py:246 int(object) (1). No changed file
  produced a mypy diagnostic. Log: backend-mypy.log.
- In apps/api, `../../.venv/Scripts/python.exe -m ruff check app tests`: exit 1,
  six pre-existing findings: db/models/chat.py and knowledge.py long strings,
  knowledge/service.py import order, quotas/sentiment.py and service.py long
  strings, tests/conftest.py import order. Log: backend-ruff.log.
- `git diff --quiet main --` all eight files named by those two checks: exit 0,
  proving these findings are in untouched main content. They are recorded here
  without expanding this maintenance task into unrelated backend refactors.


Initial frontend full run completed: exit 1, **55 passed, 7 failed**, 9.2m.
Failures: the non-staff sample handoff test (1), stale question-mark titles in
foundation/new title/sample cases (3), reset fixture endpoint typo (1), and two
existing tests that needed to click Confirm after Reset/Pause (2). All have
explicit corrections now. Both job lists, all audit views, five of the six new
complete confirmation cases, and appearance-save coverage passed in that run.
A transient closed-connection traceback appeared in API SSE cleanup; its test
passed. The final run will establish whether it recurs or affects verification.
No backend product changes followed except the documented audit-query case fix.

Updated existing `roles-control.spec.ts` and `ui-characterization.spec.ts` to
confirm the new dialogs while retaining their real payload and effective-limit
assertions. The next full browser command is again `npm.cmd run test --
--reporter=line` in apps/web with the same isolated process environment; output
is `.test-storage-group-c/frontend-final.log`. It rebuilds the final product.


Final frontend verification completed:
- `npm.cmd run lint`: exit 0; log frontend-lint-final.log.
- `npm.cmd run typecheck`: exit 0; route generation and tsc passed;
  log frontend-typecheck-final.log.
- In apps/web, `npm.cmd run test -- --reporter=line`: exit 0,
  **62 passed (5.1m)**. Final production rebuild included every source and test
  correction described above. No product/test changes followed this run.
  Log: `.test-storage-group-c/frontend-final.log` (ignored).
- All eleven new Group C tests passed, plus all 51 existing cases (with the
  documented sample-route/confirmation/metadata expectations updated).
  Coverage includes Cancel/Escape/focus restoration/no-write and one confirmed
  request for all six placements, both lists' five job statuses, all three
  audit displays, client navigation titles, SVG icons, actual rendered middle
  dots, favicon bytes, anonymous/client-admin denial of sample access, and
  staff sample access. The existing install journey verifies saved colour in
  the live public widget config with no publish step.
- The final API log includes three closed-connection tracebacks while cleaning
  up `event_stream` generators during navigation/teardown. All 62 tests passed;
  this log noise remains outside Group C changes (inbox backend is untouched).
  The frontend harness completed its normal process teardown.
- In apps/api, `../../.venv/Scripts/python.exe -m mypy --follow-imports=silent
  app/core/audit.py app/platform/router.py app/provisioning/router.py
  app/provisioning/service.py app/tenants/data.py tests/test_group_c_polish.py
  tests/test_platform.py tests/test_self_service_signup.py`: exit 0,
  no issues in eight changed files. Imported modules are excluded from this
  scoped check; the broader baseline findings above remain. Log:
  backend-mypy-changed.log.
- The same eight-file list passed `../../.venv/Scripts/python.exe -m ruff check`
  (exit 0); log backend-ruff-changed.log. `git diff --check main`: exit 0.


Group C files changed (46, relative to the repository root):

- `PROGRESS.md`
- `apps/api/app/core/audit.py`
- `apps/api/app/platform/router.py`
- `apps/api/app/provisioning/router.py`
- `apps/api/app/provisioning/service.py`
- `apps/api/app/tenants/data.py`
- `apps/api/tests/test_group_c_polish.py`
- `apps/api/tests/test_platform.py`
- `apps/api/tests/test_self_service_signup.py`
- `apps/web/app/app/[tenant]/bots/[botId]/conversations/page.tsx`
- `apps/web/app/app/[tenant]/bots/[botId]/knowledge/page.tsx`
- `apps/web/app/app/[tenant]/bots/[botId]/settings/page.tsx`
- `apps/web/app/app/[tenant]/contacts/[contactId]/page.tsx`
- `apps/web/app/app/[tenant]/settings/data/page.tsx`
- `apps/web/app/app/[tenant]/settings/members/page.tsx`
- `apps/web/app/favicon.ico`
- `apps/web/app/layout.tsx`
- `apps/web/app/platform/clients/[clientId]/page.tsx`
- `apps/web/app/platform/layout.tsx`
- `apps/web/app/platform/operations/page.tsx`
- `apps/web/app/platform/page.tsx`
- `apps/web/app/widget/sample/page.tsx`
- `apps/web/app/widget/sample/sample.tsx`
- `apps/web/lib/api.ts`
- `apps/web/lib/app-header.tsx`
- `apps/web/lib/labels.tsx`
- `apps/web/lib/page-title.tsx`
- `apps/web/lib/rag-operator-panel.tsx`
- `apps/web/lib/rag-tier-control.tsx`
- `apps/web/lib/staff-access.ts`
- `apps/web/lib/ui.tsx`
- `apps/web/tests/conversations.spec.ts`
- `apps/web/tests/e2e-helpers.ts`
- `apps/web/tests/foundation.spec.ts`
- `apps/web/tests/group-c-fixtures.ts`
- `apps/web/tests/group-c-polish.spec.ts`
- `apps/web/tests/install.spec.ts`
- `apps/web/tests/platform.spec.ts`
- `apps/web/tests/roles-control.spec.ts`
- `apps/web/tests/ui-characterization.spec.ts`
- `apps/web/tests/widget.spec.ts`
- `docs/18-EXPECTED-BEHAVIOUR.md`
- `docs/RAG-PLAN-v2.md`
- `implementation/FEATURE-INVENTORY.md`
- `implementation/MANUAL-TEST.md`
- `implementation/PHASE-CHECKLISTS.md`


Final backend and local integration readiness:
- The full backend command recorded above exited 0: **409 passed, 1 skipped,
  1 warning in 1601.46s (26m41s)**. The skip is
  tests/test_knowledge_parsers.py:52 (POSIX process-group integration on Windows).
  The warning is the existing Starlette TestClient/httpx deprecation.
- In apps/api, `../../.venv/Scripts/python.exe -u -m pytest -q --tb=short
  -p no:cacheprovider tests/test_group_c_polish.py
  --basetemp=../../.test-storage-group-c/backend-audit-final-tmp` exited 0:
  **2 passed, 1 existing warning in 2.03s**. This verifies the final uppercase
  admin/owner search behavior, immutable old/new history, tenant A/B isolation,
  authorization, stable historical provisioning fingerprints and admin replay
  responses. Same process-only disposable DB settings as the full backend run.
  Log: `.test-storage-group-c/backend-audit-final.log` (ignored).
- Final frontend: **62 passed**, full lint/typecheck passed. PowerShell
  `$files = @(git diff --name-only main -- apps/web | Where-Object {
  $_ -match '\.(ts|tsx)$' }); npm.cmd exec -- prettier --check $files`
  exited 0; log frontend-format-final.log. `git diff --check main`: exit 0.
- Runtime onboarding acceptance test passed: invited user receives admin and
  cannot access /platform/me. Self-service assigns admin and emits the new
  admin_assigned action. No DB columns or migration files were renamed.
- Confirmed the evaluation report changed only its generated timestamp and
  restored that unrelated line. Final scope is the 46 files listed above.
- Remaining limitations: manual/live browser login verification intentionally
  skipped; POSIX parser process-group behavior unverified on Windows; untouched
  baseline Ruff/mypy findings and SSE cleanup tracebacks documented above.
- No credential-file reads, persisted DB connection values, Docker commands,
  paid provider calls, customer sends, push, tags or deployment. DB runtime
  checks used only disposable databases on 127.0.0.1:55462 with the supplied test
  account. No customer or production database was inspected or changed.
- Requested implementation and checks are complete. The owner-authorized final
  local operations are `git switch main`, `git merge --no-ff
  fix/group-c-polish -m "Merge Group C safety and polish"`, then
  `git branch -d fix/group-c-polish`; leave main clean. This maintenance merge
  does not sign off unrelated roadmap phases, hosting or billing decisions.
## S1 - Staff organizations (2026-10-20; initial submission rejected, repaired and verified below)

- Branch: `feature/staff-organizations`; local commits only, no merge or push.
- Restored existing controls within the new tabs: Overview has reason-required plan assignment, quota overrides, organization data/deletion link, recent audit and usage; Bots has reason-required pause; Members has member rows and pending invitations; Knowledge retains ingestion failures and per-bot knowledge links.
- Restored the original deletion E2E journey, plan/quota/pause payload assertions, pending-invitation assertion and Recent audit check from `main`. Only tab navigation was added to those journeys; the organization title expectation reflects the S1 label rename. No assertion was replaced by an absence assertion.
- There is one plan-edit path: existing `PATCH /api/v1/platform/tenants/{id}/plan`, with required reason and existing `platform.tenant.plan_assigned` audit. New organization PATCH accepts name/status only and rejects `plan_label`. Added regression coverage for the rejected bypass and required reason/audit.
- Restored existing `PlatformStaffDep`: unauthenticated requests return 401 and authenticated non-staff return 403. Removed the custom organization staff dependency introduced by f2d92dd.
- Worker guard, backend fixtures, database guard tests and Playwright database-name derivation are restored exactly to `main`. The only E2E setup change is `TEST_DATABASE_URL ?? DATABASE_URL`. No database-name allowlist remains. The user will provide the base URL and confirm server reachability; it will be set per process only and never persisted. Tests must not target the base database.
- Repair static checks: `npm run lint` in `apps/web` exited 0; raw output tail: `> eslint . --max-warnings 0` (no findings). `npm run typecheck` in `apps/web` exited 0; raw output tail: `Generating route types...` / `Types generated successfully`.
- Repair syntax check: repository `.venv` Python `-m py_compile apps/api/app/platform/router.py apps/api/tests/test_platform.py` exited 0 with no output.
- No tests or server-connectivity probes have run during this repair, per the owner's instruction. Targeted platform tests, full backend, startup guard in its own process without either stub variable, and the five touched Playwright specs remain pending explicit server confirmation. Current repair has no runtime pass/fail/skip counts.
- Historical rejected-submission evidence only: the initial system-Python commands failed before collection (`No module named pytest`). The prior `.venv` database guard run reported `3 warnings, 6 errors in 0.14s`; these were fixture setup assertion errors caused by the invalid database-name allowlisting, not successful tests or confirmed database connection failures. Those changes are reverted. Earlier static passes do not verify this repaired implementation.
- No edits under `docs/`, credential-file reads, Docker commands, Phase 6 worktree changes, pushes, tags, deployments or merges.

## S1 verification rerun (2026-10-20; owner-approved disposable server)

- Owner authorized verification against the supplied loopback test server. Windows port probe `Test-NetConnection -ComputerName 127.0.0.1 -Port 55462 -InformationLevel Quiet` returned `True`.
- Connection values were assigned only in each test process, never written to a file. Backend fixtures derived their disposable test database; browser setup reported `/postgres_e2e_test`. No Docker commands, credential-file access, guard/allowlist changes, base-database test execution, Phase 6 changes, merge or push.
- The command records below omit the connection assignment to honor the no-URL-in-files rule; the final chat report supplies the exact commands. Backend cwd: `apps/api`; browser/static cwd: `apps/web`. All backend test commands used repository `.venv`, `-u -m pytest`, `-q --tb=short -p no:cacheprovider`, process-only workspace TEMP/TMP and basetemp. Model stubs were enabled except in the separate startup-guard process.
- Initial restricted-sandbox targeted run: 18 passed, 16 setup errors, 1 warning in 19.07s (12 KNOWLEDGE_EMPTY parser/temp restrictions, four Windows temporary-directory permission errors). A workspace-basetemp retry still failed at session cleanup with WinError 5 and no reliable final count. Running the same checks with host permissions resolved these environment failures; no application, fixture, guard or test assertions changed.
- Targeted backend: `tests/test_platform.py tests/test_platform_ops.py tests/test_quotas.py tests/test_tenant_route_matrix.py --basetemp=../../.test-storage-s1/pytest-host`: **34 passed, 0 failed, 0 skipped**.
- Initial full backend without UTF-8 mode: **402 passed, 3 failed, 1 skipped** in 1342.39s. All three failures were default Windows cp1252 decoding of Arabic evaluation outputs. The exact same three selected tests failed on both S1 (3 failed, 6.44s) and main `5c4d253` (3 failed, 7.88s): `test_rag_evaluation.py::test_two_mode_retrieval_eval_is_entirely_offline`, `test_rag_gate.py::test_stage0_raw_fts_gate_measurements`, `test_rag_stage0_baseline.py::test_real_fts_pipeline_checkpoints_and_never_replays`. Each reported `UnicodeDecodeError: 'charmap' codec can't decode byte 0x81`, respectively at positions 2399, 265 and 51. Set process-only `PYTHONUTF8=1`; all three then passed (8.38s). No test source changes.
- Final full backend ran the **identical command twice**, with `PYTHONUTF8=1`, both model stubs, `--ignore=tests/test_startup_guard.py --basetemp=../../.test-storage-s1/full-host`: **405 passed, 0 failed, 1 skipped** each (1352.44s / 1350.10s). Startup guard is excluded here because it ran separately as required.
- Startup guard: explicitly removed both `CHAT_STUB_MODEL` and `EMBEDDING_TEST_STUB` in its own process; `tests/test_startup_guard.py --basetemp=../../.test-storage-s1/startup-host`: **7 passed, 0 failed, 0 skipped**, 0.66s.
- Backend warning: existing Starlette/httpx TestClient deprecation. Sole full-suite skip: POSIX parser process-group integration on Windows.
- Initial five-spec browser run: **20 passed, 2 failed, 0 skipped (2.9m)**. The S1 platform-pause confirmation test was missing navigation to the Bots tab; added only the tab click and braces, preserving every confirmation assertion (commit `0932ce9`). The other timeout was the unchanged operations reason/cancel test: Cancel remained disabled while the previous retry asynchronously cleared the reason. An identical isolated command passed unchanged on S1 (1 passed, 45.2s) and main (1 passed, 48.5s). This does not prove a pre-existing baseline failure; record it as an observed transient with no assertion or product changes.
- Static checks after the tab fix: `npm run typecheck` exit 0; `npm run lint` exit 0; `git diff --check main...HEAD` exit 0.
- Test-line deletion review versus main: no tests or assertions removed. `e2e-api-setup.ts`: two assignments replaced by TEST_DATABASE_URL fallback. `group-c-fixtures.ts`: one `bots: [bot]` line expanded to the new response contract. `group-c-polish.spec.ts`: one unbraced if replaced with braces for the tab click, one title expectation renamed Client to Organization. All other changed test files have zero deleted lines.

Raw backend/static output tails:

```text
34 passed, 1 warning in 149.71s (0:02:29)

FAILED tests/test_rag_evaluation.py::test_two_mode_retrieval_eval_is_entirely_offline
FAILED tests/test_rag_gate.py::test_stage0_raw_fts_gate_measurements - Unicod...
FAILED tests/test_rag_stage0_baseline.py::test_real_fts_pipeline_checkpoints_and_never_replays
3 failed, 1 warning in 7.88s

3 passed, 1 warning in 8.38s

SKIPPED [1] tests\test_knowledge_parsers.py:52: POSIX process group integration; Windows unverified
405 passed, 1 skipped, 1 warning in 1352.44s (0:22:32)

SKIPPED [1] tests\test_knowledge_parsers.py:52: POSIX process group integration; Windows unverified
405 passed, 1 skipped, 1 warning in 1350.10s (0:22:30)

7 passed, 1 warning in 0.66s

> @chatbot/web@0.1.0 typecheck
> next typegen && tsc --noEmit

Generating route types...
✓ Types generated successfully

> @chatbot/web@0.1.0 lint
> eslint . --max-warnings 0
```

Verification command catalog (only the owner-supplied connection value is redacted; no URL persisted):

Targeted sandbox attempt:

```powershell
$env:TEST_DATABASE_URL='<owner-supplied base URL; process only>'; $env:CHAT_STUB_MODEL='1'; $env:EMBEDDING_TEST_STUB='1'; & ..\..\.venv\Scripts\python.exe -u -m pytest tests/test_platform.py tests/test_platform_ops.py tests/test_quotas.py tests/test_tenant_route_matrix.py -q --tb=short -p no:cacheprovider
```

Targeted sandbox basetemp retry:

```powershell
$env:TEST_DATABASE_URL='<owner-supplied base URL; process only>'; $env:CHAT_STUB_MODEL='1'; $env:EMBEDDING_TEST_STUB='1'; $env:TEMP=(Join-Path (Get-Location) '..\..\.test-storage-s1\temp'); $env:TMP=$env:TEMP; New-Item -ItemType Directory -Force -Path $env:TEMP | Out-Null; & ..\..\.venv\Scripts\python.exe -u -m pytest tests/test_platform.py tests/test_platform_ops.py tests/test_quotas.py tests/test_tenant_route_matrix.py -q --tb=short -p no:cacheprovider --basetemp=../../.test-storage-s1/pytest-tmp
```

Targeted host verification:

```powershell
$env:TEST_DATABASE_URL='<owner-supplied base URL; process only>'; $env:CHAT_STUB_MODEL='1'; $env:EMBEDDING_TEST_STUB='1'; $env:TEMP=(Join-Path (Get-Location) '..\..\.test-storage-s1\temp'); $env:TMP=$env:TEMP; New-Item -ItemType Directory -Force -Path $env:TEMP | Out-Null; & ..\..\.venv\Scripts\python.exe -u -m pytest tests/test_platform.py tests/test_platform_ops.py tests/test_quotas.py tests/test_tenant_route_matrix.py -q --tb=short -p no:cacheprovider --basetemp=../../.test-storage-s1/pytest-host
```

Initial full, without UTF-8:

```powershell
$env:TEST_DATABASE_URL='<owner-supplied base URL; process only>'; $env:CHAT_STUB_MODEL='1'; $env:EMBEDDING_TEST_STUB='1'; $env:TEMP=(Join-Path (Get-Location) '..\..\.test-storage-s1\temp'); $env:TMP=$env:TEMP; New-Item -ItemType Directory -Force -Path $env:TEMP | Out-Null; & ..\..\.venv\Scripts\python.exe -u -m pytest -q --tb=short -p no:cacheprovider --ignore=tests/test_startup_guard.py --basetemp=../../.test-storage-s1/full-host
```

Same selected encoding tests on S1 and main:

```powershell
$env:TEST_DATABASE_URL='<owner-supplied base URL; process only>'; $env:CHAT_STUB_MODEL='1'; $env:EMBEDDING_TEST_STUB='1'; $env:TEMP=(Join-Path (Get-Location) '..\..\.test-storage-s1\temp'); $env:TMP=$env:TEMP; New-Item -ItemType Directory -Force -Path $env:TEMP | Out-Null; & ..\..\.venv\Scripts\python.exe -u -m pytest tests/test_rag_evaluation.py::test_two_mode_retrieval_eval_is_entirely_offline tests/test_rag_gate.py::test_stage0_raw_fts_gate_measurements tests/test_rag_stage0_baseline.py::test_real_fts_pipeline_checkpoints_and_never_replays -q --tb=short -p no:cacheprovider --basetemp=../../.test-storage-s1/encoding-proof
```

Selected encoding tests with UTF-8:

```powershell
$env:PYTHONUTF8='1'; $env:TEST_DATABASE_URL='<owner-supplied base URL; process only>'; $env:CHAT_STUB_MODEL='1'; $env:EMBEDDING_TEST_STUB='1'; $env:TEMP=(Join-Path (Get-Location) '..\..\.test-storage-s1\temp'); $env:TMP=$env:TEMP; New-Item -ItemType Directory -Force -Path $env:TEMP | Out-Null; & ..\..\.venv\Scripts\python.exe -u -m pytest tests/test_rag_evaluation.py::test_two_mode_retrieval_eval_is_entirely_offline tests/test_rag_gate.py::test_stage0_raw_fts_gate_measurements tests/test_rag_stage0_baseline.py::test_real_fts_pipeline_checkpoints_and_never_replays -q --tb=short -p no:cacheprovider --basetemp=../../.test-storage-s1/encoding-proof
```

Final full, identical command executed twice:

```powershell
$env:PYTHONUTF8='1'; $env:TEST_DATABASE_URL='<owner-supplied base URL; process only>'; $env:CHAT_STUB_MODEL='1'; $env:EMBEDDING_TEST_STUB='1'; $env:TEMP=(Join-Path (Get-Location) '..\..\.test-storage-s1\temp'); $env:TMP=$env:TEMP; New-Item -ItemType Directory -Force -Path $env:TEMP | Out-Null; & ..\..\.venv\Scripts\python.exe -u -m pytest -q --tb=short -p no:cacheprovider --ignore=tests/test_startup_guard.py --basetemp=../../.test-storage-s1/full-host
```

Startup guard, own process:

```powershell
$env:TEST_DATABASE_URL='<owner-supplied base URL; process only>'; $env:PYTHONUTF8='1'; Remove-Item Env:CHAT_STUB_MODEL -ErrorAction SilentlyContinue; Remove-Item Env:EMBEDDING_TEST_STUB -ErrorAction SilentlyContinue; $env:TEMP=(Join-Path (Get-Location) '..\..\.test-storage-s1\temp'); $env:TMP=$env:TEMP; New-Item -ItemType Directory -Force -Path $env:TEMP | Out-Null; & ..\..\.venv\Scripts\python.exe -u -m pytest tests/test_startup_guard.py -q --tb=short -p no:cacheprovider --basetemp=../../.test-storage-s1/startup-host
```

Five browser specs, same command for initial and both subsequent runs:

```powershell
$env:TEST_DATABASE_URL='<owner-supplied base URL; process only>'; $env:DATABASE_URL=$env:TEST_DATABASE_URL; $env:ENVIRONMENT='test'; $env:PYTHONUTF8='1'; $env:CHAT_STUB_MODEL='1'; $env:EMBEDDING_TEST_STUB='1'; $env:E2E_API_PORT='18062'; $env:API_PROXY_TARGET='http://127.0.0.1:18062'; $env:PLATFORM_GUARD_ORIGIN='http://127.0.0.1:18062'; $env:E2E_REUSE_API='0'; $env:NEXT_TELEMETRY_DISABLED='1'; $env:TEMP=(Join-Path (Get-Location) '..\..\.test-storage-s1\temp'); $env:TMP=$env:TEMP; $env:STORAGE_ROOT=(Join-Path (Get-Location) '..\..\.test-storage-s1\e2e-storage'); $env:E2E_PYTHON=(Resolve-Path '..\..\.venv\Scripts\python.exe').Path; npx playwright test tests/organizations.spec.ts tests/platform.spec.ts tests/ui-characterization.spec.ts tests/group-a-members.spec.ts tests/group-c-polish.spec.ts --reporter=line
```

Operations browser check, identical command on S1 and main:

```powershell
$env:TEST_DATABASE_URL='<owner-supplied base URL; process only>'; $env:DATABASE_URL=$env:TEST_DATABASE_URL; $env:ENVIRONMENT='test'; $env:PYTHONUTF8='1'; $env:CHAT_STUB_MODEL='1'; $env:EMBEDDING_TEST_STUB='1'; $env:E2E_API_PORT='18062'; $env:API_PROXY_TARGET='http://127.0.0.1:18062'; $env:PLATFORM_GUARD_ORIGIN='http://127.0.0.1:18062'; $env:E2E_REUSE_API='0'; $env:NEXT_TELEMETRY_DISABLED='1'; $env:TEMP=(Join-Path (Get-Location) '..\..\.test-storage-s1\temp'); $env:TMP=$env:TEMP; $env:STORAGE_ROOT=(Join-Path (Get-Location) '..\..\.test-storage-s1\e2e-storage'); $env:E2E_PYTHON=(Resolve-Path '..\..\.venv\Scripts\python.exe').Path; npx playwright test tests/ui-characterization.spec.ts --grep "platform operations: reason gates" --reporter=line
```

Final verification outcome:
- Both subsequent five-spec browser commands: **22 passed, 0 failed, 0 skipped (1.7m)** each. The last run rebuilt commit `ead6e4a`, including the remaining analytics table heading rename to Organization. All original deletion, pending-invitation, recent-audit and reason-payload assertions passed.
- `npm run typecheck` and `npm run lint` passed again after the final label change. `git diff --check` passed. No backend source or tests changed after the two identical 405/0/1 backend runs.
- Confirmed zero diff versus main for worker guard, backend conftest/database guard tests, E2E database derivation helper and all of `docs/`. Restored only the evaluation report's generated timestamp after backend tests; no evaluation report change retained.
- Browser/API/worker test processes completed their normal teardown. Stopped on the feature branch for owner review; no merge, push or deployment.
- Deliberately retained existing routes, onboarding, reason-required plan/quota/pause actions, deletion flow and audit history. No new user/bot/invitation/deletion workflows, quota override UI, tables, migrations or statuses.
- Post-MVP follow-ups only: investigate the intermittent unchanged operations reason/cancel timing; make baseline evaluation-output file encoding explicit. Neither was changed in this slice.

Raw browser output tails:

```text
  2 failed
    [chromium] › tests\group-c-polish.spec.ts:74:7 › platform pause: Cancel and Escape do not write; Confirm writes once
    [chromium] › tests\ui-characterization.spec.ts:107:5 › platform operations: reason gates retry and cancel, audit search keeps its query
  20 passed (2.9m)

[e2e] Stopped the E2E API server.
[e2e] Stopped the E2E worker.
  1 passed (45.2s)

[e2e] Stopped the E2E API server.
[e2e] Stopped the E2E worker.
  1 passed (48.5s)

[e2e] Stopped the E2E API server.
[e2e] Stopped the E2E worker.
  22 passed (1.7m)

[e2e] Stopped the E2E API server.
[e2e] Stopped the E2E worker.
  22 passed (1.7m)
```

## 2026-10-21 — S4 change-password and S6 docs/auth-members (stacked on S3)

Branches, local commits only, nothing merged or pushed:
- `feature/change-password` stacked on `feature/staff-bots` (S3 tip 5ba4726): S4 endpoint
  `1beff4e` (POST /api/v1/auth/change-password: current-password verify with 400
  INVALID_CURRENT_PASSWORD, 400 PASSWORD_UNCHANGED, shared 8-200 policy via request schema
  (422), per-user failed-attempt throttle 5/300s via the existing Postgres fixed-window
  service (429 RATE_LIMITED), all OTHER sessions revoked, current session rotated so the
  caller stays signed in, auth.password_changed audit row with the user as actor, empty
  metadata) and Account UI `594470e` (shared lib/account.tsx form + top-level /account page
  reachable from both shells via a header Account link; no Google UI, no placeholder).
- `chore/docs-auth-members` stacked on feature/change-password: Register-link flag c38746f
  (login page reads /auth/config like /register; link hidden while the flag is off or the
  request fails, fail closed), docs b510a8e (docs 02/04/05/11/12/14 §19/15/18/19 §5,
  closeout §5 runbook rewrite, README first-org/user/bot, DECISIONS ADR-021 — ADR-020 is
  reserved by the Phase 6 branch, next free number ADR-022).

Pre-existing S2/S3-era browser-spec bugs fixed during the deferred combined run (no
assertions weakened, only flow/locators aligned with built behaviour):
- `5a9dff8` fix(S2): knowledge/playground/roles-control specs pre-register the member in
  an isolated context (invitations are existing-users-only since S2; page.request shares
  the context cookie jar, so registration happens outside the admin context), then
  sign in and accept; staff-members.spec selects by accessible name (wrapping labels
  include the selected option's textContent) and locates the created member via the
  directory's own search filter (oldest-first listing, 25 per page).
- `94f0584` fix(S3): staff-bots.spec create-bot Organization combobox by accessible name.
- `0d4b7ba` test(S4): the E2E harness sets LOGIN_RATE_LIMIT_ATTEMPTS=1000 through the
  existing Settings env knob because all Playwright traffic shares one client IP and the
  whole suite's logins compressed into one 300s window; product default (10/300s) and all
  pytest limiter tests unchanged.

Verification (Windows venv through WSL with WSLENV forwarding; TEST_DATABASE_URL
postgresql://test:test@127.0.0.1:55462/postgres per process, never written to a file):
- Backend targeted (apps/api, ENVIRONMENT=test PYTHONUTF8=1): test_change_password.py
  10 passed; test_change_password + test_self_service_signup + test_auth 30 passed;
  test_auth + test_change_password + test_staff_member_errors +
  test_staff_member_revocation_race 28 passed.
- Full backend suite (separate process, -p no:cacheprovider --basetemp=.test-storage-s3):
  S4 state 466 passed / 1 skipped (POSIX process-group skip) / 0 failed in 25m45s;
  final S6 state 467 passed / 1 skipped / 0 failed in 25m37s (adds the S6
  INVITATION_REQUIRED contract test). An earlier run with 3 UnicodeDecodeError failures
  was environmental (PYTHONUTF8 not forwarded through WSLENV); rerun of those three files
  48 passed.
- Web: next typegen + tsc --noEmit clean; eslint --max-warnings 0 clean; prettier clean
  on every touched file.
- Playwright: account.spec 5 passed; login-register.spec 2 passed; FULL suite
  (S1 harness: E2E_API_PORT=18062, API_PROXY_TARGET/PLATFORM_GUARD_ORIGIN to the same
  port, E2E_REUSE_API=0, stubs on, disposable postgres_e2e_test DB) 75 passed / 0 failed
  in 3.4m. Two earlier full runs (62/75 and 70/75) traced to the missing ENVIRONMENT
  forwarding (worker fell back to development, embeddings refused) and to the
  pre-existing spec issues fixed above; the worker/env diagnosis was done with
  temporary uncommitted debug prints, reverted before commit.
- S5 (Google sign-in) is deferred by owner instruction: no Google UI, no placeholder, no
  schema change; design recorded in DECISIONS.md (ADR-021).
- implementation/PHASE-03/EVAL-REPORT.md is regenerated by backend eval tests (timestamp
  only); the working-tree copy was restored after each run. Deliberately untouched:
  Stage 1 drift items (RETRIEVAL_MIN_MATCHED_TERMS alignment, fts_ar vs simple truth,
  ADR-019 dated notes in docs 07/14/18, MANUAL-TEST compose paths) and all Phase 6 files.

## 2026-10-22 — A1.2–A1.7 batch (branch feat/a1.2-field-details, created from main)

Commits (local only, no push/tag/merge): 53a3415 A1.2 API 422 field details;
b73f1bd A1.2 web inline field errors; be4a3b7 A1.3 phone country-code + national
input; 3277f2c A1.4 API domain normalization; 75cbb8b A1.4 web settings
normalization; 615d748 A1.5 provider-failure trace/log; dd267e5 A1.6 tier
provider/model display. All commit messages carry the required trailer.

Verification environment: Windows venv (`.venv/Scripts/python.exe`, Python
3.12.10) driven from WSL, as in earlier sessions.

Commands and outcomes:
- `python -m ruff check <touched files>` per commit — All checks passed!
- `python -m ruff format --check <touched files>` per commit — formatted.
- `python -m mypy --follow-imports=silent <touched app files>` — Success, no
  issues. (`mypy` on the Windows venv reports 3 pre-existing errors in
  `app/knowledge/ingest.py` (os.setsid/killpg/SIGKILL) — POSIX-only attrs,
  untouched by this batch, not fixed here per batch scope.)
- `npm run typecheck` (next typegen + tsc --noEmit) — clean after each web
  commit; `npx eslint <touched files> --max-warnings 0` — clean; prettier run
  on every touched web file.

NOT verified (blocked, no fabrication):
- Disposable test DB `saas-test-db` on 127.0.0.1:55462 refused connections
  (`psycopg` ConnectionTimeout; socket-level ConnectionRefusedError). Starting
  containers is owner-only, so NO pytest run and NO Playwright run happened in
  this session. The new/extended tests (test_validation_details.py,
  test_allowed_domains.py, test_chat.py provider-failure tests, test_rag_limits
  tier-targets test, staff-members.spec.ts, staff-bots.spec.ts) are written
  against existing fixtures but their outcome is unverified until the owner
  brings the disposable DB back and runs:
  `cd apps/api && TEST_DATABASE_URL=postgresql://test:test@127.0.0.1:55462/postgres ENVIRONMENT=test PYTHONUTF8=1 python -m pytest tests/test_validation_details.py tests/test_allowed_domains.py tests/test_chat.py tests/test_rag_limits.py`
  and the Playwright specs `staff-members.spec.ts`, `staff-bots.spec.ts`.
- A1.7 investigation (read-only, no code change): uploads never enqueue jobs —
  `upload_files` (apps/api/app/knowledge/service.py:70-162) only creates Source
  rows with status "stored"; the only enqueue path is `start_ingestion`
  (service.py:206-268) on the explicit `POST .../ingestion` endpoint
  (apps/api/app/knowledge/router.py:96-107) behind its own UI click, with the
  submit button disabled while a request is in flight
  (knowledge/page.tsx ~line 283, `disabled={ingesting || storedSources.length === 0}`).
  A second ingest POST after sources are committed as "queued" returns 409
  NOTHING_TO_INGEST (service.py:244-245). So two uploads create zero jobs (the
  explicit ingest click enqueues one batch job for all stored sources) and one
  click cannot enqueue twice. A theoretically simultaneous duplicate POST
  landing between read and commit of the first is the generic double-submit
  window on the ingest action, not an upload behavior; no idempotency added,
  nothing changed.
- A1.1 acceptance items (Dockerfile copies public / loader diff) belong to the
  feat/a1.1-serve-web-public branch (commit 7d04ef1), not this branch. Read-only
  cross-check from this branch: apps/web/public contains only `widget/`, and
  apps/web/Dockerfile on main does NOT copy public yet; on the A1.1 branch the
  generated copy `apps/web/public/widget/v1/loader.js` (206 lines) and
  `packages/widget/src/loader.js` (206 lines) are byte-identical after CRLF/LF
  normalization (cmp clean).

## R3 - answer correctness part 2 (branch fix/r3-answers, local commits only)

Items 1-6, 8, 9 implemented, one commit each (git log 1d0b2b7..HEAD); item 7 is a
read-only proposal in the batch report. Disposable DB 127.0.0.1:55462 (r3_test),
TEST_DATABASE_URL set per process, `PYTHONUTF8=1` on Windows.

- Full run: `python -m pytest tests/test_chat.py tests/test_chat_streaming*.py tests/test_cross_*.py tests/test_handoff.py tests/test_hybrid_retrieval.py tests/test_knowledge_language.py tests/test_model_not_configured.py tests/test_provider_params.py tests/test_rag_*.py tests/test_retrieval.py tests/test_routing.py tests/test_stable_tie_break.py tests/test_trace_context.py tests/test_turn_deadline.py tests/test_widget_*.py tests/test_playground_parity.py tests/test_bots.py tests/test_bot_readiness.py tests/test_conversations.py tests/test_migrations.py tests/test_quotas.py tests/eval`
  -> 370 passed, 4 failed WITHOUT PYTHONUTF8 (3 are cp1252 decode errors in test_rag_gate::test_stage0_raw_fts_gate_measurements, test_rag_evaluation::test_two_mode_retrieval_eval_is_entirely_offline, test_rag_stage0_baseline::test_real_fts_pipeline_checkpoints_and_never_replays; they pass with PYTHONUTF8=1). The 4th,
  test_chat_streaming::test_client_disconnect_stops_the_provider_and_persists_nothing, fails the same way on the R2 merge (1d0b2b7) with my changes stashed: pre-existing.
- Migration 0020 (usage_events kind 'unavailable') applied by test_migrations up/down/up.
- Web: `npx tsc --noEmit` and `npm run lint` clean. Playwright not run (needs servers).
- gate_compare before/after on nile_eval.jsonl: identical (fts_only 26/27 kept, 6/12 leaks; hybrid+test embedder 23/27, 5/12).

## R3b - router after retrieval + widget line breaks (branch fix/r3b-router-widget, local commits only)

Base: main 0a99fdb (fix/r3-answers merged). Commits: a4fc989 (routing, #111), 0792d6d (widget CSS).
Disposable DB 127.0.0.1:55462, TEST_DATABASE_URL per process, `PYTHONUTF8=1`.

- Routing: pre-retrieval only smalltalk + explicit person requests (reason visitor_requested).
  Order/account keywords count after retrieval (no evidence, model refusal, invalid_output) ->
  kind "handoff", reason order_account; handoff toggle off -> plain cannot_confirm. Trace:
  `routing_stage` (pre_retrieval|post_retrieval), `routed_handoff_reason`, `handoff_reason`.
  `decide_handoff` gives a routed handoff visitor_requested when the person keywords match, else order_account.
- Widget: the AI bubble class is `.widget-bubble` (`widget-ai-msg` is its test id) in apps/web/lib/widget-styles.ts;
  `.widget-bubble:not(.visitor){white-space:pre-wrap;overflow-wrap:anywhere}`. Playground `.message-text` already had both.
- Tests: `python -m pytest tests/test_routing.py tests/test_chat.py -q` -> 90 passed.
  `python -m pytest tests/test_handoff.py tests/test_chat_streaming.py tests/test_chat_streaming_unit.py tests/test_playground_parity.py tests/test_group_0_inbox.py tests/test_trace_context.py tests/test_widget_public.py tests/test_rag_traces.py tests/test_followups_analytics.py tests/test_model_not_configured.py -q`
  -> 114 passed, 1 failed (test_chat_streaming::test_client_disconnect_stops_the_provider_and_persists_nothing,
  already failing on the R2 merge per the R3 entry above).
- ruff check/format clean on touched files; mypy on touched files: only the existing Windows os.setsid/killpg errors in knowledge/ingest.py.
  Web `npm run typecheck` and `npm run lint` clean.
- Eval (stub, `tests/eval/test_nile_eval.py test_gate_compare.py test_eval.py`, 4 passed before and after; before = app/ from 0a99fdb):
  gate-passed 80.0/72.0 -> 96.0/88.0 (fts_only/hybrid); wrong refusals 44.0 -> 36.0 (both modes);
  cites expected page 52.0/48.0 unchanged; abstain 91.7, injection 100 unchanged; Arabic grounded 9.1 unchanged.
  The four cases: before all 8 rows (4 x 2 modes) were `handoff`. After, tracking-number-en and fu-cod-cancel-en are
  `answer` with a retrieval hit (the stub cites a different chunk, so cited_hit stays false); the Arabic pair has a
  retrieval hit but the extractive stub refuses Arabic, so they end in a post-retrieval handoff (stub limitation).
  gate_compare is retrieval-only: unaffected by routing.

## R3c - provider failures self-explaining, free chain, model defaults, widget layout (branch fix/r3c-provider-widget, local commits only)
Base check: R0, R2, R3 and R3b are all merged on main (958b48e). Commits: e1a7a8c (items 1-3), 0abd779 (4), f066949 (5), f3c199a (6), 71c5857 (7).
Tests (disposable DB 127.0.0.1:55462, TEST_DATABASE_URL per process, `PYTHONUTF8=1`, ENVIRONMENT=test):
- `pytest tests/test_free_chain.py tests/test_provider_attempts.py` -> 19 passed.
- `pytest tests/test_provider_params.py tests/test_chat.py tests/test_chat_streaming_unit.py tests/test_model_not_configured.py tests/test_rag_traces.py tests/test_playground_parity.py tests/test_bot_readiness.py tests/test_rag_limits.py` -> first run 103 passed, 1 failed (test_rag_traces::test_premium_and_standard_provider_contracts_are_mocked: plain-text reply in JSON mode lost its usage totals; fixed by recording usage on the unusable-reply fallback). Re-run of test_rag_traces, test_provider_attempts, test_free_chain, test_provider_params, test_chat_streaming_unit, test_model_not_configured -> 67 passed. The other four files passed in the first run.
- ruff check / ruff format --check / mypy on touched app files: clean. Web `npm run typecheck` and `npm run lint`: clean.
- NOT run (owner policy): full pytest, full evals, Playwright. apps/web/tests/widget-layout.spec.ts is new and was NOT run.
Deviations: items 1-3 share one commit (their hunks interleave in providers.py/service.py); the config.py default for gpt-5.4-nano landed in that commit while its docs/fixtures are in item 6. Cost for gpt-5.4-nano stays "Unmeasured" (no price table in the repo). gpt-4.1-nano remains only in the ADR note, .env.example and config comments explaining the deprecation, history docs and the owner's .env.local (not touched).

## H2 - Knowledge hygiene (working tree on fix/r3c-provider-widget, on top of the uncommitted H1 changes; NOT committed)
Implemented: migration 0022 (`sources.status` gains `removed`; `documents.duplicates_removed`); upload dedupe by sha256 per bot
(200/201, `duplicate` + `message` on the returned source); replace (`POST .../sources/{id}/replace`, refreshes `created_at` so the new
version counts as "newer"); soft delete (`DELETE .../sources/{id}`: draft rows + source_pages removed, status `removed`, size 0, file
deleted after commit, audit row); cross-source duplicate chunks (newer source wins, `duplicates_removed` warning in the document list,
`_copy_revision_snapshot` skips removed sources); always-include by stable source id (`config.always_include_source_ids`, PUT on the
source or PATCH bot config, resolved to live-revision document ids per chat turn, capped to `retrieval_final_k - 1` chunks, 3 sources);
knowledge UI controls (always include, replace, remove with confirmation) and the duplicate message; permissions table entries.
Legacy `config.always_include_document_ids` is no longer read by chat (nothing could set it).
Verified by me: `ruff check app` (only the pre-existing E501s remain: db/models/chat.py, quotas/*, db/models/knowledge.py:87), `ruff format` on touched
knowledge/bots/chat files, `python -c "import app.main"`, web `npx tsc --noEmit` clean.
NOT RUN: any pytest (no TEST_DATABASE_URL in this session), the new `apps/api/tests/test_knowledge_hygiene.py` (written, never executed),
migration 0022 against a database, Playwright (`knowledge.spec.ts` new test written, not run), the post-green review agent.
Open: publishing a draft with zero chunks is still 409 KNOWLEDGE_EMPTY, so removing the only source cannot be published.

## H3 - Conversation intelligence (working tree on fix/r3c-provider-widget, on top of the uncommitted H1/H2 changes; NOT committed)
Implemented: conversational intents in `chat/routing.py` (identity, capability, how_are_you, thanks, farewell, greeting; whole-token, EN+AR,
fillers allowed, 8-token cap; any leftover token sends the message to retrieval). Replies are composed from bot config only
(`prompts.meta_reply`, `service.conversational_reply`); `kind` stays `smalltalk` (no consumer changes), trace `meta_intent`,
`can_answer=true`, `needs_human=false`. Refusal with direction (`retrieval/trace.near_miss_topics`, `service.refusal_text`, canned
`cannot_confirm_topics`; trace `suggested_topics`). Follow-ups: `service.rewrite_reason` (opener regex, back-references, <2 content terms),
one retry on the condensed query after a refusal (not when a trigger rewrite already ran), `rewrite_plan_allowed` (empty/`*` = all plans,
unknown labels keep the rewrite, a blocked plan is traced as `rewrite_skipped`). Prompt passes the language NAME, `PROMPT_TEMPLATE_VERSION`
2026-10-25.1 (pinned hash in `test_tone_prompt.py` updated; the only body change is "en" -> "English"). History skips conversational
exchanges. Docs: dated note in docs/14 section 6.
Disposable DB: docker `saas-test-db` 127.0.0.1:55462, database `h3_test`; env `PYTHONUTF8=1 ENVIRONMENT=test`; one pytest process at a time
(two at once deadlock on TRUNCATE).
Tests (exact outcomes):
- `pytest tests/test_conversation_intelligence.py tests/test_routing.py tests/test_rag_gate.py tests/test_chat.py tests/test_playground_parity.py tests/test_tone_prompt.py tests/test_handoff.py tests/test_trace_context.py tests/test_cross_script.py tests/test_chat_streaming_unit.py tests/test_turn_deadline.py` -> 253 passed, 7 failed. Five were my own stale assertions or bugs, fixed afterwards.
- Rerun `pytest tests/test_conversation_intelligence.py tests/test_tone_prompt.py tests/test_turn_deadline.py tests/test_chat.py::test_reply_language_follows_the_visitor` -> 94 passed.
- `tests/test_rag_gate.py::test_provider_has_no_retries_and_only_one_fallback` FAILS (requests_used 3 != 2). `chat/providers.py` is unmodified, so this is not from H3; not investigated.
- NOT rerun after the final fixes: the other files in the first list (test_routing, test_rag_gate, test_chat, test_playground_parity, test_handoff, test_trace_context, test_cross_script, test_chat_streaming_unit), and the wider suite (test_widget_*, test_conversations, analytics, web/Playwright).
- Eval stub (`tests/eval/test_eval.py`): NOT obtained. Working tree: fails in `tests/knowledge_helpers.py:147` (DetachedInstanceError on an ingest Job) before any chat call, probably the uncommitted H2 ingest work. HEAD checkout: alembic cannot load the revisions the shared test DB already has. So no before/after numbers; none are claimed.
Review agent (read-only, 20+ EN/AR adversarial messages, traced by reading code): found one real bug of mine (FOLLOW_UP regex had lost its `\b`), fixed with regression tests; also fixed "are you a real person" being handed off, the Arabic "...ورحمة الله وبركاته" greeting, a double condense call after a refusal, and "كم سعره" not being condensed. Left as is: informational questions that name staff ("customer service hours, any agent available") still hand off pre-retrieval (existing documented rule: an explicit person request outranks informational wording); pure-filler messages over 8 tokens go to retrieval.
Known behaviour: conversational turns are can_answer=true, so they never count as unanswered, but like greetings before they also break a run of unanswered turns.

## H4 Part A - retrieval term quality and measurement (commit on feat/rag-hardening-h1-h3; Part B not started, needs owner spend approval)
Implemented (offline): built-in EN/AR (MSA, Gulf, Egyptian, Levantine) filler list used only for the matched-TERM count (`retrieval/query.py`; ranking query unchanged; `retrieval_gate_ignore_terms` applies on top);
Arabic stop words spelt with أ إ ى (على، إلى، أو، متى) now leave the count (they never matched after normalisation; ranking query deliberately untouched);
`ChunkVerdict.failed_rules`, `trace.refusal_diagnosis` (nearest candidate, shortfalls, best per signal), playground line; `evaluation.page_sweep` + `scripts/rag_threshold_sweep.py` (prints, applies nothing);
42 recall cases `tests/eval/nile_recall_eval.jsonl` (paraphrase/typo/dialect/mixed/unanswerable) with `recall_metrics.py`, `recall_runner.py`, `test_recall_eval.py`; docs/14 section 5 H4 note.
Verified (exact): `PYTHONUTF8=1 ENVIRONMENT=test python -m pytest tests/eval/offline -q` -> 52 passed; `ruff check` clean on touched files; mypy on touched files: only the existing ingest.py Windows setsid/killpg errors; web `npx tsc --noEmit` clean.
Fix outside the feature: `tests/knowledge_helpers.py::drain_jobs` now `refresh`+`expunge`s each Job (it returned expired, detached rows -> DetachedInstanceError that blocked every eval seeding, as noted under H3).
Disposable DB: docker `saas-test-db` 127.0.0.1:55462, database `h4_test`; `PYTHONUTF8=1 ENVIRONMENT=test`, one pytest process at a time.
DB tests (exact): `pytest tests/test_rag_gate.py tests/test_rag_traces.py tests/test_trace_context.py tests/test_retrieval.py tests/test_conversation_intelligence.py tests/test_chat.py tests/eval` -> 218 passed, 1 failed in 865.9 s.
The failure, `test_rag_gate.py::test_provider_has_no_retries_and_only_one_fallback` (requests_used 3 != 2), is the same one recorded under H3; `chat/providers.py` is unmodified. Not investigated.
Recall eval (retrieval + gate only, no provider, no chat model): `RECALL_EVAL_WRITE=1 pytest tests/eval/test_recall_eval.py -q -s` -> report `tests/eval/results/recall-2026-10-25-1603.{md,json}` (42 cases: 34 answerable, 8 unanswerable).
CAVEAT: hybrid uses the deterministic test embedder (token hash), NOT semantic. Its cosine numbers are plumbing only; real Arabic/dialect semantic recall is unmeasured (needs Part B).
| | fts_only hit@3 / hit@8 / wrong refusals | hybrid (test embedder) hit@3 / hit@8 / wrong refusals | leaks (8 unanswerable) |
|---|---|---|---|
| all | 26/34, 26/34, 12/34 | 18/34, 21/34, 11/34 | 3 / 3 |
| paraphrase | 12/14, 12/14, 1/14 | 7/14, 9/14, 2/14 | |
| typo | 9/10, 9/10, 6/10 | 8/10, 8/10, 6/10 | |
| dialect (AR) | 4/8, 4/8, 4/8 | 1/8, 2/8, 3/8 | |
| mixed | 1/2, 1/2, 1/2 | 2/2, 2/2, 0/2 | |
| Arabic / English | 14/20 hit, 7/20 refused / 12/14 hit, 5/14 refused | 12/20 hit@8, 5/20 / 9/14, 6/14 | |
Findings: most wrong refusals are retrieved-but-gated (the expected page is rank 1 or 2 yet only 1 matched term, e.g. typo-return-window-en, typo-cutoff-en, typo-electronics-ar), not retrieval misses. Leaks are the store-name + filler questions (gap-store-fillers-en/ar) and gap-instalments-en.
Gate compare on the Nile set (`GATE_CANDIDATES`, retrieval only): fts_only defaults 26/27 kept, 6/12 leaks; ignore-store 26/27, 3/12; one-term 27/27, 10/12; one-term+ignore-store 27/27, 9/12. hybrid: defaults 23/27, 5/12; ignore-store 23/27, 2/12; one-term 24/27, 10/12; one-term+ignore-store 24/27, 9/12.
Sweep (`scripts/rag_threshold_sweep.py` over recall + Nile no-history cases: 57 answerable, 22 unanswerable; chunk-level replay, so absolute leak counts exceed the case-level gate compare). fts floor 0.01, cosine off:
| min terms | wrong refusals | wrong-evidence only | unanswerable leaks |
|---|---|---|---|
| 1 | 2 | 6 | 18 |
| 2 (current) | 12 | 3 | 10 |
| 3 | 27 | 4 | 3 |
FTS floor 0.005-0.2 and (hybrid, test embedder) cosine 0.40-0.60 changed nothing material. 3 leaks remain even at 3 terms (store-name cases).
RECOMMENDATION TABLE (owner decides; nothing applied, defaults unchanged):
| Option | Effect on this sample | Risk | Status |
|---|---|---|---|
| Keep min terms 2, FTS 0.01, cosine 0.50 | baseline | high wrong refusals on typo/dialect (12/57 chunk-level) | current |
| Add store-name ignore list per bot (`retrieval_gate_ignore_terms`) | leaks 6/12 -> 3/12 (fts), 5/12 -> 2/12 (hybrid), no recall loss | needs per-bot config | recommended to adopt, owner sign-off |
| min terms 1 | wrong refusals 12 -> 2 | leaks 10 -> 18 of 22; unsafe alone | not recommended |
| min terms 3 | leaks 10 -> 3 | wrong refusals 12 -> 27 | not recommended |
| FTS floor / cosine floor changes | no measurable effect here | cosine needs a real embedder | defer to Part B |
Next: Part B (real embeddings, both tiers) needs the owner's written spend limit; not started. Nothing committed.
## H5 - staff tooling, quotas and resilience (feat/rag-hardening-h1-h3; stopped at the gate)
Implemented:
1. Draft preview: playground body `knowledge: "published"|"draft"` (default published); `resolve_preview_revision` (409 `NO_DRAFT_REVISION` if none); `chat_answer(preview_revision_id=)` -> `retrieve_hybrid(preview=True)` which only accepts a DRAFT of the same tenant+bot. `visitor_chat_turn` raises 403 if a preview id is given on a non-playground conversation; the widget paths never pass one. Trace gains `revision_kind`; playground UI has a Published/Draft radio and shows the revision in the trace.
2. Quota hygiene (no migration): playground `message` events and `ai_usage` message reservations carry `payload.source="playground"`; `counts_toward_message_quota()` excludes them from tenant monthly count (`usage_snapshot`), per-bot `monthly_usage`, widget daily cap, platform client month count and analytics event counts; a playground turn is not blocked by an exhausted message quota. Tokens still count. Platform per-client usage lists `playground_message` apart from `message`.
3. Premium fallback: `CHAT_OPENAI_FALLBACK_MODELS` (JSON, validated: unique, no whitespace, max 3), passed as `fallback_models` for the OpenAI tier (primary excluded). Provider rules unchanged: one attempt per model, 401/402 block and never fall back (buffered and streaming). Standard keeps `free_only`.
4. Widget polling: `GET .../messages` returns `X-Poll-Hint: active|idle` (human mode/waiting_human or scheduled/ready follow-up = active). Frame polls only while active (or after a seen handoff until the first hint), one look after each turn and on tab-visible, exponential backoff 2 s -> 30 s on errors, none when hidden; `?debugWidget=1` logging kept. Rules in `apps/web/lib/widget-polling.ts`.
5. PDF context: if a page ends without terminal punctuation and the next starts lowercase/uncased, the previous page's unfinished sentence (<=300 chars) leads the next page's first chunk; page_ref/document text unchanged.
Docs: docs/09, 13, 14 and `.env.example` updated.
Verified (exact): disposable DB docker `saas-test-db` database `h5_test`; `ENVIRONMENT=test PYTHONUTF8=1 pytest tests/test_h5_staff_tooling.py tests/test_quotas.py tests/test_widget_public.py tests/test_conversations.py tests/test_playground_parity.py tests/test_chat_streaming.py tests/test_chat_streaming_unit.py tests/test_chat.py tests/test_provider_attempts.py tests/test_provider_params.py tests/test_free_chain.py tests/test_rag_gate.py tests/test_rag_traces.py tests/test_trace_context.py tests/test_knowledge_pipeline.py tests/test_knowledge_parsers.py tests/test_analytics.py tests/test_platform.py tests/test_platform_ops.py tests/test_hybrid_retrieval.py tests/test_followups_analytics.py tests/test_handoff.py tests/test_rag_limits.py tests/test_tenant_route_matrix.py` -> 317 passed, 4 failed, 1 skipped (28m38s). That run predates the added streaming-401 test in test_h5_staff_tooling.py (+2 params), which was not re-run on its own.
The 4 failures also fail on the stashed pre-H5 tree (re-run: 4 failed, 4 passed): test_chat_streaming::test_client_disconnect_stops_the_provider_and_persists_nothing, test_rag_gate::test_provider_has_no_retries_and_only_one_fallback (known since H3), test_tenant_route_matrix x2 (88 vs 89 routes; `sources/{id}/replace` 422). Not investigated.
Static: ruff check clean on touched files; mypy only the existing ingest.py Windows killpg/SIGKILL errors; web `tsc --noEmit`, eslint (max-warnings 0), prettier clean.
NOT run: Playwright (`widget-polling.spec.ts` written, needs the build + API globalSetup); the polling rules were checked with a node script only. No browser behaviour verified. The independent review agent was not spawned; I reviewed the three risks by reading code and tests (widget -> no preview path; 401/402 `_blocks` before fallback in both complete and stream; polling stop/resume).
Note: the stash round-trip used for the baseline re-run also touched other modified files (widget-styles.ts, loader.js, packages/widget loader) and restored them; verify they are intact.


## UI polish B1: widget panel fix (2026-10-25, branch feat/ui-polish, uncommitted)
Root cause (reproduced in real Chromium, mocks only at /api/public/v1): `packages/widget/src/loader.js` (the source of truth that `sync-loader.mjs` copies over the served file) still had `applyFrameSize()`. The frame's `announceSize` sent `document.documentElement.scrollHeight`, which equals the iframe's own height (`html,body{height:100%}` + `.widget-frame{position:absolute;inset:0}`). New iframe = 150px -> loader clamps to its 200px minimum -> frame reports 200 forever (`chatbot:ready` is never sent, so the 600 default never applies). Result at 1920x1140 and 1280x800: panel 200px, thread 35px, composer clipped when the lead form is open. The served copy `apps/web/public/widget/v1/loader.js` already had the #113 CSS-height fix, so it measured 640px; the owner's ~250px came from an old/cached loader, and the stale source would have re-introduced it on the next sync.
Changes: packages/widget/src/loader.js (CSS-owned height clamp(320px, 100dvh-7rem, 640px) + max-height, mobile variant, `chatbot:size` and applyFrameSize removed/ignored), served copy regenerated with `node packages/widget/scripts/sync-loader.mjs` (cmp identical), apps/web/app/widget/frame/page.tsx (announceSize reports intrinsic content height, floor 600, no longer self-referential), apps/web/lib/widget-styles.ts (thin, token-coloured scrollbar on thread and open lead form), packages/widget/README.md (protocol row), new apps/web/tests/widget-panel.spec.ts.
Commands and outcomes:
- Failing-first: `npx playwright test --config <temp no-globalSetup config> ` on the new spec before the fix against the running Docker stack: source-loader cases failed (panel 200px; 107px thread at 375x667), served cases failed only the thin-scrollbar assertion, identity test failed (served != source).
- After fix, own build: `npm run build` (first run exits 1 with a one-off Next.js security-upgrade notice, retry builds), `npm run start -- --port 3101`, then the same spec: 9 passed (source+served loader x 1920x1140, 1280x800, 375x667, RTL 1280x800; lead form open/closed; thin scrollbar; loader copies identical).
- `npm run typecheck` exit 0; `npm run lint` exit 0; `npm run check:public-asset` -> "check:public-asset OK".
NOT run: widget-layout, widget, widget-streaming, widget-domain, install specs: the suite's globalSetup needs a disposable PostgreSQL (TEST_DATABASE_URL/DATABASE_URL not set here) and port 8000 is held by the dev API; I did not point it at the dev database. The temp Playwright config used for the new spec was deleted.
Screenshots (scratchpad): before = `repro\stale-*-6exch-leadclosed.png` (old frame + stale loader, 200px), after = `shots\after-*.png` (640px). Note `shots\before-*.png` use the NEW frame with the old loader (1034px at 1920x1140): the frame fix also heals cached old loaders.
Noted, not fixed: open lead form is 360px tall inside a 288px (45%) scrolling container; bounded, composer stays visible.

## UI polish B2: foundation, auth screens, link-to-button sweep (2026-10-25, branch feat/ui-polish, uncommitted, stopped at the gate)
Implemented:
- Recharts 3.10.1 pinned exactly in apps/web (`npm install recharts@3.10.1 --save-exact --workspace apps/web`; peer range includes React 19). ADR-022 added to DECISIONS.md (Recharts, Inbox+History module, read-only analytics endpoints, registration stays off). ADR-007/008 untouched.
- Primitives in apps/web/lib/ui.tsx: LinkButton (primary/secondary/ghost/danger/icon, sm/md, icon/iconEnd), StatCard (no trailing colon, delta, spark slot, hint only when given), Meter (role=meter), Switch, ColorField (+ contrastRatio), LimitField (stepper, "Uncapped", meter), SectionNav, StickyActionBar (only when dirty), StatusPill (non-interactive). Icons added: plus, minus, alert, eye, eye-off. Chart colour tokens (--chart-1..6, --chart-seq-1..5, grid/axis; dark and light; categorical contrast 5.1-12.7:1 vs --surface/--bg, computed with a WCAG script; lightest sequential steps are fills that need a border). Chart wrappers come in B4.
- Focus: `:focus:not(:focus-visible)` and `[tabindex="-1"]`/.workspace-content outlines removed; sidebar items ring only on keyboard focus. Skip link kept.
- Link-to-button sweep (app/app/**, app/platform/**, accept-invite, lib/app-header "Account", bot-readiness "Fix", staff-bots, change-requests). accept-invite: Register link removed (ADR-021).
- Landing: Register link, "·" and "Application foundation" removed; welcome + single Sign in button. /register redirects to /login (safe `next` kept). Login: split layout, eye/eye-off password toggle, inline errors, "Signing in..." state, "Contact your administrator" hint.
- e2e helper `registerAdmin` now registers through the API (POST /auth/register + /provisioning/self-service) because /register no longer has a form.
- API: test_default_config_keeps_registration_closed added to apps/api/tests/test_self_service_signup.py (default Settings, no .env, GET /auth/config false, POST /auth/register without invite -> 403 INVITATION_REQUIRED). conftest forces the flag on for the whole suite, so this is the only default-config check.
Verified (observed by me):
- `cd apps/api && TEST_DATABASE_URL=postgresql://test:test@127.0.0.1:55462/b2orch ENVIRONMENT=test PYTHONUTF8=1 ../../.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_self_service_signup.py` -> 6 passed (the agent's own run also 6 passed).
- `npm run typecheck` and `npm run lint` (apps/web): no errors.
- Playwright (dev stack holds :8000, so `E2E_API_PORT=8010 API_PROXY_TARGET=http://127.0.0.1:8010 TEST_DATABASE_URL=postgresql://test:test@127.0.0.1:55462/b2e2e npx playwright test login-register dashboard platform account foundation ui-redesign ui-characterization group-b-client-visibility`): 35 passed, 1 failed. The failure, group-b-client-visibility "staff: navigation, client DOM..." (`rag-tier-control` not visible on bot settings), reproduces on the stashed pre-change tree (`git stash -u`, same command with `-g "staff:"`: failed), so it is pre-existing and not caused by B2. Cause not investigated.
- Each first build in a fresh `npx playwright test` run exits 1 with Next's one-off security-upgrade notice; the retry builds. I did not run `next upgrade`.
NOT run: the rest of the Playwright suite (widget*, knowledge, playground, contacts, inbox, conversations, etc.), so selector impact on those specs from the link sweep is untested. `prettier --check` fails on untouched files too (line endings), so formatting was only checked with `--end-of-line auto`.
Screenshots: after-only (landing, login, login errors, login mobile 375, login light, /app/orgs, tenant overview, bots route; the bots URL redirected to Overview for the client admin used, so the staff Bots table was not captured). No "before" set was captured.
Owner action: confirm your local .env does not set SELF_SERVE_SIGNUP=true (the e2e harness sets it only for its disposable API). Leftover disposable databases on the 55462 server: b2agent_test, b2orch_test, b2e2e_e2e_test.

## UI polish B3 - backend analytics and list data (2026-10-25, branch feat/ui-polish, uncommitted)
Implemented by the orchestrator directly (no subagents: about five small files sharing one test setup). Backend only; no migration, no frontend change.
- BE-1 `GET /api/v1/tenants/{id}/analytics/timeseries` (app/analytics/handoff.py): zero-filled per-UTC-day `{day, conversations, handoffs, resolved}`, website source only, viewer+, window via `_range_window`, 422 over 366 days. Message counts skipped (would need a second query). Route registered in app/core/permissions.py.
- BE-2 `previous` block on `GET .../analytics` (same file, shared `_totals` helper; existing fields unchanged).
- BE-3 near-duplicate grouping for top-questions and unanswered (app/analytics/service.py, `question_key`): grouped in Python over the existing SQL groups (fetch cap 5000 distinct texts), newest original text shown, counts summed, response shape unchanged.
- BE-4 NO CHANGE: `cost_summary` (quotas/rag.py) already returns `unmeasured_events` per row and the web type `RagCost` already has it. The row `cost_usd` is the sum of reported costs only (a row with only unreported events reads "0"), so the fix is frontend: show "cost unreported" using `unmeasured_events` instead of a bare `$0` (rag-operator-panel.tsx already prints the count in prose; B6 F-2).
- BE-5 FINDING (different by design, no code change besides doc/comment): `quota.measured_tokens_this_month` (quotas/service.py usage_snapshot) = tenant-wide, all bots, sum of `provider_usage.total_tokens` on `message` usage events this month: provider-reported chat tokens only, playground included, embeddings excluded, unreported usage counts 0. `monthly_tokens` (quotas/rag.py monthly_usage) = per bot, sum of `accounted_tokens` over `ai_usage` ledger events of EVERY type (generation, rewrite, translation, follow_up, embed_query, embed_ingest) = measured tokens when reported, otherwise the conservative reserved bound (UTF-8 bytes + 128 + max_tokens, times fallback attempts), plus legacy unmetered message tokens. `monthly_embedding_tokens` is the `embedding_tokens` subset (embed_* events), which is therefore ALSO inside `monthly_tokens`. So the owner's 97,647 contains the 45,832 embedding tokens; the remaining 51,815 vs the measured 12,665 is explained by reserved bounds for events whose usage was not reported (and non-chat events), not by a bug. Evidence: test_token_numbers_measure_different_things_by_design (message event 100 tokens + unreported rewrite reserved 900 + embed 400 gives measured 100, monthly_tokens 1400, embedding 400). I did NOT inspect the owner's dev database (not a disposable test DB), so the exact split of 51,815 is inferred from the code, not measured. Recommendation for X-1: label the Overview/Bots number "Chat tokens reported by the provider (all bots)" and the operator numbers "Tokens counted against the AI limit (includes embeddings and reserved estimates)".
- BE-6 inbox list (app/inbox/listing.py): `total`, `bot_id`, `mode`, `status`, `channel`, `last_message`, `unread_count` already existed; added `contact_name` (null if no contact), `created_at`, and `created_from`/`created_to` (inclusive UTC dates, 422 if malformed). Pagination and delete endpoint untouched. Note the docs row said `/inbox/conversations`; the real path is `/inbox` (docs/05 corrected).
- BE-7 quota: additive `at_limit` (used >= limit) next to `warnings` (quotas/service.py); `warnings` unchanged.
- docs/05-API-CONTRACTS.md updated for all of the above.
Commands (cwd apps/api, disposable DB `b3_polish_test` on the 55462 test server, `TEST_DATABASE_URL=postgresql://test:test@127.0.0.1:55462/b3_polish ENVIRONMENT=test PYTHONUTF8=1`, one pytest process):
- `python -m pytest tests/test_ui_polish_b3.py -q -p no:cacheprovider`: 7 passed (timeseries, previous block, question_key, top/unanswered grouping EN+AR, inbox rows/range/pagination, quota at_limit, token definitions). Every new/changed endpoint has a tenant A/B check and a hidden-tenant 404.
- Combined: the same plus tests/test_analytics.py test_followups_analytics.py test_group_0_inbox.py test_inbox_list.py test_conversations.py test_conversations_view.py test_quotas.py test_rag_limits.py test_tenant_route_matrix.py: `85 passed, 2 failed in 440s`. The 2 failures are in test_tenant_route_matrix.py and are PRE-EXISTING: `test_exact_route_contract_and_operator_knowledge` asserts a hard-coded 82 routes (actual 88 on a stashed pre-change tree, 89 now with my one route), and `test_every_openapi_route_role_and_cross_tenant[staff]` gets 422 on POST sources/{id}/replace (multipart body not sent). I did not change them.
- `ruff check` on touched app files: clean except pre-existing E501 at quotas/service.py:206 (and quotas/sentiment.py, db/models, none mine); `ruff format --check` clean for touched files (3 untouched model files would be reformatted, pre-existing).
- `mypy` on touched files: only pre-existing errors in app/knowledge/ingest.py (os.setsid/killpg/SIGKILL on Windows); none in touched files.
NOT run: rag_gate/rag_evaluation/traces suites, full pytest, any frontend or Playwright.

## UI polish B6 - settings, forms, bots, organizations (2026-10-25, branch feat/ui-polish)
Implemented (3 parallel agents, integrated by orchestrator):
- AI costs and limits (lib/rag-operator-panel.tsx, app/rag-operator-panel.css): LimitField groups (Content / Monthly usage / Embedding and OCR) with meters, StickyActionBar only when dirty, "Reset to plan defaults" via ConfirmAction, cost table with unreported-cost semantics ("Not reported" instead of $0).
- Bot settings (settings/page.tsx, readiness card, tone field, theme editor, rag-tier-control, css): SectionNav, sticky Save bar on dirty (inline "Form is up to date" bar when clean so "Save settings" always exists), two-column fields, counters, Switch for handoff, local BrandColourField (shared ColorField would break getByLabel selectors and cannot be cleared), AI tier inside the AI section with inline "AI tier saved." feedback, staff-only Diagnostics `<details>` (closed by default), readiness "n/N ready" with failing first, StatusPill, Fix as LinkButton, model-failure banner.
- Bots list: card grid, compact plan-usage Meters, single "Open" button, "Request a change" button to /app/{tenant}/settings/requests. Organizations: client cards; staff buttons already done in B2.
- Role audit: no server-side gap found for rag/tone/readiness/playground/platform endpoints (report in chat). Low-severity note for owner: GET tenants/{id}/quota (viewer) returns measured_tokens_this_month and placeholder to client roles via direct API call.
- Test fixes: e2e-helpers and 6 specs now open a bot via link "Open {botName}" (table row removed); roles-control uses getByRole("spinbutton") for AI tokens; group-b fixture mock updated to full RagStatus shape (root cause of the B2-era failure "rag-tier-control not visible", by code reading, not confirmed by run). New specs: b6-limits (3 tests), b6-settings (8 tests); extra 403/404 cases in roles-control and group-b-client-visibility.
Verified (observed):
- `npm run typecheck` and `npm run lint` in apps/web: clean (orchestrator run after integration).
- Agent B: b6-settings + c-bot-settings against a throwaway dev server with mocked API: 20/20 passed (reported by subagent, not re-run by me).
NOT run / not verified:
- The combined Playwright run (c-bot-settings group-a-operator group-a-members group-b-client-visibility roles-control install staff-bots platform organizations dashboard ui-redesign ui-characterization b6-limits b6-settings overview knowledge playground) was started twice: the first attempt failed at `next build` with Next's security notice; the retry was stopped by the owner. 0 tests from it executed. b6-limits, the new role/403 cases, the e2e-helpers link change and the other specs are therefore untested at runtime.
- No before/after screenshots at 1280/375 dark/light were captured.
- Next.js build prints a known-vulnerability notice; `next upgrade` was not run (owner decision).
Owner follow-up: the full re-run planned after B4/B5 is the first real check of these changes.

## UI polish B4 - dashboards and charts (2026-10-25, branch feat/ui-polish)
Implemented (orchestrator + 4 subagents with disjoint write scopes; shared files lib/api.ts, lib/charts/types.ts and format.ts written by the orchestrator):
- lib/api.ts: `HandoffAnalyticsPrevious`, `previous` on `HandoffAnalytics`, `ConversationTimeseries(+Day)`, `conversationTimeseries()`, `handoffAnalytics(tenant, from?, to?)`, `TenantQuotaStatus.at_limit`, `InboxConversation.contact_name/created_at`. No new endpoint (all B3).
- lib/charts/** + app/charts.css: TrendChart (Recharts, area/line), DonutChart, BarList, StackedBar, Sparkline, ChartDataTable, shared formatters (percent, duration, relative time, deltas, `hasChartData`). Tokens only, reduced-motion aware, legends/values not colour-only, hidden data table on TrendChart, components return null without data. Decision: DonutChart/BarList/StackedBar have no hidden table because their legend/list is already visible text.
- Tenant Overview: KPI StatCards with deltas, conversations-over-time chart, outcomes donut, recent conversations (contact name + preview + status + relative time, dir=auto), Get-started only while incomplete (staff), Meter-based plan usage with "limit reached" vs "approaching" wording (`at_limit`), staff-only provisional footnote with relabelled token number, staff-only health alert from the existing readiness item `model_reachable`.
- Bot overview: StatCards (rates as %, response in seconds, thumbs tile hidden at 0/0), volume TrendChart (id `volume`), reply-length bars, ranked top questions, unanswered list, leads chart; empty cards hidden. All listed test ids kept.
- Insights: title "Insights", 7/30/90-day selector (from/to), outcomes donut + KPI row with previous-period deltas, channel bars, agent workload bars, sentiment stacked bar, empty cards hidden, RagOperatorPanel left in place.
- Existing specs updated for intended UI changes: overview.spec (label/value text without colon), followups.spec (heading "Insights", KPI text), group-b-client-visibility (plan usage is now role=meter). New spec tests/b4-dashboards.spec.ts (6 mocked tests).
Verified (observed): `npm run typecheck` and `npm run lint` in apps/web: no errors. `E2E_API_PORT=8010 API_PROXY_TARGET=http://127.0.0.1:8010 TEST_DATABASE_URL=postgresql://test:test@127.0.0.1:55462/b4e2e npx playwright test b4-dashboards`: 5 of 6 passed on the last full run I read; the 6th failed because my mock's "empty" case still returned resolved/open counts (test bug), fixed afterwards. The fixed spec was not yet observed passing at commit time.
NOT verified at commit time: the wider run (b4-dashboards overview dashboard group-b-client-visibility ui-redesign ui-characterization followups) had been started but its result was not read; the other specs of the suite were not run. The first build of each Playwright run still exits 1 on Next's one-off security notice; the retry builds; `next upgrade` not run.
NOT done: screenshots (skipped on the owner's instruction), 375px/RTL/light visual checks, keyboard/tooltip behaviour of TrendChart in a browser (Recharts accessibilityLayer inside an aria-hidden wrapper is an axe aria-hidden-focus risk), the dataviz palette validator (token palette from B2 was contrast-checked then).
Known gaps: `Notice` has no warning tone (Overview uses its own alert style); old `.stat-grid`/`.usage-grid`/progress rules in globals.css may now be unused; Insights has no Notice retry.

### B4 follow-up (observed after the commit)
Wider run `npx playwright test b4-dashboards overview dashboard group-b-client-visibility ui-redesign ui-characterization followups` (same env vars as above): 23 passed, 7 failed.
- group-b-client-visibility (4 role variants): failed because Plan usage meters had no visible text label (aria-label only). Fixed in the tenant Overview (visible label per meter); re-run `npx playwright test group-b-client-visibility followups`: all 7 group-b tests pass.
- overview.spec (2 tests) and followups.spec (1 test) fail in their setup, before any B4 page loads: the uploaded source's ingest job stays "pending" (overview) / the jobs poll times out (followups), so the measured-overview and Insights assertions of those specs did NOT run. Not confirmed pre-existing (I did not re-run them on the pre-B4 commit); likely an environment issue with the disposable worker/ingestion. Those three tests are therefore unverified against the new pages.
- b4-dashboards, dashboard, ui-redesign, ui-characterization all passed in that run.
- `npm run typecheck` and `npm run lint`: clean after the fix.

## UI polish B5 - Conversations module, Inbox + History (2026-10-25, branch feat/ui-polish; NOT committed, awaiting owner)
Implemented (orchestrator + 3 subagents, disjoint write scopes; two had to be resumed after a session rate limit):
- Shell: lib/conversations-module.tsx (`<main>`, h1 "Conversations", Tabs Inbox | History, contract comment block) mounted by layout.tsx in inbox/, conversations/ and bots/[botId]/conversations/; app/conversations-module.css. Routes unchanged; /conversations is now a real tenant-wide History list (no redirect).
- Sidebar: one "Conversations" item (href /app/T/inbox), active on /inbox*, /conversations*, /bots/B/conversations*; staff keep "Bots" (not active on conversation routes). Palette gets palette-only "Inbox" and "Conversation history". The per-bot listBots effect in app-header was removed.
- Inbox (Agent A): filter chips with counts (URL params), one search + Status + "More filters" popover (details), initials-avatar rows, list scrolls independently, thread pane with composer at the bottom, placeholder shrunk. Non-obvious: no more listContacts fetch (uses contact_name from B3).
- History (Agent B): lib/conversation-history.tsx (HistoryTable, RowMenu, RetentionPanel); filters q/status/channel/from/to/page, 25 per page, total; delete via row menu `<details>` with ConfirmAction `delete-${id}` always in DOM for admins; retention is a collapsible panel showing the saved value (Tenant.retention_days added to lib/api.ts), same ids and 1-365 validation.
- docs/10 and docs/18 updated minimally. Tests: new tests/b5-conversations.spec.ts (mocked API), existing specs updated for nav/h1/delete/retention.
- Orchestrator fixes found by running: shell lacked a `<main>` landmark (inner mains turned into sections); History toolbar was a column because of the global `form` rule; inbox toolbar card padding removed and search made full-width.
Commands and outcomes (apps/web):
- `npx tsc --noEmit -p .` and `npm run lint`: clean after all edits.
- `E2E_API_PORT=8011 API_PROXY_TARGET=http://127.0.0.1:8011 TEST_DATABASE_URL=postgresql://test:test@127.0.0.1:55462/b5e2e npx playwright test b5-conversations`: 18 of 18 passed (after the two test fixes; an earlier run failed 8 on the missing `<main>`, fixed). The first build of every run fails on Next's security notice, the retry builds.
- Wider run (b5-conversations conversations contacts followups dashboard roles-control group-b-client-visibility ui-characterization ui-redesign group-c-polish): 35 passed, 27 failed. 25 of the 27 are `POST /api/v1/auth/register` timeouts or 500s because the disposable test DB on 55462 is DOWN (Docker daemon not running; only the dev Postgres on 5432 is up and I did not touch it). The other 2 were my test bugs (staff sidebar list, group-c delete label "Delete conversation"), fixed; the b5 one was re-run and passes, the group-c one needs the DB and was NOT re-run.
NOT verified: every real-API spec in the list (conversations, contacts, followups, dashboard, roles-control, group-b-client-visibility, ui-characterization, ui-redesign, group-c-polish) after my changes; they need the test DB. Screenshots skipped on owner instruction (a before/after set was not produced). Last CSS tweaks (History toolbar row, inbox toolbar) were seen only in one screenshot pass and typechecked, not re-inspected.
Known gaps / owner decisions: History tenant-wide has no "Messages" column (listInbox returns no message_count; backend change out of scope, per-bot page still shows it). No bot filter on tenant-wide History (endpoint has no bot_id param). "Back to inbox" link is visible at all widths. Next.js security upgrade notice still open.

## 2026-10-18 — Phase 6 P6-00 preflight

- Worktree: `D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai-phase6`,
  branch `feature/phase-6-channels`. `git merge main` returned `Already up to
  date`; commit `5c4d253` is already an ancestor of the branch. Re-read
  `implementation/PHASE-06/AGENT-PROMPT.md`; P6-05b is present.
- Python import check, from the worktree root:
  `.\.venv\Scripts\python -c "import app; print(app.__file__)"` — passed;
  resolved to `apps/api/app/__init__.py` inside this worktree.
- API baseline command, run separately for each file from `apps/api` using the
  per-process `TEST_DATABASE_URL` targeting disposable database `phase6` on
  `127.0.0.1:55462` (the fixture uses `phase6_test`):
  `..\..\.venv\Scripts\python.exe -m pytest -q <test-file>`.
  Results: `test_conversations.py` 13 passed; `test_conversations_view.py` 5
  passed; `test_inbox_list.py` 5 passed; `test_group_0_inbox.py` 16 passed;
  `test_contacts.py` 1 passed; `test_analytics.py` 6 passed; `test_quotas.py`
  12 passed; `test_tenant_route_matrix.py` 6 passed; `test_platform.py` 9 passed;
  `test_platform_ops.py` 4 passed; `test_create_platform_staff.py` 2 passed;
  `test_widget_public.py` 14 passed; `test_widget_leads.py` 5 passed; and
  `test_widget_appearance.py` 3 passed. Total: 101 passed, 0 failed across 14
  files. Each file emitted one existing Starlette TestClient/httpx deprecation
  warning.
- Parking list — npm audit (5 high findings; package names only):
  `eslint-config-next`, `@next/eslint-plugin-next`, `fast-glob`, `micromatch`,
  `braces`. Do not change dependencies for these findings in Phase 6.

## 2026-10-18 — Phase 6 P6-01 connections, secrets, signing

- Pre-migration test-DB query on `phase6_test`: `conversations.connection_id`
  was `text`; counts were total 0, NULL 0, non-NULL 0. The migration also
  checks for non-NULL rows and stops with an owner-review error before changing
  the type.
- Migration `0017_manyosiris_channels` is hand-written and reversible. The
  migration test inserted website tenant, bot, contact, conversation and
  identity rows, then ran downgrade, upgrade, and upgrade-at-head again:
  downgrade reached `0016_arabic_fts`, restored `connection_id` to text, and
  preserved the website rows; upgrade converted it to UUID, created both
  channel tables, and preserved the rows; the second upgrade completed at
  `0017_manyosiris_channels` with the same website rows intact. Test printed
  all three outcomes and passed.
- Identity uniqueness preserves the old tenant/channel/external-ID rule for
  rows without a connection (including website visitors), and adds uniqueness
  scoped to tenant/connection/external-ID for channel identities. Regression
  coverage verifies two distinct website visitors, rejects reusing one
  website external ID, allows the same channel external ID on two connections,
  and rejects its duplicate on the same connection.
- Added channel connection/event models, composite tenant-scoped foreign keys,
  `external_conversation_id`, `origin`, inbound dedupe and partial unique
  indexes; staff lifecycle endpoints and client-safe health read model; quota
  counting; key validation at production startup; encrypted create/rotation
  secrets with show-once responses and 24-hour previous-secret verification.
  Tests cover audit rows, logs and exports excluding secrets, including after
  rotation. Added all channel routes to the route matrix and the client/staff
  rows to `implementation/ROLE-MATRIX.md`.
- Dependency-only local commit `1aac486` adds `cryptography==50.0.2` to both
  lockfiles and the API project metadata. This is isolated from the P6-01
  implementation commit(s).
- Final baseline rerun used one pytest process per file, each with
  `TEST_DATABASE_URL=postgresql://test:test@127.0.0.1:55462/phase6` and
  `-p no:cacheprovider`. Results: `test_conversations.py` 13 passed;
  `test_conversations_view.py` 5; `test_inbox_list.py` 5;
  `test_group_0_inbox.py` 16; `test_contacts.py` 1; `test_analytics.py` 6;
  `test_quotas.py` 12; `test_tenant_route_matrix.py` 7 (6 prior baseline
  checks plus 1 P6 route classification); `test_platform.py` 9;
  `test_platform_ops.py` 4; `test_create_platform_staff.py` 2;
  `test_widget_public.py` 14; `test_widget_leads.py` 5; and
  `test_widget_appearance.py` 3. The prior 101 baseline tests all passed;
  1 additional route-matrix test passed, for 102 total across these files.
- New/focused checks after the final source changes: `test_channels.py` 7
  passed; `test_channel_migrations.py` 1 passed; `test_startup_guard.py` 8
  passed (including production startup failure without the encryption key).
  `ruff check` passed for all touched Python files; strict mypy with
  `--follow-imports=silent` passed for 12 application source files; and
  `git diff --check` passed. Pytest runs emitted the existing Starlette
  TestClient/httpx deprecation warning.

## 2026-10-18 — Phase 6 P6-01 coverage follow-up

- Coverage map:
  1. Fixed signing vector, tampering, wrong secret and ±300-second boundaries:
     `apps/api/tests/test_channels.py::test_hmac_fixed_vector_and_timestamp_boundaries`.
  2. Old and new signatures accepted during rotation grace; only new accepted
     after expiry: `apps/api/tests/test_channels.py::test_multi_fernet_decrypt_and_previous_secret_grace`.
  3. Staff lifecycle access, client-role 403s, and sanitized client model:
     `test_connection_lifecycle_secrets_audit_export_and_tenant_sanitization`
     plus `test_every_platform_route_denies_each_client_role` in
     `test_tenant_route_matrix.py`.
  4. Cross-tenant channel listing isolation and foreign-tenant 404:
     `test_connection_lifecycle_secrets_audit_export_and_tenant_sanitization`.
  5. Real quota count, limit 429 and revoked connection exclusion:
     `apps/api/tests/test_channels.py::test_channel_connection_quota_counts_non_revoked_rows`.
  6. Show-once and no later secret leakage in responses, logs, audits or exports:
     `apps/api/tests/test_channels.py::test_connection_lifecycle_secrets_audit_export_and_tenant_sanitization`.
  7. Website and per-connection identity uniqueness:
     `apps/api/tests/test_channels.py::test_contact_identity_indexes_preserve_website_and_scope_channels`.
  8. Duplicate inbound visitor message rejection by the partial unique index:
     `apps/api/tests/test_channels.py::test_inbound_channel_message_dedupe_is_unique_per_conversation`.
  9. Private/loopback/local host, non-HTTP scheme, and production HTTPS
     validation: `apps/api/tests/test_channels.py::test_channel_create_rejects_private_hosts_non_http_and_production_http`.
- URL validation rejects non-global IP literals, localhost and local-only DNS
  suffixes, malformed numeric and hexadecimal IP forms, non-HTTP(S) schemes,
  and HTTP in production. It continues to accept public HTTPS Many hosts.
- Follow-up channel test run: 7 passed. The 14 P6-00 baseline files were run
  again individually: the original 101 cases all passed; the route matrix
  added one P6 classification test (7 passed in that file), for 102 total
  across the 14 files. Existing TestClient/httpx deprecation warning only.


## 2026-10-18 — P6-03 outbound delivery and status (verification BLOCKED)

- P6-02 accepted by the owner. Continued on `feature/phase-6-channels` in
  the existing isolated `SAAS-chats-ai-phase6` worktree. Import check:
  `.venv/Scripts/python.exe -c "import app; print(app.__file__)"` resolved
  inside that worktree. Main product files and all 14 website baseline test
  files remain unchanged. No push, merge, deployment, Docker command, real
  Many/Meta request, paid provider call, or credential-file read occurred.
- Implemented transactional `channel_send` outbox jobs for finalized AI,
  handoff/busy/text-only and agent replies. System/internal notes are excluded.
  Split parts preserve their text, get distinct message IDs and ordered jobs;
  one partial unique job index enforces one outbox row per tenant/message.
  Migration `0019_channel_send` registers the job type and the index. Its
  upgrade/downgrade test is collected but has NOT executed against PostgreSQL.
- Jobs re-check and lock the current connection, decrypt/sign with its current
  secret only at send time, and keep successful acknowledgements pending until
  callbacks. DNS resolves once; every answer must be global; the socket target
  is pinned to a validated IP, preserving Host/TLS SNI and certificate checking.
  No environment proxies or redirects; connect/read timeouts 5/15 seconds;
  response cap 64KiB. Six attempts, exponential 18-second base with jitter
  (five waits total roughly nine minutes), honoring numeric/date Retry-After.
  Permanent failures and callbacks stop further sends; exhaustion marks
  many_unreachable and degrades connection health. Exceptions/body text/secrets
  are not logged or stored in job errors. Many must dedupe message_id after an
  ambiguous network acknowledgement/crash; a completed job rerun skips sending.
- Inbox permits channel thread actions with tenant scoping and exposes only
  connection status and per-outbound-message delivery/error codes. Paused or
  revoked agent replies return 409 CONNECTION_PAUSED before storing anything.
  Website agent reply response/storage logic is preserved. Delivery changes
  create durable inbox events; thread polling also refreshes pause/revoke state.
  UI has readable delivery/failure text and disabled composer explanation,
  uses existing layout and dir=auto, and hides delivery state for websites.
- Fake Many uses httpx.MockTransport and actual signature verification, records
  requests, supports success/500/timeout/network/429/permanent responses,
  dedupes logical deliveries, and posts signed status callbacks in-process.
  New integration coverage: 27 collected cases, including secret rotation
  after enqueue, duplicate jobs, tenant isolation, ordering, retry exhaustion,
  callbacks, agent pause and unchanged website replies. These 27 cases remain
  UNVERIFIED because the approved disposable PostgreSQL service is unavailable.
- Existing channel-only tests updated: P6-02 expected no send job; P6-03 now
  expects one. Migration test expects current head 0019. Added type-narrowing
  assertions to that channel event test file for strict mypy. No existing
  website test was edited or relaxed.

Commands and actual outcomes (paths relative to worktree root unless stated):

1. From apps/api, with TEST_DATABASE_URL set per process to the approved
   disposable phase6 base on 127.0.0.1:55462 (fixture targets phase6_test),
   `../../.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider
   tests/test_channel_outbound.py --tb=short`: initially stalled at connection
   setup and was interrupted (exit 1; no test result). Direct psycopg probes
   with connect_timeout=5 and 3 each failed with ConnectionTimeout.
2. Repeated with a process-only connect_timeout=3 URL and
   `../../.venv/Scripts/python.exe -m pytest -q -x -p no:cacheprovider
   tests/<file> --tb=short`, one process per file, in this exact order:
   test_conversations.py, test_conversations_view.py, test_inbox_list.py,
   test_group_0_inbox.py, test_contacts.py, test_analytics.py, test_quotas.py,
   test_tenant_route_matrix.py, test_platform.py, test_platform_ops.py,
   test_create_platform_staff.py, test_widget_public.py, test_widget_leads.py,
   test_widget_appearance.py, test_channels.py, test_channel_migrations.py,
   test_channel_events.py, test_channel_outbound.py,
   test_channel_outbound_unit.py. First 18 files: EACH exit 1, one setup error,
   psycopg.errors.ConnectionTimeout before any test executed (about 3.2–3.4s
   each). Final file: exit 0, 16 passed, one existing Starlette/httpx warning.
   Per-file logs: `.test-storage-p6-03/<file>.log` (ignored). Do not count
   blocked baseline/channel files as passing tests. Owner was asked to start
   the existing saas-test-db service; no authorization to run Docker inferred.
3. `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider
   apps/api/tests/test_channel_outbound_unit.py --tb=short`: final exit 0,
   16 passed, one existing Starlette/httpx deprecation warning. Pure security,
   DNS pinning/rejection, Retry-After, splitting, streaming fake signature,
   response cap and no-redirect tests override only DB cleanup in this unit
   module; they use no database and no network.
4. `.venv/Scripts/python.exe -m pytest --collect-only -q -p no:cacheprovider
   apps/api/tests/test_channel_outbound.py`: exit 0, 27 cases collected.
5. `.venv/Scripts/python.exe -m ruff check --no-cache <all 15 touched Python
   files plus tests/fakes/__init__.py>`: final exit 0, all checks passed.
   `.venv/Scripts/python.exe -m mypy --strict --follow-imports=silent
   --no-incremental <the same 15 Python files>`: final exit 0, no issues in
   15 files. Scope: channels/config.py, outbound.py, inbound.py;
   chat/conversations.py; inbox/router.py, listing.py; jobs/queue.py, runner.py;
   db/models/knowledge.py; alembic/versions/0019_channel_send.py;
   tests/fakes/fake_many.py; tests/test_channel_outbound.py,
   test_channel_outbound_unit.py, test_channel_events.py,
   test_channel_migrations.py. Earlier formatting/type findings were corrected;
   an attempted `--cache-dir NUL` mypy invocation produced an internal error,
   so the passing final run uses --no-incremental with the ordinary cache.
6. From apps/web, `node --test tests/channel-delivery.unit.mjs`: exit 0,
   14 passed. `npm.cmd run lint`: final exit 0. `npm.cmd run typecheck`:
   final exit 0. An initial CommonJS unit harness failed ESLint's require rule;
   replaced it with ESM, then reran all three commands successfully.
7. From apps/web, `npm.cmd exec -- playwright test
   --config=playwright.channel.config.ts --reporter=line`: exit 0, 1 passed
   in 52.9s including production build. Every API route is mocked; no DB or
   worker starts. Verifies four delivery states, window_closed reason,
   paused/revoked composer, website hiding/enabling, Arabic text, RTL and no
   horizontal overflow at 360px. The separate React component unit suite
   includes template_required and recipient_unreachable explanations.
8. `git diff --check`: final exit 0 (Git emits CRLF conversion notices only).

Files changed/added for P6-03:
- apps/api/alembic/versions/0019_channel_send.py
- apps/api/app/channels/config.py
- apps/api/app/channels/outbound.py
- apps/api/app/channels/inbound.py
- apps/api/app/chat/conversations.py
- apps/api/app/db/models/knowledge.py
- apps/api/app/inbox/listing.py
- apps/api/app/inbox/router.py
- apps/api/app/jobs/queue.py
- apps/api/app/jobs/runner.py
- apps/api/tests/fakes/__init__.py
- apps/api/tests/fakes/fake_many.py
- apps/api/tests/test_channel_outbound.py
- apps/api/tests/test_channel_outbound_unit.py
- apps/api/tests/test_channel_events.py
- apps/api/tests/test_channel_migrations.py
- apps/web/lib/channel-delivery.tsx
- apps/web/lib/api.ts
- apps/web/app/app/[tenant]/inbox/[conversation]/page.tsx
- apps/web/playwright.channel.config.ts
- apps/web/tests/channel-delivery.spec.ts
- apps/web/tests/channel-delivery.unit.mjs
- PROGRESS.md

P6-03 is NOT accepted/complete: restore the owner-managed disposable database,
then run all 14 baseline files and all channel files fully (remove -x if desired),
fix any implementation failures, run migration round trips, and repeat relevant
checks after corrections. Stop and ask before editing an existing website test.
No local implementation commit yet while integration verification is blocked.

### P6-03 database readiness follow-up

Owner opened Docker Desktop and requested resumption. Rechecked isolated import
path successfully. PostgreSQL connection with connect_timeout=5 still failed
with psycopg.errors.ConnectionTimeout. Get-NetTCPConnection -LocalPort 55462
returned no listener; a direct Python socket connect_ex to 127.0.0.1:55462
returned 10061 (connection refused). A second PostgreSQL handshake probe with
sslmode=disable also timed out. Requested that the owner start the existing
saas-test-db container and confirm 55462 -> 5432 mapping, consistent with the
Phase 6 prohibition on agent Docker commands. No tests were counted or marked
passing during this readiness follow-up; all previous blocked checks remain.


## P6-03 owner-requested verification audit (2026-10-18)

This section records the resumed verification after the owner started the
approved disposable PostgreSQL database. Final counts follow in the next
verification-results section; earlier timeout results are historical only.

### Scratch-file audit

Ran `git status --short` and the exact requested
`git ls-files | findstr /R "^\.p6_"` in the Phase 6 worktree. Also checked the
main worktree, enumerated root `.p6*` files, and ran
`git log --all --oneline -- '.p6*' ':(glob)**/.p6*'`.
All scratch-path/tracked/history queries returned no matches. Main is clean.
There are no P6-03 commits yet, and no scratch file was ever tracked or committed.
No introducing commit or cleanup commit exists/was needed. All nine scratch
scripts below were temporary authoring helpers created in the main workspace,
used to write authorized files into the separate Phase 6 worktree, and deleted
before the previous report. None remains in either worktree:
- `.p6_edit.py`
- `.p6_tests.py`
- `.p6_fix.py`
- `.p6_review.py`
- `.p6_final_review.py`
- `.p6_types.py`
- `.p6_contract.py`
- `.p6_last.py`
- `.p6_progress.py`

### Existing website test and product-path audit

P6-03 diff against accepted HEAD changes only these existing test files:
`apps/api/tests/test_channel_events.py` and
`apps/api/tests/test_channel_migrations.py` (both channel-only). The former now
expects one outbound job and adds strict type-narrowing assertions; the latter
expects the current Alembic head. No existing website test was changed in P6-03.
New outbound/fake-Many test files remain untracked pending final review.

The requested comparison with main also includes earlier accepted P6-01/P6-02
work; it must not be represented as an empty test diff. Exact command:
`git diff --stat main -- apps/api/tests`:

```text
 apps/api/tests/test_channel_events.py      | 613 +++++++++++++++++++++++++++++
 apps/api/tests/test_channel_migrations.py  | 133 +++++++
 apps/api/tests/test_channels.py            | 468 ++++++++++++++++++++++
 apps/api/tests/test_chat.py                |  16 +
 apps/api/tests/test_handoff.py             |  24 +-
 apps/api/tests/test_startup_guard.py       |  30 +-
 apps/api/tests/test_tenant_route_matrix.py |  35 +-
 7 files changed, 1315 insertions(+), 4 deletions(-)
```

Changed existing files relative to main are `test_chat.py`, `test_handoff.py`,
`test_startup_guard.py`, and `test_tenant_route_matrix.py`. These were already
present in accepted HEAD, and P6-03 does not edit them. Their prior changes are
respectively a new fixed-website-prompt hash test/imports, a new unknown-source
handoff regression/imports, production encryption-key fixture/guard coverage,
and channel route classification/count coverage. `git log main..HEAD --` these
paths identifies `0eb1011` (unknown-source handoff regression) and `d9a25f1`
(P6-01 security/migration coverage). No new website test change is needed.

Exact requested product diff: `git diff --stat main -- apps/api/app/chat
apps/api/app/inbox`:

```text
 apps/api/app/chat/conversations.py | 211 ++++++++++++++++++++++++++++++++++++-
 apps/api/app/chat/prompts.py       |   2 +
 apps/api/app/inbox/handoff.py      |   4 +-
 apps/api/app/inbox/listing.py      |  16 +--
 apps/api/app/inbox/router.py       |  40 ++++++-
 5 files changed, 255 insertions(+), 18 deletions(-)
```

For P6-03 alone (`git diff --stat HEAD -- apps/api/app/chat apps/api/app/inbox`):

```text
 apps/api/app/chat/conversations.py |  9 +++++++--
 apps/api/app/inbox/listing.py      | 16 +++++++--------
 apps/api/app/inbox/router.py       | 40 +++++++++++++++++++++++++++++++++++---
 3 files changed, 52 insertions(+), 13 deletions(-)
```

Python AST comparison against `git show main:<path>` returned:
- `visitor_chat_turn`: exactly identical, with no normalization.
- Website `agent_reply`: identical after excluding the new settings dependency
  and the two `if row.source == "channel"` branches. The whole route is extended,
  not byte-identical; website role/mode/resolved checks, stored reply, commit,
  trimming and response fields remain identical. `_conversation` additionally
  permits channel rows, with the same tenant predicate and website acceptance.

### Requested P6-03 coverage map

Paths below are relative to the repository root. Each row names actual tests,
not a planned claim; pass/fail counts are recorded separately below.

| Requested scenario | Test mapping |
|---|---|
| Success, acknowledgement ID, pending until callback | `apps/api/tests/test_channel_outbound.py::test_success_duplicate_current_secret_rotation_and_no_text_logs` |
| 500 then success, same message_id | `apps/api/tests/test_channel_outbound.py::test_retry_then_success_with_same_id` (500 parameter) |
| Timeout then success | `apps/api/tests/test_channel_outbound.py::test_retry_then_success_with_same_id` (ReadTimeout parameter; ConnectError also covered) |
| 429 Retry-After honored | `apps/api/tests/test_channel_outbound.py::test_retry_then_success_with_same_id` ((429,120) parameter); date-form header in `apps/api/tests/test_channel_outbound_unit.py::test_dns_pin_and_date_retry_after` |
| Permanent 4xx | `apps/api/tests/test_channel_outbound.py::test_permanent_4xx_and_callback_reason_not_retried`; generic 401 in `test_redirect_response_cap_and_invalid_ack` |
| Retry exhaustion to many_unreachable | `apps/api/tests/test_channel_outbound.py::test_retry_exhaustion` |
| Duplicate job run sends once | `apps/api/tests/test_channel_outbound.py::test_success_duplicate_current_secret_rotation_and_no_text_logs`; unique job key in `test_job_unique_key_and_foreign_job_cannot_send` |
| Paused/revoked at job time | `apps/api/tests/test_channel_outbound.py::test_paused_at_job_time` (both parameters) |
| agent_reply 409 and no stored message | `apps/api/tests/test_channel_outbound.py::test_agent_reply_pause_atomic_enqueue_notes_and_tenant_isolation` (paused and revoked, then active enqueue; notes excluded) |
| Website agent_reply unchanged | `apps/api/tests/test_channel_outbound.py::test_website_agent_reply_keeps_response_and_has_no_outbox`; unchanged website baseline files |
| Long reply split into N ordered messages | `apps/api/tests/test_channel_outbound.py::test_long_reply_order_and_enqueue_idempotency`; all three channel constants in `apps/api/tests/test_channel_outbound_unit.py::test_split_sentence_boundaries_and_unbroken_text` |
| window_closed callback, readable reason, no retry | `apps/api/tests/test_channel_outbound.py::test_status_callbacks_and_out_of_order` (window_closed); `test_permanent_4xx_and_callback_reason_not_retried`; `apps/web/tests/channel-delivery.unit.mjs::readable reason for window_closed`; `apps/web/tests/channel-delivery.spec.ts::channel delivery and paused composer fit Arabic RTL at 360px` |
| Out-of-order statuses | `apps/api/tests/test_channel_outbound.py::test_status_callbacks_and_out_of_order`; `apps/api/tests/test_channel_events.py::test_message_status_is_monotonic_and_health_ignores_old_events` |
| Current-secret signature verification | `apps/api/tests/test_channel_outbound.py::test_success_duplicate_current_secret_rotation_and_no_text_logs`; `apps/api/tests/test_channel_outbound_unit.py::test_fake_many_real_streaming_client_and_signature` (FakeMany.handle verifies every received signature) |
| Rotated secret, including job queued before rotation | `apps/api/tests/test_channel_outbound.py::test_job_queued_before_rotation_signs_with_new_secret`; `test_success_duplicate_current_secret_rotation_and_no_text_logs` |
| No message text or secrets in logs | `apps/api/tests/test_channel_outbound.py::test_success_duplicate_current_secret_rotation_and_no_text_logs`; existing `apps/api/tests/test_channel_events.py::test_quota_and_provider_failures_store_handoff_replies_without_logging_text` |
| Target-host rejection at send time | `apps/api/tests/test_channel_outbound.py::test_send_time_target_rejection`; `apps/api/tests/test_channel_outbound_unit.py::test_non_global_dns_answers_are_rejected`, `test_invalid_target_rejected_before_dns`, `test_dns_pin_and_date_retry_after` |
| Frontend delivery states and website hiding | `apps/web/tests/channel-delivery.unit.mjs::channel delivery renders ${status}`, `website and unstated deliveries are hidden`, `${sender} has no delivery state`; Chromium spec above |
| Frontend disabled composer and explanation | `apps/web/tests/channel-delivery.unit.mjs::${status} disables composer and explains why`, `active channel and website composer stay enabled`; Chromium spec above |

Additional coverage: actual streaming response cap/no redirects, typed wire
payload, unsupported/busy/final handoff outbox integration, tenant A/B isolation,
internal-note exclusion, malformed acknowledgements, migration up/down and
partial unique job key. No requested scenario is marked NOT COVERED.

## 2026-10-18 — Unattended Phase 6 run stopped at baseline hard stop

The user-authorized run resumed in `D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai-phase6`, branch `feature/phase-6-channels`. The worktree already contained uncommitted P6-03 product/test changes and progress notes; these were preserved. No new Phase 6 code was added in this resumed run.

Exact checks and outcomes:
- `git status --short --branch`, `git worktree list`: expected feature worktree exists; existing P6-03 changes were already dirty.
- An initial connectivity probe using `postgresql+psycopg://.../phase6` reached PostgreSQL but the named base DB did not exist (the test fixture appends `_test`).
- First API baseline attempt used that SQLAlchemy URL form; it failed at fixture `psycopg.connect()` with `ProgrammingError: missing "="`. This was a command-format failure, not a test result.
- Retried the 14-file baseline one file at a time with `TEST_DATABASE_URL=postgresql://test:test@127.0.0.1:55462/phase6`; the existing `phase6_test` database had 8 users. `test_conversations.py` failed at setup with `EMAIL_TAKEN`, followed by a cleanup deadlock. No manual truncation was performed.
- To avoid destructive cleanup, diagnostic retry used a fresh test base on the same disposable server: `TEST_DATABASE_URL=postgresql://test:test@127.0.0.1:55462/phase6_run_20261018`; the fixture created `phase6_run_20261018_test`. `python -m pytest -q -x -p no:cacheprovider tests/test_conversations.py --tb=short` exited 1: 0 passed, 1 setup error, `KNOWLEDGE_EMPTY` while publishing the retrieval helper corpus.
- Reproduction on clean `main`: from the main worktree, `TEST_DATABASE_URL=postgresql://test:test@127.0.0.1:55462/phase6_mainprobe`; `.venv/Scripts/python.exe -m pytest -q -x -p no:cacheprovider apps/api/tests/test_conversations.py --tb=short` exited 1 with the same `KNOWLEDGE_EMPTY` corpus setup error. This establishes the blocker as pre-existing on main, before the conversation test reaches its assertion.

Decision: apply the pasted run's hard stop because the baseline is below the required 102 passed and the failure is shared website knowledge setup. Do not change an existing website test or website behavior to force it green. Do not manually clear existing test data. The alternate disposable test database is a recorded deviation from the requested base name `phase6`; it was used only for an isolated reproduction.

Verification status: the remaining 13 baseline files were not run; channel suites, full API, frontend checks and Playwright were not run during this resumed attempt. Existing earlier P6-03 coverage mapping and website diff evidence remain above; this run does not claim new pass counts. Scratch-file checks were not repeated, but no scratch files were created by this run. No additional commits were made.

See `implementation/PHASE-06/PHASE-REPORT.md` for the concise owner-facing run summary and parking list.


### Final P6-03 verification results ? 2026-10-18

**Supersedes the earlier database-blocked status. P6-03 implementation and all
requested verification are complete; awaiting owner acceptance. No later ticket,
merge, deployment, push, Docker operation, or paid/real provider call was made.**
No source or test correction was needed during this verification turn.

The approved DB now accepts connections. `.venv/Scripts/python.exe -c
"import app; print(app.__file__)"` again resolved inside the Phase 6 worktree.
All backend runs used TEST_DATABASE_URL set only in the process environment
with base database `phase6` on the approved local endpoint; conftest exclusively
used disposable `phase6_test`. The URL was not saved to a configuration file.
Final serial runs also set `ENVIRONMENT=test`, `CHAT_STUB_MODEL=true`, and
`EMBEDDING_TEST_STUB=true` per process so no real provider is used.

Exact final command from apps/api, one Python process/file at a time:
`../../.venv/Scripts/python.exe -u -m pytest -q -p no:cacheprovider
 tests/<file> --tb=short`. The table is the execution order. Every file exited 0.
Logs: `.test-storage-p6-03/<file>.log` (ignored).

| File | Exact final pytest summary |
|---|---|
| `test_conversations.py` | 13 passed, 1 warning in 140.83s (0:02:20) |
| `test_conversations_view.py` | 5 passed, 1 warning in 55.06s |
| `test_inbox_list.py` | 5 passed, 1 warning in 9.72s |
| `test_group_0_inbox.py` | 16 passed, 1 warning in 14.07s |
| `test_contacts.py` | 1 passed, 1 warning in 10.28s |
| `test_analytics.py` | 6 passed, 1 warning in 90.05s (0:01:30) |
| `test_quotas.py` | 12 passed, 1 warning in 10.88s |
| `test_tenant_route_matrix.py` | 7 passed, 1 warning in 42.52s |
| `test_platform.py` | 9 passed, 1 warning in 90.67s (0:01:30) |
| `test_platform_ops.py` | 4 passed, 1 warning in 2.16s |
| `test_create_platform_staff.py` | 2 passed, 1 warning in 0.51s |
| `test_widget_public.py` | 14 passed, 1 warning in 163.78s (0:02:43) |
| `test_widget_leads.py` | 5 passed, 1 warning in 67.03s (0:01:07) |
| `test_widget_appearance.py` | 3 passed, 1 warning in 34.86s |
| `test_channels.py` | 7 passed, 1 warning in 3.31s |
| `test_channel_migrations.py` | 1 passed, 1 warning in 0.53s |
| `test_channel_events.py` | 12 passed, 1 warning in 7.45s |
| `test_channel_outbound.py` | 27 passed, 1 warning in 15.15s |
| `test_channel_outbound_unit.py` | 16 passed, 1 warning in 0.13s |

Totals: **14-file baseline 102 passed; four database-backed channel suites
47 passed (7 + 1 + 12 + 27); outbound pure unit suite 16 passed; 165 backend
tests passed overall, 0 failed, 0 skipped.** The only warning in each file is
the existing Starlette TestClient/httpx deprecation. Both the general channel
migration round trip and the dedicated 0019 send-job/index round trip passed.

Diagnostic history (excluded from final totals): an initial serial attempt was
interrupted while output was redirected and had no completed file summary.
A second first-file attempt with `-o faulthandler_timeout=60` was also
interrupted without a final result. The diagnostic command
`../../.venv/Scripts/python.exe -u -c "import faulthandler,pytest;
faulthandler.dump_traceback_later(25,repeat=True);
raise SystemExit(pytest.main(['-vv','-s','-p','no:cacheprovider',
 'tests/test_conversations.py','--tb=short']))"` completed with **12 passed,
1 setup error**: EMAIL_TAKEN for a fixture user left by an interrupted run.
Normal fixture teardown cleaned the disposable tables. The subsequent full,
clean serial run above passed all 13 conversation cases and all other files.
No test was modified, weakened, or skipped to obtain the final results.

Final Python static checks:
- `.venv/Scripts/python.exe -m ruff check --no-cache` with all touched Python
  paths listed in the earlier scope, including the entire `apps/api/tests/fakes`
  directory: exit 0, **All checks passed**.
- `.venv/Scripts/python.exe -m mypy --strict --follow-imports=silent
  --no-incremental` with the same application/migration/test paths and both
  `tests/fakes/__init__.py` and `tests/fakes/fake_many.py`: exit 0,
  **no issues in 16 source files**. The initializer was explicitly added to
  the prior 15-file scope; no imported-module findings were suppressed beyond
  the requested --follow-imports=silent.

Final frontend commands from apps/web:
- `npm.cmd run lint`: exit 0, no errors/warnings.
- `npm.cmd run typecheck`: exit 0, Next route types generated and tsc passed.
- `node --test tests/channel-delivery.unit.mjs`: exit 0, **14 passed, 0 failed**.
- `npm.cmd exec -- playwright test --config=playwright.channel.config.ts
  --reporter=line`: exit 0, **1 passed in 38.2s**, including production build;
  verifies actual rendered Arabic/RTL/360px channel delivery and disabled
  composer UI with fully mocked API requests (no separate DB/worker/server
  network dependency). Harmless Node NO_COLOR/FORCE_COLOR notices only.

The preceding coverage map is now backed by passing runs for every listed
scenario, with no NOT COVERED item. The requested main-vs-branch and
HEAD-vs-P6-03 diff statistics above remain unchanged. No P6-03 website test
edit; visitor_chat_turn remains identical; website agent_reply behavior and
response remain identical outside the new channel-only branches. The 14-file
website baseline passed unchanged. Main-vs-branch differences in four existing
shared test files predate P6-03 and are disclosed in the audit above.

All nine scratch authoring scripts remain deleted, untracked and absent from
all commit history; no P6-03 commit or scratch cleanup commit exists. Main
worktree remains clean. Final git diff --check passes (CRLF notices only).
Awaiting owner review/acceptance; do not start the next ticket automatically.


Final concurrent-file note: the closing git status additionally showed a new,
untracked `implementation/PHASE-06/PHASE-REPORT.md` that this verification run
did not create. It describes a separate stopped attempt on a differently named
disposable database and says baseline/channel/frontend checks are incomplete.
That report is stale relative to the completed 165-test backend run and passing
frontend/static checks documented immediately above. It was read to identify
the discrepancy and left untouched (no overwrite, deletion or commit). The
successful results above come from actual commands/logs using phase6_test,
not from that report. No later Phase 6 ticket was started by this run.

## 2026-10-19 — P6-03 resume: environment probe and Step 2 review (new agent session)

Environment probe (new session):
- Worktree/branch re-verified. The worktree `.git` pointer file contained a
  Windows-style gitdir path that WSL git could not resolve; it was rewritten to
  the equivalent `/mnt/d/...` path (metadata only; no repo content touched).
  Working tree clean; P6-03 exists solely as WIP commit `cd47060`
  "wip: P6-03 (unverified)"; no uncommitted edits, no untracked files,
  no `.p6_*` scratch files on disk and none tracked (`git ls-files | grep p6_` = 0).
- Tests run through the worktree's Windows venv (`.venv/Scripts/python.exe`)
  via WSL interop; `import app` resolves inside this worktree. Env vars pass
  into the Windows process only with `WSLENV=TEST_DATABASE_URL/w:ENVIRONMENT/w:CHAT_STUB_MODEL/w:EMBEDDING_TEST_STUB/w`.
- DB-backed capability probe: from `apps/api`,
  `TEST_DATABASE_URL=postgresql://test:test@127.0.0.1:55462/phase6_r2` (fixture
  created `phase6_r2_test`), `ENVIRONMENT=test CHAT_STUB_MODEL=true
  EMBEDDING_TEST_STUB=true`, `python.exe -m pytest -q -p no:cacheprovider
  tests/test_conversations.py --tb=short` — exit 0, **13 passed, 1 warning in
  252.27s**. The prior sessions' blockers (WinError 5 named-pipe denial,
  psycopg ConnectionTimeout, KNOWLEDGE_EMPTY corpus setup failure) did NOT
  reproduce in this session. DB-backed verification can proceed here.

Step 2 review of P6-03 (`cd47060`) against PLAN D8/D9 and docs/17 §5.1, §6:

| Item | Status |
|---|---|
| Enqueue points: AI reply, handoff/busy reply, text-only notice, agent reply | implemented + covered by `test_channel_outbound.py` |
| agent_reply 409 CONNECTION_PAUSED (paused or revoked, locked row check) | implemented + covered |
| Send-time host validation (`_validate_base_url` + global-IP pin), no redirects, trust_env off, connect 5 s / read 15 s, 64 KB response cap | implemented + covered (fake asserts SNI/host/timeouts) |
| Retry 5xx/timeout/network/429 with exponential backoff + jitter, Retry-After honored (job `retry_after_seconds`), max 6 attempts, then `many_unreachable` + degraded health | implemented + covered |
| Idempotency: same `message_id` (our message UUID) every attempt, existing-job guard, `channel_message_id` guard, `previous_message_id` ordering (waits consume no retry budget) | implemented + covered |
| Long-reply split at sentence boundaries, per-channel constants (`REPLY_CHAR_LIMITS`, 1000) | implemented + covered (`test_channel_outbound_unit.py`) |
| Delivery status monotonic pending<sent<delivered<read; failed only below delivered; out-of-order/duplicate harmless | implemented (`inbound._message_status`) + covered |
| Inbox delivery-state UI + Arabic error text (window_closed, template_required, recipient_unreachable, many_unreachable, etc.), disabled composer when paused | implemented (`channel-delivery.tsx`, inbox page) + Playwright spec and unit tests exist (earlier run recorded in PROGRESS above) |
| No message text in logs: SendRetry carries a static message; httpx/OSError strings swallowed; final errors are static strings | implemented; verified by reading `outbound.py` |
| Secret decrypted only inside the send job | implemented (`run_channel_send`) |
| Website isolation: `visitor_chat_turn` untouched (all channel work is the new `channel_chat_turn`); `agent_reply` website path unchanged (channel-only branches); append_message inbox events extended to `source in {website, channel}`; `decide_handoff` generalized to `{website, channel}` (unknown sources keep prior disabled behavior) | verified via `git diff main..HEAD` |
| No existing website test edited | verified: diff vs main touches only `test_chat.py`/`test_handoff.py` (new tests appended) and `test_startup_guard.py`/`test_tenant_route_matrix.py` (additions required by P6-01 scope: env guard + route classification) |

Known inconsistency (to fix in P6-06): committed `PHASE-REPORT.md` still
describes the earlier STOPPED attempt and contradicts the completed 165-test
run recorded in PROGRESS.md above; it must be rewritten when the phase report
is finalized.

### 2026-10-19 (cont.) — P6-03 DB-backed verification completed in this session

All commands from `apps/api` with `ENVIRONMENT=test`,
`TEST_DATABASE_URL=postgresql://test:test@127.0.0.1:55462/<fresh>` per process
(fixture appends `_test`; each base name used once), via
`.venv/Scripts/python.exe` with the `WSLENV=/w` passthrough described above.

| Files | Command | Result |
|---|---|---|
| `tests/test_channels.py tests/test_channel_migrations.py tests/test_channel_events.py tests/test_channel_outbound.py tests/test_channel_outbound_unit.py` | `python.exe -m pytest -q -p no:cacheprovider <files> --tb=short` (phase6_r3) | exit 0; **63 passed, 1 warning in 25.29s** |
| `tests/test_chat.py tests/test_handoff.py tests/test_tenant_route_matrix.py` | same one-process form (phase6_r4) | exit 0 for these three files; **30 passed** (see next row for the fourth file in that process) |
| `tests/test_startup_guard.py` (phase6_r4 run) | run WITH `CHAT_STUB_MODEL=true EMBEDDING_TEST_STUB=true` in the process env | 1 failed (`test_real_settings_object_tracks_explicit_provider`), 7 passed |
| `tests/test_startup_guard.py` | re-ran WITHOUT `CHAT_STUB_MODEL`/`EMBEDDING_TEST_STUB` in the process env (phase6_r8; still `ENVIRONMENT=test` + `TEST_DATABASE_URL`) | exit 0; **8 passed, 1 warning in 1.03s** |

Diagnosis of the startup_guard failure (no code or test changed): the test
builds a real `Settings(_env_file=None, environment="production")` and only
deletes `EMBEDDING_PROVIDER` from the process env, so session-level
`EMBEDDING_TEST_STUB=true` / `CHAT_STUB_MODEL=true` leaked in and made a
different guard fire first ("Embedding test vectors are allowed only in the
test environment." and then "CHAT_STUB_MODEL cannot be enabled with
environment=production..."). The file is self-contained and needs neither stub
flag; with the standard env it passes 8/8. The three channel-invasive env
vars remain required for every other suite; only `test_startup_guard.py`
must be run without `CHAT_STUB_MODEL`/`EMBEDDING_TEST_STUB`. This caveat is
noted for the P6-06 full-suite run.

Static checks (this session):
- `python.exe -m ruff check --no-cache` on the 12 P6-03-touched app/test/fake
  files: exit 0, **All checks passed**.
- `python.exe -m mypy --strict --follow-imports=silent --no-incremental` on 10
  of them: exit 0, **no issues found in 10 source files**.

Cumulative session totals (all freshly executed in this session, no result
carried over from any prior claim): 13 (conversations) + 63 (channel suites)
+ 30 (chat/handoff/route_matrix) + 8 (startup_guard) = **114 passed, 0 failed**.
The remaining 10 baseline files of the 14-file website set are re-verified in
the P6-06 full-suite run, not claimed here.

## 2026-10-19 — New session: Phase 6 Step 1 gate PASSED (fresh full numbers)

Read in order: AGENTS.md, implementation/PHASE-06/PLAN.md, PROGRESS.md (P6
entries), docs/17, `git log --oneline main..HEAD` (16 commits, HEAD `7ac8353`).
Worktree `SAAS-chats-ai-phase6`, branch `feature/phase-6-channels`; tests via
`.venv/Scripts/python.exe` (WSL interop, WSLENV passthrough); `import app`
resolves inside this worktree. No Docker, push, merge, or credential read.

Baseline command (one pytest process per file, from apps/api):
`TEST_DATABASE_URL=postgresql://test:test@127.0.0.1:55462/phase6` (fixture uses
`phase6_test`; verified 0 users before the run) plus `ENVIRONMENT=test
CHAT_STUB_MODEL=true EMBEDDING_TEST_STUB=true`:
`python.exe -m pytest -q -p no:cacheprovider tests/<file> --tb=short`.

1. 14-file baseline (all exit 0): test_conversations.py 13; test_conversations_view.py 5;
   test_inbox_list.py 5; test_group_0_inbox.py 16; test_contacts.py 1; test_analytics.py 6;
   test_quotas.py 12; test_tenant_route_matrix.py 7; test_platform.py 9; test_platform_ops.py 4;
   test_create_platform_staff.py 2; test_widget_public.py 14; test_widget_leads.py 5;
   test_widget_appearance.py 3. **Total 102 passed, 0 failed, 0 skipped** (existing
   Starlette/httpx deprecation warning only). Website tests unchanged.

2. Five channel suites vs counts accepted at P6-01/P6-02/P6-03:
   test_channels.py 7 (=accepted 7); test_channel_migrations.py 1 (=1);
   test_channel_events.py 12 (=12); test_channel_outbound.py 27 (=27);
   test_channel_outbound_unit.py 16 (=16). Total 63 (=accepted 63). No drift.

3. Website prompt digest test:
   `apps/api/tests/test_chat.py::test_system_prompt_matches_main_bytes_for_fixed_website_input`
   (fixed SHA-256 of the website `system_prompt`). PASSED this session both
   standalone (1 passed in 0.52s) and inside the full `test_chat.py` file run
   (17 passed in 188.03s).

4. Requested git output (from the worktree):
   - `git status --short` — (empty; clean)
   - `git status --ignored --short | grep p6_` — (no matches)
   - `git ls-files | grep p6_` — (no matches)
   - `git show --stat 7ac8353` — `PROGRESS.md | 81 ++++++ 1 file changed, 81 insertions(+)`
     ("test: verify P6-03 against the disposable database in-session")
   - `git worktree list` — main worktree `SAAS-chats-ai` on `main` @5c4d253;
     worktree entry `.../SAAS-chats-ai-phase6` @7ac8353 [feature/phase-6-channels]
     (listed "prunable" only because the stored gitdir is the Windows-style path;
     the worktree is intact and in use — pointer not touched per owner rule).

5. P6-03 decision-to-test map (D8/D9 + no-AI-fallback), file::test per behavior
   (paths from repo root; all passed this session):

   D8 — outbound `channel_send`:
   | Behavior | Test |
   |---|---|
   | Enqueue on AI reply / handoff/busy/text-only reply | `tests/test_channel_outbound.py::test_channel_pipeline_enqueues_final_replies` |
   | Enqueue on agent reply; internal notes never sent | `tests/test_channel_outbound.py::test_agent_reply_pause_atomic_enqueue_notes_and_tenant_isolation` |
   | 409 CONNECTION_PAUSED on paused OR revoked agent reply (nothing stored) | `tests/test_channel_outbound.py::test_agent_reply_pause_atomic_enqueue_notes_and_tenant_isolation` (asserts code) |
   | Paused/revoked at job time (send refused) | `tests/test_channel_outbound.py::test_paused_at_job_time` |
   | Signed POST per docs/17 §5.1 to stored `many_base_url` only | `tests/test_channel_outbound.py::test_success_duplicate_current_secret_rotation_and_no_text_logs`; `tests/test_channel_outbound_unit.py::test_fake_many_real_streaming_client_and_signature` (FakeMany verifies signatures) |
   | No redirects; 5 s connect / 15 s read; 64 KB response cap | `tests/test_channel_outbound_unit.py::test_transport_cap_and_no_redirects`; `tests/test_channel_outbound.py::test_redirect_response_cap_and_invalid_ack` |
   | Send-time host validation / DNS pin to global IP | `tests/test_channel_outbound.py::test_send_time_target_rejection`; `tests/test_channel_outbound_unit.py::test_non_global_dns_answers_are_rejected`, `::test_invalid_target_rejected_before_dns`, `::test_dns_pin_and_date_retry_after` |
   | Retry 5xx/timeout/network/429, exponential backoff, same `message_id`, Retry-After honored | `tests/test_channel_outbound.py::test_retry_then_success_with_same_id` (500/ReadTimeout/ConnectError/(429,120) params); date-form Retry-After in `::test_dns_pin_and_date_retry_after` |
   | Permanent 4xx → failed with readable code, not retried | `tests/test_channel_outbound.py::test_permanent_4xx_and_callback_reason_not_retried`; generic 401 in `::test_redirect_response_cap_and_invalid_ack` |
   | Retry exhaustion → `many_unreachable` + degraded health | `tests/test_channel_outbound.py::test_retry_exhaustion` |
   | Duplicate send idempotency (unique job key; rerun skips) | `tests/test_channel_outbound.py::test_success_duplicate_current_secret_rotation_and_no_text_logs`; `::test_job_unique_key_and_foreign_job_cannot_send` |
   | Ack id stored as `channel_message_id`; `pending` until `message.status` | `tests/test_channel_outbound.py::test_success_duplicate_current_secret_rotation_and_no_text_logs` |
   | Long reply split at sentence boundaries, ordered parts | `tests/test_channel_outbound.py::test_long_reply_order_and_enqueue_idempotency`; `tests/test_channel_outbound_unit.py::test_split_sentence_boundaries_and_unbroken_text` |
   | Signs with CURRENT secret at send time (incl. job queued before rotation) | `tests/test_channel_outbound.py::test_job_queued_before_rotation_signs_with_new_secret`; `::test_success_duplicate_current_secret_rotation_and_no_text_logs` |
   | 0019 migration round trip + one outbox job per tenant/message | `tests/test_channel_outbound.py::test_send_migration_round_trip_and_unique_message_key` |
   | No message text/secrets in logs or job errors | `tests/test_channel_outbound.py::test_success_duplicate_current_secret_rotation_and_no_text_logs` |

   D9 — delivery status:
   | Behavior | Test |
   |---|---|
   | Monotonic rank pending<sent<delivered<read; failed only below delivered | `tests/test_channel_events.py::test_message_status_is_monotonic_and_health_ignores_old_events` |
   | Out-of-order / duplicate status callbacks harmless | `tests/test_channel_outbound.py::test_status_callbacks_and_out_of_order`; `tests/test_channel_events.py::test_message_status_is_monotonic_and_health_ignores_old_events` |
   | `window_closed`/`template_required`/`recipient_unreachable` not retried, readable reason | `tests/test_channel_outbound.py::test_permanent_4xx_and_callback_reason_not_retried` (parametrized 3 codes); `::test_status_callbacks_and_out_of_order` (window_closed); `apps/web/tests/channel-delivery.unit.mjs` (readable reasons) |
   | Delivery state surfaced per message in inbox; hidden for website; paused composer disabled | `apps/web/tests/channel-delivery.spec.ts`; `apps/web/tests/channel-delivery.unit.mjs` |
   | Website agent-reply response/storage unchanged, no outbox | `tests/test_channel_outbound.py::test_website_agent_reply_keeps_response_and_has_no_outbox` |

   No AI fallback:
   | Behavior | Test |
   |---|---|
   | Human mode: inbound stored, no AI reply (silent) | `tests/test_channel_events.py::test_human_mode_is_silent_and_resolved_conversation_reopens_in_ai_mode` |
   | `ai_enabled=false`: stored, `waiting_human`, agents can still reply | `tests/test_channel_events.py::test_ai_disabled_and_unsupported_hourly_reply_rules` |
   | Paused: inbound accepted+stored, no AI, no outbound | `tests/test_channel_events.py::test_event_duplicate_replay_paused_acceptance_and_atomic_enqueue`; `tests/test_channel_outbound.py::test_paused_at_job_time` |
   | Quota/provider failure → stored handoff/busy reply (never a fake success) | `tests/test_channel_events.py::test_quota_and_provider_failures_store_handoff_replies_without_logging_text` |
   | Many-side "no AI fallback when SaaS unreachable" is a Many requirement (docs/17 §1.4/§6): NOT testable in this repo; contract requirement carried to P6-06 handover/MANY-AGENT-PROMPT check |

   Gate verdict: GO — baseline 102/102, channel suites match accepted counts,
   digest green. Proceeding to P6-05.

## Phase 6 close-out, R-00 preflight (cloud session, 2026-10-26)
- Branch: session branch `claude/saas-rebuild-r00-jrd3an`, identical to `origin/feature/phase-6-channels` (f9def26); `git status` clean (the two uncommitted test-file edits are not in this clone, per CLOUD-ADDENDUM item 6). `origin/main` = 2b9e015, 181 commits ahead of merge-base 5c4d253.
- `git merge --no-commit --no-ff origin/main` dry run, aborted: 20 content conflicts. .env.example, DECISIONS.md, PROGRESS.md, api/app/{analytics/handoff,chat/conversations,chat/prompts,core/config,db/models/chat,inbox/listing,main}.py, api/tests/test_chat.py, web {analytics,contacts,inbox/[conversation],tenant page}.tsx, globals.css, lib/{api.ts,app-header.tsx,inbox-list.tsx}, tests/e2e-api-setup.ts.
- Alembic: branch single head `0020_channel_health_poll` (0017..0020 channel chain on 0016). main head `0022_knowledge_hygiene`, so channel migrations renumber to 0023..0026 in R-01.
- Environment: Python 3.12.3 venv from requirements-dev.lock; PostgreSQL 16 started; `apt-get update` was needed before `apt-get install postgresql-16-pgvector postgresql-contrib` succeeded; role `test` created (SUPERUSER + CREATEDB, so CREATE EXTENSION works). TEST_DATABASE_URL must be `postgresql://test:test@127.0.0.1:5432/phase6` (no `+psycopg`): tests/conftest.py passes it to raw psycopg.connect; conftest derives `phase6_test`. Set per process, not in a file. Playwright not attempted yet.
- Baseline on the unmerged branch (cwd apps/api, `python -m pytest tests/<file> -q`): test_channel_contract 17, test_channel_events 12, test_channel_health 9, test_channel_inbox_insights 9, test_channel_migrations 1, test_channel_outbound 28, test_channel_outbound_unit 16, test_channels 7, test_chat 17, test_inbox_list 5. All passed (121 total, 0 failed). Not run: the rest of the API suite, web lint/typecheck, Playwright (R-07).
- Docs only: ADR-023 added to DECISIONS.md, v1.1 delta A1-A13 merged into docs/17 as section 11. ADR-020 still awaiting owner sign-off.

## Phase 6 close-out, R-01 update the branch (cloud session, 2026-10-26)
- `git merge --no-ff origin/main` (main 2b9e015) into the session branch. 20 conflicts resolved: docs/config taken from both sides; `analytics/handoff.py` rebuilt on main's `_totals`/timeseries with the channel filter, `channel_breakdown` and `conversations_by_campaign` re-applied; `prompts.py` union (`unsupported` + `cannot_confirm_topics`); `conversations.py` imports union and `channel_chat_turn` adapted to main's `history_for_turn` result (`.messages`, `.skipped`); `inbox/listing.py` row tuple is now 4 wide. Web: main's redesigned pages/`inbox-list.tsx`/`app-header.tsx` kept, so the staff Channels nav link, channel inbox/insights/contacts/overview UI and the Playwright channel specs' targets are gone until R-06; `lib/api.ts` keeps main's range API plus an optional `channel` argument; `globals.css` and `e2e-api-setup.ts` hold both sides.
- ADR number clash: main already used ADR-021 (staff accounts), so contract v1.1 is ADR-023 (DECISIONS.md, docs/17 section 11). ADR-020 still awaiting sign-off.
- Migrations renumbered 0017..0020 -> 0023..0026 (chain on `0022_knowledge_hygiene`); `alembic heads` = `0026_channel_health_poll` (single head). Forced decision: main stores playground thread keys (`playground:<user_id>`) in the old text `conversations.connection_id`; 0023 now moves them to `external_conversation_id` (and back on downgrade) before the column becomes a UUID FK, and the non-NULL guard ignores `source='playground'`. `chat/conversations.py` playground lookups use `external_conversation_id`. `test_channel_migrations.py` now covers a non-empty table incl. a playground row (up/down/up).
- `tests/test_chat.py::test_system_prompt_matches_main_bytes...` repinned to main's current prompt hash (system_prompt is byte-identical to origin/main; verified by hashing origin/main source).
- Commands (cwd apps/api, venv 3.12, `TEST_DATABASE_URL=postgresql://test:test@127.0.0.1:5432/phase6`, `phase6_test` dropped before runs): `python -m pytest tests/<file>.py -q` for each of the 88 test files: 971 passed, 1 failed. The failure, `test_bot_names_migration.py::test_bot_name_backfill_keeps_existing_values` (inserts `tenants.updated_at`, a column that does not exist), also fails on a clean `origin/main` worktree, so it is pre-existing and not caused by this merge. Web (apps/web): `npm ci`, `npm run typecheck` and `npm run lint` pass. `ruff check app` passes except pre-existing E501 in tests; `mypy` reports 16 errors, 11 in files this branch did not touch plus 5 in the branch's `tests/test_channels.py` (SimpleNamespace args); left for R-07.
- NOT RUN: Playwright (R-06/R-07), no behaviour change beyond the forced merge fixes above.

## Phase 6 close-out, R-02 shared turn core + channel turn (cloud session, 2026-10-26)
- `chat/conversations.py`: new `run_ai_turn` (history, quota reserve, metered `chat_answer`, AI message, handoff decision, usage event, settle, handoff effects) used by BOTH `visitor_chat_turn` (behaviour unchanged, no `degrade`) and `channel_chat_turn` (passes `degrade` for missing model / quota / provider failure, `shape_answer` plain-text sanitizer, `channel_style`). Returns `AiTurn` (dataclass with `extras`) so tool calls can be added later. `chat_answer`/`system_prompt` gained an optional `channel_style` (empty for the website, so its prompt bytes are unchanged; placed before the evidence marker).
- Channel-only parts: gating (human mode now beats AI-off/paused/flood flags; D6), flood throttle (`INBOUND_PER_MINUTE=15`, store + `waiting_human`, no AI; A8), busy/quota reply at most once per conversation per 10 min (A8), plain-text output (`channels/sanitize.py`: markdown, citation markers, source links; `bot.config.channel_allow_source_links` keeps links), per-bot `channel_style_hint` with a default short-DM hint, channel turn deadline 120 s, outbound enqueue.
- `channels/inbound.py`: whole `message.received` handling runs under `conversation_turn_lock` (PostgreSQL session advisory lock on a dedicated connection keyed by connection + external conversation; a row lock cannot span `reserve()`, which commits), then commits before releasing; conversation creation race falls back to the winner; unsupported placeholder is localized by bot language (D4) and no longer pre-sets `waiting_human`, so the turn's `start_handoff` fires (D5). Note: the lock assumes the handler holds no open write transaction before it (true for `claim_job`, which commits).
- Not yet done by design (later tickets): event ordering by receipt (A7), `received_at` clamp (D7), 422 on channel mismatch (D1), bytes-safe signature compare (D3) = R-03; byte-aware splitting, `unconfirmed` sweep, resend = R-04.
- Tests (cwd apps/api, `TEST_DATABASE_URL=postgresql://test:test@127.0.0.1:5432/phase6`, file by file, targeted only per owner instruction): new `tests/test_channel_turn.py` 11 passed (sanitizer, shared core + style hint, human mode wins, unsupported handoff + Arabic placeholder, flood throttle, busy cap, no model, rerun idempotency, lock blocks second worker, two concurrent messages never overlap, provider failure). Regression after the refactor: test_channel_events 12 + test_widget_public 14 (29 together), test_channel_contract 17, test_conversations 13, test_handoff 6, test_playground_parity + test_turn_deadline 18, test_chat `-k system_prompt` 1: all passed. `mypy app` clean; `ruff check` clean except pre-existing E501. NOT re-run: the rest of the API suite and all web/Playwright.

## Phase 6 close-out, R-03 inbound events (cloud session, 2026-10-26)
- D1/A1: `message.received.channel` must equal the connection's channel, else signed 422 and nothing stored (`events.py`). D3: `signing.verify` compares bytes, so a non-ASCII `X-Osiris-Signature` is the generic 401, never a 500. D7/A10: `received_at` clamped to [now-24h, now+5min] (`inbound.clamp_received_at`), else our receipt time. A7: under the conversation turn lock, earlier unprocessed `message.received` events of the same conversation (by `channel_events.received_at`, then id) are processed first; their own jobs later find them processed. Contact name/phone/handle refresh on later events but staff edits are kept (last channel-provided values stored in `custom_fields.channel_*`). Origin stays first-wins (A11, existing test). D11: migration `0027_channel_ref_unique` = partial unique index on (channel, many_channel_ref) for non-revoked connections; create/patch return 409 `CHANNEL_REF_IN_USE`; revoking frees the reference; the migration refuses to run if live duplicates exist.
- Existing test changed on purpose: `test_channel_events.py::test_inbound_dedupe_sanitization_and_origin_is_written_once` now repeats the same contact on later events, because contact details now refresh (the old test pinned "set only at creation"). Head assertions in test_channel_health/outbound/migrations moved to `0027_channel_ref_unique`.
- Tests (cwd apps/api, targeted per owner instruction): new `tests/test_channel_ingest_hardening.py` 6 passed (channel mismatch 422, non-ASCII signature 401, clamp, receipt ordering, contact refresh, unique channel ref + revoke frees it). Also passed: test_channel_events 12, test_channel_contract 17, test_channels 7, test_channel_migrations 1, test_channel_turn 11, plus the migration/head tests in test_channel_health and test_channel_outbound (2). `alembic heads` = 0027 only; `mypy app` clean. NOT re-run: the rest of the API suite, web, Playwright. Not covered here: full replay/auth-matrix is the existing test_channel_events matrix (unchanged, passing).

## CORRECTION to the R-01 record above (found during R-04)
The R-01 line "971 passed, 1 failed" was wrong: my summary filter dropped every file whose result line contained both "failed" and "passed". The R-01 file-by-file run actually had 22 failures in 11 files: test_bot_names_migration 1, test_chat_streaming 1, test_embedding_readiness 3, test_hybrid_retrieval 3, test_knowledge_hygiene 2, test_rag_evaluation 2, test_rag_gate 1, test_rag_stage0_baseline 1, test_staff_members 6, test_tenant_route_matrix 2 (and test_chat after repin passed). Triage during R-04: the same files were run on a clean `origin/main` worktree (database `mainchk`) and fail with the same counts and test names, so none is caused by this branch's merge. They are pre-existing on `main` (causes not investigated: stale route-count assertion `82`, a `tenants.updated_at` column in a migration test, RAG/embedding tests that may need provider or pgvector settings). Open question for the owner: fix them on `main`, or accept as known baseline.

## Phase 6 close-out, R-04 outbound + delivery (cloud session, 2026-10-26)
- A4 byte-aware splitting: `split_reply` keeps WhatsApp/Messenger at 1000 characters and splits Instagram by 900 UTF-8 bytes AND 1000 characters (Arabic = 450 chars/part). A3 closed error enum (`CHANNEL_ERROR_CODES`): callback `error_code` outside the set is stored as `unknown`; `message_too_long` and `channel_disconnected` are permanent 4xx outcomes. Fake Many gained `limit_chars`/`limit_bytes` and answers 400 `message_too_long` (never truncates).
- A2/D8 `unconfirmed`: migration `0028_channel_unconfirmed` adds `messages.accepted_at` (set when Many answers 202) and the `unconfirmed` delivery state; `sweep_unconfirmed` (run from the worker's maintenance cycle next to the health-poll scheduler) marks accepted-but-unreported messages after 15 min; a later `sent/delivered/read/failed` callback overrides it (`unconfirmed` ranks like `pending`). A8 busy-reply cap was delivered in R-02.
- Resend: `POST /api/v1/tenants/{tid}/conversations/{cid}/messages/{mid}/resend` (editor; 404 for foreign/missing, 409 `NOT_RESENDABLE` unless the message failed with `connection_paused`, 409 `CONNECTION_PAUSED` while the connection is not active). It re-arms the message's single send job (the `uq_channel_send_message` invariant allows one per message) and adds an audited system message. Auto-resume still never re-sends (existing test unchanged).
- Tests changed: unit split test for Instagram is byte-based; head assertions now `0028_channel_unconfirmed`; the route matrix builds a failed channel message for the new route. New `tests/test_channel_delivery.py` 12 passed. Targeted regression passed: test_channel_outbound 28, test_channel_outbound_unit 16, test_channel_contract 17, test_channel_events 12, test_channel_inbox_insights 9, test_channel_migrations 1, health migration tests; test_tenant_route_matrix: editor and admin pass with the resend route, the 2 remaining failures are the pre-existing `main` ones listed above. mypy app clean. Not re-run: other API files, web, Playwright.

## Phase 6 close-out, R-05 health and operations (cloud session, 2026-10-26)
- A9: the signed pull stays the freshness source (15-minute stale rule unchanged). `parse_health_body` now treats a future `checked_at` as "now", so a Many clock that runs ahead cannot freeze freshness or make later signals look older. A successful poll on a stale connection returns it to its real state (new test).
- Multiple workers: `schedule_health_polls` takes a transaction-scoped PostgreSQL advisory lock (`pg_try_advisory_xact_lock`), so only one worker schedules per cycle; each enqueue runs in a savepoint so a unique-index conflict skips one connection instead of losing the cycle. No migration needed.
- ADR-020: sign-off request text added to DECISIONS.md (options a/b); status stays "pending owner sign-off". docs/16 runbook updated: migrations 0023-0028, health model, alerts, canary uses 0023-0028, rollback = pause first, resend for paused failures.
- Tests (cwd apps/api, `TEST_DATABASE_URL=postgresql://test:test@127.0.0.1:5432/phase6`, targeted): `test_channel_health.py` 12 passed (3 new: scheduler lock between two sessions, future `checked_at`, A9 stale cleared by poll); `test_channel_contract.py` 17 passed; ruff check and format clean on `app/channels` and the health test file.

## Phase 6 close-out, R-06 UI on the redesigned app (cloud session, 2026-10-26)
- Built on the B2 components: staff Channels tab in the organization workspace (`lib/staff-channels.tsx`) and staff overview list (`/platform/channels`, nav link), client read-only "Connected channels" card, conversation thread badges (channel, connection, campaign), per-message delivery state incl. "Not confirmed", paused composer, "Send again", inbox/History connection and campaign, Insights channel filter + performance table + campaign chart, Contacts channel filter/column. API: inbox list adds `connection_status`/`campaign_name`; thread detail adds `contact_name`.
- Verified (targeted): Playwright `channels.spec.ts` 2 passed, `channel-insights.spec.ts` 1 passed, `channel-delivery.spec.ts` 2 passed (360px + RTL); node unit tests 23 passed; web tsc and eslint clean; API inbox tests passed file by file.
- `next build` compiles and generates pages but exits 1 on the Next.js 16.4.0 security-advisory gate (owner decision on upgrade pending); Playwright was run against the compiled output with an uncommitted local config.
- Regression subset on the branch (contacts, organizations, overview, b4-dashboards, b5-conversations, group-a-operator, conversations): 30 passed, 5 failed (conversations.spec:69, group-a-operator:26 and :94, overview:135 and :219). The same specs on a clean origin/main build (separate DB, `next start` of its compiled output) fail the same five plus conversations.spec:12 (6 failed, 20 passed), so the five are pre-existing on main (causes not investigated: widget chat waits time out; two operator tests look for UI that the redesign changed).

## Phase 6 close-out, R-07 verification gate (cloud session, 2026-10-26)
- API suite, file by file (91 files, `TEST_DATABASE_URL=postgresql://test:test@127.0.0.1:5432/phase6`, per-file result lines kept): 1003 passed, 22 failed, 0 errors. The 22 are in the same 10 files with the same per-file counts as a clean origin/main (listed with scope in `implementation/PHASE-06-V2/PRE-EXISTING-FAILURES.md`).
- ruff check: 33 findings, all in files this work did not change (also on main); `ruff format --check app`: 3 files flagged (not mine); `mypy app`: clean. Full `mypy` with tests: 16 errors, 5 in `tests/test_channels.py` (Phase 6 follow-up), the rest pre-existing.
- Web: tsc and eslint clean; node unit tests 23 passed. `next build` compiles but exits 1 on the Next.js 16.4.0 security-advisory gate (same on main; CI `npm audit` fails the same way). Playwright was run against the compiled output with an uncommitted local config (`next start`) and the pre-installed Chromium.
- Playwright full run once (168 tests): 154 passed, 14 failed. All 14 fail on a clean origin/main build too: conversations:69, group-a-operator:26 and :94, overview:135 and :219 (first comparison); group-c-polish:129, install:26, knowledge:199, widget-domain:156 and :230, widget-polling:155 and :171, widget-streaming:369, widget:285 (second comparison, where main failed 11 of 40 including knowledge:45 and widget:227 that passed on the branch). Causes not investigated.
- Channel specs all passed: channels (2), channel-insights (1), channel-delivery (2) at 360 px with RTL.
- Not verified: real end-to-end with Many (staging, owner step); ADR-020 awaits owner sign-off; R-08 not started; no merge into main.

## RAG quality fixes after live playground failure (2026-10-27, owner-directed; main)
Symptom: "how can i refund an item?" answered with the canned cannot_confirm on both OpenAI and OpenRouter although the refund PDFs were ingested and embedded.
Findings (observed, read-only DB + traces): (1) the bot had `01-shipping-ar_1.pdf` as an always-include source; its reserved pages took 3 of the 4 evidence slots, failed the gate, and squeezed out the ranked pages, so the model saw one chunk; (2) the 0.50 cosine floor cut refund page 1 (0.494); (3) the query embed opened a new HTTPS connection per call and once exceeded the 5 s cap (turn fell back to FTS-only); (4) Arabic PDFs were stored as presentation-form glyphs (U+FB50-FEFF; 690 of 1152 chars on one page) and English had ligatures, so text_norm did not match typed queries; (5) the first free-chain model (`dots-3-note-preview:free`) took 17 s to first token and refused.
Changes: vector floor 0.50 -> 0.30 (owner instruction; off-topic "weather in Cairo" scored 0.284, "pizza" 0.065, on-topic 0.44-0.59); NFKC fold of PDF text (`normalise_pdf_text`); reserved chunks no longer consume the ranked `final_k` budget (`assemble_evidence`); shared keep-alive httpx pool for embeddings (`_shared_client`); `chunk_size` 1500 -> 900, `chunk_overlap` 200 -> 120, `retrieval_final_k` 4 -> 6 (measured on the test bot: answer in top-4 6/8 -> 7/8, in top-6 8/8; 600 and 400 ranked broad answers 11th-14th). docs/14 updated with dated notes. Pulled origin/main 9551b09 (knowledge Ingest files button) first.
Commands and outcomes:
- `pytest tests/test_rag_gate.py tests/test_knowledge_parsers.py tests/test_retrieval.py tests/test_hybrid_retrieval.py tests/test_cross_language_evidence.py` on a throwaway pgvector container (TEST_DATABASE_URL, removed afterwards): 87 passed. This run covered the floor, parser and assemble_evidence changes.
- Added AFTER that run and NOT run: `tests/test_embedding_foundation.py::test_query_embeds_share_one_connection_pool`, the chunk_size/overlap/final_k default changes, and the updated floor in `tests/eval/offline/test_gate_trace.py::test_defaults_are_unchanged` (that test failed once on the old 0.50 expectation, which is what the edit fixes).
- Full suite (`pytest tests`) was started and stopped on the owner's instruction; its result is unknown. The chunk-size experiment used ad-hoc scripts (not committed) against the production embedding model (about $0.01 total).
Not done / open: free-chain tuning (put a faster free model first, per-model timeout) is only a recommendation; existing sources must be re-ingested for the new chunking and Arabic fix; the fts-only fallback after an embed timeout is unchanged.

## Knowledge tabs, bulk delete, chunk quality, reply formatting, contact sheet (2026-10-27, owner-directed; branch feature/knowledge-tabs-bulk-delete)
Changes: (1) Knowledge page tabs render one section at a time; Files tab multi-select + "Delete selected", backed by `POST /sources/bulk-delete` (all-or-nothing, 404 for unknown/other-tenant ids, 409 if a source is being ingested, registered in `core/permissions.py`); document/chunk previews no longer sliced (display-only cut text). (2) Chunk quality (owner-approved, docs/14 §4/§5): `knowledge/pdf_structure.py` heading sections for PDFs and merging of sections that run over a page break ("Pages a-b"); hard slicing ends on spaces and starts overlaps on a whole word; retrieval neighbour expansion (hit chunk of a long document brings the chunks before/after within the soft budget). Title + heading were already part of the embedded/indexed text. (3) Replies: `lib/message-body.tsx` + `lib/message-parse.ts` (safe markdown subset, no raw HTML) used in the widget, playground and inbox; system prompt asks for a one-line answer, numbered steps, bullets and a bold notes label. (4) Widget: "Contact us" pill button opens a slide-up sheet with floating-label fields, email check, spinner, success mark; Escape closes the sheet first.
Commands and outcomes (throwaway local container `pgvector/pgvector:pg17` on port 55480, removed afterwards; no existing database touched):
- `pytest tests/test_knowledge_hygiene.py tests/test_knowledge_parsers.py tests/test_pdf_structure.py` -> 55 passed, 1 skipped (POSIX-only test).
- `pytest tests/test_rag_gate.py tests/test_retrieval.py tests/test_cross_language_evidence.py` -> 48 passed (includes the two new neighbour tests).
- `pytest tests/test_pdf_structure.py --noconftest` -> 11 passed (pure functions).
- Web: `tsc --noEmit`, eslint on changed files and `next build` clean; `lib/message-parse.ts` checked with a node script (7 assertions, same cases as `tests/message-body.spec.ts`).
NOT run: the Playwright specs (`knowledge.spec.ts` incl. the new bulk-delete test, `widget-layout.spec.ts`, `message-body.spec.ts`) - they need the full API + worker + web build; the existing specs were edited for the tabs/sheet but not executed. The full API suite was not run (owner instruction). Existing sources must be re-ingested for the PDF heading/section change to take effect.
Open: free-tier OpenRouter quality diagnosis (parked by the owner); phase 6 branch review and ManyOsirisChat wiring (deferred by the owner).

## Phase 6 review fixes (cloud session, 2026-10-27): batch 1, merge origin/main
- Environment: PostgreSQL 16.15 with pgvector built from source v0.8.0 (`SELECT extversion` = 0.8.0), disposable DB `phase6_test`, role/password random, Python 3.12 venv; `TEST_DATABASE_URL` set per process only.
- `git merge origin/main` (d189893) -> d61d343. 5 conflicts: `chat/conversations.py` (kept the shared `run_ai_turn`; ported main's `_discard_unanswered_message` into its abort path for the website only (`degrade is None`); channel turns keep the visitor message so the retry can re-drive it, batch 2), `db/models/knowledge.py` (`ck_jobs_type` keeps the three channel job types), `test_tenant_route_matrix.py`, `e2e-api-setup.ts` (comment), PROGRESS.md (both sides).
- Route matrix: 93 tenant routes (counted from the OpenAPI schema); new `POST .../sources/bulk-delete` is in `core/permissions.py`; the matrix now sends it a spare source (main's own matrix lacked a body for it). Website prompt hash re-pinned to main's `8e28195c...a804e` (the prompt is byte-identical to origin/main).
- Commands (cwd apps/api): `python -m pytest tests/test_tenant_route_matrix.py tests/test_chat.py::test_system_prompt_matches_main_bytes_for_fixed_website_input tests/test_channel_migrations.py -q`: all passed (route matrix 7 passed after the fix). `alembic heads` = `0028_channel_unconfirmed` only. `ruff check app`: clean.
- `alembic check` after merge reports drift in `bots.uq_bots_widget_locator` and `provisioning_requests` (from main, not this branch) besides the two channel indexes fixed in batch 5.
- B1 (P7 / green Playwright gate): OPEN, owner decision; nothing merged to main.
