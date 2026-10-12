# Local development ? P1-01

## Environment and dependencies

Use Node 24/npm, Python 3.12 and Docker Desktop Linux containers. Direct dependency versions are exact in package.json and pyproject.toml; transitive versions are recorded in package-lock.json and the two Python requirements lockfiles. Install from locks in CI and local development. When upgrading Python dependencies, deliberately update both direct pins and transitive lockfiles, then validate Windows and Linux. Python lockfiles contain version pins, not wheel hashes.

`.env.example` contains development placeholders only. Copy it to `.env` if absent. Set POSTGRES_DB, POSTGRES_USER and a new URL-safe POSTGRES_PASSWORD, then update DATABASE_URL to the same credentials. Generated local `.env` is ignored by Git and Docker build context. Never reuse these credentials outside local development.

The host database defaults to `127.0.0.1:55432`, avoiding the Windows reserved/occupied 5432 port. Optional POSTGRES_PORT changes the published port; update the host DATABASE_URL to match. Containers always connect to `db:5432`. API and web publish only on loopback, at 8000 and 3000. All three are local development services.

## Host development (PowerShell, repository root)

```powershell
npm.cmd ci
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r apps/api/requirements-dev.lock
# Start the database; no application schema or vector extension is created yet.
docker compose --env-file .env -f infra/compose.yaml up -d db --wait
# Terminal 1: API reads the root .env and reloads application code.
.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir apps/api --host 127.0.0.1 --port 8000 --reload
# Terminal 2:
npm.cmd run dev
```

On Linux/macOS replace `.venv/Scripts/python.exe` with `.venv/bin/python` and `npm.cmd` with `npm`. Run commands from the root unless specified. For backend tools, change directory to apps/api so the pyproject configuration and package imports are resolved without an editable install:

```powershell
cd apps/api
../../.venv/Scripts/python.exe -m ruff check .
../../.venv/Scripts/python.exe -m ruff format --check .
../../.venv/Scripts/python.exe -m mypy
../../.venv/Scripts/python.exe -m pytest
```

Tests override application settings and mock database connections. They never execute real SQL against an environment-supplied database. No destructive fixtures or migrations are included.

## Frontend validation (repository root)

```powershell
npm.cmd run format:check
npm.cmd run lint
npm.cmd run typecheck
npx.cmd playwright install chromium
npm.cmd test
```

Playwright builds the frontend, starts a production server on loopback port 3100, checks the rendered page and browser errors, then stops that server. It refuses to reuse an existing server. CI installs Chromium with Linux dependencies. `npm run build` and `npm run start --workspace apps/web` are also available separately. No external font download is required by the page. Host builds use normal Next.js output; the Docker builder sets NEXT_STANDALONE=1 and copies only standalone server dependencies and static assets into the non-root runtime image.

## Linux backend checks on Windows

If Windows Application Control blocks mypy's compiled extension, use the supported Linux validation image; do not disable system security policy:

```powershell
docker build --target checks -f apps/api/Dockerfile -t saas-chats-ai-api-checks .
docker run --rm saas-chats-ai-api-checks
```

This executes Ruff lint, Ruff format check, strict mypy and pytest from the pinned development dependencies. It receives no developer environment or database credentials.

## Full local container stack

```powershell
docker compose --env-file .env -f infra/compose.yaml config --quiet
docker compose --env-file .env -f infra/compose.yaml up --build -d --wait
docker compose --env-file .env -f infra/compose.yaml ps
python scripts/smoke_local.py
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/ready
Invoke-WebRequest http://127.0.0.1:3000
# Stop only this development stack; keep its volume.
docker compose --env-file .env -f infra/compose.yaml down
```

Do not print `docker compose config` without `--quiet`: resolved configuration contains the local password. Readiness executes only SELECT 1, with a bounded connection timeout; missing/unreachable databases produce 503 and a safe response without credentials or exception details. Liveness stays available independently. The pgvector image includes the extension files; CREATE EXTENSION and application migrations belong to later approved tickets.

## Security and ticket boundaries

API/web containers run as non-root users. No public deployment, auth, tenant schema, bot CRUD, RAG, ingestion, widget, billing or integration is included. No cross-origin API exposure is needed for this foundation, so CORS is not enabled. PostgreSQL's bootstrap development role is for this isolated local stack only; application roles/least privilege are to be designed before production.

The npm development lint chain currently includes GHSA-vfj7-8cjw-p6xm (braces; no patched release at review time): https://github.com/advisories/GHSA-vfj7-8cjw-p6xm. The affected patterns are repository-controlled lint configuration and are not accepted from application requests. Track this until upstream remediation; do not apply forced framework downgrades. Runtime audit results and actual command evidence are recorded in PROGRESS.md.

A GitHub remote, push, merge and deployment remain unapproved. A generated workflow is not evidence that hosted CI ran.
