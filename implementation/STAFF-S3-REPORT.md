# S3 — staff Bots and onboarding retirement

Status: backend and static verification complete. Browser execution is deferred
to one combined pass after S4.
Branch `feature/staff-bots` is STACKED on S2 `691382c`, not main. Local commits
only; no merge, push, deployment, Docker or paid API calls.

## Changes

- `app/bots/factory.py`: one runtime bot construction function with active-tenant
  locking, existing plan quota enforcement, trimmed 1–100 character name, draft
  status/default config, unique public widget locator and transactional audit.
  Existing BotService, staff tenant-bot endpoint and provisioning wrapper delegate.
- `app/platform/bots.py`, main registration and organization detail: staff-only
  typed global directory/create endpoints, search and organization filter, source
  count/latest ingestion/published revision summaries scoped by tenant AND bot.
  Organization detail reuses the same summary function. Existing 401/403 behavior
  and staff dependency remain. Strict bot update schemas reject ownership changes.
- New platform Bots page and shared creation form, including organization-locked
  variant, Knowledge/Settings links and creation next steps. Organization detail
  retains Pause. Settings displays organization as read-only text.
- Removed staff onboarding POST, form/state/client function/unused interface and
  styles. Updated workspace creation link. Historical status/CSV routes remain
  operational and tested; historical audit vocabulary remains readable.
- Added bot lifecycle/validation/quota/authorization/isolation/audit/immutability
  and history tests, plus browser specs checked statically. Existing staff setup
  and legacy provisioning regressions are adapted as described below.

## Verification evidence

Targeted command, in apps/api with owner-provided TEST_DATABASE_URL supplied per
process, ENVIRONMENT=test, PYTHONUTF8=1 and both model stubs=true:

```text
python -u -m pytest -q --tb=short -p no:cacheprovider tests/test_staff_bots.py tests/test_platform.py tests/test_group_c_polish.py tests/test_self_service_signup.py tests/test_tenant_route_matrix.py tests/test_quotas.py tests/test_staff_members.py tests/test_staff_members_migration.py --basetemp=<workspace>/.test-storage-s3/q --junitxml=../../.test-storage-s3/targeted.xml
77 passed, 1 warning in 173.29s (0:02:53)
```

There were 0 failed and 0 skipped. The existing Starlette/httpx warning remains.
The migration test upgrades/downgrades S2's 0017 schema; S3 adds no migration.

```text
All checks passed!
Success: no issues found in 10 source files
```

These are the final Ruff and scoped mypy output tails. Exact source lists and
initial formatting/import corrections are recorded in PROGRESS.md.
Web `npm.cmd run lint` and `npm.cmd run typecheck` exited 0; route generation
and tsc succeeded. `npm.cmd run test -- --list` exited 0:

```text
Total: 68 tests in 22 files
```

No browser tests were executed. Static seed/Compose verification:

```text
python -m unittest discover -s scripts -p test_dev_compose.py
Ran 7 tests in 0.006s
OK
```

Full run 1 exited 0 (0 failed):

```text
449 passed, 1 skipped, 1 warning in 1335.63s (0:22:15)
```

The skip is the existing POSIX process-group parser integration on Windows.
The identical repeat also exited 0 (0 failed), confirming reproducible counts:

```text
449 passed, 1 skipped, 1 warning in 1335.95s (0:22:15)
```

Standalone startup guard, in its own process with BOTH stub variables removed:

```text
7 passed, 1 warning in 0.66s
```

Full Python command, identical in both runs (only Tee log filename changed):

```powershell
& 'D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai\.venv\Scripts\python.exe' -u -m pytest -q --tb=short -p no:cacheprovider --ignore=tests/test_startup_guard.py --basetemp='D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai\.test-storage-s3\f' --junitxml=../../.test-storage-s3/full.xml
```

Working directory is this worktree's apps/api. Environment is supplied per process:
owner-provided TEST_DATABASE_URL, ENVIRONMENT=test, PYTHONUTF8=1, both model stubs=true,
TEMP/TMP at root `.test-storage-s3/t`. Logs: `.test-storage-s3/full-1.log`,
`full-2.log`, `targeted.log`, `startup-guard.log`. No new S3 test is skipped.

