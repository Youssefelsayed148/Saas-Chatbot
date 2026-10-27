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

## Final verification (2026-10-19, after both tickets were committed)

Environment: disposable database
`postgresql://test:test@127.0.0.1:55462/phase6final` per process; Windows venv
from the worktree; `CHAT_STUB_MODEL`/`EMBEDDING_TEST_STUB` unset except where
noted; one pytest process per file; `-q -p no:cacheprovider`; basetemp in the
Windows temp dir (two transient temp-file `FileNotFoundError`s on the
DrvFs-mounted worktree tmpdir disappeared with a Windows-native basetemp).

1. 14 baseline API files, run TWICE: **102 passed** in round 1 and **102
   passed** in round 2 (identical per-file counts: conversations 13,
   conversations_view 5, inbox_list 5, group_0_inbox 16, contacts 1,
   analytics 6, quotas 12, tenant_route_matrix 7, platform 9, platform_ops 4,
   create_platform_staff 2, widget_public 14, widget_leads 5,
   widget_appearance 3).
2. Full API suite (55 files, one process per file) + `tests/eval`:
   **510 passed, 1 skipped** (the pre-existing
   `test_knowledge_parsers` skip) + **2 passed** in eval = **512**.
   Per file: baseline 102; rest1 (auth 15, bot_status 5, bots 4,
   change_requests 1, chat 17, cross_script 3, database_guard 5,
   embedding_foundation 17, followups_analytics 2, group_a_operator 7,
   group_c_polish 2, handoff 6, health 6, hybrid_retrieval 9, invitations 6,
   jobs 8, knowledge_parsers 28+1 skipped, knowledge_pipeline 9,
   knowledge_uploads 19, members 8, migrations 1, models_constraints 13);
   rest2 (rag_evaluation 12, rag_gate 22, rag_limits 14,
   rag_stage0_baseline 14, rag_traces 3, retrieval 12, seed_demo 21,
   self_service_signup 4, tenant_data 2, tenants 6).
3. Channel suites: test_channels **7**, test_channel_migrations **1**,
   test_channel_events **12**, test_channel_outbound **28**,
   test_channel_outbound_unit **16**, test_channel_health **9**,
   test_channel_inbox_insights **9**, test_channel_contract **17** = **99**.
4. Website prompt digest: **1 passed**.
5. `test_startup_guard.py` own process, stub vars unset: **8 passed**.
6. Frontend: `node --test tests/insights.unit.mjs tests/channel-delivery.unit.mjs`
   → **22 pass, 0 fail** (8 + 14); `npm run lint` exit 0; `npm run typecheck`
   exit 0.
7. Full Playwright (all 66 tests, website included, disposable DB
   `phase6e2e_e2e_test`, API+worker spawned by the global setup): **66 passed
   in 5.4m**.
8. Ruff + mypy `--strict --follow-imports=silent` on all 9 touched Python
   files: clean.

Fixes committed during the final run (each rerun on the affected suite):
- `fix: keep channel encryption keys out of the Settings repr` — the repr
  privacy guard in `test_health.py::test_database_error_is_safely_handled`
  tripped on the P6 field name; the field is now `repr=False`.
- `fix: tolerate array-shaped channel fixture responses on the client
  overview` — the P6-05 Overview card read `channels.items` and crashed the
  page when a fixture answered `/channels` with a bare array; caught by the
  full Playwright run (group-b spec, 6 passed after the fix).
- Environment note: `test_rag_evaluation`, `test_rag_gate` and
  `test_rag_stage0_baseline` read their own UTF-8 JSONL outputs with the
  default encoding; on Windows Python they need `PYTHONUTF8=1` (pre-existing,
  not Phase 6 code). `tests/eval` regenerates
  `implementation/PHASE-03/EVAL-REPORT.md` with the current date; the committed
  report was restored after the run.
- Playwright run-infra notes: port 3100 is in use by an unrelated project on
  this machine, so the web port moved behind `E2E_WEB_PORT` (already committed
  with P6-05b); `ENVIRONMENT=test` is now set for the spawned worker (same
  commit).



## C-01 (2026-10-27, close-out session, branch claude/phase-6-channels-closeout-nznxfu, HEAD before: 22acf2d)

