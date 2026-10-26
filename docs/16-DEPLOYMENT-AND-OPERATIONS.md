# Environments and operations

Local Compose: PostgreSQL pgvector, FastAPI, Next.js, worker. `.env.example`
placeholder-only; no live secrets in Git. Staging uses separate database and
keys; production provider undecided. Apply Alembic migrations as release step;
backups and restore drill before production; health/readiness checks,
structured logs with request/tenant correlation but no sensitive payloads,
error tracking, resource/cost alerts, rate limits, retention/delete process.
Static widget may use CDN later. Do not deploy, spend money, create cloud
resources or enable public crawling without explicit approval.

## ManyOsirisChat channel runbook (P6, docs/17; ADR-002/017, ADR-020)

### Environment variables (names only; values go in the process env / .env.example, never in Git)

- `CHANNEL_SECRET_ENCRYPTION_KEYS` — required in production startup (Fernet keys, newest first, comma separated).
- `DATABASE_URL` — API and worker.
- `ENVIRONMENT` — startup guard refuses stub models and tests out of production.
- `CHAT_STUB_MODEL` / `EMBEDDING_TEST_STUB` — test-only; production startup refuses both.
- `EMBEDDING_PROVIDER` — must be explicit when `environment=production`.
- `WORKER_ALLOW_ONLY_TEST_DB` — worker refuses non-`_test` databases when set.
- `WORKER_HEARTBEAT_FILE` — worker liveness for the Compose healthcheck.
- `CHANNEL_HEALTH_POLL_INTERVAL_SECONDS`, `CHANNEL_HEALTH_POLL_JITTER_SECONDS`, `CHANNEL_HEALTH_POLL_BATCH` — the 5-minute poll job knobs.
- `SELF_SERVE_SIGNUP` — staging/onboarding switch.

### Migrations to include in the release (alembic, in order)

`0023_manyosiris_channels` (connections + events + conversation/identity
changes) · `0024_channel_inbound` (job type constraint, channel contact shape)
· `0025_channel_send` (outbound bookkeeping/unique keys) ·
`0026_channel_health_poll` (extends `ck_jobs_type`, adds the partial unique
index `uq_channel_health_poll_connection` that caps poll concurrency). All four
are reversible and were round-trip tested up and down on the disposable
database.

### Staging canary (needs explicit owner approval + a real test number)

1. Prereqs: staging deployed (ADR-007 hosting decision), the Many side in
   delegated mode for one WhatsApp number (MANY-AGENT-PROMPT.md), and the
   tenant limited to one bot and one connection.
2. Apply migrations 0023–0027 before booting the API; the worker refuses to
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
- Secret compromise: rotate (previous secret stays valid for the grace
  window, default 24 h); repeated 401s on a fresh connection indicate a
  secret/clock mismatch.
- Last resort: revoke + alembic downgrade 0020→0019 (undo the poll job type)
  and deploy the previous image; never downgrade across 0017 with live data.

