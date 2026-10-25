# Phase 6 (ManyOsirisChat) review and rework basis

Date: 2026-10-26. Reviewer: Claude (read-only; no tests were run in this review, no code changed).
Reviewed: branch `feature/phase-6-channels` (worktree `SAAS-chats-ai-phase6`, head `57b1417`, 28 commits, 81 files, +9780/-94), against docs/17 (contract v1), docs/19, implementation/PHASE-06/PLAN.md, PHASE-REPORT.md, and the current `feat/ui-polish` and `main`. Many side: `Youssefelsayed148/ManyOsirisChat` `main` (`5cc60c7`, 2026-10-06), read-only clone.

## 1. Verdict

The SaaS-side channel module is well built and matches contract v1 closely (signing, dedupe, paused/revoked semantics, health, outbox, SSRF controls, encrypted secrets, 99 channel tests plus a 17-test contract suite against a fake Many). It is NOT mergeable and cannot be merged as-is. Three structural problems, a set of real defects, and several contract gaps that only show up when you read the Many code.

## 2. Structural problems (must fix before anything else)

| # | Problem | Evidence | Consequence |
|---|---|---|---|
| S1 | Migration number collision | Branch adds `0017_manyosiris_channels`..`0020_channel_health_poll`. `main`/`ui-polish` already have 0017..0022 (bot tone/rules, usage_event_unavailable, revision_embedding_state, knowledge_hygiene). | Alembic multiple heads / wrong order. Renumber to 0023+ and re-chain. |
| S2 | 164 commits of drift | Branch base `5c4d253`. Main since then rewrote the chat pipeline (`chat/service.py`, `history.py`, `streaming.py`, `deadline.py`, `routing.py`, `providers.py`, `prompts.py`), added bot tone/rules/assistant name, RAG hardening, widget changes. 28 files are touched on both sides. | Merge conflicts in `chat/conversations.py`, `inbox/*`, `quotas/service.py`, `db/models/*`, `main.py`, and most of the web files. |
| S3 | `channel_chat_turn` is a ~200-line copy of `visitor_chat_turn` | `apps/api/app/chat/conversations.py` on the branch. PLAN D6 required one shared path. | Every main change to the website turn (persona, tone/rules, routing, history, language, handoff, deadline) silently does NOT apply to Meta channels. Two behaviours for one bot, which breaks "one bot = one brain". |
| S4 | UI built on the pre-redesign design system | `ui-polish` B2 to B6 rebuilt shell, dashboards, Conversations (Inbox + History tabs), settings, bots, organizations. The branch's `platform/channels/page.tsx`, inbox, insights, contacts, overview changes were written against the old components. | UI must be re-done on the new components, not merged. Also: channels belong inside the new organization workspace, not a standalone global page. |

Recommended route: do NOT merge main into the old branch. Cut a new branch from the `feat/ui-polish` tip (or from `main` once ui-polish is merged), port the additive files (they are mostly new files), and re-implement the touch points by hand against current code. Prompt: `SAAS-REBUILD-PROMPT.md` (owner decision 2026-10-26: update the existing branch instead of a new one).

## 3. Defects found in the SaaS code (all read from the branch source)

Severity: H = fix before staging, M = fix in the rework, L = polish.

| # | Sev | File | Finding |
|---|---|---|---|
| D1 | H | `channels/inbound.py` `_identity/_conversation/_received` | `payload["channel"]` is trusted. It is only validated to be one of the three names, never compared with `connection.channel`. A signed event on a WhatsApp connection with `channel: "instagram"` creates an instagram conversation (wrong metering channel, wrong reply-length limit, wrong badge). Contract says tenant, bot and (by extension) channel come from the connection. Reject with 422 on mismatch. |
| D2 | H | `channels/inbound.py` + `chat/conversations.py` | No per-conversation serialization. Two quick customer messages become two jobs that can run in parallel workers: both AI turns read history without the other, replies can arrive out of order, `_conversation()` can race on the unique index. Lock the conversation row (`SELECT ... FOR UPDATE`) for the whole turn, and order by event receipt. |
| D3 | H | `channels/signing.py` | `hmac.compare_digest(str, str)` raises `TypeError` for a non-ASCII header value. A crafted `X-Osiris-Signature` returns 500 (not the generic 401) and is a tiny oracle. Compare bytes. |
| D4 | M | `channels/inbound.py` `_received` | Unsupported-message placeholder is hard-coded Arabic for every channel (the `if channel in {...}` is always true). English-only tenants show Arabic text in the thread. Use the localized canned text by detected/bot language. |
| D5 | M | `channels/inbound.py` + `channel_chat_turn` | For `unsupported`, `_received` already sets `status = waiting_human`, so `channel_chat_turn` takes the `else` branch and never calls `start_handoff`. Handoff side effects (system message, inbox event, notification, analytics) probably never fire for unsupported messages. Verify with a test, then fix. |
| D6 | M | `channel_chat_turn` | Order of checks: when `ai_enabled` is false or the connection is paused the status is forced to `waiting_human` BEFORE the `mode == human` check, so every customer message on a human-handled thread flips it back to `waiting_human`. Human mode must win. |
| D7 | M | `channels/inbound.py` | `Message.created_at` is taken from Many's `received_at`. A skewed or wrong clock reorders the thread and the AI history. Clamp to `[now-24h, now+5min]`, else use now. |
| D8 | M | `channels/outbound.py` | After Many's `202`, `delivery_status` stays `pending` until a callback. If Many never sends `sent` (see C2) the message shows a clock forever. Add a sweep: pending with a Many id and no status after 15 min becomes `unconfirmed` (neutral in the UI); a later real status overrides it. |
| D9 | M | `channels/config.py`, `outbound.split_reply` | Limits are characters. Instagram DM text is limited in UTF-8 BYTES (1000, verify in current Meta docs). Arabic is 2 bytes per character, so 1000 chars is ~2000 bytes and fails. Split by bytes for Instagram (<= 900). |
| D10 | M | pipeline | No loop or flood guard. A customer-side auto-responder or another bot creates an endless AI-to-bot loop; the busy/quota reply is also sent on every inbound while over quota. Add a per-contact inbound throttle (default 15/min: store, no AI) and at most one busy reply per conversation per 10 minutes. |
| D11 | L | `channels/inbound.py` | Contact name/phone is only set at creation; later events never refresh them. Also two connections to the same Many channel ref are allowed. Add a unique (channel, many_channel_ref) among non-revoked. |
| D12 | L | `channels/router.py` | `status` change `resume` from `paused` restores `active` but nothing re-queues messages that failed `connection_paused`. This is per contract (no auto-resend), but the inbox should offer "resend" for those. |
| D13 | L | docs | ADR-020 (health degradation model) still awaits owner sign-off. |

