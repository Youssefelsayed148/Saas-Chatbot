# SaaS full-test evidence — 2026-10-29

D1 is MET: the complete normal Playwright run passed 176/176, no failures,
errors or skips, at 88599d7a9034f670dc0ee0fead89fa828feb69cc.
No merge, push, deployment, live send, authenticated external request or paid API.

## Source and isolation

- Worktree: ManyOsirisChat/.closeout-worktrees/batch-c, branch closeout/batch-c.
- Initial HEAD: 86c992dafee0caf36f4b26e861e6a89bf1de17f1. Tracked tree clean;
  pre-existing untracked .r19-validation/ preserved and excluded.
- implementation/CLOSEOUT-PLAN.md was absent. This session creates its worktree
  copy and synchronizes it with Many's canonical plan. Neither prohibited
  original SaaS checkout was modified.
- Fresh source-only snapshots: 595 allowlisted files each. source-sha.txt,
  source-files.txt and snapshot-manifest.json record provenance. Only explicit
  placeholder templates and synthetic fixtures included; actual env/credential
  files, token files, backups and dumps were never read/copied/hashed.
- Each run starts a new private Postgres cluster under /var/tmp/saas-full-*,
  with a private Unix socket and loopback listener inside an unshare --net
  namespace containing only lo. No system/Windows/production DB used.
- env -i launch; APP_ENV=test, ENVIRONMENT=test, explicit TEST_DATABASE_URL and
  DATABASE_URL, CHAT_STUB_MODEL=1, EMBEDDING_TEST_STUB=1,
  WORKER_ALLOW_ONLY_TEST_DB=1; empty provider keys. current_database() and the
  fixture's explicit URL selection asserted before suites.
- Query-free disposable URLs avoid Alembic ConfigParser percent-encoding issues.
  All schema creation/transitions use Alembic. No create_all or stamp.
- Python 3.12.16, Postgres 18.6, Node 24.22.1, npm 11.19.1, Next 16.4.3.
  Cached dependencies' lock SHA256 equals this source:
  65daab584e0b81a87f9be01bce924fd8b31b0c47997965f1b44bf8e1b6d91895.
- API/web ports: initial 8187/3287; affected browser 8188/3288; final 8189/3289.
  API_PROXY_TARGET and PLATFORM_GUARD_ORIGIN match each API port. E2E_PYTHON and
  PLAYWRIGHT_BROWSERS_PATH use the handoff's cached toolchain.
- All clusters stopped by their own traps. Final process audit found no
  python/node/cp test processes. No source snapshots, dependencies, .next,
  test storage, traces, browser reports or database files are committed here.

## Exact results

commands.log and each child directory's commands.log record expanded commands,
cwd and explicit test DB; results.tsv records exit code and whole-second wall
duration. Logs/JUnit retain finer test durations and all warnings. counts.json
summarizes every JUnit, including invalid/incomplete attempts.

| Check | Outcome |
|---|---|
| Full API at 86c992d | 1,208 passed, 8 failed, 0 errors/skips; exit 1; pytest 1330.93s, JUnit 1330.916s, wall 1333s |
| Affected API, latest distinct cases | 78 passed in 32.08s + 16 passed in 5.08s = 94 distinct; zero failures/errors/skips |
| Earlier affected API | 48 passed in 10.85s (subset of the 78); schema typing follow-up 3 passed in 0.44s (also a subset) |
| Ruff final | exit 0 |
| Ruff format final | 304 files formatted; exit 0 |
| mypy app final | 128 files clean; exit 0 |
| Configured full mypy final | 289 files clean; exit 0 |
| Repository unittest final | 23 passed, 0.218s; exit 0 (initial stale Compose assertion: 1 failure among 22) |
| Contract copies | exit 0; both manifests' 6 LF-normalized hashes and 3 cross-repository pairs match |
| Migrations | 3 fresh DB rehearsals pass; all three alembic checks clean; exit 0 |
| Frontend typecheck / lint | exit 0 / 0, wall 6s / 8s |
| Node unit tests | 24 passed, 0 failed/cancelled/skipped/todo; 274.397106ms; exit 0 |
| Production build | exit 0, wall 11s |
| Public widget asset guard | exit 0 |
| Initial full Playwright | 174 passed, 2 failed (JUnit errors=2), 0 skipped; exit 1, JUnit 203.734884s |
| Affected widget-domain spec | 2 passed, no failures/errors/skips; exit 0, JUnit 23.249229s; normal setup/build/teardown |
| Final complete Playwright | 176 passed, no failures/errors/skips; exit 0, JUnit 224.45107s, wall 225s |

