# Phase 6 progress

## P6-02 Stage A — event transport and inbound storage

- Added the signed Many event endpoint, bounded body reading, uniform authentication failures, rate limiting, idempotent event persistence, and atomic `channel_inbound` enqueueing.
- Added idempotent inbound handlers for contact identity/conversation/message storage, message delivery status, and channel health status. `visitor_chat_turn` was not changed.
- Migration `0018_channel_inbound` expands the job type constraint and permits a channel contact without website email/phone; downgrade restores the prior constraints.
- New focused tests: `apps/api/tests/test_channel_events.py` — **8 passed**.
- Ruff on Stage A touched Python files: **passed**.
- Strict mypy on the six touched application modules with `--follow-imports=silent`: **passed**. Without that flag, imported `knowledge/ingest.py` reports existing Windows-only `os.setsid`, `os.killpg`, and `signal.SIGKILL` typing errors.

### P6-00 baseline after Stage A

Each file was run in a separate process with `TEST_DATABASE_URL=postgresql://test:test@127.0.0.1:55462/phase6`, `-q -p no:cacheprovider`, and a worktree-local pytest basetemp. Results:

| File | Result |
| --- | --- |
| `test_conversations.py` | 13 passed |
| `test_conversations_view.py` | 5 passed |
| `test_inbox_list.py` | 5 passed |
| `test_group_0_inbox.py` | 16 passed |
| `test_contacts.py` | 1 passed |
| `test_analytics.py` | 6 passed |
| `test_quotas.py` | 12 passed |
| `test_tenant_route_matrix.py` | 7 passed |
| `test_platform.py` | 9 passed |
| `test_platform_ops.py` | 4 passed |
| `test_create_platform_staff.py` | 2 passed |
| `test_widget_public.py` | 14 passed |
| `test_widget_leads.py` | 5 passed |
| `test_widget_appearance.py` | 3 passed |

Total: **102 passed**. The first sandbox-restricted attempt could not create pytest temporary fixture directories; the verified rerun enabled fixture writes in the phase worktree. No existing website tests or fixtures were edited.

### P6-02 Stage B design note — written before pipeline edits

1. Keep `visitor_chat_turn` unchanged so the website request validation, persistence, quota, and reply path stay identical.
2. Add a separate `channel_chat_turn` entry point for an already-stored channel visitor message and its connection context.
3. Update `run_channel_inbound` and `_received` only to reopen eligible resolved conversations and invoke that channel entry point.
4. Reuse `history_messages`, `append_message`, `chat_answer`, `MeteredChatModel`, `reserve`, `release`, `settle`, and `record_usage_event`.
5. Persist the full inbound text in Stage A storage, then pass at most the first 1000 characters as the current pipeline question.
6. Reserve and meter with `conversation.channel`, preserving real WhatsApp, Messenger, or Instagram usage attribution.
7. Add `channel` and `connection_id` to the stored RAG trace; keep all visitor message text out of logs.
8. Handle human mode, paused/AI-disabled status, resolved reopening, and unsupported messages in the channel entry path, outside `visitor_chat_turn`.
9. Reuse `visitor_handoff_reply` and existing handoff decisions for quota/provider fallback; store text replies only and enqueue no send job.
10. Leave the website router, session-conversation helper, and website tests untouched; stop if any website test would need a change.

## P6-02 Stage B — pipeline generalization

- Added `channel_chat_turn` as a separate channel entry point. `visitor_chat_turn` and the website tests remain unchanged.
- Reopened resolved channel conversations in AI mode; preserved silent human, paused, and AI-disabled behavior; truncated only the model input to 1000 characters while retaining the full inbound message.
- Added localized unsupported-message replies with one pending text reply per conversation per hour. Quota and provider failures store the existing localized busy/handoff response. No `channel_send` job is created.
- Stored channel AI replies with pending delivery state and recorded real channel plus connection id in metering traces. Message contents are not logged.
- Expanded focused suite `test_channel_events.py`: **12 passed**.
- Ruff on all touched Python files: **passed**.
- Strict mypy on nine touched application modules with `--follow-imports=silent`: **passed**.

### P6-00 baseline after Stage B

Each file was run in a separate Python process with `TEST_DATABASE_URL=postgresql://test:test@127.0.0.1:55462/phase6`, `-q -p no:cacheprovider`, and `--basetemp=.pytest-tmp-phase6-baseline-b`:

