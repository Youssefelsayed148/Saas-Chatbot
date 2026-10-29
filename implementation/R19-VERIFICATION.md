# R19 SaaS verification - 2026-10-28

Worktree: ManyOsirisChat/.closeout-worktrees/batch-c, branch closeout/batch-c.
The named application fixes already exist in this source; no duplicate migration,
phone-guard rewrite or prompt behavior change was invented.

- `apps/api/app/contacts/router.py`: `_PHONE_SHAPE` requires leading plus then a
  digit; `-1-1` is escaped. Existing tests cover =, +, -, @, formatted real numbers
  and CSV output. `test_contacts.py` also verifies tenant A/B scope.
- `0030_channel_health_poll_index` already supplies the partial expression index
  on tenant_id, payload->>'connection_id', created_at for channel_health_poll.
  The model matches it. New `tests/test_r19_index_migration.py` proves actual
  0029 -> 0030 -> 0029 -> head transitions, exact index expression and clean
  Alembic drift. No migration after 0031 is needed or added.
- Bot widget locator and provisioning constraints/indexes already match migrations
  0004/0006 in `app/db/models/core.py`; existing schema-drift tests pass.
- No S10 reference exists in the current rebuild prompt (or current prompt files
  searched). The mention of an undefined S10 in older PROGRESS entries is history.
  No prompt requirement was invented; five prompt golden/behavior tests passed.
- Both CI YAML definitions parse, are manual-only, pass shell syntax checks and
  reference existing script/test/package commands. No workflow was run.
- Provider-global webhook_unhealthy is unchanged.

## Exact commands and outcomes

Private source snapshot: `.r19-validation/source`, allowlisted code/config and
synthetic fixtures only; no env/credential/token files. Cached Python 3.12.16,
Postgres 18 + pgvector, loopback-only network namespace, fresh private cluster
`/var/tmp/saas-r19-x3JcJhSZ`, base DB many_test_r19. Fixtures create only disposable
_test databases in that cluster. Stub models and empty provider keys; no network
provider call. Trap stopped only the run's own cluster.

PowerShell from batch-c:

```text
wsl -d Ubuntu -u root -- unshare --net bash '/mnt/d/Projects/Work Projects/The Osiris Labs/ManyOsirisChat/.closeout-worktrees/batch-c/.r19-validation/run.sh'
```

The harness sets APP_ENV=test, ENVIRONMENT=test, explicit TEST_DATABASE_URL and
DATABASE_URL, PGHOST to the new private socket, PGPORT=55449, PGUSER=postgres,
CHAT_STUB_MODEL=1, EMBEDDING_TEST_STUB=1 and WORKER_ALLOW_ONLY_TEST_DB=1. It prints
host/database only, checks the actual database and snapshot import path, then runs:

```sh
APP_ENV=test TEST_DATABASE_URL="$TEST_DATABASE_URL" pytest tests/test_contacts_export_safety.py tests/test_closeout_schema_drift.py tests/test_r19_index_migration.py tests/test_channel_health.py tests/test_contacts.py tests/test_tone_prompt.py -q --junitxml="$scratch/evidence/targeted.xml"
```

41 passed, zero failures/errors/skips, 54.07 s, exit 0. Evidence:
`/var/tmp/saas-r19-x3JcJhSZ/evidence/targeted.log` and `targeted.xml`.
The new test's `alembic.command.check(config)` returned no upgrade operations.
Warnings: existing vector introspection and bots/knowledge_revisions cycle,
plus Starlette TestClient deprecation. These were not suppressed.

Initial attempt `/var/tmp/saas-r19-rahbhmJ4` failed setup for all 41 cases because
fixture psycopg.connect requires a plain postgresql:// URL, not the SQLAlchemy
+psycopg spelling. The harness was corrected to the documented query-free URL
and private PGHOST; no tests passed in that initial attempt.

```text
wsl -d Ubuntu -u root -- /var/tmp/saas-closeout-tools/venv/bin/python '/mnt/d/Projects/Work Projects/The Osiris Labs/ManyOsirisChat/.closeout-worktrees/batch-c/.r19-validation/ci_static.py'
```

Exit 0: YAML parsed with yaml.BaseLoader, manual-only events asserted, bash -n
and file/npm script references checked for 4 Many and 14 SaaS run blocks.
S10 absent assertion passed. The CI run blocks themselves were NOT executed.

```text
python -m unittest discover -s scripts -p test_closeout_deploy_readiness.py -k release_chain -v
```

1 passed in 0.017 s, exit 0. C3 still correctly requires single head 0031,
0030 and 0022 ancestry. No new migration means no head-reference change.

```text
wsl -d Ubuntu -u root -- /var/tmp/saas-closeout-tools/venv/bin/ruff check --fix apps/api/tests/test_r19_index_migration.py
wsl -d Ubuntu -u root -- /var/tmp/saas-closeout-tools/venv/bin/ruff format --check apps/api/tests/test_r19_index_migration.py
wsl -d Ubuntu -u root -- /var/tmp/saas-closeout-tools/venv/bin/ruff check apps/api/tests/test_r19_index_migration.py
```

Final lint/format exit 0. An earlier check found unsorted imports; Ruff fixed
those imports only after formatting. Test behavior was unchanged.
`git diff --check -- apps/api/tests/test_r19_index_migration.py` passed.

## Explicit commit files and limits

- apps/api/tests/test_r19_index_migration.py
- implementation/R19-VERIFICATION.md
- PROGRESS.md (this ticket entry only)

No generated output, applied migration or application service code is committed.
Private logs/snapshots/harnesses remain untracked evidence. No full API/frontend/
Playwright suite or hosted CI was run; these remain UNVERIFIED. No push, merge,
deploy, live/authenticated/paid service call or production database operation.
The external plan copy was updated only under the owner's explicit one-file
exception; its bytes match Many's canonical plan. It is outside batch-c and is
not committed by modifying another checkout's branch.

## Full-testing follow-up — 2026-10-29

Full API baseline 86c992d includes 18 contacts-export safety passes, contact
tenant-isolation pass and channel/health/schema passes. Its migration-index
test failed solely on the old saas-r19 directory prefix. New explicit test-mode,
private-socket, matching port, loopback host and disposable-name guards remove
that session dependency; actual 0029/0030 roundtrip and head drift pass.
Final strict typing also passes (app 128 / configured full 289 files).
Sole head remains 0031; three fresh migration rehearsals and checks pass.
Current rebuild prompt has no S10 reference (new source assertion passes).

Final complete normal Playwright: 176/176 at 88599d7, D1 MET. This does not
verify hosted CI, runtime deployed rebuild, live Meta or real Many round trip.
Full API 1208-pass/8-failure baseline and all passing affected fixes are reported
separately, with no second complete green API claim. See
../saas-full-test-evidence/README.md, logs/JUnit and source manifests.
No production code/migration change, skip/xfail, push, merge, deploy or live call.