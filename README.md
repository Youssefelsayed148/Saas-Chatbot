# Website Chatbot SaaS

A new standalone application. This ticket provides the web/API toolchain and local PostgreSQL/pgvector infrastructure. Business functionality is not implemented yet.

Read [README_START_HERE.md](README_START_HERE.md) for the V2 handoff and [docs/LOCAL-DEVELOPMENT.md](docs/LOCAL-DEVELOPMENT.md) for commands, configuration and troubleshooting. The existing handoff and historical references are preserved.

## Structure

```text
apps/web/                  Next.js App Router, TypeScript, browser smoke test
apps/api/app/api/          Health/readiness routes
apps/api/app/core/         Environment configuration
apps/api/app/db/           Read-only database readiness probe
apps/api/tests/            Isolated pytest tests
apps/api/requirements*.lock Pinned runtime and development dependencies
infra/compose.yaml         Local PostgreSQL/pgvector, API and web
.github/workflows/ci.yml    Separate frontend/backend validation jobs
docs/, implementation/     V2 specifications and ticket evidence
reference/original/        Historical documents, read-only references
```

## Start locally

Prerequisites: Node 24, Python 3.12, Docker Desktop with Linux containers.

1. Copy `.env.example` to `.env` if absent and replace the local password. Keep the password URL-safe and update `DATABASE_URL` to match. Never commit `.env`.
2. Run `docker compose --env-file .env -f infra/compose.yaml up --build -d --wait`.
3. Visit http://127.0.0.1:3000 and http://127.0.0.1:8000/health. `/ready` returns 200 only when the configured database responds.
4. Stop with `docker compose --env-file .env -f infra/compose.yaml down`. This preserves the local database volume; do not add `--volumes` without explicit authorization.

Alternatively run web/API on the host with the database in Compose, as documented in the local-development guide.

CI is configured; a hosted GitHub Actions run requires a separately authorized remote push. See PROGRESS.md for actual local execution evidence and remaining issues. P1-02 requires separate approval.