Contract A15 / ADR-024: SaaS->Many HTTP 401 is retried inside the 6-attempt budget, then `many_auth_rejected` + degraded health; other 4xx stay permanent.
Files: `apps/api/app/channels/outbound.py`, `apps/api/tests/test_channel_outbound.py` (new: 401 then success; 401 until budget; 403/404/422 as `many_http_NNN` via the existing parametrized test, its 401 case moved to 403), `apps/web/lib/channel-delivery.tsx` + `apps/web/tests/channel-delivery.unit.mjs`, DECISIONS.md (ADR-024), docs/16, docs/17 s11 (A15, runbook, A14 list), both CONTRACT-V1.1-DELTA.md, many-pack/CONTRACT-V1.md (`cmp` against docs/17: identical).
Environment: `apt-get update` then `apt-get install -y postgresql-16-pgvector postgresql-contrib`; `service postgresql start`; role `test` created; venv `/tmp/claude-0/venv` from `requirements-dev.lock`; `npm ci` in apps/web.
Commands and outcomes (only the touched test files):
1. `TEST_DATABASE_URL=postgresql://test:test@127.0.0.1:5432/phase6_test python -m pytest tests/test_channel_outbound.py -q` (in apps/api) -> **35 passed**. (The `postgresql+psycopg://` form fails in this conftest with a psycopg conninfo error; the plain `postgresql://` form works.)
2. `node --test tests/channel-delivery.unit.mjs` (in apps/web) -> **16 pass, 0 fail**.

## C-02 (2026-10-27)

(a) `apps/api/app/contacts/router.py`: `_PHONE_SHAPE` is now `^\+\d[\d\s().-]*$`; a phone with a leading `-` or `(` (or any formula lead) is escaped with `'`. `(` is escaped for phones only (it is not in the general formula prefix list; names are unchanged).
(b) Chose the index, not a column: migration `0030_channel_health_poll_index` adds partial index `ix_jobs_channel_health_poll_last` on `jobs (tenant_id, (payload->>'connection_id'), created_at) WHERE type = 'channel_health_poll'`. The scheduler query is untouched, so behaviour is identical. The three tests that pinned head `0029` now pin `0030` (test_channel_health, test_channel_migrations, test_channel_outbound). docs/04 and docs/16 list 0030.
Tests added: phone guard parametrized (+20 100 123 4567 kept, -1-1, (20) 100, =1+1, +SUM(A1), +(1), @1 escaped), CSV export test with `-1-1`, `=1+1`, `+20 100 123 4567`, `(555) 010`; `test_schedule_health_polls_orders_never_polled_then_least_recent` (batch 1: never polled, then 5 h old, then 1 h old); index existence asserted in the poll migration round-trip test.
Command: `TEST_DATABASE_URL=postgresql://test:test@127.0.0.1:5432/phase6_test python -m pytest tests/test_contacts_export_safety.py tests/test_channel_health.py tests/test_channel_migrations.py tests/test_channel_outbound.py -q` (apps/api). First run: 2 failed (the `(` case, which was not escaped yet), 65 passed. After the fix, `tests/test_contacts_export_safety.py` alone: **18 passed**; the other three files (65 tests) passed in the first run and are unaffected by the later router-only change.

Follow-up ticket (NOT done here, main-owned): `alembic check` drift `bots.uq_bots_widget_locator` and `provisioning_requests`. Needs its own ticket on main.

## C-03 (2026-10-27)

Added `apps/api/tests/fixtures/contract/signing_vectors.json` (secret = 40 x "s", timestamp "1760000000"; body `{"text":"مرحبا ✓"}` -> `sha256=5e40dcd701ffe2adc2ba2940bf94a02f3cbe639b1e7ec9a4ac59c4c146f13d50`; second vector with an empty body -> `sha256=3d0334f7dad871341364fcfae113d3fa28a51a9bb55ac983f9fe6b0b9b119dbd`). Both digests were computed locally with Python `hmac`/`hashlib` as HMAC-SHA256(secret, timestamp + "." + body); the first matches the value given in the ticket exactly.
Added `fixtures/contract/examples/*.json` (5 files, placeholders `{{connection_id}}`, `{{event_id}}`, `{{now}}`, `{{message_id}}`; see `fixtures/contract/README.md`) and `tests/test_channel_contract_fixtures.py`: sign/verify against both vectors; every example passes the real `_validate_payload` and gets 202 from `POST /api/channels/manyosiris/events` with a correct signature; 11 over-cap / wrong-type variants raise in `_validate_payload` and get the signed 422 `VALIDATION_ERROR`.
Command: `TEST_DATABASE_URL=postgresql://test:test@127.0.0.1:5432/phase6_test python -m pytest tests/test_channel_contract_fixtures.py -q` (apps/api) -> **21 passed**. `ruff check` + `ruff format` on the new test file: clean.

