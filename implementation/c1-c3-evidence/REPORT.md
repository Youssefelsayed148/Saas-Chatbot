# C1 / C3 rebuild readiness - 2026-10-28

Base: SaaS `5fa72f7`, isolated branch `closeout/c1-c3`.
Worktree: `D:/Projects/Work Projects/The Osiris Labs/ManyOsirisChat/.closeout-worktrees/c1-c3`.
No commit, push, merge, Docker invocation, deployment, production DB access,
Meta/OpenAI/SaaS request, generated key, or actual credential/env-file read.
The explicitly authorized `.env.production.example` is a placeholder template.

## Files changed

- `DECISIONS.md`: ADR-007 hosting decided from owner D2; existing VPS, Docker
  Compose, Caddy, rebuild only. No invented storage provider/region decision.
- `.env.production.example`: one empty `CHANNEL_SECRET_ENCRYPTION_KEYS` entry.
- `compose.prod.yaml`: required encryption key passthrough in the shared API
  and worker environment. Discovery: adding the template alone would not fix
  startup because Compose previously omitted the setting.
- `scripts/deploy.sh`: private timestamped pre-deploy dump from the existing
  DB container, independent of the scheduled backup service; fail closed on
  missing running database, status failure, dump failure, empty archive or
  archive-list failure, before build/up. Failed output remains `.partial`.
- `DEPLOY.md`, `docs/16-DEPLOYMENT-AND-OPERATIONS.md`: secure key generation
  without terminal output (documented, NOT executed), preserve deployed keys,
  actual public `DOMAIN` URL, correct events route, worker source registration,
  0022 to 0030 migration/restore rehearsal prerequisites, pause-first rollback
  and older-image/schema compatibility warning.
- `scripts/test_closeout_deploy_readiness.py`: six offline source checks.
- `implementation/c1-c3-evidence/static-tests.log`: exact passing unittest output.

## Tests added

Six source checks: blank template key; required key flow to both services;
worker channel dispatch and health/sweep scheduling; one migration head and
0022 ancestry; backup checks before build/restart; documented event path
matches the actual router. These do not load app settings or dotenv, import
application modules, connect to services, generate keys or access a database.

## Command + outcome

All PowerShell commands below ran in the isolated worktree unless noted.

1. In the original SaaS checkout, `git status --short; git rev-parse --short HEAD;
   git branch --show-current`: clean `feature/phase-6-channels`, `5fa72f7`.
2. `git worktree add -b closeout/c1-c3 'D:/Projects/Work Projects/The Osiris Labs/ManyOsirisChat/.closeout-worktrees/c1-c3' HEAD`
   (sandbox escalation): exit 0. Original checkout not edited.
3. Read AGENTS.md, CLAUDE.md, close-out plan, source contracts; inspected
   DECISIONS/DEPLOY/template/docs16, config/secrets, worker/runner,
   compose.prod.yaml, deploy.sh, Caddyfile, route and migration source.
   One guessed `events_router.py` read/search failed (path absent); corrected
   to `apps/api/app/channels/events.py`, confirming
   `/api/channels/manyosiris/events`. No result inferred from absent path.
4. Initial targeted test command:

   ```powershell
   $env:APP_ENV='test'; $env:TEST_DATABASE_URL='postgresql+psycopg://unused.invalid/many_test_c1_c3'; python -m unittest discover -s scripts -p test_closeout_deploy_readiness.py -v 2>&1 | Tee-Object -FilePath implementation/c1-c3-evidence/static-tests.log
   ```

   Unittest printed 6 tests OK in 0.023 s, but PowerShell treated native stderr
   as a NativeCommandError and the tool aggregate exit was 1. The six-check
   result was repeated once through an explicit subprocess-return-code driver
   to resolve that shell reporting ambiguity (no full suite was run).
5. Exact final test driver:

   ```powershell
   @'
   from pathlib import Path
   import os,subprocess,sys
   os.environ['APP_ENV']='test'
   os.environ['TEST_DATABASE_URL']='postgresql+psycopg://unused.invalid/many_test_c1_c3'
   result=subprocess.run([sys.executable,'-m','unittest','discover','-s','scripts','-p','test_closeout_deploy_readiness.py','-v'],capture_output=True,text=True)
   log=Path('implementation/c1-c3-evidence/static-tests.log')
   log.write_text(result.stdout+result.stderr+'\nUNITTEST_EXIT='+str(result.returncode)+'\n',encoding='utf-8')
   print(log.read_text(encoding='utf-8'))
   sys.exit(result.returncode)
   '@ | python -
   ```

   Exit 0: **6 passed in 0.015 s**, `UNITTEST_EXIT=0`; log retained.
   Explicit test variables are unreachable sentinels only; these static checks
   do not use a database, so no disposable cluster was required or started.
6. `wsl -d Ubuntu -u root -- bash -n '/mnt/d/Projects/Work Projects/The Osiris Labs/ManyOsirisChat/.closeout-worktrees/c1-c3/scripts/deploy.sh'`
   (sandbox escalation): exit 0, no syntax diagnostics. Syntax check only;
   deploy.sh was NEVER executed.
7. `git diff --check`: exit 0. Git emits LF-to-CRLF working-copy warnings,
   with no whitespace errors. After tests, only report/prose was corrected
   (ASCII migration arrows/date separator and documented temporary-key path);
   no application/Compose/shell/test logic changed.

## Open questions

- Actual deployed `alembic current`, source/image SHA, existing encryption key
  provisioning, public hostname and runtime job/worker health need operator
  evidence. No values were read or inferred.
- ADR-007's original broad storage/retention/residency heading is preserved;
  D2 decides hosting only. No new region/storage decision is asserted.

## Risks / UNVERIFIED

- Compose interpolation, container startup and required-key behavior were
  source-checked only; `docker compose config` was NOT run because no actual
  deployment environment was authorized/loaded. Runtime remains UNVERIFIED.
- Deploy script failure paths are source-checked plus Bash syntax-checked,
  not exercised against Docker. Dump/list integrity is not a restore drill.
  Backups, restore and 0022 to 0030 rehearsal remain UNVERIFIED here.
- Rebuild now requires the existing database container running. The bootstrap
  runbook explicitly starts the database first; a stopped existing database
  cannot be mistaken for a new install and migrated without backup.
- No tenant query or schema implementation changed; A/B tests and API/full
  Playwright suites were not needed for this targeted source-only work and
  remain for lead's final integrated validation. No full suite was run.
- Main merge, rebuild, migration/deployment and live canary remain separate
  owner-approved operations; C1/C3 does not satisfy those gates.