| File | Result |
| --- | --- |
| `test_conversations.py` | 13 passed |
| `test_conversations_view.py` | 5 passed |
| `test_inbox_list.py` | 5 passed |
| `test_group_0_inbox.py` | 16 passed |
| `test_contacts.py` | 1 passed |
| `test_analytics.py` | 6 passed |
| `test_quotas.py` | 12 passed |
| `test_tenant_route_matrix.py` | 7 passed |
| `test_platform.py` | 9 passed |
| `test_platform_ops.py` | 4 passed |
| `test_create_platform_staff.py` | 2 passed |
| `test_widget_public.py` | 14 passed |
| `test_widget_leads.py` | 5 passed |
| `test_widget_appearance.py` | 3 passed |

Total: **102 passed**. No existing website tests or fixtures were changed.

### P6-02 post-acceptance verification

- Main worktree read-only strict mypy check, using shared targets present on `main`. Exact PowerShell command: `$env:MYPY_CACHE_DIR = Join-Path $env:TEMP 'phase6-main-mypy-cache'; & 'D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai-phase6\.venv\Scripts\python.exe' -m mypy --strict --cache-dir $env:MYPY_CACHE_DIR apps/api/app/db/models/knowledge.py apps/api/app/db/models/chat.py apps/api/app/jobs/runner.py apps/api/app/main.py`. Result: **3 errors**, matching the P6 worktree diagnostics in `apps/api/app/knowledge/ingest.py`: `os.setsid` line 112, `os.killpg` line 127, and `signal.SIGKILL` line 127. Main worktree remained clean.
- Post-acceptance coverage review: all 26 requested P6-02 assertions map to tests in `apps/api/tests/test_channel_events.py`; no additional tests were needed.

### Additional website-path verification

- `Conversation.source` is a `Text` column and has no source check constraint in the model or migrations. Application assignments found by code search are `website` (widget), `playground` (playground), and `channel` (Many inbound). The column can technically store other text values. The previous handoff guard blocked every non-website source; the initial P6 edit enabled unknown values. The guard now allows only `website` and `channel`, preserving the previous behavior for `playground` and all other values. Regression: `apps/api/tests/test_handoff.py::test_unknown_conversation_source_keeps_handoff_disabled`.
- The added English and Arabic `unsupported` strings are `CANNED` reply templates, not model prompt content. They are called from `channel_chat_turn` only, and `SYSTEM_TEMPLATE` is unchanged. A fixed website-input prompt digest was captured from `main` and checked in `apps/api/tests/test_chat.py::test_system_prompt_matches_main_bytes_for_fixed_website_input`: SHA-256 `aebc54a6ea68098e978211932bfa7ef50eca4933b8cb5745ad92749fdf240664`.
- New regression tests: **2 passed**. Ruff on the changed Python files: **passed** (`ruff check --no-cache`).
- The first restricted baseline attempt failed during `test_conversations.py` fixture setup with `KNOWLEDGE_EMPTY`; the permission-enabled rerun passed. Exact PowerShell loop from `apps/api`: `$env:TEST_DATABASE_URL = 'postgresql://test:test@127.0.0.1:55462/phase6'; $pytest = 'D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai-phase6\.venv\Scripts\python.exe'; $files = @('test_conversations.py','test_conversations_view.py','test_inbox_list.py','test_group_0_inbox.py','test_contacts.py','test_analytics.py','test_quotas.py','test_tenant_route_matrix.py','test_platform.py','test_platform_ops.py','test_create_platform_staff.py','test_widget_public.py','test_widget_leads.py','test_widget_appearance.py'); foreach ($file in $files) { & $pytest -m pytest "tests/$file" -q -p no:cacheprovider --basetemp=".pytest-tmp-phase6-website-checks"; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE } }`. The verified 14-file baseline used the disposable database one file per process:

| File | Result |
| --- | --- |
| `test_conversations.py` | 13 passed |
| `test_conversations_view.py` | 5 passed |
| `test_inbox_list.py` | 5 passed |
| `test_group_0_inbox.py` | 16 passed |
| `test_contacts.py` | 1 passed |
| `test_analytics.py` | 6 passed |
| `test_quotas.py` | 12 passed |
| `test_tenant_route_matrix.py` | 7 passed |
| `test_platform.py` | 9 passed |
| `test_platform_ops.py` | 4 passed |
| `test_create_platform_staff.py` | 2 passed |
| `test_widget_public.py` | 14 passed |
| `test_widget_leads.py` | 5 passed |
| `test_widget_appearance.py` | 3 passed |

