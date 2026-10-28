# New-session prompt: integrated close-out testing

Copy the prompt below into a new session. This file is a testing handoff, not a
claim that the full suites have passed. Final branch SHAs and implementation
review results are recorded in the close-out entry at the end of PROGRESS.md.

---

You are the lead for the **testing stage** of ManyOsirisChat + the SaaS chatbot
close-out. The previous owner asked the implementation session to finish the
remaining three fixes, then defer full testing to this new session.

Read first, in order:

1. Many root `CLAUDE.md` and SaaS `AGENTS.md` / `CLAUDE.md`.
2. Many `docs/saas-delegation/CLOSEOUT-PLAN.md` and this handoff.
3. The latest close-out entries at the tail of Many
   `docs/saas-delegation/PROGRESS.md` and the integrated SaaS `PROGRESS.md`.
4. The worker reports and independent review records linked from those entries.
5. The adopted A16 contract and `CONTRACT.sha256` in both repos.

Owner authorizations carried forward:

- Use the **existing isolated closeout worktrees/branches** below. This overrides
  the older root-branch-only and one-ticket-per-turn instructions. Do not switch
  either original checkout or merge into main.
- Run the full suites once on the final integrated source. If something fails,
  investigate and fix it, rerun affected checks, and broaden only when the changes
  justify it. Do not repeatedly run whole suites without a reason.
- No push, main merge, deployment, live send, authenticated Meta/OpenAI/SaaS call,
  paid API, cloud resource or real database operation. Only new disposable test
  databases. Public Meta documentation lookup was approved, but it is not needed
  to begin this testing stage.
- D5 is deliberately OPEN: leave the Instagram unsupported-message commit
  `59d3442` unchanged and report it. Do not ask for its decision again during
  independent testing.
- A16 was approved and adopted. Shared hashed dedupe keys and their migration
  were explicitly approved; no Instagram dispatch/send-handler refactor was
  authorized.

## Integrated source to test

Many repository:
`D:\Projects\Work Projects\The Osiris Labs\ManyOsirisChat`

- Use `.closeout-worktrees/batch-b`, branch `closeout/batch-b`.
- `closeout/batch-a` preserves the earlier reviewed Batch A integration.
- The original `feature/saas-delegation` checkout contains lead documentation
  and contract/evidence commits; it is **not** the integrated application tree.

SaaS repository:
`D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai-phase6`

- Use the worktree physically at
  `ManyOsirisChat\.closeout-worktrees\batch-c`, branch `closeout/batch-c`.
- Original `feature/phase-6-channels` remains unmerged to main.
- The other plan copy is at
  `D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai\implementation\CLOSEOUT-PLAN.md`.
  It must remain byte-identical to Many's canonical plan. The phase-6 original
  checkout did not originally contain that plan file.

Verify git branch, HEAD and status in both integrated worktrees before running.
Use the final SHAs in the latest PROGRESS entry. Preserve any unexpected edits;
do not reset, clean, or delete worktrees.

Application integration bases (only lead documentation/source-check updates follow):
Many `33bde97`, SaaS `1ee703e`. Migration heads: Many
`0029_hash_processed_event_keys`, SaaS `0031_contact_erasure`.
See `FINAL-IMPLEMENTATION-REVIEW.md` for the independent review and exact limits.

## Test environment and safety

Use Ubuntu WSL and **new private PostgreSQL clusters** started in this session;
never the Windows PostgreSQL service, system cluster, Docker deployment or a
database resolved from an existing env file. Give independent workers separate
database names and Redis namespaces. Stop only processes started by this run.

Cached tooling from implementation:

- Many Python 3.11:
  `/var/tmp/many-t0-20261028/venv/bin/python`.
- SaaS Python 3.12.16 with pinned `requirements-dev.lock`:
  `/var/tmp/saas-closeout-tools/venv/bin/python`.
- Node 24.22.1:
  `/var/tmp/saas-closeout-tools/node-v24.22.1-linux-x64/bin`.
- PostgreSQL 18 binaries and pgvector 0.8.1 extension files are installed.
- Linux Playwright Chromium 1248 was installed by the C4/C5 worker. Set
  `PLAYWRIGHT_BROWSERS_PATH=/var/tmp/saas-closeout-tools/playwright`.

Inspect the retained worker harnesses for setup patterns, but **do not rerun an
old snapshot and claim it tests the integrated branch**. Make a fresh source-only
snapshot from the verified integrated worktree, including current uncommitted
changes only if explicitly reviewed and recorded. Keep the source SHA/file list.
Never copy/read/hash `popeye access token.txt`, actual `.env`/credential files,
backups or dumps. Do not use an unrestricted whole-repo archive that could copy the
forbidden token file. Explicit placeholder templates may be copied only if needed
by source checks. Include synthetic test fixtures and the SaaS root marker
`README_START_HERE.md`, workspace manifests and contract copies.

