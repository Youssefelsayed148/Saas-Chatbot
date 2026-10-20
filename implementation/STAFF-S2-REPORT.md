# S2 — staff Members

Status: S2 backend and static verification complete. Browser execution is deferred until the combined
run after S4. No branch has been merged, pushed or deployed.

Branch: `feature/staff-members`. Base: finalized S1 commit `bb2e847`, with owner approval
to work before S1's verification/merge. Isolated worktree:
`.worktrees/staff-members`. The S1 and Phase 6 checkouts are untouched.

## Changes

- `apps/api/app/db/models/core.py` and migration `0017_staff_members`: nullable
  phone and an active account flag defaulting true for existing accounts.
- `apps/api/app/auth/service.py` and `cookies.py`: one shared session-issuance
  eligibility check, user-row locking against reset/deactivation races, revocation
  of every target-user session, and inactive-account denial at session resolution.
- `apps/api/app/platform/users.py` and application router registration: typed staff-only
  account list/detail/create, membership assignment/change/removal, password reset
  and deactivate/reactivate endpoints. Staff accounts are excluded. Organization
  filtered lists expose only that organization's memberships. All mutations are
  attributed to the staff actor; responses prohibit caching.
- `apps/api/app/tenants/service.py`: invitations require an existing account;
  membership changes reuse tenant locks, seat capacity and last-admin rules.
  Staff operations retain their real actor and use the requested audit names.
- `apps/web/app/platform/members/`, `lib/staff-members.tsx`, API types/navigation
  and organization detail: list/filter/pagination, create/detail, password issuance,
  membership controls and existing-user invitation/revocation controls.
- Backend lifecycle, authorization, validation, privacy, isolation, migration and
  concurrent revocation tests; Members browser journeys written for later execution.

## Verification evidence

All commands run in the isolated worktree. Python uses the existing root virtual
environment. TEST_DATABASE_URL is supplied per process, never loaded from dotenv
or saved as runtime configuration.

- Web `npm.cmd run lint`: exit 0, no warnings.
- Web `npm.cmd run typecheck`: exit 0; raw tail:

  ```text
  > next typegen && tsc --noEmit
  Generating route types...
  ✓ Types generated successfully
  ```

- Web `npm.cmd run test -- --list`: exit 0; raw tail:

  ```text
  Total: 66 tests in 21 files
  ```

- Backend Ruff over changed files: exit 0, `All checks passed!`.
- Scoped backend mypy: exit 0, no issues; exact file groups and intermediate
  failures/corrections are recorded in `PROGRESS.md`.
- Backend collection only:

  ```text
  python -m pytest --collect-only -q -p no:cacheprovider tests/test_staff_members.py tests/test_staff_members_migration.py tests/test_staff_member_revocation_race.py
  31 tests collected in 0.25s
  ```

Targeted execution (including the migration upgrade/downgrade round trip) passed:

```text
75 passed, 1 warning in 49.85s
```

This is 0 failed and 0 skipped. The existing Starlette/httpx warning remains.
The first sandbox attempt crashed during pytest temporary-directory cleanup and
did not print a reliable final summary. The first host repeat reported
`1 failed, 74 passed, 1 warning in 47.10s`; its remaining failure was missing
permission metadata on nested routes. Moving registration to the existing
top-level application path fixed it. Full commands and intermediate failures
are recorded in PROGRESS.md; raw logs are in the ignored `.test-storage-s2/`.

Two identical full-suite runs passed (0 failed in both):

```text
437 passed, 1 skipped, 1 warning in 1425.32s (0:23:45)
437 passed, 1 skipped, 1 warning in 1335.86s (0:22:15)
```

The one skip is the pre-existing POSIX process-group parser integration on Windows.
The first full attempt before Windows environment correction reported
`3 failed, 434 passed, 1 skipped, 1 warning in 1374.94s (0:22:54)`:
two cp1252 decoding errors and one fixture path over the classic Windows limit.
Process-only PYTHONUTF8=1 and a short workspace temporary path fixed these;
the three affected cases separately passed (`3 passed, 1 warning in 8.49s`).
Neither tests nor safety guards were weakened.

Standalone startup guard, in its own process with BOTH stub variables removed:

```text
7 passed, 1 warning in 0.63s
```

Final changed-Python Ruff and mypy checks exited 0:

```text
All checks passed!
Success: no issues found in 15 source files
```

Full Python command (both runs, same arguments; only the Tee output filename changed):

```powershell
& 'D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai\.venv\Scripts\python.exe' -u -m pytest -q --tb=short -p no:cacheprovider --ignore=tests/test_startup_guard.py --basetemp='D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai\.test-storage-s2\f' --junitxml=../../.test-storage-s2/full-utf8.xml
```

Working directory is this worktree's apps/api. Per-process environment:
owner-supplied TEST_DATABASE_URL, ENVIRONMENT=test, PYTHONUTF8=1, both model stubs=true,
TEMP/TMP at the root workspace's `.test-storage-s2/t`. Full logs are
`.test-storage-s2/full-utf8-1.log` and `full-utf8-2.log`; startup log is
`startup-guard.log`. Test-generated evaluation timestamps were restored, and
no evaluation/retrieval source was changed. No paid provider calls, Docker
commands, merges, pushes or deployments were made.

## Deviations and preserved behavior

- The base is unmerged S1, rather than main after S1 merge, as subsequently
  authorized by the owner. Started at `49710c7` and incorporated finalized S1 by
  local rebase onto `bb2e847`. Main remains untouched by this work.
- Existing invitation fixture setup provisions accounts first. `logged_in` can
  log in to those provisioned fixture accounts. Existing assertions remain; direct
  invitation/route-matrix setups add the existing-account prerequisite. The legacy
  registration test represents an old outstanding invitation by removing only its
  disposable fixture account. The browser dashboard invitee signs in, rather than
  trying to register an already-provisioned account.
- Membership services accept an audit action parameter to reuse existing locking
  and protection rules without granting staff a tenant membership or tenant role.
- Password generation occurs on submission; the result appears once with the
  required sharing note. Typed passwords are shown from the form's transient state
  and are not echoed by the API. They are not stored in browser storage or URLs.
- The initial worktree typecheck could not resolve installed TypeScript packages;
  an ignored local dependency junction resolved this without changing dependencies.
- The legacy batch-onboarding path is unchanged in S2 and is retired in S3, as
  explicitly scoped. Existing-user enforcement here applies to tenant invitation
  creation; S3 removes the legacy staff invitation-creation path.
- Later owner instruction "dont stop" was applied to repairing S2 failures before
  advancing. Initial red results and the environment corrections are recorded,
  rather than omitted. No S3 implementation began before S2 was green.

Deployment consideration: apply Alembic 0017 before running the S2 code against a
deployment database. Its downgrade drops the newly added phone/active fields.
Only disposable databases were migrated here; production migration is not authorized.

Self-service settings, password-change pages, Google login, email changes, deletion,
bulk import, onboarding retirement, knowledge behavior and docs under `docs/` were
not changed in S2.

## Manual browser checks

1. Sign in as staff. Open Platform → Members. Search, select an organization,
   filter Active/Inactive and exercise pagination.
2. Create a user with a mixed-case email, optional international phone, generated
   password and an organization/role. Copy the one-time password, dismiss it, and
   confirm navigation/reload does not reveal it again.
3. In a clean browser context, sign in as that user. Confirm the correct
   organization and role, and that staff-only pages are inaccessible.
4. As staff, reset the password. Confirm every existing user session is rejected;
   sign in with the new password. Repeat using a typed password.
5. Deactivate with confirmation. Confirm session rejection and login refusal.
   Reactivate with confirmation and confirm login works again.
6. Open organization detail → Members. Search for an existing user, assign a role,
   change it and remove the membership. Attempt to demote/remove the last admin
   and confirm refusal.
7. Invite an existing account that has no membership, using mixed-case input.
   Accept while signed in as that account. Revoke another pending invitation.
   An unknown email must return the specified USER_NOT_FOUND message.
8. Check tenant Team, invitations and /me responses: none contains account phone.
   Check audit rows identify the staff actor and contain no password/hash.

## Post-MVP ideas

- Batch membership loading if global staff user lists grow enough to need it.
- Review the pre-existing revoked-only-account login rule when designing future
  invitation/rejoining behavior; this slice preserves it.