Total: **102 passed**.

## Clean restart (2026-10-19) - Step 1 gate BLOCKED

Unattended decisions:
- The previous session is void. Trusted state is the committed history of `feature/phase-6-channels` (HEAD 9c0b1cc at restart).
- The worktree had 14 modified and 4 untracked uncommitted files from the voided session (P6-05 health work: `channels/health.py`, migration `0020_channel_health_poll.py`, `test_channel_health.py`, `apps/web/app/platform/channels/`, plus edits to config/inbound/outbound/router/runner/fake_many/tests/web files). They were backed up outside the repo and set aside with `git stash push -u -m "voided-session P6-05 WIP (unverified)"` (stash@{0}). Nothing was deleted or applied. They are not evidence of anything and P6-05 will be rebuilt from the plan.
- Shell: the worktree `.git` file points to a WSL path (`/mnt/d/...`), so git works only from WSL; the only venv (`.venv\Scripts\python.exe`) is a Windows venv. Git commands were run through `wsl`; test runs need the Windows venv.
- Gate result: NOT RUN. The disposable test database `saas-test-db` is not listening on 127.0.0.1:55462 (TCP connect refused from Windows and WSL). Starting it needs docker, which is forbidden for the agent. No test counts are recorded for this restart.

## Step 1 gate and P6-03 close-out (2026-10-19)

Command (PowerShell, Windows venv, one file per process, run twice back to back; `PYTHONDONTWRITEBYTECODE=1`, `TEST_DATABASE_URL=postgresql://test:test@127.0.0.1:55462/phase6_r9`, `CHAT_STUB_MODEL` and `EMBEDDING_TEST_STUB` unset): `python -m pytest tests/<file> -q -p no:cacheprovider --basetemp=.pytest-tmp-gate` from `apps/api`. Script kept outside the repo.

Result, run 1 and run 2 identical:
- 14 baseline files: conversations 13, conversations_view 5, inbox_list 5, group_0_inbox 16, contacts 1, analytics 6, quotas 12, tenant_route_matrix 7, platform 9, platform_ops 4, create_platform_staff 2, widget_public 14, widget_leads 5, widget_appearance 3 = **102 passed**.
- Channel suites: test_channels 7, test_channel_events 12, test_channel_migrations 1, test_channel_outbound 27, test_channel_outbound_unit 16 (63 total).
- Website prompt digest `test_chat.py::test_system_prompt_matches_main_bytes_for_fixed_website_input`: 1 passed.
- `test_startup_guard.py` (own process, no stub vars): 8 passed.
- Website tests unchanged. `git ls-files | grep p6_`: empty.

### P6-03 decision-to-test map (apps/api/tests/test_channel_outbound.py unless noted)
- D8 signed send, same message_id, rotation, no text in logs: `test_success_duplicate_current_secret_rotation_and_no_text_logs`; queued-before-rotation signs with new secret: `test_job_queued_before_rotation_signs_with_new_secret`.
- D8 retry on 5xx/timeout/429 with same id: `test_retry_then_success_with_same_id`; budget of 6 attempts then `many_unreachable` and health degraded: `test_retry_exhaustion`.
- D8 4xx permanent, never retried: `test_permanent_4xx_and_callback_reason_not_retried`.
- D8 no redirects, size cap, invalid ack: `test_redirect_response_cap_and_invalid_ack`; transport/DNS/target rules: `test_channel_outbound_unit.py` (dns pin, non-global DNS, invalid target, transport cap); send-time target rejection: `test_send_time_target_rejection`.
- D8 only ai/agent sent, notes never sent, enqueue idempotent, long reply split in order: `test_long_reply_order_and_enqueue_idempotency`, `test_agent_reply_pause_atomic_enqueue_notes_and_tenant_isolation`, split units in `test_channel_outbound_unit.py`; pipeline replies enqueued: `test_channel_pipeline_enqueues_final_replies`; website unchanged, no outbox: `test_website_agent_reply_keeps_response_and_has_no_outbox`.
- 409 CONNECTION_PAUSED: agent reply refused for paused and revoked, no message stored, tenant B gets 404, active reply enqueues a job: `test_agent_reply_pause_atomic_enqueue_notes_and_tenant_isolation`. Paused/revoked at job time fails with `connection_paused`, nothing sent: `test_paused_at_job_time`.
- D9 status transitions: pending < sent < delivered < read, failed only below delivered, out-of-order and duplicates harmless; window_closed/template_required/recipient_unreachable shown and not retried: `test_status_callbacks_and_out_of_order`.
- Job uniqueness and tenant safety, migration: `test_job_unique_key_and_foreign_job_cannot_send`, `test_send_migration_round_trip_and_unique_message_key`.
- "No AI fallback": there is no SaaS-side test for this and none is claimed. It is a Many-side rule (docs/17 section 1.4). SaaS side evidence is only that exhaustion ends in `failed`/`many_unreachable` with no alternate send path (`test_retry_exhaustion`).

