# C4 / C5 targeted repair report - 2026-10-28

Worktree: `D:/Projects/Work Projects/The Osiris Labs/ManyOsirisChat/.closeout-worktrees/c4-c5`.
Branch: `closeout/c4-c5`; base `216a4f0` (includes A16 contract text `205bdab`,
before C2 implementation/migration 0031 integration). Changes are UNCOMMITTED.
Lead owns shared progress/plan integration and subsequent read-only review.

## Files changed and behavior

- `apps/api/tests/test_tone_prompt.py` and new
  `tests/fixtures/prompts/website-system-d189893.txt`: replace a stale opaque
  prompt hash with independently captured golden prompt bytes from historical
  main commit `d189893`. That commit introduced the approved list/bold wording;
  the old hash predates it. Historical fixture SHA-256 is
  `33c625421010876daa0a9ea38688521874ba59afe1c002d4f7dab0b290d72580`.
  Empty tone/default optional sections must still preserve the entire body.
- `apps/api/tests/test_trace_context.py`: the forced-refusal fixture disables
  the vector OR leg as well as raising the keyword floor. All assertions on
  no model call, refusal, rejected candidate details and privacy remain.
- `apps/api/app/db/models/core.py`: declare the existing named unique widget
  index and provisioning unique constraint/created index exactly as existing
  migrations 0004/0006 do. No database migration or schema change is needed.
- New `apps/api/tests/test_closeout_schema_drift.py`: three real migrated-schema
  checks for widget uniqueness, provisioning indexes and the existing 0030
  health-poll lookup index. No create_all/stamping shortcut.
- `apps/web/tests/group-c-polish.spec.ts`: explicitly select the Jobs tab
  before checking job status/actions on the tabbed knowledge page.
- `apps/web/tests/widget-streaming.spec.ts`: inspect MessageBody's actual
  formatted content wrapper/automatic-direction blocks rather than the old
  removed `div[dir=auto]`. Progressive, abort, replacement, errors and fallback
  assertions remain; no timeout was increased.
- `apps/web/tests/knowledge.spec.ts`: wait for the asynchronous upload/ingest
  transition to select Jobs before navigating to Files. The original test
  raced with a late `setTab('jobs')`; its failure snapshot had Files focused
  while Jobs was selected. Duplicate/always-include/replace/remove assertions
  remain.
- `apps/web/app/app/[tenant]/bots/[botId]/knowledge/page.tsx`: actual product
  repair discovered after that race was fixed. A duplicate-only upload can
  legitimately leave nothing to ingest; preserve its useful duplicate notice
  instead of replacing it with the API's `409 NOTHING_TO_INGEST`. Only that
  exact code/status with an existing duplicate notice is handled as success;
  other errors retain the original failure handling. Existing stored sources
  can still be ingested; the server remains authoritative about whether work
  exists.
- `apps/web/tests/overview.spec.ts`: wait for the current visitor message,
  re-enabled input, no Stop button and persisted final reply feedback instead
  of hanging on SSE transport EOF. The widget intentionally cancels its
  reader after `done`; failure evidence showed the final committed reply and
  enabled input while the old response.finished wait timed out. An initial
  attempted announcement assertion was incorrect for done-only canned replies
  and was corrected to persisted-message feedback. Analytics, measured counts,
  tenant A/B isolation, CSV and unanswered-question assertions are unchanged.
- New public `apps/web/app/privacy/page.tsx` and `terms/page.tsx`: SaaS/business
  processor roles, Many's separate Meta transport/credentials, configured AI
  processing, retention/erasure, limited accounting records and pseudonymous
  replay-prevention record disclosed without inventing hosting location or
  retention periods. This text awaits owner publication/review, not a claim
  that a deployment occurred.
- `apps/web/lib/page-title.tsx`, link-only `apps/web/app/login/page.tsx`: route
  titles and discoverable public privacy/terms links follow existing UI.
- New `apps/web/tests/privacy-terms.spec.ts`: both notices must be publicly
  readable without a staff session and cross-link correctly.
- `.github/workflows/ci.yml`: root-working-directory contract-copy check before
  backend dependency installation. The hosted workflow was NOT run.

## C5 items already implemented / unresolved

- The `-1-1` CSV guard and its real export integration coverage already exist
  at the base. No rewrite: the existing `test_contacts_export_safety.py` passed
  in the targeted API run.
- Migration 0030 and the Job model already contain
  `ix_jobs_channel_health_poll_last`; the new migrated-schema check passed.
