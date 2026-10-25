# Rules for this repository (binding)

- You work ONLY on branch `feature/saas-delegation`. Do not create or switch branches. You may push this branch to origin; never push `main`, never force-push, no tags, no merges, no PR merge.
- Never open, print, copy or commit `popeye access token.txt` or any `.env`/token/secret. If you notice a real secret anywhere, report it; do not act on it.
- Tests: `backend/tests/conftest.py` runs `Base.metadata.drop_all()` at the end of the session against `TEST_DATABASE_URL or DATABASE_URL`. Use a disposable local Postgres started inside the session, set `APP_ENV=test` and `TEST_DATABASE_URL` explicitly on every test command, and print the URL (host/db only) before running. If you cannot, STOP. No real Meta or OpenAI calls.
- Instagram is live. Do not refactor existing handlers; add one early delegation branch per platform that calls a shared helper. Any other change to Instagram dispatch/send code needs the owner's confirmation first: STOP and ask.
- `saas_delegation_enabled` defaults to false. With it off, behaviour must be exactly as today (prove it with tests).
- Migrations reversible, chained on the real head (`alembic heads`; the last seen was `0022_whatsapp_opt_in`; there is no 0016).
- Never fabricate results. Report exact commands and outcomes. If the contract is unclear or contradicts the code, STOP and ask.
- One ticket per turn (see docs/saas-delegation/TASK.md). After each, report in five lines and wait for "continue".

## Cloud session notes
PostgreSQL 16 and Redis 7 are installed but not running: `service postgresql start`, `service redis-server start`. Create a throwaway database (for example `createdb many_test`) and use that for TEST_DATABASE_URL. Python 3.11 (see backend/Dockerfile).
