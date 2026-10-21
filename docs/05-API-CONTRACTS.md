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
| POST /api/public/v1/sessions/{session_id}/messages/{message_id}/feedback | session capability | Thumbs up/down |
| GET /api/v1/tenants/{tenant_id}/bots/{bot_id}/analytics/{summary,volume,top-questions,unanswered,leads} | member | Measured analytics |
| POST /api/v1/tenants/{tenant_id}/bots/{bot_id}/revisions/{id}/publish | admin+ | Publish knowledge |
| GET /api/public/v1/widgets/{locator}/config | public | Safe public config only |
| POST /api/public/v1/widgets/{locator}/sessions | public + abuse controls | Session |
| POST /api/public/v1/sessions/{session_id}/messages | session capability | Chat |
| GET /api/v1/tenants/{tenant_id}/inbox/conversations | member | Inbox list with filters/search (P5) |
| GET /api/v1/tenants/{tenant_id}/inbox/stream | member | SSE live updates, resumes via Last-Event-ID (P5) |
| GET/POST /api/v1/tenants/{tenant_id}/conversations/{id}, /messages | member; reply editor+ | Thread, agent reply (P5) |
| POST /api/v1/tenants/{tenant_id}/conversations/{id}/{takeover,return-to-ai,resolve,assign} | editor+ | State changes; 409 if already owned (P5) |
| POST /api/v1/tenants/{tenant_id}/conversations/{id}/notes, tags | editor+ | Internal notes and tags (P5) |
| GET/POST/PATCH /api/v1/tenants/{tenant_id}/contacts, /contacts/{id}, POST /contacts/{id}/merge, GET /contacts.csv | member; writes editor+ | Light CRM (P5) |
| POST/GET /api/v1/tenants/{tenant_id}/followups | editor+ | Schedule/list follow-ups (P5) |
| GET /api/public/v1/sessions/{session_id}/messages?since=cursor | session capability | Widget polls for agent replies (P5) |
| POST /api/channels/manyosiris/events | HMAC signature (no cookie) | Inbound Many events, 202 then job (P6) |
| POST/GET /api/v1/tenants/{tenant_id}/channels/connections | admin + staff approval | Link a bot to a Many channel (P6) |
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
