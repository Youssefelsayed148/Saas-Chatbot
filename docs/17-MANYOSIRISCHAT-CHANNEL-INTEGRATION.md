# ManyOsirisChat channel integration (ADR-002, ADR-017) — built in P6
## Roles
- **This SaaS** owns the bot, knowledge, conversations, inbox, handoff, contacts/CRM and follow-up scheduling for every linked channel.
- **ManyOsirisChat (Many)** owns everything Meta: app credentials and tokens, webhook verification, WhatsApp 24-hour window, approved templates, opt-in rules, delivery to the user's phone. It stays a separate app and database. This repo never stores Meta tokens and never reads Many's database.
- Assumption to confirm when Many's side is designed: a Many channel linked to this SaaS runs in **delegated mode** — Many forwards inbound messages and sends outbound ones, but runs no bot and no human takeover of its own for that channel.

## Connection (explicit, staff-created)
A `channel_connection` links one SaaS tenant + bot to one Many channel (WhatsApp number / Messenger page / Instagram account). Created by platform staff or the owner with staff approval; never inferred from email or domain. It has `connection_id`, `channel`, Many base URL, a per-connection signing secret (shown once, stored encrypted, rotatable) and a status (active/paused/revoked). Pausing a connection stops AI replies and outbound sends for it.

## Signing (both directions)
Headers: `X-Osiris-Connection: <connection_id>`, `X-Osiris-Timestamp: <unix seconds>`, `X-Osiris-Signature: sha256=<hex HMAC-SHA256(secret, timestamp + "." + raw_body)>`. Reject if the timestamp is more than 5 minutes off, the signature is wrong (constant-time compare), or the connection is not active. Every event carries an `event_id`; the receiver dedupes on (connection_id, event_id).

## Many → SaaS: `POST /api/channels/manyosiris/events`
Responds `202` immediately; processing runs as a job.
- `message.received`: `event_id, connection_id, channel, external_contact_id, contact{name?, phone?, handle?}, external_conversation_id, external_message_id, type ("text" | "unsupported"), text?, received_at, window_expires_at?`
- `message.status`: `event_id, external_message_id (or our message_id), status (sent|delivered|read|failed), error_code? (e.g. window_closed, template_required, recipient_unreachable), occurred_at`
- Out-of-order or duplicate events are harmless (idempotent); status never moves backwards (read > delivered > sent).
- v1 handles text only. `unsupported` (voice, image, etc.) gets a localized "text only" reply and is flagged for a human.

## SaaS → Many: `POST {many_base_url}/api/saas/messages`
Body: `message_id` (our id = idempotency key), `connection_id`, `external_contact_id`, `external_conversation_id`, `text`, `kind` (reply | agent | followup | broadcast), `template_ref?`, `variables?`. Many answers `202` with its own id; the final outcome arrives as `message.status`. Retries use exponential backoff and the same `message_id`. Many enforces the window and templates: outside the window without a template, status is `failed` with `window_closed`/`template_required`; the SaaS shows this in the inbox and does not retry blindly.

## Identity and data
`contact_identities(contact_id, channel, external_id)` is unique per (tenant, connection, external_id). A WhatsApp phone and a website lead may be merged into one contact only by an explicit action (or an exact verified phone/email match the owner enabled). Opt-in/consent for follow-ups and broadcasts is recorded per contact and channel; Many enforces Meta policy, the SaaS refuses to send to contacts without recorded opt-in.

## What Many must provide (separate workstream in the Many repo)
Delegated-mode flag per channel; event forwarding to the SaaS endpoint with signing; an inbound endpoint for outbound messages; status callbacks; window/template enforcement and error codes. The SaaS side is contract-tested against a fake Many (P6-05); the real end-to-end test runs in staging with a test number and needs the owner's approval.

## Out of scope
Meta app review, webhook verification, token storage, template creation/approval UI (all Many). Voice/image/media in v1. Shared tenant identity or shared database with Many. Billing coupling.