- S10 remains undefined. Existing evidence:
  `implementation/PHASE-06/OWNER-DECISIONS.md:51` and
  `implementation/PHASE-06/PROGRESS.md:473-475`. No behavior was guessed or
  declared complete for it; owner must supply text or declare it void.

## Tests / exact commands and outcomes

The retained shell scripts contain every environment variable, startup,
namespace, PostgreSQL and nested test command. They use synthetic credentials
only, never load actual dotenv files, and disable external networking while
running tests. Browser/dependency downloads were separately authorized.

### Setup and API

1. Browser setup (exit 0):

   ```powershell
   wsl -d Ubuntu -u root -- bash '/mnt/d/Projects/Work Projects/The Osiris Labs/ManyOsirisChat/.closeout-worktrees/c4-c5/implementation/c4-c5-evidence/install-browser.sh'
   ```

   Nested `npx playwright install --with-deps chromium` installed matching
   Linux Chromium/headless-shell build 1248 under
   `/var/tmp/saas-closeout-tools/playwright`. Node 24.22.1 and Python 3.12.16
   tooling were supplied by the lead under `/var/tmp/saas-closeout-tools`.
   The lead's npm ci was not repeated.
2. Initial API attempt used the script below but a URL carrying the Unix-socket
   host query was percent-encoded by SQLAlchemy. Conftest's ConfigParser
   rejected its percent signs: **31 setup errors**, exit 1; no test behavior
   ran. Full logs/XML retained as `api-tests-attempt1.*`. Harness-only fix:
   `PGHOST=/var/tmp/saas-c4-c5/socket` and a URL without an encoded host query.
   No conftest/application workaround was introduced.
3. Corrected targeted run:

   ```powershell
   wsl -d Ubuntu -u root -- bash '/mnt/d/Projects/Work Projects/The Osiris Labs/ManyOsirisChat/.closeout-worktrees/c4-c5/implementation/c4-c5-evidence/test-api.sh'
   ```

   Nested from `apps/api`:

   ```sh
   APP_ENV=test TEST_DATABASE_URL="$TEST_DATABASE_URL" pytest tests/test_tone_prompt.py tests/test_trace_context.py tests/test_contacts_export_safety.py tests/test_closeout_schema_drift.py -q --junitxml="$repo/implementation/c4-c5-evidence/api-tests.xml"
   ```

   **31 passed, zero failures/errors/skips, one Starlette dependency warning,
   93.21 s**. Independently parsed JUnit verifies the counts. Own disposable
   PG18 cluster `/var/tmp/saas-c4-c5/pg`; socket port 55455, TCP disabled;
   base `many_test_c4_c5`, fixture-created `many_test_c4_c5_test`. Both database
   identity and explicit test setting printed before invocation. Private
   loopback-only namespace, per-worker TMPDIR, stub models, no Redis required.
4. In the same offline/disposable run:

   ```sh
   DATABASE_URL='postgresql://postgres@/many_test_c4_c5_test?port=55455' alembic check
   ```

   Exit 0: `No new upgrade operations detected.` See `alembic-check.log`.
   Existing warnings: vector type reflection unrecognized and cyclic
   bots/knowledge_revisions sorting; no claim of a complete vector-type audit.
   No new migration was needed. The script then exited 1 on newly introduced
   import-format lint errors, not on pytest or Alembic. Ruff fixed/formatted
   those imports/test wrapping; no behavioral API change after passing tests.
   API tests were not unnecessarily repeated.

### Targeted Playwright repair iterations

Each run used the standard config's `npm run build && npm run start`, real
API/worker and Chromium, with offline stub models in one loopback-only network
namespace. Own PG cluster `/var/tmp/saas-c4-c5-e2e/pg`, port 55456 on namespace
loopback only; DB `many_test_c4_c5_e2e_test`, API 8115, web 3215. Nothing used
an existing application/database service. PostgreSQL shutdown succeeded after
each run; API/worker teardown was invoked by Playwright. Some shutdown noise
from terminating pooled connections followed the early failed run.

1. Initial affected files:

   ```powershell
   wsl -d Ubuntu -u root -- bash '/mnt/d/Projects/Work Projects/The Osiris Labs/ManyOsirisChat/.closeout-worktrees/c4-c5/implementation/c4-c5-evidence/test-web.sh'
   ```

   Nested: `APP_ENV=test TEST_DATABASE_URL="$TEST_DATABASE_URL" npx playwright test tests/group-c-polish.spec.ts:129 tests/knowledge.spec.ts:204 tests/overview.spec.ts tests/widget-streaming.spec.ts --reporter=line`.

   Exit 1: **13 passed, 2 failed, 5.8 min**, `web-tests.log`.
   All 11 widget cases and the Jobs action case passed. Knowledge reproduced
   the late-tab race; overview reproduced the 240 s transport-EOF hang. Source
   fixes were applied after first failures while this run finished, so these
   counts are exact but do not independently prove every final-source case.
   No inference about which worker import saw a later edit is required.
