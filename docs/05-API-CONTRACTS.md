# Proposed REST API contracts (to finalize before implementing endpoints)
JSON error: `{ "error": {"code":"FORBIDDEN","message":"...","request_id":"..."}}`; 400 validation, 401 unauthenticated, 403 unauthorized, 404 hidden tenant resource, 409 conflict, 422 invalid input, 429 limit, 503 dependency.
| Method/path | Auth | Intent |
|---|---|---|
| POST /api/v1/auth/register, /login, /logout | public/session | Auth lifecycle |
| GET /api/v1/me | session | User + memberships |
| POST /api/v1/tenants | session | Create organization |
| GET /api/v1/tenants/{tenant_id} | member | Tenant details |
| GET/POST /api/v1/tenants/{tenant_id}/bots | member editor+ for POST | Bot listing/create |
| GET/PATCH/DELETE /api/v1/tenants/{tenant_id}/bots/{bot_id} | role-based | Bot lifecycle |
| POST /api/v1/tenants/{tenant_id}/provisioning | owner or platform staff | Shared onboarding request; Idempotency-Key |
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
| POST/GET /api/v1/tenants/{tenant_id}/channels/connections | owner/admin + staff approval | Link a bot to a Many channel (P6) |
| GET /api/v1/platform/tenants, /tenants/{id} | platform staff | Client list and detail (P4-06) |
| POST /api/v1/platform/onboarding | platform staff + Idempotency-Key | Staff onboarding via ProvisioningService; returns owner one-time invite link (P4-06) |
| GET /api/v1/platform/{jobs,connections,analytics,audit} ; POST /api/v1/platform/{bots,connections}/{id}/pause | platform staff, reason required | Advanced operations (P7) |

## Contracts must include
Request/response schemas with example, pagination, ownership checks, idempotency, validation, side effects and stable error codes. Define CSRF protection for cookie auth, secure cookie settings, CORS, rate limits, and origin checks. Public locator is NOT an authentication secret. The inbox, CRM and channel routes are proposals until P5/P6 start. Phase 1 freezes only auth, tenants, bots and platform listing contracts; later routes remain proposals.