The Git snapshot below is captured immediately before the final verification-report
commit. No existing test was deleted; fixture/journey adaptations are described above.

## Git review

Base: `bb2e847` (final S1).

git log --oneline bb2e847..HEAD

```text
0c192f0 fix: reuse organization invitation list and record verification setup
a6d6bac fix: include archived organizations in staff member filters
76973a0 fix: register staff routes with permission metadata and protect account errors
e98dd14 test: cover staff session revocation races
b9a2d28 feat: add platform Members screens and organization member controls
e8b686d feat: add staff account lifecycle and membership administration
```

git diff --stat bb2e847

```text
 PROGRESS.md                                        | 144 +++++++++
 apps/api/alembic/versions/0017_staff_members.py    |  22 ++
 apps/api/app/auth/cookies.py                       |   2 +-
 apps/api/app/auth/service.py                       |  39 ++-
 apps/api/app/db/models/core.py                     |   4 +
 apps/api/app/main.py                               |   4 +-
 apps/api/app/platform/router.py                    |   1 +
 apps/api/app/platform/users.py                     | 335 +++++++++++++++++++++
 apps/api/app/tenants/service.py                    |  28 +-
 apps/api/tests/helpers.py                          |  13 +-
 apps/api/tests/test_invitations.py                 |   2 +
 apps/api/tests/test_self_service_signup.py         |   6 +
 apps/api/tests/test_staff_member_errors.py         |  37 +++
 .../api/tests/test_staff_member_revocation_race.py |  54 ++++
 apps/api/tests/test_staff_members.py               | 311 +++++++++++++++++++
 apps/api/tests/test_staff_members_migration.py     |  39 +++
 apps/api/tests/test_tenant_route_matrix.py         |   3 +
 apps/web/app/platform/clients/[clientId]/page.tsx  |  79 ++++-
 apps/web/app/platform/members/[userId]/page.tsx    | 120 ++++++++
 apps/web/app/platform/members/page.tsx             | 211 +++++++++++++
 apps/web/lib/api.ts                                |  76 +++++
 apps/web/lib/app-header.tsx                        |   1 +
 apps/web/lib/page-title.tsx                        |   2 +
 apps/web/lib/staff-members.tsx                     | 299 ++++++++++++++++++
 apps/web/tests/dashboard.spec.ts                   |  19 +-
 apps/web/tests/group-a-members.spec.ts             |  29 +-
 apps/web/tests/staff-members.spec.ts               | 112 +++++++
 implementation/STAFF-S2-REPORT.md                  | 262 ++++++++++++++++
 28 files changed, 2219 insertions(+), 35 deletions(-)
```

git diff --numstat bb2e847

```text
144	0	PROGRESS.md
22	0	apps/api/alembic/versions/0017_staff_members.py
1	1	apps/api/app/auth/cookies.py
27	12	apps/api/app/auth/service.py
4	0	apps/api/app/db/models/core.py
3	1	apps/api/app/main.py
1	0	apps/api/app/platform/router.py
335	0	apps/api/app/platform/users.py
22	6	apps/api/app/tenants/service.py
12	1	apps/api/tests/helpers.py
2	0	apps/api/tests/test_invitations.py
6	0	apps/api/tests/test_self_service_signup.py
37	0	apps/api/tests/test_staff_member_errors.py
54	0	apps/api/tests/test_staff_member_revocation_race.py
311	0	apps/api/tests/test_staff_members.py
39	0	apps/api/tests/test_staff_members_migration.py
3	0	apps/api/tests/test_tenant_route_matrix.py
78	1	apps/web/app/platform/clients/[clientId]/page.tsx
120	0	apps/web/app/platform/members/[userId]/page.tsx
211	0	apps/web/app/platform/members/page.tsx
76	0	apps/web/lib/api.ts
1	0	apps/web/lib/app-header.tsx
2	0	apps/web/lib/page-title.tsx
299	0	apps/web/lib/staff-members.tsx
16	3	apps/web/tests/dashboard.spec.ts
19	10	apps/web/tests/group-a-members.spec.ts
112	0	apps/web/tests/staff-members.spec.ts
262	0	implementation/STAFF-S2-REPORT.md
```