## Deviations and regression mapping

- Owner approved a minimal ProvisioningService._make_bot delegation to reconcile
  the two conflicting instructions: one creation function and preservation of the
  provisioning service. Every other provisioning method remains unchanged.
- Initially stacked on S2 `df826b5`, then restacked onto `691382c` to incorporate
  its final main-landmark markup alignment. The diff between those S2 bases under
  apps/api is empty; backend source stayed identical during both full runs and
  final restacking. Web checks were repeated on the final stacked source.
- Retained provisioning-specific assertions run against the real service because
  the new separate endpoints intentionally have no batch-onboarding idempotency,
  fingerprint or file-staging contract. Duplicate submit still proves one tenant
  and one bot; payload conflict remains 409; old owner-format fingerprints and
  persisted results remain unchanged while responses use admin vocabulary.
- Staff setup/acceptance and widget-locator tests use actual organization, user,
  invitation and bot endpoints. Audit assertions now name their real new actions
  while preserving staff attribution, pending-admin state and client-area denial.
- The old missing Idempotency-Key HTTP test now proves retired POST returns
  404/405. Its old 400 contract cannot remain after the route is removed.
- Historical optional-file staging remains a service regression; new bot creation
  accepts no uploads. Production file work continues through Knowledge.
- The existing platform browser journey now uses the organization/shared bot forms
  and real user/invitation endpoints. It keeps search, detail, unpublished state,
  staff-without-membership, deletion-preview and cancel/confirm assertions. The
  retired durable-request UI assertion becomes creation feedback; durable behavior
  remains tested at service level. The workspace-link locator/target is updated
  to Create organization, retaining the navigation assertion.
- Historical owner/admin audit labels and fixture actions are deliberately retained
  because the existing audit-history tests and persisted records still use them.
- Deterministic seed/test fixture Bot inserts remain fixtures; all runtime API and
  provisioning creation paths use the shared factory. The seed never used the
  removed route, so its code was not changed.

No knowledge/retrieval pipeline, client bot-creation permission, bot deletion,
cloning/moving, Google, S4 password page, docs under `docs/`, or safety guard was
changed. S2's schema migration must precede deployment of this stacked branch;
no production migration or deployment was performed.

## Manual browser checks

1. Sign in as staff. Create an active organization in Organizations; choose a plan
   with room for at least two bots, or use the existing reasoned quota controls.
2. Open Bots. Search and filter by organization. Create a bot with whitespace
   around its name; confirm the saved name is trimmed and ownership is correct.
3. Follow its Knowledge link. Return and follow Settings. Verify organization is
   read-only and configure allowed website domains through the existing form.
4. Open organization detail → Bots. Create another bot; organization is preselected
   and fixed. Follow its next-step links and row links. Confirm Pause still uses
   its existing reason/confirmation workflow.
5. Exhaust the bot quota and attempt another creation; confirm the safe limit
   message. An archived organization must not be selectable for new creation.
6. Confirm the platform page has no onboarding form and the workspace creation
   link reaches New organization. A non-staff session must not reach Bots.
7. Repeat the full Organizations → Members → Bots setup, sign in as the created
   client, and verify tenant permissions. Run the combined Playwright suite only
   after S4, as requested.

## Seed and owner-run commands

No reseed is required for S3 because scripts/seed_dev_stack.py and seed_demo.py do
not call onboarding. Seven static wiring tests pass. If you deliberately choose
to exercise the existing seed in a configured checkout on this branch:

```powershell
.\scripts\dev_up.ps1
.\scripts\dev_compose.ps1 --profile seed run --rm seed
```

Check demo creation/reuse, staff sign-in, the demo bot/knowledge pages and the
reported backfill job in Operations/worker logs. The existing seed queues a premium
embedding backfill; run it only when you intend that existing provider behavior.
These commands were not executed here and no credential file was opened.

## Post-MVP cleanup candidates

- Retired staff-only ProvisioningService.onboard_platform_client and the staff
  invitation/file-staging branches, including their token helper, remain for
  historical/service compatibility review. Shared self-service helpers remain active.
- Batch global directory summary queries if operator volume warrants it.

The Git snapshot below is captured immediately before this final verification
report commit. No existing test file was deleted; replacements are mapped above.
