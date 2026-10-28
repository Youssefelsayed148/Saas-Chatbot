# Deploying to a VPS (Docker)

This file is the runbook for whoever (or whichever agent) deploys on the VPS. Everything runs in Docker; the only host requirements are Docker Engine with the Compose plugin, git, curl, and DNS for the domain.

Architecture: Caddy (automatic HTTPS, the only published ports 80/443) → Next.js web (same-origin `/api` proxy) → FastAPI API. A worker process handles ingestion, embeddings and follow-ups. PostgreSQL with pgvector holds all data; uploads live in the `app_data` volume. Nothing but Caddy is reachable from the internet.

## Existing deployment: close-out rebuild

The owner confirmed on 2026-10-28 (ADR-007 / D2) that this SaaS is already
running on a VPS with Docker Compose and Caddy. Close-out prepares a rebuild
of that deployment. Commands here are an operator runbook, not evidence that
a rebuild, backup or production migration has run. Each live operation needs
separate owner approval; preserve the existing Compose project and volumes.

Before an approved rebuild:

1. Record the deployed commit/image, database revision and current backup
   location. Confirm the intended existing Compose project and `DOMAIN`.
2. Provision `CHANNEL_SECRET_ENCRYPTION_KEYS` for **both API and worker**.
   The production startup guard requires it even before a channel is enabled;
   `compose.prod.yaml` passes it through their shared environment and refuses
   an empty value. Keep existing deployed keys on rebuild. These encrypt the
   stored per-connection signing secrets; they are separate from those secrets
   and from Meta tokens. Replacing the key without retaining the old key makes
   stored connections unreadable. During key rotation list newest first,
   comma-separated, retaining old keys until stored ciphertext is re-encrypted.
3. For a deployment with no encryption key yet, generate one in a trusted API
   Python environment into a private, exclusively created file; this command
   does not print the key. Transfer it using secure secret provisioning into
   the deployment environment, then remove the temporary file securely. Never
   run it with shell tracing or use it to overwrite existing deployed keys.
   On Linux the file is `/tmp/saas-channel-secret-<uid>.env` (or under the
   configured temporary directory), outside the checkout:

   ```sh
   python - <<'PYKEY'
   import os, tempfile
   from cryptography.fernet import Fernet
   path = os.path.join(tempfile.gettempdir(), f'saas-channel-secret-{os.getuid()}.env')
   fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
   with os.fdopen(fd, 'w', encoding='ascii') as output:
       output.write('CHANNEL_SECRET_ENCRYPTION_KEYS=' + Fernet.generate_key().decode('ascii') + '\n')
   PYKEY
   ```

4. Public URL: set the existing `DOMAIN` host name (without scheme/path) for
   Caddy, DNS and TLS. The public SaaS base URL entered in Many is
   `https://<DOMAIN>`; the signed events route is under `/api/channels/manyosiris/events`.
   This SaaS has **no `APP_BASE_URL` setting**. `API_PROXY_TARGET` and
   `PLATFORM_GUARD_ORIGIN` are internal Compose URLs; do not replace them with
   the public domain. Do not expose the API or database ports.
5. Confirm the existing database container is running before invoking the
   script. `scripts/deploy.sh` refuses to rebuild if no database is running,
   if `pg_dump` fails, or if `pg_restore --list` cannot read its nonempty custom
   archive. Archives use a UTC timestamp and private file permissions; failed
   dumps remain `.partial` files and are not success evidence. Archive listing
   checks structure, **not restorability**: rehearse restoration on a separate
   disposable database and retain a separate off-VPS copy before release.
6. Follow the 0022 to 0030 migration and pause-first rollback notes below and in
   `docs/16-DEPLOYMENT-AND-OPERATIONS.md`. Only after prerequisites and release
   approval run `./scripts/deploy.sh` from the approved checkout. It rebuilds
   the current checkout; `--pull` additionally contacts Git and is not implied
   by rebuild approval.

