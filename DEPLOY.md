# Deploying to a VPS (Docker)

This file is the runbook for whoever (or whichever agent) deploys on the VPS. Everything runs in Docker; the only host requirements are Docker Engine with the Compose plugin, git, curl, and DNS for the domain.

Architecture: Caddy (automatic HTTPS, the only published ports 80/443) → Next.js web (same-origin `/api` proxy) → FastAPI API. A worker process handles ingestion, embeddings and follow-ups. PostgreSQL with pgvector holds all data; uploads live in the `app_data` volume. Nothing but Caddy is reachable from the internet.

## First deploy

1. Point the domain's DNS A/AAAA record at the VPS and open ports 80 and 443 (also 22 for SSH). Nothing else needs to be open.
2. `git clone <repo-url> && cd <repo>` and check out `main`.
3. `cp .env.production.example .env.production`, fill in every value, then `chmod 600 .env.production`.
   - Use long random values for `POSTGRES_PASSWORD` and `PLATFORM_STAFF_PASSWORD`.
   - `CHAT_OPENAI_API_KEY` is required (premium chat and embeddings). `CHAT_OPENROUTER_API_KEY` and `CHAT_FREE_MODEL_CHAIN` are only needed for the free tier.
4. `./scripts/deploy.sh`. It builds the images, backs up an existing database, runs migrations (`alembic upgrade head`), creates or updates the platform-admin account, starts everything and checks `https://$DOMAIN/login`.
5. Sign in at `https://$DOMAIN/login` with `PLATFORM_STAFF_EMAIL` / `PLATFORM_STAFF_PASSWORD`. After the first login you may blank `PLATFORM_STAFF_PASSWORD` in `.env.production`; the bootstrap is skipped while it is empty.

## Updating

```
./scripts/deploy.sh --pull      # git pull --ff-only, rebuild, migrate, restart, verify
```

Migrations are forward-only in normal operation. The script takes a `pre-deploy-<sha>.dump` backup first.

## Rolling back

```
./scripts/deploy.sh --rollback <previous-git-sha>
```

This redeploys the older code. If the newer release applied a migration the older code cannot read, restore the pre-deploy dump instead (below), then redeploy the older sha.

## Operations

| Task | Command |
|---|---|
| Status | `docker compose -f compose.prod.yaml --env-file .env.production ps` |
| Logs | `docker compose -f compose.prod.yaml --env-file .env.production logs -f --tail=200 api worker web caddy` |
| Health | `curl -fsS https://$DOMAIN/login -o /dev/null` and `docker compose ... ps` (all services `healthy`) |
| Shell in API | `docker compose ... exec api sh` |
| Restart one service | `docker compose ... restart worker` |

Logs are rotated (5 × 20 MB per container). The `backup` service writes a daily `db-*.dump` and `files-*.tar.gz` to `./backups` and keeps `BACKUP_KEEP_DAYS` days. **Copy `./backups` off the VPS regularly** (a backup on the same disk is not a disaster backup).

### Restore a database backup

```
docker compose -f compose.prod.yaml --env-file .env.production stop api worker web
docker compose -f compose.prod.yaml --env-file .env.production exec -T db \
  pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner < backups/db-<stamp>.dump
docker compose -f compose.prod.yaml --env-file .env.production up -d --wait
```

Uploaded files: `tar -xzf backups/files-<stamp>.tar.gz` into the `app_data` volume (mount it with a throwaway container).

## Security notes

- Keep the API and database unpublished. The API trusts the first `X-Forwarded-For` value for per-IP rate limits; Caddy overwrites that header with the real client address, so the API must only be reachable through Caddy.
- `.env.production` and `./backups` are git-ignored. Never commit secrets or paste them into logs, issues or chats.
- Rotate `CHAT_OPENAI_API_KEY` by editing `.env.production` and running `docker compose ... up -d api worker`.
- Embed the widget on client sites from `https://$DOMAIN` (the widget loader is served from `/widget/v1`). Each bot's allowed domains control where it may run.

## Scope

This deploys the website chatbot SaaS only. WhatsApp, Messenger and Instagram live in ManyOsirisChat; connecting it is a separate step (the signed channel contract in `docs/17`, Phase 6 branch) and needs no change to this runbook until that branch is merged.
