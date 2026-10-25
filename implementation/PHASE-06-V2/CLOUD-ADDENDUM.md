# Cloud-session addendum (owner-approved for this session only)

You are running in a Claude Code cloud VM (Ubuntu 24.04), not on the owner's Windows machine. Adjust the prompt like this:

1. Ignore every mention of worktrees, `..\SAAS-chats-ai-phase6`, WSL, `git worktree repair`, docker, and port 55462. You are in a normal clone on branch `feature/phase-6-channels`. Work only on this branch. Do not create or switch branches.
2. Approvals that override AGENTS.md for this session: you MAY run `git merge origin/main` into this branch (R-01) and you MAY push `feature/phase-6-channels` to origin after each ticket. You may NOT push or merge into `main`, force-push, tag, or touch other branches. No paid API calls, no deploy.
3. Disposable database: PostgreSQL 16 is installed but not running. Start it (`service postgresql start`), install pgvector and contrib (`apt-get install -y postgresql-16-pgvector postgresql-contrib`; if apt is blocked, STOP and report), create role `test` / password `test` with CREATEDB, and use `TEST_DATABASE_URL=postgresql+psycopg://test:test@127.0.0.1:5432/phase6` (match the driver the repo's tests expect; check docs/LOCAL-DEVELOPMENT.md). Set it per process, never in a file. Never point anything at a non-local database.
4. Python 3.12 is required (`apps/api/pyproject.toml`). Create a venv and install from the lock files; if 3.12 is missing, install it or STOP and report. Node/npm for `apps/web`.
5. Playwright needs browsers. Try `npx playwright install --with-deps chromium`. If the network blocks it, do everything else, mark Playwright as NOT RUN in PROGRESS.md and tell the owner (they will run it locally). Never claim a result you did not get.
6. Two test files (`apps/api/tests/test_channel_events.py`, `test_channel_health.py`) had uncommitted edits on the owner's machine that are NOT in this clone. Ignore that part of R-00; the owner will merge those edits afterwards.
7. Record exact commands and outcomes in PROGRESS.md as AGENTS.md requires, commit small, and after each ticket report in five lines and wait for "continue".
8. `ENVIRONMENT`/keys: no real provider keys exist here; use the stub chat model.
