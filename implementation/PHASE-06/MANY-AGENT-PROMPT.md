# Agent prompt: ManyOsirisChat side of the SaaS channel integration (delegated mode)

Repo: ManyOsirisChat (Youssefelsayed148/ManyOsirisChat). Attach with the contract: docs/17-MANYOSIRISCHAT-CHANNEL-INTEGRATION.md (contract v1, from the SaaS repo). Paste everything below the line into the coding agent working in the MANY repo.

---

You are a senior engineer in the ManyOsirisChat repo (FastAPI + Celery + Next.js dashboard, Postgres, Alembic). Implement the Many side of contract v1: a per-channel "delegated mode" where the external SaaS generates the AI replies, and Many keeps everything Meta. Read the contract first; it is the source of truth for payloads, signing, retries and error codes.

WHAT STAYS UNCHANGED (do not touch): Meta tokens, OAuth/connect flows, webhook verification, campaigns, automations, comment-to-DM, templates, WhatsApp outreach, follow gates, consent/window services, dashboards and all existing routes. Many-only workspaces and channels (delegation off) must behave exactly as today.

WHAT CHANGES, only for a channel with delegation ON:
1. Reply generation is replaced by forwarding. Today each platform has its own turn handler in `backend/app/workers/tasks.py` (`_dispatch_ai_turn` for Instagram, `_dispatch_whatsapp_ai_turn`, `_dispatch_facebook_ai_turn`): they store the inbound message, check `conversation.status == "bot_active"`, then call `process_ai_conversation_turn` (gpt-4o-mini via `ai_service.py`). For a delegated channel, after the inbound message is stored, enqueue a forward task instead of the AI task. Do not call `ai_service` and never fall back to it, even when the SaaS is unreachable.
2. Forward EVERY inbound message of the channel (text and unsupported types), regardless of `ai_enabled` flags, turn limits, daily caps or `conversation.status`. Many's AI gates do not apply; the SaaS decides. Include `origin` (campaign_name, opening_message_text, campaign_ref) when the conversation came from a campaign.
3. Take Over / Resume Bot (`routes_conversations.py`, conversation_service hand_off/resume_bot): on a delegated channel, return 409 with a clear code and show "Managed in the SaaS inbox" in the dashboard. Hand-off state is owned by the SaaS.
4. New signed inbound endpoint `POST /api/saas/messages` (HMAC per contract section 3, 5-minute skew, constant-time compare, generic 401, 64 KB cap, dedupe on `message_id` for at least 7 days, respond 202 `{"id": ...}`), which sends through the EXISTING send paths (`send_direct_message`, WhatsApp `send_text_message`, Facebook `send_direct_message`) and respects the WhatsApp 24 h window and templates. Never accept a request for a channel that is not delegated or not linked to the given connection_id.
5. Delivery callbacks: send `message.status` events (sent, delivered, read, failed) to the SaaS, mapping Meta/WhatsApp errors to the contract codes (window_closed, template_required, recipient_unreachable, rate_limited, channel_disconnected, unknown). Reuse the existing status webhook handling (for example in `whatsapp_webhook_service.py`) and the existing `classify_meta_error`.
6. Health: send `channel.status` events on every transition (connected, token_expiring, token_expired, webhook_unhealthy, disconnected) and a heartbeat at least every 6 hours (Celery beat); expose signed `GET /api/saas/connections/{connection_id}/health`. Derive state from the existing token services and webhook health; do not invent new Meta calls beyond what exists.
7. Delegation config per channel (Instagram account, WhatsApp account, Facebook page): `saas_delegation_enabled` (default false), `saas_connection_id`, `saas_base_url`, secret (encrypted at rest using the app's existing secret handling; if none exists, STOP and ask), optional previous secret + expiry for rotation (accept either during the window, sign outbound with the new). Dashboard: a small settings section per channel to enable/disable and enter these values, show last forward status and queue depth. Disabling returns the channel to today's behavior immediately.
8. Forwarder: Celery task, signed POST to `{saas_base_url}/api/channels/manyosiris/events`; retry on network error, 5xx and 429 (honor Retry-After) with exponential backoff and jitter, same `event_id`, up to 24 hours; no retry on other 4xx (log, mark failed). Preserve per-conversation message order as far as practical (do not let a later message overtake an earlier one on retry). While retrying, report the channel as degraded in the dashboard.

HARD RULES
1. Work on a new branch `feature/saas-delegation` cut from main. Local commits, small, one concern each. Never push. No tags. No force operations.
2. Do NOT open, print, copy or commit the file `popeye access token.txt` in the repo root, or any .env/token/secret. If it holds a real token, tell the owner to rotate it and remove it from git history; do not do this yourself.
3. The Instagram path is live and tested by the owner. Any change that touches the Instagram dispatch/send code beyond adding the delegation branch requires the owner's confirmation first: STOP and ask. Prefer a shared helper that the three handlers call, but do not refactor the existing handlers beyond the minimal branch.
4. Add Alembic migration(s) after the current head (check `backend/alembic/versions`; the latest seen is 0022; note two files share the numbering gap 0016, so confirm the real head with `alembic heads`). Migrations must be reversible.
5. Tests: unit and integration tests with a FAKE SaaS server (verifies signatures, records requests, configurable responses). Cover: delegation off = unchanged behavior; delegation on = no AI call at all (assert `ai_service` never invoked), forward on every inbound, no fallback when the SaaS is down, retry/backoff/dedupe, signature rejection matrix, window_closed mapping, idempotent `/api/saas/messages`, health endpoint and heartbeat, Take Over blocked, rotation grace window. No real Meta or OpenAI calls. Do not run docker; the owner does.
6. Never fabricate results; report exact commands and outcomes. If the contract is unclear or contradicts the code, STOP and ask.

ORDER (one step per turn, report in five lines, wait for "continue"):
M-00 read-only: confirm branch, map the exact hook points (the three turn handlers, status webhook handlers, send paths, secret handling, Celery beat), run the baseline tests, list the files you will change.
M-01 delegation config model + migration + secret handling + dashboard settings.
M-02 signing module + forwarder task + inbound-message hook for each platform (Instagram last, after owner confirmation).
M-03 `POST /api/saas/messages` + send integration + idempotency.
M-04 `message.status` callbacks + error-code mapping.
M-05 `channel.status` events + health endpoint + heartbeat.
M-06 Take Over / Resume Bot guards + dashboard labels.
M-07 contract tests against the fake SaaS, rollback check (disable delegation = old behavior), short README section. STOP; the owner runs staging with one test number.

FIRST ACTION: M-00 only, and report.