2. After those fixes, only remaining specs plus new policies:

   ```powershell
   wsl -d Ubuntu -u root -- bash '/mnt/d/Projects/Work Projects/The Osiris Labs/ManyOsirisChat/.closeout-worktrees/c4-c5/implementation/c4-c5-evidence/test-web-final.sh'
   ```

   Nested: `APP_ENV=test TEST_DATABASE_URL="$TEST_DATABASE_URL" npx playwright test tests/knowledge.spec.ts:204 tests/overview.spec.ts tests/privacy-terms.spec.ts --reporter=line`.

   Exit 1: **2 passed, 3 failed, 2.3 min**, `web-tests-final.log`.
   Both public-policy cases passed. Knowledge progressed past the tab race
   and exposed the actual duplicate-only upload/409 UX bug. Both overview
   cases exposed the incorrect newly added announcement assumption; the
   source only announces progressive streams, not done-only canned replies.
3. After fixing that product bug and using final persisted-message feedback:

   ```powershell
   wsl -d Ubuntu -u root -- bash '/mnt/d/Projects/Work Projects/The Osiris Labs/ManyOsirisChat/.closeout-worktrees/c4-c5/implementation/c4-c5-evidence/test-web-repaired.sh'
   ```

   Nested: `APP_ENV=test TEST_DATABASE_URL="$TEST_DATABASE_URL" npx playwright test tests/knowledge.spec.ts:204 tests/overview.spec.ts --reporter=line`.

   **Exit 0: 3 passed, zero failures, 1.9 min**, `web-tests-repaired.log`.
   Only the still-failing cases were rerun. The policy, Jobs and widget behavior
   did not change after their passing evidence. Across focused runs, 17 distinct
   cases have passing evidence: 11 widget + 1 Jobs + 1 knowledge + 2 overview +
   2 policy. This is NOT an aggregate full-suite result or a full D1 gate pass.

### Related static checks

Command (offline namespace):

```powershell
wsl -d Ubuntu -u root -- unshare --net bash '/mnt/d/Projects/Work Projects/The Osiris Labs/ManyOsirisChat/.closeout-worktrees/c4-c5/implementation/c4-c5-evidence/check-style.sh'
```

Final exit 0: owned-file Prettier formatting, ESLint, contract copies OK,
Ruff checks pass, four Python files already formatted. The script was extended
only as later failure repairs added changed files; it does not run any suite
or database. All nested filenames/commands are preserved in the script.
Next production builds in focused E2E runs succeeded, including their normal
TypeScript check. Standalone whole-project lint/type commands and mypy were
not run here. `git diff --check` exit 0 (LF/CRLF Git warnings only).

## Open questions, risks and next-session handoff

- Full SaaS API suite and **full Playwright suite remain UNVERIFIED / NOT RUN**,
  deliberately deferred by the owner's latest instruction to a new session.
  A green D1 full run and owner merge/deployment approvals are still required.
- These results are on isolated base 216a4f0 plus this worker diff, before C2
  implementation integration. Lead must integrate/review and run the full
  suites once in the new session; do not describe targeted evidence as an
  integrated regression result.
- S10 undefined and hosted CI execution remain open. Policies require owner
  review before publication. No push, merge, deploy, Docker operation, live
  send, provider API call, paid call or production data access occurred.
- Actual env/token/secret files were not read or copied. No credentials were
  generated outside ephemeral test-only keys supplied by the test harness.
- Preserve the toolchain: `/var/tmp/saas-closeout-tools/venv`,
  `/var/tmp/saas-closeout-tools/node-v24.22.1-linux-x64/bin`,
  `/var/tmp/saas-closeout-tools/playwright`. Browser environment must set
  `PLAYWRIGHT_BROWSERS_PATH` to that last path.
- Existing harness commands above run TARGETED tests only. For new-session
  full validation, adapt copies to the final integrated worktree and run the
  full API `pytest tests` and Playwright `npx playwright test` once, keeping
  explicit test variables, a newly named disposable cluster/DB, namespace-only
  loopback, stub models, distinct ports and dotenv absence guards. Avoid
  percent-encoded Unix-socket host queries in Alembic's ConfigParser path;
  use PGHOST/PGPORT plus a query-free URL for socket tests, or namespace-local
  loopback TCP for the browser stack. No full-run command was executed here.
