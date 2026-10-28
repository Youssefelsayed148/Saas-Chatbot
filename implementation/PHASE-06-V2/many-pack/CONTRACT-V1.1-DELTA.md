# Contract v1.1 delta (amends docs/17 v1)

Status: ADOPTED 2026-10-26 as ADR-023 (the owner approved it by issuing the rebuild prompt; ADR-021 is a different decision) and merged into docs/17 section 11. Where this delta and docs/17 v1 differ, this delta wins. Anything not mentioned stays as in v1.

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

A14. Review fixes (2026-10-27, batches 2-5; additions, nothing above is relaxed).
- Retention: `channel_events.payload` is purged (set to NULL) at the tenant's message-retention cutoff; the dedupe record (connection_id, event_id) is deleted once it is older than that cutoff and 30 days. A duplicate `event_id` inside the 30 days is still answered `202 duplicate`.
- Origin caps are enforced: `campaign_name` <= 120, `opening_message_text` <= 2000, `campaign_ref` <= 128, all strings; otherwise a signed `422`. Only these fields (and `type`) are stored. The opening message reaches the bot as untrusted, fenced context (<= 500 characters) and cannot override the system prompt.
- Many must not compress the `202` body (the SaaS sends `Accept-Encoding: identity`; a compressed body is still decoded, capped at 64 KB). Many's `Retry-After` is honoured up to 300 s. The health response is capped at 64 KB.
- A pushed `channel.status` with `occurred_at` in the future counts as "now" (like a pull with a future `checked_at`), so it cannot shadow later signals. `received_at` stays clamped to `[now-24h, now+5min]`.
- SaaS-local delivery errors outside the Many enum: `connection_paused` (resendable), `connection_revoked`, `secret_unavailable` (stored secret cannot be decrypted; operator action), `many_unreachable`, `many_auth_rejected` (A15), `invalid_many_target`.
- Rotating the secret a second time inside the 24 h window keeps only the newest and the immediately previous secret: the original stops verifying at once (this is the emergency-rotation behaviour).
- Known limitations: the unauthenticated events route does one connection lookup before any throttle; a failed rollback of migrations 0023/0024 is expected once channel data exists (the rollback plan is to pause the connection, docs/16).

A15. Retryable 401 and rotation runbook (2026-10-27, ADR-024, owner-assumed default). Secret rotation skews the two sides for a short time, so a `401` from the receiver is retryable for the sender.
- SaaS to Many: HTTP `401` is a retryable failure inside the existing 6-attempt budget (same backoff, about 9 minutes in total). If every attempt is rejected the message fails with the SaaS-local code `many_auth_rejected` (not `many_unreachable`) and the connection health becomes degraded with that reason. The same label applies when the budget ends on a transient failure but any earlier attempt of that message saw a `401` (for example `401` then five timeouts, or five timeouts then `401`): a `401` is the actionable signal (the secrets differ) and a later timeout must not hide it. The sender remembers it in the send job and forgets it when the message is sent again. A budget with no `401` at all stays `many_unreachable`. All other `4xx` (403, 404, 422, ...) stay permanent (`many_http_NNN`, or the Many `error_code` when it is in the enum).
- Many to SaaS: Many retries a `401` from the SaaS inside its 24 h budget (A7).
- Rotation runbook: (1) pause the connection in the SaaS (inbound is still stored, nothing is sent); (2) rotate the secret in the SaaS; (3) enter the new secret in Many; (4) resume the connection. A send that still sees `401` while the two sides differ is retried for about 9 minutes; after that it fails with `many_auth_rejected` and can be sent again once both sides match.

A16. End-customer erasure. Many may send `contact.erasure` to the existing
signed events endpoint. The version-1 envelope contains `event_id` (max 128),
`event_type: "contact.erasure"`, `connection_id`, `occurred_at` (UTC), and
`external_contact_id` (the same channel identity used by `message.received`).
It contains no separate name or phone field, message body, tenant id, or bot id. The connection
and identity fields are required; blank or malformed fields return 422.

Authentication, body-size limits, rotation, rate limits, and deduplication are
unchanged. The signed connection header and body must identify the same
connection. Tenant scope comes only from the authenticated connection.
Active and paused connections accept erasure; revoked connections retain the
existing generic 401 behavior and require operator handling.

The SaaS resolves the identity by `(connection.tenant_id, connection.id,
external_contact_id)`, never by a global external-id lookup. It erases that
contact and its messages and personal contact fields, purges stored event
payloads for that identity, and cancels pending channel jobs/sends associated
with the erased contact. If contacts were explicitly merged, the erasure
covers the resulting contact and its linked conversations/messages within
that tenant; it never affects another tenant. Conversation records retained
for accounting must contain no erased customer content or identity. Pending
pre-erasure inbound work must not recreate the erased content after completion.

Acceptance and durable job storage return `202 {"status":"accepted"}`;
duplicate acceptance returns `202 {"status":"duplicate"}`. Acceptance is not
proof that erasure has completed. A missing identity is an idempotent success.
Processing is transactional; transient processing failures use durable job
retries and must remain visible for operator remediation. Audit completion
without message bodies, external identifiers, or secrets. Retain the existing
event-id dedupe record for at least 30 days with its payload cleared.

Many erases the matching local customer data, raw webhook payloads and pending
ordinary forwards, and durably queues this event atomically. Its erasure event
must survive local customer deletion and remain sendable while delegation is
disabled, provided the connection's signing configuration remains available.
Use the existing signed forward retry policy (including the 24-hour budget);
exhaustion is an explicit operator-action failure, never reported as completed.
Never send a Meta message or generate an AI reply as part of erasure.

Until both sides are verified, use the documented operator process: erase in
Many, erase the tenant-scoped SaaS contact with `erase_messages=true`, purge
the identity's stored channel payloads, and record sanitized completion evidence.