No second complete API pass is claimed: every failed case has a passing affected
rerun, and production code is byte-identical to the full API snapshot.
The later change is one Playwright fixture line. Final full Playwright was
repeated because the initial full run failed and D1 requires a green full run.

## Every baseline failure and its resolution

1. Four retrieval diagnostic tests implicitly assumed a 0.50 OpenAI cosine
   floor, while docs/14's owner-approved default is 0.30. Pin their synthetic
   diagnostic cases explicitly to 0.50; retain assertions and the default test.
2. Inbound-ordering test passed STUB=True while asserting the no-model busy
   reply cap. Explicitly supply no model for that scenario; preserve one busy
   reply, receipt ordering, idempotence and no failed-job assertions.
3. R19 migration test required an earlier session's saas-r19 scratch prefix.
   Replace it with test-mode, existing private socket, loopback host, matching
   port and disposable-name guards. Actual index round trip/drift checks pass.
4. Real production Settings test inherited the suite's test stubs. Explicitly
   turn those off only in the production-settings fixture; production guard
   expectations remain intact.
5. Tenant deletion compared Cairo wall times across the DST boundary. Compare
   UTC instants instead; retain the exact 48-hour grace-period assertion.
6. Compose source test omitted the existing optional staff service. Recognize
   it and add checks for password-optional, migration-gated staff bootstrap.
7. Initial full mypy had 13 pre-existing test-typing errors in 6 files, separate
   from runtime failures. Repair defining-module references, typed transient
   ChannelConnection, SQLAlchemy metadata access, optional/payload type checks,
   and Source.sha256 (the fixture assigned nonexistent Source.content_hash).
   Final full mypy is clean; no type ignores or assertion removals added.
8. Both Playwright failures used hard-coded port 3100 in widget-domain.spec.ts.
   Follow E2E_WEB_PORT with the same 3100 default. Preserve CSP, denied-host,
   server-side 403, allowed-host answering and cross-host staff-session checks.

Fix commits: ce1532adc4f2a2066bf28a270bf5a9c13aa51966 (explicit 12-file test
list) and 88599d7a9034f670dc0ee0fead89fa828feb69cc (one Playwright file).
No production source or migration changed; no skip/xfail added.

## Required focused confirmations

- A16 receiver: all 23 test_channel_erasure cases pass in the full API run and
  affected validation, including tenant/connection scope, merged contacts,
  pending sends, rollback/retry, replay fences and race interleavings.
- Tenant A/B route matrix: 7 cases pass; contacts/export isolation remains
  intact. Full API channel group: 216 cases, initially one stale ordering
  fixture failure, subsequently all 6 ingest-hardening cases pass.
- CSV phone/formula guard: all 18 contacts export safety cases pass; contact
  tenant scope case also passes. No phone-guard rewrite.
- Health-poll index: actual 0029 -> 0030 -> 0029 -> head and clean drift pass.
- Single source head: 0031_contact_erasure. Empty-to-head, 0022-to-head, and
  head -> 0022 -> base -> head on separate empty disposable DBs all pass.
  Downgrades contained no channel data or erasure fences; data-sensitive
  0023/0024 limits and 0031 privacy limits were not bypassed. Operational
  rollback remains pause/forward fix.