Run tests inside a network namespace with **loopback only**. Use private Redis
for Many; flush only that instance. API, worker, browser and local frontend for
Playwright must share their isolated namespace. Use dummy test secrets and stub
models; do not print generated keys or inherit provider credentials.

For every test command explicitly set `APP_ENV=test` and `TEST_DATABASE_URL`.
Set SaaS `ENVIRONMENT=test`, `CHAT_STUB_MODEL=1`, `EMBEDDING_TEST_STUB=1`, and
`WORKER_ALLOW_ONLY_TEST_DB=1` where appropriate. Before execution print only the
database **host and name**, assert actual `current_database()`, and verify the
test fixture selects the explicit target. Many conftest drops its schema; its
migration fixtures also need `DATABASE_URL` explicitly pointed to the same
private disposable cluster. Never inherit that variable from the workstation.

SaaS Alembic ConfigParser rejects percent-encoded Unix-socket URL query values.
Use a query-free explicit disposable URL with `PGHOST`, `PGPORT` and `PGUSER`
pointing to the private socket. The retained C2/C4 harnesses demonstrate this.
SaaS fixtures derive additional names ending `_test`; all must remain inside the
new private cluster. Use Alembic only, never create_all/stamp shortcuts.

## Validation to execute once

Use evidence directories dedicated to this session. Capture exact expanded
commands, exit codes, durations, pass/fail/error/skip counts, logs and JUnit.

Many, from the env-free snapshot's `backend` directory:

```sh
APP_ENV=test TEST_DATABASE_URL="$TEST_DATABASE_URL" pytest tests -q --junitxml="$evidence/many-backend.xml"
```

Then from its root, on an empty dedicated disposable DB for canary fixtures:

```sh
APP_ENV=test TEST_DATABASE_URL="$TEST_DATABASE_URL" python -m unittest discover -s scripts -p 'test_*.py' -v
python scripts/check_contract_copies.py
```

Run the dashboard's configured TypeScript and lint checks using cached/locked
dependencies. Disable incremental output or keep generated files out of commits.

SaaS, from the env-free snapshot's `apps/api` directory:

```sh
APP_ENV=test ENVIRONMENT=test TEST_DATABASE_URL="$TEST_DATABASE_URL" python -m pytest tests -q --junitxml="$evidence/saas-api.xml"
python -m ruff check .
python -m ruff format --check .
python -m mypy app
```

Also run configured full mypy if appropriate; report existing test-typing
failures separately and accurately rather than silently narrowing the command.
Run SaaS script/unit checks and both contract-copy/hash checks. Rehearse actual
Alembic empty-to-head and 0022-to-head, downgrade/upgrade and `alembic check` on
new disposable databases. Source heads must be single and match the final
recorded migrations. Do not treat expected data-sensitive 0023/0024 rollback
limitations as permission to bypass them; production rollback is pause/forward
fix, not an unapproved destructive downgrade.

SaaS frontend: run configured typecheck, lint and Node unit tests. Build the
actual integrated source. Set unique E2E API/web ports and `API_PROXY_TARGET`
consistently, with `E2E_PYTHON` pointing to the cached Linux Python 3.12 toolchain.
Then run the **entire Playwright suite once** with its normal global setup and
teardown against the private DB/API/worker. Do not use a temporary config that
skips specs or bypasses production build. No existing server reuse.

```sh
APP_ENV=test ENVIRONMENT=test TEST_DATABASE_URL="$TEST_DATABASE_URL" npm test
```

Keep credentials out of logs/artifacts. Do not commit generated `.next`,
node_modules, test storage, source ZIPs, browser traces or DB files. Retain
sanitized reports/logs/JUnit with exact provenance.

## Interpret results honestly

Targeted implementation runs and independent review are not full-suite passes.
The prior full suites remain UNVERIFIED for the final integrated source until
you execute them. Fix genuine defects and stale fixtures without weakening
authorization, tenant isolation, dedupe, erasure, billing or meaningful asserts.
Do not add skips/xfails merely to obtain green output.

Known non-test release blockers remain: D5; official Graph-version evidence
(A5, official docs returned 429); automatic Meta callback admin/authorization
mapping and full Facebook/WhatsApp admin-account erasure (R1 remains partial);
owner-run Business Verification/Tech Provider/dashboard actions; staging canary;
main merge/rebuild/deployment/submission approvals. Do not mark them complete
because local tests pass. SaaS main merge still requires a genuinely green full
Playwright run and separate owner approval (D1).

Update both PROGRESS files and keep the two existing CLOSEOUT-PLAN copies
identical. Tick backlog items only with evidence. Finish with exact results,
remaining failures/blockers, tested SHAs and evidence links. Do not push, merge
main, deploy, send a live message or publish policies/campaigns.
