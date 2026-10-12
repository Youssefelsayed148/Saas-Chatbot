# P1-02 — Schema + Auth

Date: 2026-10-12. Status: IMPLEMENTED AND LOCALLY VERIFIED (Windows host + Linux container). Awaiting owner acceptance as part of the P1 gate.

Branch: `feat/p1-01-foundation` (local commits only; no push/merge/deploy).

## Built

### Database (SQLAlchemy 2 + Alembic, one history)
- `apps/api/alembic.ini`, `apps/api/alembic/{env.py,script.py.mako,versions/0001_initial.py}`. Revision `0001_initial` creates the whole P1 schema in one migration with `CREATE EXTENSION IF NOT EXISTS citext`; downgrade drops tables and the extension.
- Tables (`app/db/models/core.py`, docs/04):
  - `users(id UUID PK, email CITEXT UNIQUE, password_hash, is_platform_staff default false, created_at)`
  - `sessions(id UUID PK, token_hash UNIQUE, user_id FK→users CASCADE, expires_at, revoked_at, created_at, index user_id)`
  - `tenants(id, name, slug UNIQUE, status 'active'|'archived' CHECK, created_at)`
  - `memberships(tenant_id, user_id FKs, role CHECK owner/admin/editor/viewer, status CHECK, UNIQUE(tenant_id,user_id), indexes on both)`
  - `bots(id, tenant_id FK, name, status CHECK draft/active/paused/archived, config JSONB default {}, created_at, updated_at, UNIQUE(tenant_id,id) anchor index for later composite FKs, index tenant_id)`
  - `invitations(id, tenant_id FK, email CITEXT, role CHECK, token_hash UNIQUE, expires_at, accepted_at, revoked_at, created_by FK→users RESTRICT, created_at, indexes tenant_id+email)`
  - `audit_events(id, tenant_id FK NULL, actor_user_id FK NULL, action, target_type, target_id, metadata_json, created_at, index (tenant_id, created_at))`
- Alembic only — no `create_all`.

### Auth module (ADR-004, docs/05/06)
- `POST /api/v1/auth/register` (201, sets session+CSRF cookies), `POST /api/v1/auth/login` (200, sets session+CSRF cookies), `POST /api/v1/auth/logout` (CSRF-checked, revokes session), `GET /api/v1/auth/me` (user + memberships, 401 otherwise).
- Argon2id via `argon2-cffi` (Argon2id defaults); passwords never stored or echoed.
- Server-side sessions: random 256-bit token in an HttpOnly SameSite=Lax cookie; only SHA-256 hash stored. Invalid/expired/revoked → 401 `SESSION_INVALID`; no cookie → 401 `UNAUTHENTICATED`.
- Rotation on login: each login issues a fresh session and revokes the presented one; the old cookie value no longer authenticates.
- CSRF: double-submit cookie (`chatbot_csrf`, not HttpOnly) + `X-CSRF-Token` header compared with constant-time compare on cookie-authenticated writes; missing token → 403 `CSRF_MISSING`, wrong → 403 `CSRF_INVALID` (fails closed).
- Login rate limiting: in-process fixed-window limiter per client IP (default 10 attempts / 300 s from settings) → 429 `RATE_LIMITED`.
- Stable error contract docs/05: middleware assigns a request id, every error is `{error:{code,message,request_id}}`; `X-Request-ID` echoed. Validation errors are 422 `VALIDATION_ERROR` and never echo input back.
- CORS: narrow allowlist (`http://localhost:3000`, `http://127.0.0.1:3000`), credentials allowed, allow-listed headers incl. `X-CSRF-Token`.

### Test infrastructure
- `apps/api/tests/conftest.py`: `_test`-guard (refuses DB names not ending in `_test`), creates the disposable DB (`chatbot_dev_test`, `chatbot_dev_migration_test`) from `TEST_DATABASE_URL` or `DATABASE_URL`/repo `.env`, runs Alembic migrations (never `create_all`), per-test table truncation, cookie-safe settings (Secure off for the plain-HTTP test client).
- Unset `TEST_DATABASE_URL` outside a reachable dev environment fails with a clear message; tests do not fabricate.

