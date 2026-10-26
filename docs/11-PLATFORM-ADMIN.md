# Platform admin console — manage all clients (ADR-018)
Separate route group `/platform`, protected by the server-validated `users.is_platform_staff` flag (never a tenant role; non-staff get 403, unauthenticated 401). Any cross-tenant operation needs actor attribution and a reason where applicable. No impersonation and no arbitrary edits: staff actions run as the staff user and never borrow tenant roles; client users keep the ADR-009 role matrix inside their own organization. Built in S1–S3 of the account/administration slice (2026-10-21).

## Organizations (S1)
- **Organizations list** (`/platform`): every tenant with plan label (internal), status, bot count, seat count, message usage this month and last activity; search by name/slug, filter by status, pagination (`GET /api/v1/platform/tenants?q&status&limit&offset`).
- **Create organization** (`POST /api/v1/platform/tenants`): name + plan label; audited `platform.organization.created`.
- **Organization detail** (`GET /api/v1/platform/tenants/{id}`): counts (members, bots), placeholder quota view, per-bot summaries (status, published flag/widget state, source count, last ingestion job status, published revision), failed jobs, members, pending invitations, recent audit events.
- **Update organization** (`PATCH /api/v1/platform/tenants/{id}`): name/status; audited `platform.organization.updated`.
- **Plan and quota overrides** (`PATCH /api/v1/platform/tenants/{id}/plan`, `/quota-overrides`): reason required; audited.
- **Organization workspaces**: staff may open `/app/{tenant}` for any active organization (staff view of the client workspace; read/operate without membership, never impersonating a client user).

## Members (S2)
Staff-managed accounts: accounts are created by platform staff; there is no self-serve account creation unless the `self_serve_signup` flag is explicitly enabled (ADR-021). No email provider — passwords are set by staff or generated once and shown at issuance only.
- **Members directory** (`/platform/members`): all client users (`is_platform_staff = false`) with email, phone, active flag and memberships; search by email, filter by organization and active/inactive (`GET /api/v1/platform/users`).
- **Create user** (`POST /api/v1/platform/users`): email, optional international phone (`users.phone`), and EITHER a staff-set password OR `"generate": true` (random password shown once in the response, never stored in plaintext, never logged). Audited `platform.user.created`.
- **Assign membership** (`POST /api/v1/platform/users/{id}/memberships`): organization + role (admin/editor/viewer), seat quota enforced; audited `platform.user.membership_added`. Role change (`PATCH .../memberships/{org}`) and removal (`DELETE`, audited) reuse the tenant service with last-admin protection.
- **Password reset** (`POST /api/v1/platform/users/{id}/password`): staff-set or generated; stores the Argon2id hash and revokes ALL of the user's sessions; audited `platform.user.password_reset`.
- **Deactivate / reactivate** (`POST .../deactivate`, `.../reactivate`): sets `users.is_active`; deactivation revokes all sessions immediately (the user cannot sign in again while inactive); both audited.
- User detail and list responses never include password hashes; generated passwords are returned exactly once at issuance.

## Bots (S3)
- **Global bots list** (`/platform/bots`): every bot across organizations with per-bot summaries (knowledge source count, ingestion job status, revision/publication state) plus the owning organization; search by name, filter by organization, pagination (`GET /api/v1/platform/bots`).
- **Create bot** (`POST /api/v1/platform/bots`): organization + name, locked to an active tenant, bot quota enforced, public widget locator issued; audited `platform.bot.created`. The same `app/bots/factory.py::create_bot_record` backs every runtime creation path (staff global, organization detail, provisioning self-service).
- **Pause bot** (`POST /api/v1/platform/bots/{id}/pause`, reason required, audited `platform.bot.paused`); archive via organization detail (`DELETE /api/v1/platform/tenants/{tenant_id}/bots/{bot_id}`, audited `platform.bot.archived`).
- Knowledge upload/ingest/publish for a client bot runs through that bot's Knowledge tab in the organization workspace (staff or client admin/editor per ADR-009); the staff console surfaces job status and failure summaries.

## Operations, analytics and audit (P7, already built)
- **Operations** (`/platform/operations`): job queue health, retry/cancel job (reason, audited `platform.job.retry`/`platform.job.cancel`), pause bots.
- **Change requests**: triage queue for client-submitted requests (`platform/change-requests`, PATCH status).
- **Platform analytics** (`GET /api/v1/platform/analytics`): tenants, bots, conversations, messages, handoff rate, per-client usage.
- **Audit review** (`GET /api/v1/platform/audit?q=`): searchable audit trail. Built actions include: `platform.organization.created|updated`, `platform.user.created|membership_added|role_changed|membership_removed|password_reset|reactivated|deactivated`, `platform.bot.created|paused|archived`, `platform.job.retry|cancel`, `platform.tenant.plan_assigned|quota_override`, `auth.password_changed` (self-service password change, actor = the user), plus the historical tenant admin labels.

## Tests
Non-staff get 403 and unauthenticated 401 (tenant admin, tenant member and anonymous are covered); staff flag is separate from tenant roles; every staff write requires CSRF and writes an audit row with the staff actor; staff password reset and deactivation revoke the user's sessions; double submit of organization creation is guarded; cross-organization data never appears in another organization's lists.
