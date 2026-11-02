# REST API contracts

> **Status (2026-11-02):** the API is implemented. The tables below are the original design narrative, which covers roughly half of the operations. The **generated endpoint index at the end of this file lists every operation** and is authoritative together with the code and tests.

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

## Endpoint index (generated from the OpenAPI schema, 2026-11-02)
The tables above are the original design narrative. This index is generated from the application's OpenAPI schema and lists every operation it exposes: **152 operations**. Where it differs from the narrative, this index wins. Regenerate it with:
```sh
cd apps/api && ENVIRONMENT=test python -c "import app.main as m; import json; s=m.create_app().openapi(); [print(k.upper(), p) for p,v in s['paths'].items() for k in v]"
```

### Authentication (6)

| Method | Path | Handler |
| --- | --- | --- |
| POST | `/api/v1/auth/change-password` | `change_password` |
| GET | `/api/v1/auth/config` | `auth_config` |
| POST | `/api/v1/auth/login` | `login` |
| POST | `/api/v1/auth/logout` | `logout` |
| GET | `/api/v1/auth/me` | `me` |
| POST | `/api/v1/auth/register` | `register` |

### Channel contract (ManyOsirisChat) (1)

| Method | Path | Handler |
| --- | --- | --- |
| POST | `/api/channels/manyosiris/events` | `receive_channel_event` |

### Invitations and health (3)

| Method | Path | Handler |
| --- | --- | --- |
| POST | `/api/v1/invitations/accept` | `accept_invitation` |
| GET | `/health` | `health_health_get` |
| GET | `/ready` | `ready_ready_get` |

### Platform staff (40)

| Method | Path | Handler |
| --- | --- | --- |
| GET | `/api/v1/platform/analytics` | `platform_analytics` |
| GET | `/api/v1/platform/audit` | `platform_audit_review` |
| GET | `/api/v1/platform/bots` | `list_bots` |
| POST | `/api/v1/platform/bots` | `create_bot` |
| POST | `/api/v1/platform/bots/{bot_id}/pause` | `platform_pause_bot` |
| GET | `/api/v1/platform/change-requests` | `operator_change_queue` |
| PATCH | `/api/v1/platform/change-requests/{request_id}` | `triage_change_request` |
| GET | `/api/v1/platform/channel-connections` | `list_channel_connections` |
| POST | `/api/v1/platform/channel-connections` | `create_channel_connection` |
| GET | `/api/v1/platform/channel-connections/{connection_id}` | `get_channel_connection` |
| PATCH | `/api/v1/platform/channel-connections/{connection_id}` | `update_channel_connection` |
| POST | `/api/v1/platform/channel-connections/{connection_id}/check-health` | `check_channel_connection_health` |
| POST | `/api/v1/platform/channel-connections/{connection_id}/pause` | `pause_channel_connection` |
| POST | `/api/v1/platform/channel-connections/{connection_id}/resume` | `resume_channel_connection` |
| POST | `/api/v1/platform/channel-connections/{connection_id}/revoke` | `revoke_channel_connection` |
| POST | `/api/v1/platform/channel-connections/{connection_id}/rotate-secret` | `rotate_channel_secret` |
| GET | `/api/v1/platform/me` | `platform_me` |
| GET | `/api/v1/platform/onboarding.csv` | `platform_provisioning_csv` |
| GET | `/api/v1/platform/onboarding/{request_id}` | `platform_onboarding_status` |
| GET | `/api/v1/platform/operations/jobs` | `platform_job_health` |
| POST | `/api/v1/platform/operations/jobs/{job_id}/cancel` | `platform_cancel_job` |
| POST | `/api/v1/platform/operations/jobs/{job_id}/retry` | `platform_retry_job` |
| GET | `/api/v1/platform/quotas` | `platform_quotas` |
| GET | `/api/v1/platform/tenants` | `platform_tenants` |
| POST | `/api/v1/platform/tenants` | `platform_create_organization` |
| GET | `/api/v1/platform/tenants/{tenant_id}` | `platform_tenant_detail` |
| PATCH | `/api/v1/platform/tenants/{tenant_id}` | `platform_update_organization` |
| POST | `/api/v1/platform/tenants/{tenant_id}/bots` | `platform_create_bot` |
| DELETE | `/api/v1/platform/tenants/{tenant_id}/bots/{bot_id}` | `platform_archive_bot` |
| PATCH | `/api/v1/platform/tenants/{tenant_id}/plan` | `platform_assign_plan` |
| PATCH | `/api/v1/platform/tenants/{tenant_id}/quota-overrides` | `platform_quota_override` |
| GET | `/api/v1/platform/users` | `list_users` |
| POST | `/api/v1/platform/users` | `create_user` |
| GET | `/api/v1/platform/users/{user_id}` | `get_user` |
| POST | `/api/v1/platform/users/{user_id}/deactivate` | `deactivate` |
| POST | `/api/v1/platform/users/{user_id}/memberships` | `assign` |
| DELETE | `/api/v1/platform/users/{user_id}/memberships/{organization_id}` | `remove` |
| PATCH | `/api/v1/platform/users/{user_id}/memberships/{organization_id}` | `role` |
| POST | `/api/v1/platform/users/{user_id}/password` | `reset` |
| POST | `/api/v1/platform/users/{user_id}/reactivate` | `reactivate` |