### P6-03 status
- Backend: accepted on the evidence above.
- Not auto-resent on resume: behaviour follows from `test_paused_at_job_time` (message failed) but there is no explicit resume test.
- UNVERIFIED: inbox delivery-state UI (`apps/web/lib/channel-delivery.tsx`, `channel-delivery.spec.ts`, `channel-delivery.unit.mjs`). No frontend or Playwright run in this restart. P6-03 is closed as backend-verified, UI pending.
- P6-05 not started; the voided WIP remains in stash@{0}.

## P6-05 (2026-10-19, session in the worktree, HEAD before 4d5b5a5)

Built from scratch; stash@{0} (voided-session WIP) was NOT applied. Owner started
`saas-test-db` on request; all runs below used the disposable database.

What changed:
- Backend: `app/channels/health.py` (NEW: signed health pull client per docs/17
  §5.2 — DNS pin, no redirects, 5s/15s timeouts, 64 KB cap, signature over
  `timestamp + "."`; effective-health staleness 15 min → `unknown/stale`;
  `apply_health`/`degrade_health` with one audit row per transition (D10);
  `run_channel_health_poll`; `schedule_health_polls`). `outbound.resolve_target`
  gained a `path` parameter (default unchanged). `inbound._channel_status` now
  routes through `apply_health` (push events audited too). `router.py`: staff
  `POST .../check-health` ("Check now", 409 on revoked) and staleness applied in
  the staff and client read models (client shape unchanged, 5 keys). `runner.py`
  registers `channel_health_poll`; `worker/__main__.py` schedules polls every
  `channel_health_poll_interval_seconds` (300s default, jitter ≤ 60s, batch ≤
  100, one live job per connection). `config.py` gained the three poll settings.
- Migration `0020_channel_health_poll`: extends `ck_jobs_type`, adds partial
  unique index `uq_channel_health_poll_connection` (concurrency cap). Round trip
  tested up and down.
- Inbox: `conversation_detail` exposes `campaign_name` from `origin`; the thread
  header shows "From campaign: <name>" (D7 display).
- Frontend: NEW `app/platform/channels/page.tsx` (staff Channels management:
  create wizard with copy-once secret, pause/resume/revoke with confirmations,
  rotate with copy-once re-reveal, AI toggle, Check now, health + last event +
  secret version); platform nav gains "Channels" (client sidebar untouched);
  client Overview gains a read-only "Connected channels" card (only when the
  tenant has connections); `lib/api.ts` channel client functions and types;
  labels for health states and channel audit actions; CSS for the channels page.
- E2E infra: `e2e-api-setup.ts` generates a test-only `CHANNEL_SECRET_
  ENCRYPTION_KEYS` for the spawned API and worker (Fernet needs the 44-char
  padded form). NEW `tests/channels.spec.ts`: staff lifecycle at 360px+RTL and
  the fake-Many flow (HMAC-signed `message.received` with campaign origin posted
  to the real events endpoint; worker ingests; thread shows channel, "From
  campaign: Spring", the localized handoff reply as pending delivery; client
  Overview card).

Verification (all commands from `apps/api` unless noted; Windows venv
`.venv\Scripts\python.exe`; `TEST_DATABASE_URL=postgresql://test:test@127.0.0.1:55462/phase6`;
`ENVIRONMENT=test CHAT_STUB_MODEL=true EMBEDDING_TEST_STUB=true` via WSLENV;
one pytest process per file; `--basetemp=.pytest-tmp-p6-05-*`):

1. `python -m pytest tests/test_channel_health.py -q -p no:cacheprovider --tb=short`
   → **9 passed** (pull+audit, failure outcomes, paused allowed, poll apply/older
   ignored, skip non-active, foreign job isolation, retry-then-exhaustion,
   scheduling jitter/batch/single-live-job, 0020 round trip, staleness in both
   read models).
