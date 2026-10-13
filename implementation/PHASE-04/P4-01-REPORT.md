# P4-01 — Public widget API: locator config, visitor sessions, abuse limits

Implements the docs/05 public rows, docs/09 contract and docs/14 §7 defaults.

## What was built

- **Migration `0004_widget_public`** (up/down verified by `test_migrations.py` on a
  disposable DB): `bots.widget_locator` (opaque, unique; NOT a secret — assigned at bot
  creation), `visitor_sessions` (capability token hash only, composite FKs
  `(tenant_id, bot_id)` → bots), `conversations.session_id` (composite FK → visitor
  sessions), `rate_limit_counters` (Postgres-backed fixed windows — survive restarts and
  share across processes).
- **Public endpoints** (`app/widget/router.py`, no dashboard cookie involved; authority is
  always the session capability token or the server-side locator, callers NEVER pass a
  tenant id):
  - `GET  /api/public/v1/widgets/{locator}/config` — safe fields only (branding, welcome,
    opening questions, colour/position/language/dir). Paused/not-ready bots still return
    the config with `available:false, reason:` so the widget shows its controlled UI.
    Internal config (support contact, allowed domains, always-include ids) never leaks.
  - `POST /api/public/v1/widgets/{locator}/sessions` — short-lived capability token
    (SHA-256 stored; raw shown once), bound to the bot through composite FKs; the
    allowed-domain check runs on the PAGE origin as a defence signal, not auth
    (403 DOMAIN_NOT_ALLOWED when configured and mismatched/missing); raises the specific
    unavailability codes `BOT_PAUSED` / `BOT_NOT_READY` / `BOT_DISABLED`.
  - `POST /api/public/v1/sessions/{session_id}/messages` — one grounded turn through the
    SAME P3 pipeline (citations, needs_human routing); per-(IP, session) fixed window
    (default 20/min) and the daily message cap per bot from real usage events
    (429 QUOTA_EXCEEDED — quota hook for P7's per-plan enforcement).
  - `GET  /api/public/v1/sessions/{session_id}/messages` — thread recovery within the
    retention window (`?since=` supported for P5 polling).
  - `POST /api/public/v1/sessions/{session_id}/messages/{message_id}/feedback` — widget
    thumbs, idempotent per message+session.
- **Rate limiting** (`app/core/ratelimit.py`): atomic `INSERT … ON CONFLICT DO UPDATE`
  upsert returning the post-increment count; windows age out in the same statement. The
  P1 in-process login limiter (`app/auth/ratelimit.py` DELETED) now uses these Postgres
  counters (`login:{ip}`), with the increment committed in its own transaction so FAILED
  logins count; the 429 contract is unchanged (tests update, same RATE_LIMITED code).
- **Bot lifecycle** (needed for the widget's active/pause handling): `PATCH bots …`
  accepts `status` with validated transitions (draft→active, active↔paused; archive
  stays DELETE-only; archived cannot be revived), audited, viewer denied.

## Test evidence (all on disposable `_test` DBs)

- `tests/test_widget_public.py` (14 passed): safe config fields; invalid locator 404;
  session boot with capability token/expiry and hash-only storage; expired session →
  401 SESSION_EXPIRED; **cross-bot misuse impossible** (A's token against B's session
  401; guessed ids 401); disabled/paused bot controlled 409 for sessions and 200 w/
  `reason:"paused"` for config; draft bot `not_ready`; domain allow-list defence signal
  (bad/missing origin 403, subdomain allowed); session-creation abuse limit (3rd in
  window → 429); message rate-limit window + next-window reset (Postgres counter);
  daily quota hook (5 seeded usage events → 429 QUOTA_EXCEEDED); grounded pipeline with
  citations + history; feedback idempotency (2 calls → 1 usage row); conversation rows
  carry the session's own tenant/bot (isolation asserted against tenant B).
- `tests/test_bot_status.py` (5 passed): draft→active audit, active↔paused, invalid
  transitions 422, archived revive 409, viewer 403 + editor/admin/owner OK, tenant-B
  guessed-UUID 404.
- `tests/test_auth.py`: the login limiter behaves identically Postgres-backed (429 after
  2 failed attempts; independent unit covers the window reset through the counter).
- Full backend suite after this ticket: **189 passed** (ruff, ruff-format, mypy strict
  99 sources clean) — see PROGRESS.md for exact commands.

## Notes / beyond-spec defaults recorded here

- Session TTL default 30 min (`widget_session_ttl_seconds`); session-creation abuse cap
  10/min/IP (spec did not number it; P7 quotas revisit); daily message cap default 500/bot.
- The widget language hint is accepted on messages (`language`), matching docs/14 §2's
  "widget hint" fallback.
- Conversation creation is lazy on the first visitor message; the `widget_open` usage
  event anchors the "sessions started" metric (docs/14 §9, consumed by P4-05 analytics).
