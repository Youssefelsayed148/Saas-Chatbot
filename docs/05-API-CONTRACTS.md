# Proposed REST API contracts (to finalize before implementing endpoints)
JSON error: `{ "error": {"code":"FORBIDDEN","message":"...","request_id":"..."}}`; 400 validation, 401 unauthenticated, 403 unauthorized, 404 hidden tenant resource, 409 conflict, 422 invalid input, 429 limit, 503 dependency.
| Method/path | Auth | Intent |
|---|---|---|
| GET /api/v1/auth/config | public | Feature flags for the web UI (`self_serve_signup`, default false) |
| POST /api/v1/auth/register, /login, /logout | public/session | Auth lifecycle; with the flag off, register requires a valid invitation token (403 `INVITATION_REQUIRED`) |
| POST /api/v1/auth/change-password | session + CSRF | Verify current password (400 `INVALID_CURRENT_PASSWORD`), reject unchanged password (400 `PASSWORD_UNCHANGED`), apply the shared password policy (422), rotate the presented session, revoke all OTHER sessions, audit `auth.password_changed` |
| GET /api/v1/me | session | User + memberships |
| GET/POST/DELETE /api/v1/tenants/{tenant_id}/invitations ; POST /api/v1/invitations/accept | admin ; accept = session + token | Team invitations by one-time link. Invitations target EXISTING users only: creating an invitation for an unknown email returns 404 `USER_NOT_FOUND` (staff create accounts first); accept requires a signed-in user with the matching email (docs/14 §19) |
| GET/PATCH/DELETE /api/v1/tenants/{tenant_id}/members | admin+ | List, change role, remove |
| POST /api/v1/tenants | session | Create organization |
| GET /api/v1/tenants/{tenant_id} | member | Tenant details |
| GET/POST /api/v1/tenants/{tenant_id}/bots | member editor+ for POST | Bot listing/create |
| GET/PATCH/DELETE /api/v1/tenants/{tenant_id}/bots/{bot_id} | role-based | Bot lifecycle |
| POST /api/v1/tenants/{tenant_id}/provisioning | platform staff | Shared onboarding request; Idempotency-Key |
| GET /api/v1/tenants/{tenant_id}/provisioning/{id} | authorized | Progress |
| POST /api/v1/tenants/{tenant_id}/bots/{bot_id}/sources | editor+ | Add source |
| POST /api/v1/tenants/{tenant_id}/bots/{bot_id}/ingestion | editor+ | Start job |
| POST /api/v1/tenants/{tenant_id}/bots/{bot_id}/sources/files | editor+ | Upload PDF/DOCX/TXT/MD/CSV (multipart) |
| GET /api/v1/tenants/{tenant_id}/bots/{bot_id}/sources/qa-template | editor+ | Q&A CSV template |
| POST .../bots/{bot_id}/sources/files (dedupe, H2) | platform staff | A file whose sha256 matches a live source of the same bot stores nothing and returns that source with `duplicate: true` and a `message`; 200 when every file was a duplicate, else 201 |
| POST .../bots/{bot_id}/sources/{source_id}/replace (H2) | platform staff | Multipart `file`; same source id, new bytes, status `stored`; identical bytes return `duplicate: true`; ingest again to apply to the draft; 409 `SOURCE_BUSY` while queued |
| DELETE .../bots/{bot_id}/sources/{source_id} (H2) | platform staff | 204. Removes the source's documents/chunks from the DRAFT revision, marks it `removed` (404 afterwards), deletes the stored file, audit `knowledge.source_removed`. Published/archived revisions are untouched until publish |
| PUT .../bots/{bot_id}/sources/{source_id}/always-include (H2) | platform staff | Body `{enabled}`; stored as `config.always_include_source_ids` (max 3 live sources of the bot). Also settable through PATCH bot `config.always_include_source_ids` (422 for unknown/foreign/over-cap ids) |
| POST /api/public/v1/sessions/{session_id}/messages/{message_id}/feedback | session capability | Thumbs up/down |
| GET /api/v1/tenants/{tenant_id}/bots/{bot_id}/analytics/{summary,volume,top-questions,unanswered,leads} | member | Measured analytics. `top-questions` and `unanswered` group near-duplicates (case, whitespace, trailing `? ؟ ! .`, Arabic diacritics/alef/yaa/teh-marbuta); the grouping key is never shown, the display text is the most recent original, counts are summed, response shape unchanged (UI polish B3) |
| GET /api/v1/tenants/{tenant_id}/analytics | viewer+ | Website handoff analytics (`from`/`to`, default last 30 days). Additive `previous` block: `{from, to, total_conversations, handoff_count, handoff_rate (null when 0), average_first_human_reply_seconds (null when none)}` for the equal-length window ending the second before `from` (B3) |
| GET /api/v1/tenants/{tenant_id}/analytics/timeseries | viewer+ | `{from, to, days:[{day, conversations, handoffs, resolved}]}`: one row per UTC day of the window, zero-filled, ascending; website source only (playground never counts); a window over 366 days or invalid dates is 422 `VALIDATION_ERROR` (B3) |
| GET /api/v1/tenants/{tenant_id}/quota | member | Plan usage snapshot. `warnings` = counters at >=80% of a limit (including at the limit); additive `at_limit` = the subset with used >= limit, so the rest are only approaching. `measured_tokens_this_month` = tenant-wide, provider-reported chat tokens on message events this month (excludes embeddings and unreported usage). It is NOT the per-bot AI limit counters `monthly_tokens` / `monthly_embedding_tokens` (`.../bots/{bot_id}/rag/limits`, staff): those sum `ai_usage` ledger events of every type, counting embedding tokens in both counters and counting unreported usage at its conservative reserved bound. They are expected to differ (B3 / BE-5) |
| POST /api/v1/tenants/{tenant_id}/bots/{bot_id}/revisions/{id}/publish | admin+ | Publish knowledge |
| GET /api/public/v1/widgets/{locator}/config | public | Safe public config only |
| POST /api/public/v1/widgets/{locator}/sessions | public + abuse controls | Session |
| POST /api/public/v1/sessions/{session_id}/messages | session capability | Chat |
| GET /api/v1/tenants/{tenant_id}/inbox | member | Inbox/History list: filters `status mode channel assignee tag unread q`, plus `created_from`/`created_to` (inclusive UTC calendar dates, 422 if malformed) and `limit`/`offset`. Response `{conversations, total, limit, offset}`; `total` counts every match before paging. Each row: `id bot_id contact_id contact_name (null when no contact) created_at channel mode status assigned_user_id handoff_reason last_message_at last_message unread_count tags` (B3) |
| GET /api/v1/tenants/{tenant_id}/inbox/stream | member | SSE live updates, resumes via Last-Event-ID (P5) |
| GET/POST /api/v1/tenants/{tenant_id}/conversations/{id}, /messages | member; reply editor+ | Thread, agent reply (P5) |
| POST /api/v1/tenants/{tenant_id}/conversations/{id}/{takeover,return-to-ai,resolve,assign} | editor+ | State changes; 409 if already owned (P5) |
| POST /api/v1/tenants/{tenant_id}/conversations/{id}/notes, tags | editor+ | Internal notes and tags (P5) |
| GET/POST/PATCH /api/v1/tenants/{tenant_id}/contacts, /contacts/{id}, POST /contacts/{id}/merge, GET /contacts.csv | member; writes editor+ | Light CRM (P5) |
| POST/GET /api/v1/tenants/{tenant_id}/followups | editor+ | Schedule/list follow-ups (P5) |
| GET /api/public/v1/sessions/{session_id}/messages?since=cursor | session capability | Widget polls for agent replies (P5) |
| POST /api/channels/manyosiris/events | HMAC signature (no cookie) | Inbound Many events, 202 then job (P6) |
| GET /api/v1/tenants/{tenant_id}/channels | member | Read-only connected channels for client roles: channel, display name, status, health (stored state, or `unknown/stale` after 15 minutes without a signal), last event. No Many URL, reference or secret |
| GET/POST /api/v1/platform/channel-connections ; GET/PATCH /{id} ; POST /{id}/{pause,resume,revoke,rotate-secret,check-health} | platform staff + CSRF | Staff channel management. The signing secret is returned once (create, rotate). 409 `CHANNEL_REF_IN_USE` when a non-revoked connection already uses the same `(channel, many_channel_ref)`. Audited |
| POST /api/v1/tenants/{tenant_id}/conversations/{id}/messages/{message_id}/resend | editor+ | Send again a channel message that failed with `connection_paused`: 404 missing, 409 `NOT_RESENDABLE` (any other message), 409 `CONNECTION_PAUSED` (connection not active). Adds a system message and audit `message.resent` |
| Inbox list/thread additions (P6) | member | Channel rows carry `connection_name`, `connection_status`, `campaign_name` (origin); thread detail also `contact_name`; channel AI/agent messages carry `delivery_status` (`pending`,`sent`,`delivered`,`read`,`failed`,`unconfirmed`) and `error_code` from a closed set |
| GET /api/v1/platform/tenants, /tenants/{id} | platform staff | Client list (search/status/pagination) and detail with counts, per-bot summaries, members, invitations, audit (P4-06) |
| POST /api/v1/platform/tenants; PATCH /api/v1/platform/tenants/{id} | platform staff + CSRF | Create organization; update name/status (S1); audited |
| PATCH /api/v1/platform/tenants/{id}/plan, /quota-overrides | platform staff + CSRF | Assign plan label / override limits; reason required; audited (P7) |
| GET/POST /api/v1/platform/users | platform staff | Client-user directory (search, organization/active filters); create user with staff-set OR generated password (shown once) (S2) |
| GET /api/v1/platform/users/{id} | platform staff | User detail with memberships (S2) |
| POST/PATCH/DELETE /api/v1/platform/users/{id}/memberships… | platform staff + CSRF | Assign membership, change role, remove; seat quota and last-admin rules apply; audited (S2) |
| POST /api/v1/platform/users/{id}/password | platform staff + CSRF | Staff password reset (set or generate); revokes ALL user sessions; audited (S2) |
| POST /api/v1/platform/users/{id}/deactivate, /reactivate | platform staff + CSRF | Set `users.is_active`; deactivation revokes all sessions; audited (S2) |
| GET/POST /api/v1/platform/bots | platform staff | Global bot list (search, organization filter, summaries) and create bot in an organization (S3) |
| POST /api/v1/platform/bots/{bot_id}/pause | platform staff, reason required | Pause a bot across organizations; audited (P7) |
| DELETE /api/v1/platform/tenants/{tenant_id}/bots/{bot_id} | platform staff | Archive a client bot from the organization detail; audited (S3) |
| POST /api/v1/platform/onboarding | RETIRED (S3) | Legacy staff onboarding form; the durable `ProvisioningService` remains for the flagged-on self-service path; historical GET `/onboarding/{id}` and `/onboarding.csv` remain |
| GET /api/v1/platform/{jobs,connections,analytics,audit} ; POST /api/v1/platform/{bots,connections}/{id}/pause | platform staff, reason required | Advanced operations (P7) |

## Contracts must include
Request/response schemas with example, pagination, ownership checks, idempotency, validation, side effects and stable error codes. Define CSRF protection for cookie auth, secure cookie settings, CORS, rate limits, and origin checks. Public locator is NOT an authentication secret. The inbox, CRM and channel routes are proposals until P5/P6 start. Phase 1 freezes only auth, tenants, bots and platform listing contracts; later routes remain proposals.

## Error codes added by the account/administration slices (S1–S4)
`USER_NOT_FOUND` (404, invitation for an email with no account — staff create accounts first); `INVALID_CURRENT_PASSWORD` (400, change-password verification failure, throttled per user after 5 failed attempts in a 300 s window with 429 `RATE_LIMITED`); `PASSWORD_UNCHANGED` (400, new password equals current). Password-change failures never reveal whether an account exists beyond the caller's own session; policy failures remain 422 `VALIDATION_ERROR`.
