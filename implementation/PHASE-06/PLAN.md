# Phase 6 plan: ManyOsirisChat channel (delegated mode, MVP)

Status: APPROVED v1, 2026-10-18. Contract: docs/17 (v1). Decisions record: docs/19. ADRs: ADR-002, ADR-015, ADR-016, ADR-017, ADR-019.
Attach this file together with `AGENT-PROMPT.md` (same folder) when starting the SaaS agent.

## 1. Branch and parallel-work rules (owner decision 2026-10-18)

- Roadmap order was P5, P7, then P6 with a full green Playwright run before P6. The owner approved building P6 NOW on an isolated branch while the website MVP is tested. This is a recorded deviation (DECISIONS.md 2026-10-18). The P6 prerequisites in PHASE-CHECKLISTS stay unticked; they gate the MERGE, not the build.
- Branch: `feature/phase-6-channels`, cut from main AFTER docs/17 v1 and this folder are committed to main by the owner.
- Work in a separate git worktree so the owner's main folder stays on main for docker and manual tests:
  `git worktree add ..\SAAS-chats-ai-phase6 -b feature/phase-6-channels main`
- The worktree needs its own Python venv and node_modules. The existing venv has an editable install pointing at the main folder, so tests run from the worktree could silently import main's code. Create a new venv in the worktree, install the lock files, then `pip install -e apps/api --no-deps`, and check with `python -c "import app; print(app.__file__)"` that the path is inside the worktree before running any test.
- Tests: only against the disposable DB on 127.0.0.1:55462 (user test / password test, container saas-test-db), set per process as TEST_DATABASE_URL, never in a file, never the dev DB. Use a database name that is not used by the website test runs (the fixture appends `_test`), for example `phase6`.
- Local commits only. Never push. No tags. No merge to main, no rebase of main, no docker (the owner runs docker), never read or print .env/.env.local or keys, no paid API calls (use the stub chat model; no provider keys).
- Sync with main: when the owner merges a website fix to main, merge main into the branch (not the other way), resolve on the branch, re-run affected tests. Migration numbering: this phase's migration is 0017; if main gains a migration first, renumber on the branch before merge.
- Merge to main happens only when ALL are true: website MVP signed off by the owner; P7 items ticked; full Playwright green on the branch; owner approval. Then `git merge --no-ff`, `git branch -d`, worktree removed, main left clean, no push.

## 2. Scope

In (MVP): channel connections (staff-created), signing/verification, events endpoint, inbound processing into the SAME chat/handoff pipeline, outbound delivery with retry, delivery status, connection health (push events and pull), per-connection AI toggle and pause/revoke, secret rotation with grace window, campaign name and opening message as context, unsupported-message handling, Channels management UI (staff) and read-only health card (client roles), fake Many server and contract tests, Many-side requirements handover, canary and rollback plan.
Deferred (not in this branch): P6-04 follow-ups/broadcasts/outreach, mirror event for messages sent by Many, media, bot actions, per-channel knowledge or per-channel personas.
Hard rules: no Meta tokens, no Meta webhooks, no Meta API calls in this repo. Tenant is derived from the connection only. Do not modify the Many repo from this branch.

## 3. Current state of the code (verified 2026-10-17/18)

- Migration head is 0016_arabic_fts. conversations already has channel (website|whatsapp|messenger|instagram), connection_id (Text, no FK), mode, status, assigned_user_id, source. messages already has channel_message_id, delivery_status, error_code. contact_identities exists with a UNIQUE (tenant_id, channel, external_id) index and no connection scope.
- The chat pipeline entry is `visitor_chat_turn` in apps/api/app/chat/conversations.py (persists the visitor message, runs the pipeline only in AI mode, meters by conversation.channel). It contains website-specific rules: reopen on resolved applies only when `source == "website"`, and it raises 409 when `source != "website"` and mode != ai. These rules must be generalized for channel conversations without changing website behavior.
- The inbox agent reply route (apps/api/app/inbox/router.py, POST /{conversation_id}/messages) stores an agent message and returns; website visitors see it by polling. There is no outbound delivery.
- The job queue (apps/api/app/jobs: queue.py, runner.py) supports typed jobs, retry with backoff and a worker. Existing job types: reembed_backfill, ingest_batch, retention_purge, follow_up_delivery, sentiment_classify.
- There is no encryption helper or crypto dependency in apps/api. Encrypting connection secrets requires adding one (see D2).
- The plan limit `channel_connections` exists in apps/api/app/quotas/plans.py but its usage is a placeholder equal to the bot count (apps/api/app/quotas/service.py).
- Route classification is enforced by apps/api/tests/test_tenant_route_matrix.py; every new route must be classified there.