2. Channel suites rerun: test_channels **7**, test_channel_migrations **1**,
   test_channel_events **12**, test_channel_outbound **28** (27 + the new
   `test_resume_does_not_resend_messages_failed_with_connection_paused`),
   test_channel_outbound_unit **16**, test_channel_health **9** = **73 passed**.
   Two accepted assertions were updated for the new head: migration head checks
   in test_channel_migrations.py (0019→0020) and test_channel_outbound.py's
   round-trip version assert. No behavior changes behind them.
3. 14 baseline files, TWICE (one process per file, `--basetemp` per round):
   conversations 13, conversations_view 5, inbox_list 5, group_0_inbox 16,
   contacts 1, analytics 6, quotas 12, tenant_route_matrix 7 (now also covers
   check-health classification), platform 9, platform_ops 4,
   create_platform_staff 2, widget_public 14, widget_leads 5,
   widget_appearance 3 = **102 passed, 0 failed** in BOTH rounds.
4. Digest: `python -m pytest "tests/test_chat.py::
   test_system_prompt_matches_main_bytes_for_fixed_website_input" ...` → **1 passed**.
5. Startup guard, own process, stub vars unset: `python -m pytest
   tests/test_startup_guard.py ...` → **8 passed**.
6. Frontend unit (`apps/web`): `node --test tests/channel-delivery.unit.mjs`
   → **14 pass, 0 fail**. `npm run lint` exit 0; `npm run typecheck` exit 0.
7. Playwright (`apps/web`, real API+worker on the disposable DB via
   `cmd.exe /C "set DATABASE_URL=...phase6e2e&& set E2E_API_PORT=18170&& set
   API_PROXY_TARGET=http://127.0.0.1:18170&& npm exec -- playwright test ..."`):
   - `playwright test tests/channels.spec.ts` (main config) → **2 passed**.
   - `playwright test --config=playwright.channel.config.ts` → **1 passed**.
   - Inbox delivery UI: **VERIFIED** (channel-delivery.spec.ts green this
     session; unit suite green; pending/delivered states also appear in the new
     channels.spec.ts thread flow).
8. Static: ruff on all touched files → clean; mypy `--strict
   --follow-imports=silent` on the 10 touched modules → clean. Unrelated
   pre-existing findings (not touched): `knowledge/service.py:9` I001,
   `quotas/sentiment.py:153` E501, `tests/conftest.py:9` I001.

Notes and risks:
- "Consecutive outbound failures (default 5) set degraded" is implemented as
  accepted at P6-03: a message that exhausts its retry budget (6 attempts /
  ~9 min) marks the connection degraded `many_unreachable`; a successful poll
  or newer push event supersedes it. No consecutive-failure counter column was
  added to avoid changing accepted P6-03 behavior/tests.
- Staleness is computed at read time (staff and client read models) from the
  newest of `last_event_at`/`health_updated_at`; a stale signal shows
  `unknown`/`stale` without rewriting the stored row.
- The e2e fake Many cannot receive outbound SaaS→Many posts (the SaaS pins DNS
  to global IPs; no local listener can satisfy that without infra), so the
  outbound leg stays covered by the FakeMany transport tests; E2E proves the
  inbound leg, pipeline, handoff reply and pending delivery state.
- Two e2e DB-state leaks between Playwright runs (rows accumulate across runs
  in `phase6e2e_e2e_test`) were fixed by scoping assertions to the current run's
  row; the disposable e2e DB is not truncated between runs by design.

## P6-05b (2026-10-19, session in the worktree, HEAD before 6996132)

Read-only inspection first (per PLAN ticket): the API already had the inbox
`channel` filter and per-row `channel`; the web inbox already had the channel
filter and channel badge; the thread showed "From campaign: <name>" (P6-05);
handoff analytics had `conversations_by_channel` (website-only) and the
conversations CSV already carried `channel`. Missing and built:

- Inbox: `connection_name` on channel rows (list) and in the thread detail;
  shown next to the channel badge and as "Via <name> (channel)" on the thread.
- Insights: `GET /api/v1/tenants/{tenant}/analytics` gains `channel`
  (website stays default; a Meta channel value widens the source to
  `channel`), `channel_breakdown` (conversations, handoff rate, unanswered,
  median first response, resolved rate per docs/10) and
  `conversations_by_campaign` (origin.campaign_name counts). Analytics page:
  channel filter, per-channel table, by-campaign list. Contacts: `channel`
  filter (identity-based), `channels` column, robots via `ContactOut.channels`,
  and the export CSV gained the neutralized `channels` column.