- Alembic emits existing vector-introspection and bots/knowledge_revisions
  cycle warnings, then reports no new upgrade operations. No warning hidden.
- Current rebuild prompt has no S10 reference; no undefined requirement invented.
- All 176 Playwright cases run with unchanged normal config, production build,
  global setup/teardown, retries=0 and no server reuse. No temporary config.
- Post-result AdminShutdown traces in browser logs are harness teardown ordering:
  global teardown signals owned API/worker, then cluster trap stops Postgres
  before their last rollback finishes. They occur after test results; final
  JUnit and npm exit are zero, and process/cluster cleanup was verified.

## Harness attempts and limits

The initial preflight failed because initdb under an empty environment selected
SQL_ASCII (psycopg returned bytes). It ran no tests; UTF8/C.UTF-8 fixed it.
The original BOM on the first shell line was also removed.

attempt1 is INVALID: an overbroad filename exclusion omitted source secrets.py.
It produced 67 collection errors. Its other outputs are retained, not counted
as application verdicts. attempt2 is INCOMPLETE/INVALID: source asset/JSONL
omissions were found and the run was interrupted; its partial JUnit records
40 passes/21 failures among 61 cases, not a full suite. Reliable whole-attempt
duration is unavailable; logs and partial JUnit are preserved.

The complete root run used the corrected 595-file allowlist. Dependency copy
from the mounted cached worktree took several minutes; a CR at the destination
created node_modules<CR>. Only the owned shell was STOP/CONT paused after the
copy; fix-cache-path.py renamed that scratch directory before any frontend check.
No test config or application source was changed. Later runs copy this complete
Linux dependency cache into new snapshots. Both cache/source lock files match.

A supplemental namespace assertion initially used /sys/class/net, whose existing
sysfs mount reflected the outer namespace. No checks ran after that preflight
failure. It was corrected to ip -j link show in the actual namespace; only lo
was asserted. One evidence-write approval review timed out before execution;
the permitted retry succeeded. No user approval or safety control was bypassed.

## Commands and evidence entry points

Launch pattern (each run's recorded run.sh supplies its unique cluster/ports):

    wsl -d Ubuntu -u root -- env -i HOME=/root LANG=C.UTF-8 PATH=/usr/sbin:/usr/bin:/sbin:/bin unshare --net bash <evidence-directory>/run.sh

Main API commands (cwd fresh snapshot/apps/api), all through run() with
APP_ENV=test ENVIRONMENT=test TEST_DATABASE_URL explicitly set:

    python -m pytest tests -q --junitxml=<evidence>/saas-api.xml
    python -m ruff check .
    python -m ruff format --check .
    python -m mypy app
    python -m mypy

Root: python -m unittest discover -s scripts -p 'test_*.py' -v;
python scripts/check_contract_copies.py; python <evidence>/hash-check.py.
Migrations: env PYTHONPATH=. python <evidence>/migrations.py; exact Alembic
calls/revisions are in that harness and migrations.log.

Web: npm run typecheck; npm run lint; node --test
tests/channel-delivery.unit.mjs tests/insights.unit.mjs; npm run build;
npm test -- --reporter=line,junit. Final complete run command is identical.
Targeted browser repair uses npm test -- tests/widget-domain.spec.ts
--reporter=line,junit, with the same normal config/build/setup/teardown.

Final check logs: final-checks/. Latest behavioral API logs: affected-final/
and remaining-api/. Final D1: playwright-full-final/playwright.xml and
playwright.log. Full original API: saas-api.xml and api.log.
counts.json retains all report counts without double-counting overlapping runs.

R4 local source readiness verified; runtime rebuild UNVERIFIED. R18 local test
repairs verified. R19 local SaaS verification verified; hosted CI UNVERIFIED.
R5 main merge remains OPEN despite D1 being met. Deployed rebuild, live Meta,
real Many-to-SaaS round trip, staging canary and owner release approvals remain
UNVERIFIED/unperformed. No Many-side full-suite claim is made by this session.