### Provisioning (1)

| Method | Path | Handler |
| --- | --- | --- |
| POST | `/api/v1/provisioning/self-service` | `self_service_signup` |

### Public widget (8)

| Method | Path | Handler |
| --- | --- | --- |
| POST | `/api/public/v1/sessions/{session_id}/lead` | `session_lead` |
| GET | `/api/public/v1/sessions/{session_id}/messages` | `session_messages` |
| POST | `/api/public/v1/sessions/{session_id}/messages` | `send_message` |
| POST | `/api/public/v1/sessions/{session_id}/messages/stream` | `send_message_stream` |
| POST | `/api/public/v1/sessions/{session_id}/messages/{message_id}/feedback` | `session_feedback` |
| GET | `/api/public/v1/widgets/{locator}/config` | `widget_config` |
| GET | `/api/public/v1/widgets/{locator}/frame-ancestors` | `widget_frame_ancestors` |
| POST | `/api/public/v1/widgets/{locator}/sessions` | `create_session` |

### Tenant workspace (93)

| Method | Path | Handler |
| --- | --- | --- |
| POST | `/api/v1/tenants` | `create_tenant` |
| GET | `/api/v1/tenants/{tenant_id}` | `get_tenant` |
| PATCH | `/api/v1/tenants/{tenant_id}` | `update_tenant` |
| GET | `/api/v1/tenants/{tenant_id}/analytics` | `handoff_analytics` |
| GET | `/api/v1/tenants/{tenant_id}/analytics/timeseries` | `conversation_timeseries` |
| GET | `/api/v1/tenants/{tenant_id}/bots` | `list_bots` |
| POST | `/api/v1/tenants/{tenant_id}/bots` | `create_bot` |
| DELETE | `/api/v1/tenants/{tenant_id}/bots/{bot_id}` | `archive_bot` |
| GET | `/api/v1/tenants/{tenant_id}/bots/{bot_id}` | `get_bot` |
| PATCH | `/api/v1/tenants/{tenant_id}/bots/{bot_id}` | `update_bot` |
| GET | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/analytics/conversations.csv` | `analytics_conversations_csv` |
| GET | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/analytics/leads` | `analytics_leads` |
| GET | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/analytics/leads.csv` | `analytics_leads_csv` |
| GET | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/analytics/summary` | `analytics_summary` |
| GET | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/analytics/top-questions` | `analytics_top_questions` |
| GET | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/analytics/unanswered` | `analytics_unanswered` |
| GET | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/analytics/volume` | `analytics_volume` |
| GET | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/conversations` | `list_conversations` |
| DELETE | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/conversations/{conversation_id}` | `delete_conversation` |
| GET | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/conversations/{conversation_id}` | `conversation_detail` |
| GET | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/documents` | `list_documents` |
| GET | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/documents/{document_id}/chunks` | `list_document_chunks` |
| POST | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/ingestion` | `start_ingestion` |
| GET | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/jobs` | `list_jobs` |
| GET | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/jobs/{job_id}` | `get_job` |
| POST | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/jobs/{job_id}/cancel` | `cancel_job` |
| POST | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/jobs/{job_id}/retry` | `retry_job` |
| POST | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/messages/{message_id}/feedback` | `message_feedback` |
| GET | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/playground/conversation` | `playground_conversation` |
| POST | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/playground/conversation/new` | `playground_new_session` |
| POST | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/playground/messages` | `playground_turn` |
| POST | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/playground/messages/stream` | `playground_turn_stream` |
| GET | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/quota` | `bot_quota_status` |
| GET | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/rag` | `get_rag` |
| PATCH | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/rag` | `patch_rag` |
| POST | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/rag/backfill` | `start_backfill` |
| GET | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/rag/costs` | `get_costs` |
| GET | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/rag/traces` | `get_traces` |
| GET | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/readiness` | `get_readiness` |
| GET | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/revisions` | `list_revisions` |
| POST | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/revisions/{revision_id}/publish` | `publish_revision` |
| GET | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/sources` | `list_sources` |
| POST | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/sources/bulk-delete` | `bulk_delete_sources` |
| POST | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/sources/files` | `upload_sources` |
| GET | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/sources/qa-template` | `download_qa_template` |
| DELETE | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/sources/{source_id}` | `delete_source` |
| GET | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/sources/{source_id}` | `get_source` |
| PUT | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/sources/{source_id}/always-include` | `set_always_include` |
| POST | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/sources/{source_id}/replace` | `replace_source` |
| GET | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/tone-and-rules` | `get_tone_and_rules` |
| GET | `/api/v1/tenants/{tenant_id}/change-requests` | `list_change_requests` |
| POST | `/api/v1/tenants/{tenant_id}/change-requests` | `create_change_request` |
| GET | `/api/v1/tenants/{tenant_id}/change-requests/{request_id}/attachments/{attachment_id}` | `download_change_attachment` |
| GET | `/api/v1/tenants/{tenant_id}/channels` | `list_client_channels` |
| GET | `/api/v1/tenants/{tenant_id}/contacts` | `list_contacts` |
| POST | `/api/v1/tenants/{tenant_id}/contacts` | `create_contact` |
| GET | `/api/v1/tenants/{tenant_id}/contacts/export.csv` | `export_contacts` |
| GET | `/api/v1/tenants/{tenant_id}/contacts/stages` | `list_stages` |
| PATCH | `/api/v1/tenants/{tenant_id}/contacts/stages` | `rename_stage` |
| DELETE | `/api/v1/tenants/{tenant_id}/contacts/{contact_id}` | `erase_contact` |
| GET | `/api/v1/tenants/{tenant_id}/contacts/{contact_id}` | `get_contact` |
| PATCH | `/api/v1/tenants/{tenant_id}/contacts/{contact_id}` | `update_contact` |
| POST | `/api/v1/tenants/{tenant_id}/contacts/{contact_id}/merge` | `merge_contact` |
| GET | `/api/v1/tenants/{tenant_id}/conversations/{conversation_id}` | `conversation_detail` |
| POST | `/api/v1/tenants/{tenant_id}/conversations/{conversation_id}/assign` | `assign` |
| POST | `/api/v1/tenants/{tenant_id}/conversations/{conversation_id}/messages` | `agent_reply` |
| POST | `/api/v1/tenants/{tenant_id}/conversations/{conversation_id}/messages/{message_id}/resend` | `resend_message` |
| POST | `/api/v1/tenants/{tenant_id}/conversations/{conversation_id}/notes` | `add_internal_note` |
| POST | `/api/v1/tenants/{tenant_id}/conversations/{conversation_id}/resolve` | `resolve` |
| POST | `/api/v1/tenants/{tenant_id}/conversations/{conversation_id}/return-to-ai` | `return_to_ai` |
| POST | `/api/v1/tenants/{tenant_id}/conversations/{conversation_id}/takeover` | `takeover` |
| DELETE | `/api/v1/tenants/{tenant_id}/data` | `delete_tenant_data` |
| GET | `/api/v1/tenants/{tenant_id}/data/audit` | `tenant_audit_review` |
| GET | `/api/v1/tenants/{tenant_id}/data/deletion-preview` | `deletion_preview` |
| GET | `/api/v1/tenants/{tenant_id}/data/export` | `export_tenant_data` |
| GET | `/api/v1/tenants/{tenant_id}/follow-ups` | `list_follow_ups` |
| POST | `/api/v1/tenants/{tenant_id}/follow-ups` | `create_follow_up` |
| DELETE | `/api/v1/tenants/{tenant_id}/follow-ups/{follow_up_id}` | `cancel_follow_up` |
| GET | `/api/v1/tenants/{tenant_id}/inbox` | `list_inbox` |
| GET | `/api/v1/tenants/{tenant_id}/inbox/assignees` | `list_assignees` |
| GET | `/api/v1/tenants/{tenant_id}/inbox/counts` | `notification_counts` |
| GET | `/api/v1/tenants/{tenant_id}/inbox/events` | `stream_events` |
| POST | `/api/v1/tenants/{tenant_id}/inbox/{conversation_id}/read` | `mark_read` |
| POST | `/api/v1/tenants/{tenant_id}/inbox/{conversation_id}/tags` | `add_tag` |
| DELETE | `/api/v1/tenants/{tenant_id}/inbox/{conversation_id}/tags/{tag}` | `remove_tag` |
| GET | `/api/v1/tenants/{tenant_id}/invitations` | `list_invitations` |
| POST | `/api/v1/tenants/{tenant_id}/invitations` | `create_invitation` |
| DELETE | `/api/v1/tenants/{tenant_id}/invitations/{invitation_id}` | `revoke_invitation` |
| POST | `/api/v1/tenants/{tenant_id}/invitations/{invitation_id}/resend` | `resend_invitation` |
| GET | `/api/v1/tenants/{tenant_id}/members` | `list_members` |
| DELETE | `/api/v1/tenants/{tenant_id}/members/{user_id}` | `remove_member` |
| PATCH | `/api/v1/tenants/{tenant_id}/members/{user_id}` | `change_member_role` |
| GET | `/api/v1/tenants/{tenant_id}/quota` | `quota_status` |
