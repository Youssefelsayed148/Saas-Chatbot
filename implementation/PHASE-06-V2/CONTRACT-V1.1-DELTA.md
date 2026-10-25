# Contract v1.1 delta (amends docs/17 v1)

Status: PROPOSED 2026-10-26 from the Phase 6 review. Takes effect when the owner approves it (issuing the rebuild prompt counts as approval; record it as ADR-021 and merge it into docs/17 as part of ticket R-00). Where this delta and docs/17 v1 differ, this delta wins. Anything not mentioned stays as in v1.

A1. Channel must match. `message.received.channel` MUST equal the connection's channel. Otherwise the SaaS returns `422` (signed, malformed; Many must not retry).

A2. Status duty. After Meta accepts a message Many MUST send `message.status` `sent`; on rejection `failed` with an `error_code`. `delivered`/`read` only where the platform reports them (WhatsApp always; Messenger/Instagram only if Many subscribes to the receipts). The SaaS treats the `202` from `/api/saas/messages` as "accepted by Many", not "sent". A message with a Many id and no status for 15 minutes is shown as `unconfirmed` (neutral state); any later real status overrides it.

A3. Error codes. `error_code` enum gains `message_too_long`. Many maps Meta errors by code/subcode, never by message text (Meta localizes text). Starting table (VERIFY each against the current Meta docs before relying on it):
- WhatsApp: 131047 -> `window_closed`; 131026 -> `recipient_unreachable`; 130429/131056 -> `rate_limited`; template errors 132000-132015 and 131058 -> `template_required`; 190 -> `channel_disconnected`.
- Messenger/Instagram: code 10 with subcode 2534022 (outside allowed window) or 2018278 -> `window_closed`; code 100 with subcode 2018001 (no matching user) -> `recipient_unreachable`; codes 4, 17, 32, 613 -> `rate_limited`; 190, 102 -> `channel_disconnected`.
- Anything else -> `unknown`, with a short `error_detail` that contains no personal data.

A4. Length. The SaaS splits long replies per channel: WhatsApp and Messenger 1000 characters, Instagram 900 UTF-8 bytes (Instagram text is limited in bytes). Many must never truncate silently: if a message still exceeds the platform limit it fails permanently with `message_too_long`.

A5. What Many forwards. Forward every genuine customer DM of a delegated channel: free text and unsupported types (voice, image, sticker, etc). Do NOT forward Many-owned automation traffic: follow-gate postbacks/quick replies owned by Many flows, WhatsApp consent commands (STOP/START/opt-out keywords, handled by Many for compliance), echoes/own-page messages, delivery/read receipts, reactions. Placement in Many: after identity resolution and inbound storage, BEFORE any Many AI gate (`ai_enabled`, `ai_cold_dm_enabled`, `campaign.ai_enabled`, `lead_source`, turn limit, daily cap). Many's account `status != connected` still blocks (nothing can be sent anyway) and must be reported as degraded health.

A6. Identifiers. `external_contact_id` = IGSID / PSID / WhatsApp wa_id (stable per channel). `external_conversation_id` = Many's `conversations.id` as a string. Many creates or resolves the conversation row BEFORE forwarding, so the id exists. `external_message_id` = Meta's message id (`mid` / `wamid`), or Many's stable derived id when Meta provides none.

A7. Ordering. Many forwards events of one conversation in order: a retrying earlier message blocks later ones of that conversation (bounded by the 24 h retry budget; after that the earlier event is marked failed and the queue continues). The SaaS processes events of one conversation one at a time (row lock) in order of receipt.

A8. Loop and flood guard. SaaS: more than 15 inbound messages per minute from one contact on one connection are stored, flagged `waiting_human`, and get no AI reply; at most one busy/quota reply per conversation per 10 minutes. Many: never forward echoes or messages authored by the business itself.

A9. Health freshness. The SaaS 5-minute pull is the freshness source, so Many's signed health endpoint is mandatory (not optional). Many's push heartbeat (<= 6 h) and transition events remain. The SaaS stale threshold stays 15 minutes: with no event and no successful poll it shows `unknown/stale`.

A10. Clock safety. The SaaS clamps `received_at` to `[now-24h, now+5min]`; outside that range it uses its own receipt time.

A11. Campaign origin. WhatsApp: outreach campaign name and the rendered template body. Instagram/Facebook comment-to-DM: campaign name and the DM text Many delivered. `campaign_ref` stays opaque. Sent on every forwarded message of a campaign-origin conversation until the SaaS has stored it once (the SaaS keeps the first).

A12. Rotation (clarification). During the 24 h grace window each side accepts either secret on inbound and signs outbound with the NEW secret. Many stores current and previous secret with the previous expiry.

A13. Delegation off. Turning delegation off in Many returns the channel to today's behaviour immediately. Messages already queued for forwarding are dropped after the switch (logged), never sent to the SaaS afterwards.
