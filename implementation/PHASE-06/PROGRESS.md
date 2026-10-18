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