- Channel inbound now publishes the shared inbox SSE event for new visitor
  messages (`message.created`), so waiting-human inbound is visible to open
  inboxes (AI-off threads previously never appeared live). Website path
  unchanged (`append_message` already emitted it).
- E2E harness: Playwright web port is now `E2E_WEB_PORT` (default unchanged)
  and the spawned worker gets `ENVIRONMENT=test` like the API (the embedding
  test stub refuses a non-test environment; without it `reembed_backfill`
  retried forever and broke knowledge-dependent specs).

Verification (disposable DB `phase6`, Windows venv, one pytest process per
file, `-q -p no:cacheprovider`):
- New API tests `tests/test_channel_inbox_insights.py`: **9 passed** (channel
  filter + connection names, empty channel, tenant A/B isolation, per-channel
  breakdown, campaigns, channel filter, viewer roles, website-only tenant
  unchanged, contacts column/filter/export).
- Affected existing suites unchanged counts: analytics 6, inbox_list 5,
  contacts 1, conversations_view 5, group_0_inbox 16, handoff 6.
- New channel events/job coverage after the SSE change: test_channel_events
  **12 passed**.
- Node unit tests: `node --test tests/insights.unit.mjs` → **8 pass**;
  `channel-delivery.unit.mjs` **14 pass** (rerun).
- Frontend: `npm run lint` exit 0, `npm run typecheck` exit 0.
- Playwright `tests/channel-insights.spec.ts` (main config): **1 passed**
  (~60s) — mixed website+whatsapp+instagram at 360px, filter narrows, badges
  and connection names, campaign + connection on the thread, insights table
  and campaign list matching the inbox count, contacts column/filter, RTL
  without horizontal overflow on inbox/analytics/contacts.
- Ruff + mypy `--strict --follow-imports=silent` on all touched API files:
  clean.

Commits: `6996132 feat: P6-05b unified inbox and insights by channel`,
`398ed3c test: P6-05b ...`.

## P6-06 (2026-10-19, HEAD before a9a7066)

- Contract suite `apps/api/tests/test_channel_contract.py` (17 tests) pins
  docs/17 v1 against the FakeMany transport with a section→test map in the
  module docstring: §3 HMAC input bytes and ±5-min skew boundary (±299 ok,
  ±301 rejected) and one generic 401 for every auth failure including
  revoked; §2 paused (202 stored, no AI, no `channel_send`, agent reply 409
  `CONNECTION_PAUSED`, resume sends nothing) and revoked (all rejected);
  secret encrypted at rest and absent from every read model; §4 202
  accepted/duplicate, 422 signed-malformed, unknown types ignored, job-later
  processing and idempotent reruns; §5.1 signed outbound with the exact
  recorded body, contract fields, once-only sends across duplicate job runs,
  notes/system never sent; §6 same `message_id` across retries, budget →
  `failed`/`many_unreachable` + degraded health, 429 Retry-After scheduling;
  §1.4 no SaaS-side fallback (no further job after exhaustion); §5.2 signed
  empty-body health pull and §4.3 push mapping with older-occurred_at
  ignored. Confirmed instead of duplicated at P6-02/03/05 files; the
  "no AI fallback" rule itself is Many-side (docs/17 §1.4 item 4).
- MANY-AGENT-PROMPT.md compared against docs/17 §9: no blocking mismatch. The
  only nuance: item 8 says the forwarder reports degraded health "in the
  dashboard" while docs/17 §6 says the channel reports degraded health — the
  SaaS-side signal arrives via `channel.status` and the health endpoint, which
  both exist in the prompt.
- Docs: docs/17 §6 gained the failure-counter deviation note (ADR-020);
  ADR-020 added to DECISIONS.md (owner sign-off pending, small reversible
  change if the owner prefers the literal consecutive-failure model);
  docs/16 gained the channel runbook (env var names only, migrations
  0017–0020, canary steps with migration 0020 called out, rollback = pause →
  revoke → downgrade order).
- PHASE-REPORT.md reconciled with PROGRESS.md (STOPPED note superseded by the
  verified P6-05/P6-05b/P6-06 state; remaining gaps listed there, including
  "no AI fallback" being a Many-side rule with no SaaS-side proof beyond
  exhaustion and no staging end-to-end with a real number).
- Commits: `a9a7066 test: docs/17 v1 contract suite ...`, then the docs
  commit in this run.