## 4. Design decisions the agent must follow (D1 to D12)

D1 Tables (migration 0017, hand-written, never create_all):
- `channel_connections`: id, tenant_id, bot_id, channel, display_name, many_base_url, many_channel_ref, status (active|paused|revoked), ai_enabled (default true), secret_ciphertext, secret_key_version, secret_rotated_at, prev_secret_ciphertext, prev_secret_expires_at, health_status (healthy|degraded|unhealthy|unknown), health_reason, health_detail, health_updated_at, last_event_at, created_by, created_at, updated_at. Composite FK (tenant_id, bot_id) to bots; unique (tenant_id, id); check constraints on enums and channel.
- `channel_events`: id, tenant_id, connection_id (FK), event_id, event_type, payload JSONB, status (received|processed|failed|ignored), error_code, received_at, processed_at; UNIQUE (connection_id, event_id).
- conversations: convert connection_id from Text to UUID (all existing values are NULL) with composite FK (tenant_id, connection_id) to channel_connections; add external_conversation_id (Text) and origin (JSONB, nullable); unique partial index on (tenant_id, connection_id, external_conversation_id) where connection_id is not null. Channel conversations use source = 'channel'. Check for an existing check constraint on source before adding values.
- contact_identities: add connection_id (nullable UUID, FK); replace the unique index with one that is unique per (tenant_id, connection_id, external_id) for channel identities while keeping website identities unique as before (partial indexes: one where connection_id is null on (tenant_id, channel, external_id), one where it is not null on (tenant_id, connection_id, external_id)).
- messages: unique partial index on (tenant_id, conversation_id, channel_message_id) for sender_type = 'visitor' where channel_message_id is not null; add sent_attempts/last_attempt_at only if the job queue does not already track attempts (prefer the job row).
- Reversible migration, tested upgrade and downgrade on the disposable DB; existing data (all website) unchanged.

D2 Secret storage: generate a 32-byte random secret per connection; show once; store encrypted with a keyed scheme (add `cryptography`, Fernet/MultiFernet) using `CHANNEL_SECRET_ENCRYPTION_KEYS` (comma list, newest first). In production startup fails if the variable is missing (same pattern as the F-02 embedding provider check). Add to .env.example with a generation note, never a real key. Adding the dependency requires updating both lock files; mention it in the report so the owner can review. Never log secrets; never return them after creation; exports exclude them.

D3 Signing module (`app/channels/signing.py`): sign(secret, timestamp, body) and verify with constant-time compare, 5-minute skew both directions, accept current or previous secret during the grace window. Unit tests with fixed vectors, including tampered body, wrong secret, boundary timestamps.

D4 Events endpoint `POST /api/channels/manyosiris/events`: no cookie/CSRF (HMAC only); body cap 64 KB; verify before parsing JSON beyond what is needed to find nothing (the connection id comes from the header); generic 401 on any auth failure; revoked or unknown connection returns the same 401; per-connection rate limit (default 300/min, 429 with Retry-After); insert channel_event and enqueue the job in one transaction; duplicate returns 202 duplicate; unknown event types stored as ignored.

D5 Inbound job `channel_inbound` (new job type registered in the runner): handles message.received, message.status, channel.status as in docs/17 section 4. Idempotent on rerun. Must re-check connection status when the job runs. A tenant-A connection can never create or touch tenant-B rows (derive tenant only from the connection).

D6 Pipeline reuse: extract or generalize the turn logic so website and channel conversations share one code path. Website behavior must remain byte-for-byte equivalent in the existing tests. Required channel behaviors: in human mode store the inbound message and stay silent (no 409); reopen resolved conversations; truncate pipeline input to 1000 chars while storing full text; unsupported type flow; AI off and paused flow; quota exceeded and provider failure use the existing busy/handoff reply logic (apps/api/app/inbox/handoff.py) and send that reply; metering uses the real channel; traces record channel and connection. If any generalization changes a website test, STOP and report.

D7 Campaign context: store `origin` on the conversation; show "From campaign: <name>" in the inbox thread. The campaign opening message is given to the bot as context (docs/17 wins; owner decision 2026-10-27): capped at 500 characters, delimited by `<<<CAMPAIGN_CONTEXT` fences as untrusted DATA, placed after the rules and before the evidence, and unable to override the system prompt (test pins it). Website prompt bytes are unchanged when there is no campaign.