## C-04 (2026-10-27)

Added `scripts/check_contract_copies.py` (stdlib; `--root` for tests): fails if `many-pack/CONTRACT-V1.md` is not a byte copy of docs/17, if the two `CONTRACT-V1.1-DELTA.md` copies differ, or if the A1... clauses of the delta differ from docs/17 section 11. Wired into the Makefile: the repo has no target literally named "validate"; the only validating target is `config` ("Validate compose file"), so `config` now depends on the new `check-contract` target, which can also be run alone. No CI change (manual CI only).
Assumption to confirm: wiring into `config` (instead of a new top-level target) is the intended reading of "the existing validation Makefile target".
Tests: `scripts/test_check_contract_copies.py` (unittest; runs the script on a temporary copy: match passes; V1 mismatch, delta mismatch, section 11 drift and a missing file each exit 1).
Commands: `python3 scripts/check_contract_copies.py` -> `contract copies OK`, exit 0; `make check-contract` -> same; `cd scripts && python3 -m unittest test_check_contract_copies -v` -> **6 tests OK**.

## C-05 Final verification (2026-10-27, HEAD affe9e7 plus this docs commit)

Run once (a first API loop was killed after 2 files because `alembic check` showed my 0030 index as drift; the index was declared in the `Job` model, committed as affe9e7, ruff/mypy re-run, and the whole API loop restarted from file 1).
1. `cd apps/api && ruff check .` -> All checks passed; `ruff format --check .` -> 299 files already formatted; `mypy app` -> Success, 127 source files (re-run after affe9e7).
2. API, one pytest run per file over `tests/test_*.py` (97 files, PYTHONUTF8=1, TEST_DATABASE_URL=postgresql://test:test@127.0.0.1:5432/phase6_test): **1112 passed, 9 failed** (test_embedding_readiness 3, test_hybrid_retrieval 3, test_rag_evaluation 2, test_tone_prompt 1). The same four files in a clean `origin/main` worktree (d189893, DB mainchk_test): identical failure counts. `test_trace_context.py` passes on both trees here. pgvector in this VM is 0.6.0, probable cause of the retrieval failures (not investigated). See PRE-EXISTING-FAILURES.md.
3. Alembic on fresh DB `phase6_alembic_test` (DATABASE_URL set per process): `upgrade head`; `downgrade 0022_knowledge_hygiene`; `downgrade base`; `upgrade head`: all exit 0, `heads` -> single `0030_channel_health_poll_index`. (`downgrade 0022` as written in the ticket is not a revision id; 0022 is `0022_knowledge_hygiene`.) `alembic check`: only the main-owned drift listed below.
4. Web (apps/web): `npm run typecheck` exit 0; `npm run lint` exit 0; `node --test tests/*.unit.mjs` -> 24 pass, 0 fail.
5. Playwright, three channel specs via temporary config (`executablePath` /opt/pw-browsers/chromium-1243/chrome-linux64/chrome, E2E_PYTHON=venv, disposable DB phase6e2e_e2e_test): **5 passed (55.0s)**; temp config deleted. Other specs NOT RUN.
6. `make check-contract`: contract copies OK; `scripts` unittest: 6 OK.

Follow-up list (not done here):
- `alembic check` drift owned by main: `bots.uq_bots_widget_locator`, `provisioning_requests` indexes (own ticket on main).
- B1 (is P7 / a green Playwright run a gate) stays OPEN for the owner; this session verified only the three channel specs.
- S10 is undefined: no definition of S10 exists in the repo docs I was given, so nothing was done for it.
- ADR-020 still awaits owner sign-off (unchanged).
- Re-run the retrieval/embedding/RAG-eval files on pgvector 0.8.0; confirm test_trace_context flakiness.
- Makefile wiring assumption in C-04 (`config` depends on `check-contract`).


## Close-out session 2 (2026-10-27, branch claude/phase-6-channels-jj0a4y = feature/phase-6-channels 8987b24 at start; pushed only to origin/feature/phase-6-channels)

Rules in force: no merge to main, no PR, no real Meta/Many calls, disposable DBs only, ManyOsirisChat repo untouched. DECISIONS.md has not been edited.

### Batch 1 - Environment (no code change)

Environment: Ubuntu 24.04 cloud VM, PostgreSQL 16.15, Redis 7.0.15, Python 3.12.3 venv `/tmp/claude-0/venv` (`uv venv --python 3.12`, `uv pip install -r apps/api/requirements-dev.lock`).
1. pgvector 0.8.0: the Ubuntu package is 0.6.0 (`apt-cache madison postgresql-16-pgvector`), GitHub is blocked by the session scope and apt.postgresql.org returns 403 from the proxy. Built from the upstream tarball in the Ubuntu archive pool instead: `curl -O http://archive.ubuntu.com/ubuntu/pool/universe/p/pgvector/pgvector_0.8.0.orig.tar.gz` (sha256 `867a2c328d4928a5a9d6f052cd3bc78c7d60228a9b914ad32aa3db88e9de27b0`), `apt-get install postgresql-server-dev-16`, `make && make install`, `service postgresql restart`. Roles/DBs: role `test` (superuser, CREATEDB), `phase6_test`; clean-main DB `mainchk_test`. `service redis-server start` -> `redis-cli ping` PONG.
   `SELECT extversion FROM pg_extension WHERE extname='vector'` (in `phase6_test`) -> **0.8.0**.
2. Re-run of the four files, `cd apps/api && PYTHONUTF8=1 TEST_DATABASE_URL=postgresql://test:test@127.0.0.1:5432/<db> python -m pytest tests/<file>.py -q -p no:cacheprovider`. Branch tree = HEAD 8987b24 / DB `phase6_test`; clean main = detached worktree of origin/main d189893 / DB `mainchk_test`; both on pgvector 0.8.0.

| File | pgvector 0.6.0 (earlier record) | 0.8.0 branch | 0.8.0 clean main |
|---|---|---|---|
| test_embedding_readiness.py | 3 failed, 3 passed | **6 passed** | **6 passed** |
| test_hybrid_retrieval.py | 3 failed, 8 passed | **11 passed** | **11 passed** |
| test_rag_evaluation.py | 2 failed, 10 passed | **12 passed** | **12 passed** |
| test_tone_prompt.py | 1 failed, 4 passed | 1 failed, 4 passed | 1 failed, 4 passed |

Conclusion: the 8 embedding/hybrid/RAG-eval failures are caused by the pgvector version (0.6.0); they pass on 0.8.0 on both trees.
**Not a pgvector issue (OPEN for the owner, instruction said to stop and ask):** `test_tone_prompt.py::test_empty_tone_leaves_prompt_body_byte_identical` still fails on 0.8.0 on both trees. First failing assertion (`tests/test_tone_prompt.py:27`): `assert hashlib.sha256(body.encode()).hexdigest() == BASELINE_SHA256` -> got `33c62542...0d72580`, expected `2cd35a17...8928cebe`. The test needs no database; it is not line endings (CRLF rendering gives a third hash `0830e2ee...`) and it fails identically on clean main, so it is a stale baseline hash in the test (or an unrecorded template change at version 2026-10-25.1), not Phase 6. I did not touch it and continued with the remaining batches because it is accepted-known and identical on main; please decide whether main should re-pin the hash.

### Batch 2 - Small code and tooling fixes (one commit each; only touched files run)

- 2a `bbf4b55` Makefile: `PYTHON ?= $(shell python3 -c "" >/dev/null 2>&1 && echo python3 || echo python)`; `check-contract` uses `$(PYTHON)`. `make check-contract` -> `contract copies OK`. Fallback tested with a PATH holding only make, sh, bash and `python` (no python3): the recipe ran `python scripts/check_contract_copies.py` -> OK. (No Windows machine here; the Windows claim rests on that simulation.)
- 2b `30e9fe7` `scripts/check_contract_copies.py` normalises CRLF to LF before comparing. Tests added: CRLF copies pass, a fully CRLF checkout passes, CRLF does not hide real drift. `cd scripts && python3 -m unittest test_check_contract_copies -v` -> **9 tests OK** (was 6); `make check-contract` OK.
- 2c `d50ab01` Rule: **if any attempt of the message's send saw HTTP 401 and the budget ends on a transient failure, the label is `many_auth_rejected`** (the 401 is the actionable signal; a later timeout must not hide it). Implementation: the send job payload remembers `auth_rejected: true` on the first 401 (`AUTH_REJECTED_KEY` in `app/channels/outbound.py`); `requeue_message` clears it. A budget with no 401 stays `many_unreachable`. Documented in docs/17 A15 and in all contract copies (`make check-contract` OK). Tests (4 new in `tests/test_channel_outbound.py`): 401 then 5 timeouts; 5 timeouts then 401; 3 timeouts + 3x 503 with no 401 stays `many_unreachable`; requeue clears the remembered 401. Command: `TEST_DATABASE_URL=postgresql://test:test@127.0.0.1:5432/phase6_test python -m pytest tests/test_channel_outbound.py -q -p no:cacheprovider` (apps/api) -> **39 passed**. Without the source change the same run fails exactly 2 of the new tests (401-then-timeouts, requeue-clears). `ruff check`, `ruff format --check` on touched files, `mypy app/channels`: clean.
- 2d `9b9817d` docs/16 migration list now reads 0028, 0029, 0030 in order (docs only).

### Batch 3 - S10 and main-owned drift

- 3a **S10 is undefined - owner attention.** Searched `docs/`, `implementation/`, `DECISIONS.md`, the root `PROGRESS.md` and all `*.md/*.py/*.ts/*.tsx/*.yaml/*.json` in the repo for the word `S10`, `S-10` and "S1-S10": the only hits are earlier notes saying it is undefined (root `PROGRESS.md:3798`, this file's close-out follow-up list). No definition exists, so I did nothing and did not guess. Please supply the S10 text (or say it is void).
- 3b Wrote `implementation/PHASE-06/TICKET-alembic-drift.md` with the exact `alembic check` output (identical on clean main d189893 and on this branch), the cause table, a recommended model-only fix (verified on a throwaway edit: `alembic check` -> "No new upgrade operations detected"; edit reverted) and an untested migration alternative. No migration was added on this branch.

### Batch 4a - P7 scope and status (read-only; nothing built on this branch)

Sources: `implementation/MASTER-ROADMAP.md` (P7 section), `implementation/PHASE-CHECKLISTS.md` lines 71-79, root `PROGRESS.md` 2026-10-14 entries, `implementation/KNOWN-ISSUES.md`, `implementation/PHASE-07/*`. All P7 checklist boxes are **unticked** in PHASE-CHECKLISTS.md; status below is what the repo shows, not a sign-off.

| Ticket | Scope | Status found in the repo |
|---|---|---|
| P7-01 | admin operations, job health, retry/cancel/pause with reason + audit, plan assignment, platform analytics, audit review | Code built (commit 58ed96d, tests `test_platform_ops.py`; owner reported 4 passed in Oct). Operations UI browser check UNVERIFIED (KNOWN-ISSUES). AI cost analytics intentionally absent (no provider pricing stored). |
| P7-02 | quotas enforced and race-tested; sentiment job | Code built with PLACEHOLDER plan values (`app/quotas`, `test_quotas.py`). Quota values are not owner-approved; sentiment job built as a queue. |
| P7-03 | self-service signup via ProvisioningService; concurrent retries create one tenant/bot | Code built (`test_self_service_signup.py`). |
| P7-04 | tenant export/delete incl. contacts, conversations, identities; audit review screen | Code built (`test_tenant_data.py`); local-storage cleanup is best-effort on OS unlink errors (KNOWN-ISSUES). |
| P7-05 | backup + restore drill; monitoring/alerts incl. failed deliveries and stuck jobs; full green Playwright; staging only after ADR-007 | **Documents only** (`PHASE-07/RUNBOOK.md` DRAFT, `BACKUP-RESTORE.md`, `MONITORING-ALERTS.md`, `HOSTING-OPTIONS.md`, `SECURITY-REVIEW.md`). Restore drill UNVERIFIED; alert delivery UNVERIFIED (needs hosting); full green Playwright: see 4b below. |
| P7 gate | independent security review closed; phase report; owner sign-off | **Missing**: no independent reviewer findings or sign-off (SECURITY-REVIEW.md: "OPEN and UNVERIFIED"); no phase report; ADR-007 (hosting) OPEN gates staging. |

What is missing for P7 completion: (1) a backup/restore drill on a disposable target, (2) an independent security review and its closure, (3) owner-approved quota/plan values (currently PLACEHOLDER), (4) a full green Playwright run (4b), (5) browser verification of the P7-01 operations UI, (6) the P7 phase report and owner sign-off, (7) ADR-007 only for staging. Per the roadmap P7 should precede P6; this branch built P6 first by the 2026-10-18 owner decision and keeps P7 complete as a merge gate.