### Channel migration and worker readiness

The expected pre-P6 SaaS revision is `0022_knowledge_hygiene`; the release head
at this source is `0030_channel_health_poll_index`. Before migration record
`alembic current` and `alembic heads` using the approved deployment environment.
An unexpected revision, multiple heads or schema drift blocks release. Apply
0023-0030 using Alembic only, after a verified pre-deploy dump and disposable
restore/migration rehearsal. Never stamp a revision or use `create_all` as a
substitute. Production commands and rehearsal outcomes remain **UNVERIFIED**
until an operator records them.

The same API image runs `python -m app.worker`. Source registration covers
`channel_inbound`, `channel_send` and `channel_health_poll` in
`app/jobs/runner.py`. The worker schedules health polls and the unconfirmed
outbound sweep every `CHANNEL_HEALTH_POLL_INTERVAL_SECONDS` (default 300),
and runs retention maintenance. This is source evidence only: a healthy
heartbeat does not prove successful channel jobs or connectivity. After an
approved rebuild inspect job failures, current health timestamps and worker
logs without logging tokens, keys or message bodies.

## First deploy (historical bootstrap; not the close-out task)

1. Point the domain's DNS A/AAAA record at the VPS and open ports 80 and 443 (also 22 for SSH). Nothing else needs to be open.
2. `git clone <repo-url> && cd <repo>` and check out `main`.
3. `cp .env.production.example .env.production`, fill in every value, then `chmod 600 .env.production`.
   - Use long random values for `POSTGRES_PASSWORD` and `PLATFORM_STAFF_PASSWORD`.
   - `CHAT_OPENAI_API_KEY` is required (premium chat and embeddings). `CHAT_OPENROUTER_API_KEY` and `CHAT_FREE_MODEL_CHAIN` are only needed for the free tier.
4. Start the private database with `docker compose -f compose.prod.yaml --env-file .env.production up -d --wait db`, then run `./scripts/deploy.sh`. The rebuild script requires a running database so it can fail closed on backup failure. It builds the images, backs up an existing database, runs migrations (`alembic upgrade head`), creates or updates the platform-admin account, starts everything and checks `https://$DOMAIN/login`.
5. Sign in at `https://$DOMAIN/login` with `PLATFORM_STAFF_EMAIL` / `PLATFORM_STAFF_PASSWORD`. After the first login you may blank `PLATFORM_STAFF_PASSWORD` in `.env.production`; the bootstrap is skipped while it is empty.

## Updating

```
./scripts/deploy.sh --pull      # git pull --ff-only, rebuild, migrate, restart, verify
```

Migrations are forward-only in normal operation. The script first writes and checks a private `pre-deploy-<sha>-<UTC timestamp>.dump` archive; any failure aborts before build, migration or restart. Check archive restoration on a disposable database separately.

## Rolling back

```
./scripts/deploy.sh --rollback <previous-git-sha>
```

Pause affected channel connections first. The rollback option redeploys older
code and still invokes `alembic upgrade head`; it does **not** downgrade the
database, and may fail if that older checkout cannot recognize the current
revision. For Phase 6, do not use it as an automatic schema rollback. Once
channel data exists, 0023/0024 downgrade can fail or destroy channel data.
Keep the migrated schema and pause connections while assessing a compatible
image/forward fix. A database restore discards writes after the backup and
needs separate explicit destructive-operation approval and a recorded recovery
plan; the restore example below is not authorization to run it.

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

This deployment serves the website chatbot and the SaaS side of the signed
Many channel contract (`docs/17`). WhatsApp, Messenger and Instagram transport,
Meta tokens and webhooks remain in ManyOsirisChat. Linking/resuming a connection,
real provider calls and live canary sends require separate owner approval.
A rebuild does not authorize a merge to `main`; the owner still requires a
green full Playwright run and merge sign-off.
