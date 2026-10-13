# P4-04 — Conversations view, leads → contacts with consent, retention

## Backend

- **Conversations views** (`app/conversations/router.py`): `GET …/bots/{bot}/conversations`
  (list with status filter, newest-first, message counts, contact name; playground threads
  excluded), `GET …/conversations/{id}` (thread within the retention window, citations
  title+source_url+page_ref) and `DELETE …/conversations/{id}` (editor+, explicit
  deletion of the thread AND its messages). Tenant-scoped 404 everywhere (tests: tenant-B
  computed UUIDs → 404 incl. DELETE; guessed ids → 404; viewer delete → 403, edit delete → 200
  with messages gone).
- **Lead capture** (docs/14 §14, §16): `POST /api/public/v1/sessions/{session_id}/lead`
  (capability token). `CONSENT_REQUIRED` (422) unless `consent_accepted` is true — NO
  contact write without explicit consent; a reachable channel (email or phone) required.
  Creates or updates ONE tenant contact (email match via citext, else phone match;
  website-sourced contacts refresh their display name from a later lead), records
  `consent.website {granted_at, text_version: "widget-lead/v1 2026-10"}` on the contact,
  binds the session as a `contact_identities` row (unique per tenant/channel/external id,
  deleted when the lead repeats binds the SAME contact), attaches the conversation to the
  contact, records an idempotent `lead` usage event. Tenant isolation asserted
  (shared email across two tenants → exactly one contact per tenant).
- **Retention** (docs/14 §7): migration `0005_retention_leads` adds
  `tenants.retention_days` (NULL = deployment default; CHECK 1–365).
  `PATCH /api/v1/tenants/{tenant_id}` (admin+, CSRF, audited) sets it; the
  retention purge now applies EACH tenant's own window (7-day tenant purges a
  10-day-old message, keeps a 5-day-old one) and also clears aged rate-limit
  windows. Widget conversations list exposes the setting in the UI (admin+).

## UI

- `/app/[tenant]/bots/[botId]/conversations` — read-only list (status, channel, lead,
  message count, delete for editor+), retention editor for admins.
- `/…/conversations/[id]` — thread with citations (title + source link) and
  needs-human notices.
- **Widget lead form** (frame page): named fields + the consent text (EN/AR) + checkbox;
  submit without consent shows the error and records NOTHING; success shows a
  confirmation. Server rules above make consent non-bypassable.

## Evidence

- `tests/test_conversations_view.py` — 5 passed (list/detail citations, playground
  exclusion, tenant-B/guessed 404 on GET+DELETE, viewer 403 vs editor delete + messages
  gone, retention round trip 403/200/422 + per-tenant purge windows).
- `tests/test_widget_leads.py` — 5 passed (consent required + reachable channel,
  create-with-conversation binding + consent JSON + identity, update-not-duplicate via
  citext email + name refresh, phone match, tenant isolation).
- Playwright `tests/conversations.spec.ts` — 1 passed: widget chat → lead form (empty
  consent rejected visually) → consent → dashboard list shows the thread; detail shows
  the lead name and 9:00 with citations. (Run per-ticket; the FULL Playwright suite runs
  at phase verification.)
- Backend batch after this ticket: ruff/format/mypy clean; related suites
  (widget/auth/bots/migrations/chat/startup/cross-script/appearance) — 90 passed.
