# S2 — staff Members

Status: targeted verification green; full backend verification in progress. This is not a
completion or phase sign-off. Browser execution is deferred until the combined
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

Two identical full-suite runs and the standalone startup guard remain pending.
No results are claimed for unexecuted checks. No paid provider calls, Docker
commands or database/startup/worker safety-guard changes were made.

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

Git log, final diff/numstat and executed test tails will be added after verification.