D8 Outbound job `channel_send`: created whenever an AI reply, handoff/busy/text-only reply, or agent reply is stored on a channel conversation (inbox agent_reply route enqueues it; refuse with 409 CONNECTION_PAUSED if paused/revoked). Signed POST per docs/17 section 5.1 to the stored many_base_url only; no redirects; connect 5 s / read 15 s; response size cap; retry 5xx/timeout/network/429 with exponential backoff and the same message_id; 4xx permanent with a readable code; store Many's id as channel_message_id; delivery_status stays `pending` until message.status. Only sender types ai and agent are sent; system notes and internal notes never. Long replies are split at sentence boundaries with a conservative per-channel constant; the real limits belong to Many.

D9 Delivery status: monotonic rank pending < sent < delivered < read; failed accepted only below delivered; error codes per docs/17; surfaced in the inbox per message; window_closed/template_required/recipient_unreachable are not retried.

D10 Health: `channel.status` events update the connection (ignore older occurred_at); a signed pull `GET /api/saas/connections/{id}/health` to Many from a staff "Check now" action and a periodic job `channel_health_poll` (every 5 minutes, active connections only, jittered, concurrency capped); stale after 15 minutes without signal; health transitions write audit rows; consecutive outbound failures (default 5) set degraded `many_unreachable`.

D11 API and roles (versioned tenant routes): staff-only create/update/pause/resume/revoke/rotate-secret/check-health/delete(soft via revoke); list/detail for staff include many_base_url and refs; client roles get a sanitized read model (channel, display name, status, health, last_event_at) rendered as a read-only "Connected channels" card on Overview. No new client sidebar item (ROLE-MATRIX sidebar unchanged); add the matrix rows. Quota: enforce the plan limit `channel_connections` on create using the real count of non-revoked connections (429 QUOTA_EXCEEDED), replacing the placeholder. Audit rows for every lifecycle action (actor, connection id, action; never secrets).

D12 Data lifecycle: channel_events payloads are purged by the retention job with messages; tenant export includes connections (without secrets) and tenant deletion purges connections and events; exports neutralize CSV formula injection for any new text fields; contact names and handles from events are length-limited and stripped of control characters.

## 5. Tickets (one per turn; stop and report in five lines after each)

