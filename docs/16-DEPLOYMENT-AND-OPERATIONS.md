# Environments and operations

Local Compose: PostgreSQL pgvector, FastAPI, Next.js, worker. `.env.example`
placeholder-only; no live secrets in Git. Staging uses separate database and
keys. ADR-007 hosting is decided (owner 2026-10-28): the existing VPS runs
Docker Compose with Caddy; close-out rebuilds it without provisioning a new
provider. Apply Alembic migrations as release step;
backups and restore drill before production; health/readiness checks,
structured logs with request/tenant correlation but no sensitive payloads,
error tracking, resource/cost alerts, rate limits, retention/delete process.
Static widget may use CDN later. Do not deploy, spend money, create cloud
resources or enable public crawling without explicit approval.

## ManyOsirisChat channel runbook (P6, docs/17; ADR-002/017, ADR-020)

### Environment variables (names only; values go in the process env / .env.example, never in Git)

- `CHANNEL_SECRET_ENCRYPTION_KEYS` - required in production startup and passed to API and worker by the shared Compose environment (Fernet keys, newest first, comma separated). Preserve deployed keys on rebuild; see `DEPLOY.md` for secure generation without terminal output.
- `DOMAIN` - the public Caddy host name; Many uses `https://<DOMAIN>` as the SaaS base URL. No SaaS `APP_BASE_URL` setting exists. Internal `API_PROXY_TARGET` / `PLATFORM_GUARD_ORIGIN` stay on the Compose network.
- `DATABASE_URL` — API and worker.
- `ENVIRONMENT` — startup guard refuses stub models and tests out of production.
- `CHAT_STUB_MODEL` / `EMBEDDING_TEST_STUB` — test-only; production startup refuses both.
- `EMBEDDING_PROVIDER` — must be explicit when `environment=production`.
- `WORKER_ALLOW_ONLY_TEST_DB` — worker refuses non-`_test` databases when set.
- `WORKER_HEARTBEAT_FILE` — worker liveness for the Compose healthcheck.
- `CHANNEL_HEALTH_POLL_INTERVAL_SECONDS`, `CHANNEL_HEALTH_POLL_JITTER_SECONDS`, `CHANNEL_HEALTH_POLL_BATCH` — the 5-minute poll job knobs.
- `SELF_SERVE_SIGNUP` — staging/onboarding switch.

### Migrations to include in the release (alembic, in order)