## Deviations / micro-decisions (recorded, not blocking)
1. Ticket text said `sessions(id hashed token …)` while also requiring UUID PKs. Implemented UUID PK + unique `token_hash` column — satisfies both rules and keeps guest-friendly FK semantics. Raw tokens are never stored.
2. Password minimum length 8 (not specified anywhere in docs; recorded as the MVP default).
3. `EMAIL_TAKEN` (409) reveals address existence at registration — accepted per docs/05 409 contract; no email verification in MVP (ADR-004).
4. Login limiter is process-local (single uvicorn process in P1). DB-backed counters arrive with the jobs/abuse-limit scope of later phases (docs/14 §7 uses Postgres counters for the public widget API).
5. `memberships.status` defaults to `active`; removal is a row delete (P1-03), `revoked` reserved.

## Evidence — exact commands and results

Windows host (venv Python 3.12.10), from `apps/api` unless noted:

| Command | Result |
|---|---|
| `.venv/Scripts/python.exe -m pip install SQLAlchemy==2.0.54 alembic==1.20.0 argon2-cffi==25.1.0 email-validator==2.3.0` | Installed; also pulled greenlet, Mako/MarkupSafe, cffi bindings, dnspython |
| `ruff check . --fix` then `ruff check .` | "All checks passed!" |
| `ruff format .` then `ruff format --check .` | "30 files already formatted" |
| `mypy` (strict; files app, tests, alembic) | "Success: no issues found in 30 source files" |
| `python -m pytest` | "40 passed, 1 warning in 3.32s" (tests: migrations up/down, constraints incl. citext case-insensitive duplicate emails, sessions valid/invalid/expired/revoked, CSRF missing/wrong, wrong password, duplicate email, rotation, rate limit, stable error format + header, no-secret leakage in errors, `_test`-guard unit tests, regression-tested /health & /ready) |
| `python -m alembic upgrade head` (dev DB `chatbot_dev` with DATABASE_URL from `.env`) | "Running upgrade -> 0001_initial …"; `alembic current` = `0001_initial (head)` |
| Live API smoke (uvicorn 127.0.0.1:8010 against dev DB): `curl.exe` register → login (with CSRF header) → me → logout → me | 201 → 200 → 200 → 200 → 401 `SESSION_INVALID`; `Set-Cookie: chatbot_session=…; HttpOnly; SameSite=lax; Secure` observed on the real response |
| `docker build --quiet --target checks -f apps/api/Dockerfile -t saas-chats-ai-api-checks .` | Built |
| `docker run --rm --network saas-chats-ai-dev_default -e TEST_DATABASE_URL=…@db:5432/chatbot_dev saas-chats-ai-api-checks` | ruff+format+mypy green; "40 passed, 1 warning" (Linux container) |
| `docker build --quiet --target runtime …` + `import app.main` | Runtime imports cleanly; no alembic in runtime path needed in P1 |

The one warning is the known Starlette↔httpx TestClient deprecation tracked since P1-01.

## Files
Created: `apps/api/alembic.ini`, `apps/api/alembic/{env.py,script.py.mako}`, `apps/api/alembic/versions/0001_initial.py`, `apps/api/app/auth/{__init__,cookies,errors-handover,ratelimit,schemas,security,service,router}.py` (modules: security, cookies, ratelimit, schemas, service, router), `apps/api/app/core/errors.py`, `apps/api/app/db/{__init__,session,base}.py`, `apps/api/app/db/models/{__init__,core,types}.py`, `apps/api/tests/{__init__,conftest,test_migrations,test_models_constraints,test_auth,test_database_guard}.py`, this report.
Modified: `app/core/config.py` (session/CSRF/rate-limit settings), `app/main.py` (middleware, CORS, routers, error handlers), `apps/api/requirements.lock`, `apps/api/requirements-dev.lock`, `apps/api/pyproject.toml`, `apps/api/Dockerfile` (checks stage ships alembic), `.github/workflows/ci.yml` (Postgres service + `TEST_DATABASE_URL`), `docs/LOCAL-DEVELOPMENT.md`, checklist + PROGRESS.md.

## Limitations / open risks
1. GitHub-hosted CI still not run (no push authorized); config updated so CI would validate against a disposable `_test` DB with services.postgres.
2. Login rate limiter is in-process; a multi-process deployment needs the planned Postgres-backed counters (later phase scope).
3. Hosted CI/`docker run` variant of the checks container exercises `mypy`+ruff+tests against a disposable DB created inside Postgres `chatbot_dev` user (superuser of its instance) — production least-privilege roles remain open (P1-01 note).
4. Secure cookie flag asserted via unit test (production settings) and real response header observed over HTTPS in later phase; local HTTP smoke necessarily sets Secure (documented in the local-dev guide).
5. Password reset/account recovery not in MVP (ADR-004).

## Status
P1-02 done with local evidence. Next: P1-03 (tenants, roles, bots, team management).