- P6-00 Preflight: confirm worktree and venv isolation, baseline tests for touched areas green, list the exact files that will change. No code.
- P6-01 Connections, secrets, signing: migration 0017 (connections, events, indexes above), models, signing module, secret encryption and config, staff API, audit, quota enforcement, route-matrix classification. Tests: signing vectors, rotation grace, role matrix, tenant isolation, quota, migration up/down.
- P6-02 Inbound events and processing: events endpoint, `channel_inbound` job, contact identities, conversations, pipeline generalization (D6), unsupported flow, AI off and paused flows, origin storage (D7 display). Tests: auth matrix (bad signature, old/future timestamp, replay with new timestamp and same event_id, wrong connection, revoked, paused accepted, oversized, malformed), dedupe, out-of-order, duplicate external_message_id, tenant A/B, reopen resolved, human mode silent, long text, quota exceeded, provider failure, rerun idempotency. Existing website tests unchanged and green.
- P6-02b Campaign opening message to the bot (done in the review fixes, see D7).
- P6-03 Outbound delivery and status: `channel_send` job, agent reply integration, status updates, inbox delivery state UI, paused composer state, error text for window/template. Tests with the fake Many: success, 500 then success, timeout, 429 Retry-After, 4xx permanent, duplicate send idempotency, window_closed callback, out-of-order statuses, paused connection.
- P6-04 DEFERRED (follow-ups/broadcasts). Do not build.
- P6-05 Health and operations: health events, pull endpoint client, periodic poll job, staleness, Channels management UI for staff (create wizard with copy-once secret, pause/resume/revoke, rotate, AI toggle, check now, health and last event), client Overview card, Arabic/RTL and 360px layout, Playwright E2E with the fake Many.
- P6-05b Unified inbox and insights by channel (reuses the existing `conversations.channel` field; no new tables expected). FIRST read the existing inbox, contacts and analytics code and report what already exists before building. Then deliver, only where missing: (a) inbox list: channel badge/icon on every row, channel filter (All, Website, Instagram, WhatsApp, Messenger) combinable with the existing status/assignee filters, and a connection name when a tenant has several connections of one channel; (b) thread header shows channel, connection display name and "From campaign: <name>" when `origin` is set; (c) Insights: per-channel breakdown (conversations, handoff rate, unanswered questions, median first-response time, resolved rate), a channel filter on existing charts, and a by-campaign count for channel conversations; (d) Contacts: channel column and channel filter; (e) CSV/export includes the channel column (formula-injection neutralized). Counts must exclude other tenants and respect the existing role rules (clients see their own tenant's data; no staff-only fields). Website-only tenants see no regression: with a single channel the filter may be hidden. Tests: API tests for each aggregate with mixed-channel fixtures including a second tenant, an empty channel, and website-only data; Playwright: mixed inbox shows badges, filter narrows the list, insights breakdown matches the list counts, Arabic/RTL and 360px layouts.
- P6-06 Contract suite, handover, canary: fake Many server fixture, full contract tests in the normal test run, Many-side requirements doc check against MANY-AGENT-PROMPT.md, canary plan (one test number, staging only, owner approval) and rollback (pause the connection), docs updates (docs/04, 05, 06, 17, ROLE-MATRIX, PROGRESS, PHASE-CHECKLISTS), PHASE-REPORT.md.

## 6. Test plan

- Fake Many (apps/api/tests/fakes/fake_many.py or similar): verifies signatures, records requests, configurable responses (202, 500, timeout, 4xx, 429 with Retry-After), can post signed events (message.received, message.status, channel.status), can replay, reorder and duplicate. No network, no docker.
- Unit: signing, status ranking, health mapping, payload validation, message splitting.
- API integration on the disposable DB (one file per area, run file by file): everything listed in the tickets plus route-matrix classification, audit rows, retention purge of channel_events, export without secrets, migration upgrade/downgrade.
- Regression: all existing conversations, inbox, widget, contacts, quotas and platform tests stay green. Run the affected existing files after every change to the pipeline or inbox route.
- Playwright (once per ticket affecting UI, full suite once at the end): staff creates a connection and copies the secret; fake Many posts a message; the thread appears with channel badge; the stub bot replies; fake Many receives the outbound and posts delivered; inbox shows delivery state; takeover and agent reply reach the fake Many; pause blocks the composer; client roles see health only.
- Static: Ruff and mypy on touched files; report remaining unrelated findings separately.
- Never claim a result that was not run; record exact commands and outcomes in PROGRESS.md.

## 7. Acceptance gate for the branch (not a merge)

- Duplicate and out-of-order events are harmless; bad signature rejected; two tenants' connections never mix; secrets never leave the SaaS after creation; website behavior unchanged; all new routes classified; fake-Many contract suite green; full API suite (file by file) and full Playwright green on the branch; documentation updated; PHASE-REPORT.md written with evidence.
- Staging end-to-end with a real test number is a separate step that needs the Many-side delegated mode, a staging environment (ADR-007) and explicit owner approval.

## 8. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Pipeline generalization breaks the website path | Smallest possible change, existing tests as the guard, STOP rule in D6 |
| Branch drifts from main | Merge main into the branch after each website fix |
| Test runs import the wrong code (editable install) | Dedicated venv in the worktree and an import-path check |
| Test DB clashes with website runs | Distinct database name |
| New crypto dependency | Single small library, lock files reviewed by the owner |
| Many-side not ready | Fake Many contract tests; real E2E deferred |
| Customer message loops or cost spikes | Per-connection rate limit, existing metering and quotas, text-only reply at most hourly |
| SSRF through many_base_url | Staff-only, scheme validation (https in production), no redirects, fixed base URL, size/time caps |
| Lost messages while paused | Paused still accepts and stores inbound |

## 9. Open items for the owner (answer before or during the build)

1. Approve the new dependency `cryptography` and the key variable name `CHANNEL_SECRET_ENCRYPTION_KEYS`.
2. Confirm paused = accept-and-store (no AI, no sends) rather than reject, and that pending messages are not auto-resent on resume.
3. Confirm the client-visible surface is only a read-only card on Overview (no new sidebar item).
4. Confirm default rate limit and retry budget (300 events/min per connection; outbound up to 6 attempts over roughly 10 minutes).
5. Confirm per-channel reply length constants after checking Meta's current limits.
6. Decide when the Many-side work starts (separate repo; see MANY-AGENT-PROMPT.md).