`0023_manyosiris_channels` (connections, events, `conversations.connection_id`
Text to UUID, playground key moved to `external_conversation_id`) ·
`0024_channel_inbound` (job type, channel contact shape) · `0025_channel_send`
(outbound bookkeeping, `uq_channel_send_message`) · `0026_channel_health_poll`
(job type, `uq_channel_health_poll_connection`) · `0027_channel_ref_unique`
(unique live `(channel, many_channel_ref)`; refuses to run if duplicates exist,
fix them first) · `0028_channel_unconfirmed` (`messages.accepted_at`,
`unconfirmed` delivery state) · `0029_channel_event_payload_purge` (`channel_events.payload` nullable for retention) · `0030_channel_health_poll_index` (partial index for the health scheduler's last-poll lookup; no behaviour change). All are reversible and were round-trip tested on
the disposable database in the historical build report; that is not a fresh
close-out rehearsal. The supported pre-P6 starting revision is
`0022_knowledge_hygiene`, with one head `0030_channel_health_poll_index` at
this source. Before any approved migration: record current/head, confirm the
existing database/project/volumes, obtain the script's nonempty custom-format
pre-deploy dump, check its archive listing, and rehearse restoration and
0022 to 0030 migration on a disposable database. Stop for unexpected revisions or
drift; do not stamp or use `create_all`. Apply migrations before booting the
new API/worker. `scripts/deploy.sh` aborts before build or migration if the
existing database is not running, the dump fails or the archive is invalid.
No production migration, rebuild or fresh rehearsal is asserted by this text;
these remain **UNVERIFIED** pending recorded operator evidence.

### Health model (contract v1.1 A9) and what to watch

- `compose.prod.yaml` runs the same API image with `python -m app.worker`.
  Source dispatch in `app/jobs/runner.py` registers `channel_inbound`,
  `channel_send` and `channel_health_poll`; `app/worker/__main__.py` schedules
  health polls plus `sweep_unconfirmed` on the configured interval (300 s by
  default). No separate channel daemon/Redis is required. Runtime liveness,
  job completion and real Many connectivity remain **UNVERIFIED** until checked
  after an approved rebuild; a heartbeat alone proves neither jobs nor sends.
- Health comes from three signals: pushed `channel.status` events, the signed
  5-minute pull (worker job `channel_health_poll`, active connections only) and
  staff "Check now". Many's signed health endpoint is mandatory.
- No event and no successful pull for 15 minutes shows `unknown / stale`. Stale
  usually means the worker is down, Many is silent or the secret does not match.
- Several workers can run: scheduling takes a database advisory lock, so one
  worker schedules per cycle and there is at most one live poll job per
  connection (partial unique index). Nothing needs configuring.
- A future `checked_at` from Many (clock ahead) is treated as "now".
- Messages accepted by Many with no status after 15 minutes become
  `unconfirmed` (worker sweep, same cycle); a later real status overrides it.
- Alert on: connections stale for more than 30 minutes, `channel_send` /
  `channel_inbound` job failures, `failed` messages with `many_unreachable`.

### Staging canary (needs explicit owner approval + a real test number)

1. Prereqs: staging deployed (ADR-007 hosting decision), the Many side in
   delegated mode for one WhatsApp number (MANY-AGENT-PROMPT.md), and the
   tenant limited to one bot and one connection.
2. Apply migrations 0023–0030 before booting the API; the worker refuses to
   start against a non-migrated head implicitly (job type constraint).
3. Create the connection as platform staff, copy the once-shown secret into
   the Many channel operator screen; many_base_url pins the staging peer.
4. "Check now" green → replay the fake-Many flow manually: one inbound text
   message → AI reply delivered → one inbound while paused → stored, no AI, no
   send → resume → message.status delivered / read appear in the inbox.
5. Watch: `jobs` failures, connection health, SSE inbox updates, metering by
   the real channel. Success criterion: the one test number completes one full
   round trip with no unknown errors.

### Rollback / incident steps

- First move is always: **pause the connection** (staff UI or
  `POST /api/v1/platform/channel-connections/{id}/pause`). Inbound is still
  accepted and stored (202), the AI is silent, no outbound is sent, agent
  replies 409 `CONNECTION_PAUSED`. No customer message is lost.
- If Many itself misbehaves: revoke (terminal, rejects all inbound with 401)
  — conversations stay readable. Reconnect later via a NEW connection.
- Outbound failures: after the retry budget (6 attempts ≈ 10 minutes) the
  message is `failed` / `many_unreachable` and health shows degraded
  (ADR-020); check the inbox error text and the audit rows before retrying
  a send. Paused-while-pending messages are NOT auto-resent on resume.
- Secret rotation without losing sends (docs/17 A15): pause the connection,
  rotate the secret, enter the new secret in Many, resume. A `401` from Many
  is retried inside the 6-attempt budget (about 9 minutes); if it persists the
  message fails with `many_auth_rejected` and health shows degraded with that
  reason (both sides hold different secrets).
- Secret compromise: rotate (previous secret stays valid for the grace
  window, default 24 h); repeated 401s on a fresh connection indicate a
  secret/clock mismatch.
- Messages that failed because the connection was paused can be sent again by
  an agent with the inbox "Send again" action (never automatic).
- Rollback = pause first. Already accepted/in-flight messages cannot be
  recalled; verify outstanding jobs separately. Keep the migrated schema while
  assessing a compatible image/forward fix. `deploy.sh --rollback` runs
  `alembic upgrade head` from the older checkout, so it is not an automatic
  schema rollback and can fail on an unrecognized newer revision. The
  downgrade of 0024 FAILS once channel contacts without email or phone exist
  (it restores the "reachable" check), and the downgrade of 0023 drops the
  connections, events and per-conversation channel ids and can fail on
  identities shared by several connections: neither is a safe rollback with live
  channel data. The rollback plan for a live deployment is "pause the connection" (or
  revoke), not a database downgrade. Downgrading 0029 turns purged payloads
  into `{}`.
- Known limitations: the unauthenticated events route does one connection
  lookup before any throttle (the rate limit is per connection and runs after
  the signature check); `received_at` may be up to 5 minutes in the future
  (contract A10).

