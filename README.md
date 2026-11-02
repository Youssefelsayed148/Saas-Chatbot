# Website Chatbot SaaS

A multi-tenant website chatbot: a business adds its data, publishes an AI agent, installs one script tag, and runs conversations through an inbox with human handoff, a light CRM and follow-ups. WhatsApp, Messenger and Instagram arrive through ManyOsirisChat, which owns all Meta connectivity; this repository only implements the signed channel contract (`docs/17`).

Start with [docs/README.md](docs/README.md), the index of every maintained document, and [docs/LOCAL-DEVELOPMENT.md](docs/LOCAL-DEVELOPMENT.md) for commands, configuration and troubleshooting. Current status and verified test results are in [PROGRESS.md](PROGRESS.md); open issues are in [implementation/KNOWN-ISSUES.md](implementation/KNOWN-ISSUES.md).

## Structure

```text
apps/web/                  Next.js App Router dashboard (client workspace and platform console), Playwright tests
apps/api/app/              FastAPI modular monolith: auth, tenants, bots, knowledge, chat, channels, inbox, analytics, platform
apps/api/alembic/          Migrations (sole head 0031_contact_erasure)
apps/api/tests/            pytest suite
packages/widget/           Embeddable website widget (loader and iframe)
compose.yaml               Development db, migrator, API, worker, web and opt-in seed
compose.prod.yaml          Production stack (Caddy HTTPS, db, API, worker, web, backups); see DEPLOY.md
deploy/                    Caddyfile and backup script used by compose.prod.yaml
scripts/                   deploy.sh, contract check, RAG calibration, smoke test and their tests
.github/workflows/ci.yml   Separate frontend/backend validation jobs
docs/                      Specifications 00 to 19, RAG plan, operations drafts; index in docs/README.md
implementation/            Roadmap, checklists, role matrix, manual test, known issues, contract copies
```

## Deploy

Production runs entirely in Docker on a VPS: see [DEPLOY.md](DEPLOY.md) (`.env.production.example`, `scripts/deploy.sh`).

## Start locally

Requires Docker Desktop Linux containers and Compose v2. The root `compose.yaml`
defines pgvector/Postgres 17, one-shot Alembic migration, API, worker, web and opt-in seed.
API/worker wait for successful migration; database and uploads use persistent volumes.

Set `CHAT_OPENAI_API_KEY` and `CHAT_OPENAI_MODEL` in your host environment, or create
a git-ignored `.env.local` yourself with those variable assignments. Both are required;
Missing variables fail with a clear Compose error. Optional variables:
`CHAT_OPENROUTER_API_KEY`, `CHAT_FREE_MODEL_CHAIN` (JSON array), `DEMO_SEED_PASSWORD`,
`PLATFORM_STAFF_EMAIL` (default `staff@example.com`), `PLATFORM_STAFF_PASSWORD`.
The containers explicitly use `EMBEDDING_PROVIDER=openai` and `COOKIE_SECURE=false`.
Provider keys reach only API/worker at runtime. Dotenv files are ignored by Git
and excluded from image builds.

PowerShell, repository root, with variables already set in the host environment:

```powershell
# Prevent Compose from reading an existing .env or COMPOSE_ENV_FILES override.
$env:COMPOSE_DISABLE_ENV_FILE = '1'
Remove-Item Env:COMPOSE_ENV_FILES -ErrorAction SilentlyContinue
docker compose up --build -d --wait
# Requires PLATFORM_STAFF_PASSWORD (8-200 characters); may incur embedding costs.
docker compose --profile seed up seed
docker compose down
```

For `.env.local`, add `--env-file .env.local` immediately after `docker compose` in
each command above. Wrappers select that file and disable implicit `.env` loading:
`.\scripts\dev_up.ps1`, `.\scripts\dev_compose.ps1 --profile seed up seed`,
`.\scripts\dev_down.ps1`. The down command preserves both volumes.

Open http://localhost:3000; API readiness is http://127.0.0.1:8000/ready.
If `PLATFORM_STAFF_PASSWORD` is set, the one-shot `staff` service creates/updates the platform admin on every `up` (otherwise it skips); no extra command is needed to sign in.
A `Makefile` wraps the day-to-day commands (`make help`); it reads `.env.local` when present.
Seed creates/reuses the demo, creates/updates staff using `PLATFORM_STAFF_PASSWORD`,
sets premium through the staff API, queues backfill, and prints staff email/web URL.
Embedding completion is asynchronous; check bot RAG status or worker logs.

### Creating the first organization, user and bot (platform admin)

Sign in at http://localhost:3000/login with the seeded staff account
(`PLATFORM_STAFF_EMAIL` / `PLATFORM_STAFF_PASSWORD`). Registration is closed by
default (`self_serve_signup=false`): the login screen has no Register link.
Then, from `/platform`:

1. **Organizations** → create the client's organization (name + plan label).
2. **Members** → create the user (email, optional phone, staff-set password or
   `"generate"` — the password is shown once), then assign the organization and
   role (admin/editor/viewer).
3. **Bots** → create the bot in that organization, open the organization
   workspace, upload knowledge in the bot's Knowledge tab, ingest, publish,
   then set allowed domains in bot Settings.
4. The user signs in with the staff-set password and can replace it on their
   **Account** page (header link); a password change signs out every other
   session of that account. Staff can reset a password or deactivate an account
   from **Members** at any time (deactivation revokes all sessions).

PostgreSQL is internal, defaults to `saas_dev` / user `saas` with a development-only
password. `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` overrides must match an
existing volume; passwords must be URL-safe. Seed requires a `_dev` / `_demo` database.
Old plain-Docker runner resources are not adopted; stop them before reusing ports.

Current verified test results (what was run, where, and what passed) are recorded in [PROGRESS.md](PROGRESS.md). How to run each suite, and what PostgreSQL version it needs, is in [docs/15-TESTING-AND-ACCEPTANCE.md](docs/15-TESTING-AND-ACCEPTANCE.md). Hosted CI is configured in `.github/workflows/ci.yml`.