What is solid and should be kept as-is: HMAC signing with 5-minute skew and dual-secret rotation window; generic 401; 64 KB cap; (connection_id, event_id) dedupe with `202 duplicate`; tenant derived only from the connection; `begin_nested` + `enqueue_job` atomicity; DNS-pinned outbound with no redirects and global-IP-only targets; Fernet/MultiFernet secrets with a production startup guard, not in repr/logs/exports; monotonic delivery ranking; health mapping with stale handling; route-matrix classification; tenant A/B tests; fake Many.

## 4. Contract gaps found by reading the Many code

The contract and `MANY-AGENT-PROMPT.md` were written without seeing the details of Many's handlers. Findings (Many `main`, `backend/app/workers/tasks.py` and services):

| # | Finding | Impact |
|---|---|---|
| C1 | The old Many prompt says "after the inbound message is stored, enqueue a forward task". But Many gates inbound text BEFORE `_dispatch_*`: `account.ai_enabled`, `ai_cold_dm_enabled`, `campaign.ai_enabled`, `lead_source` checks, WhatsApp `account.status != connected`, and consent-command handling. All of them `continue` before storing anything. | "Forward every inbound message regardless of AI flags" is impossible with the hook where the prompt put it. The delegation branch must sit right after identity resolution and before those gates. |
| C2 | Only WhatsApp has delivery statuses (`process_whatsapp_status_events`). Instagram and Facebook paths have only the Send API result (`provider_message_id`, success/fail); no delivered/read parsing exists. | Contract §4.2 implicitly assumed all three. Many must at least emit `sent`/`failed` for IG/FB; delivered/read only where the platform webhook exists. The SaaS must not wait forever (D8). |
| C3 | `classify_meta_error` is keyword based and English only, with no window concept. Messenger window errors (code 10) are classified as `permission_error`. | The old prompt says "reuse classify_meta_error"; it cannot produce `window_closed`/`template_required`. Many needs a code+subcode table (see delta A3). |
| C4 | Many creates its `Conversation` row only inside `_dispatch_*`, after the gates. `external_conversation_id` must exist before forwarding. | Define it as Many's conversation id and create it first (delta A6). |
| C5 | Many follow-gate postbacks (`FOLLOW_CHECK:*`), WhatsApp consent commands (STOP/START) and echoes are Many automation traffic, not customer questions. | The "forward EVERY inbound message" wording would send these to the bot. Delta A5 defines exactly what is and is not forwarded. |
| C6 | Many has per-platform copies of the turn handler and a 3000-line `tasks.py`; Instagram is live and tested by the owner. | Minimal, shared helper; no refactor of live handlers beyond one early branch. |
| C7 | `backend/tests/conftest.py` runs `drop_all()` at session end against `TEST_DATABASE_URL or settings.DATABASE_URL`. A tracked `popeye access token.txt` still sits in the repo root. | A cloud session must set a disposable `TEST_DATABASE_URL` explicitly. Rotate and purge the token file (owner action, not the agent's). |
| C8 | Many has no CLAUDE.md/AGENTS.md. | Add one in the first commit of the Many branch (rules are in `MANY-CLOUD-PROMPT.md`). |

## 5. Integration gaps (things built after Phase 6 that the channels must connect to)

1. Knowledge and RAG: channel answers must go through the same `chat_answer` path as the widget so they inherit R1 to R3 hardening, thresholds, routing, bot tone/rules/assistant name (migration 0019) and language behaviour. Fixed by S3.
2. DM style: WhatsApp/Instagram/Messenger do not render markdown or citation markers. Add a channel output sanitizer (strip markdown, no source links unless the bot config allows) and a short per-channel style hint (docs/19 §8, still missing).
3. Conversations module (B5): channel badge and filter, connection name, "From campaign", delivery state per message and the paused composer must be rebuilt inside the new Inbox/History tabs.
4. Insights/dashboards (B3/B4): `conversations_by_channel` already exists on main (`analytics/handoff.py`); reuse the B3 backend and B4 charts for the per-channel breakdown instead of a second implementation.
5. Overview plan-usage meters (B4): the `channel_connections` meter must use the real count (non-revoked connections) the branch already computes.
6. Staff organization workspace (S1 to S4): Channels management belongs there (per organization), with the global list as a staff overview.
7. Contacts/CRM: channel column/filter, identities per connection; explicit merge only (already designed).
8. Retention, export and tenant deletion: connections and events covered (done on the branch; re-verify after rebase).

## 6. Test status honesty

The branch's PROGRESS.md records green runs (512 API tests, 66 Playwright). I did not re-run anything in this review. After the rebuild, only fresh runs count, recorded in PROGRESS.md with exact commands.
