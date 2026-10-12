# P1-03 — Tenants, roles, bots + team management

Date: 2026-10-12. Status: IMPLEMENTED AND LOCALLY VERIFIED (Windows host + Linux container). Awaiting owner review as part of the P1 gate.

Branch: `feat/p1-01-foundation` (local commit only; no push/merge/deploy).

## Built

### Reusable tenancy dependency (`app/core/tenancy.py`)
`get_tenant_context` resolves `tenant_id` from the path, loads the tenant, verifies an **active** membership, and returns a `TenantContext` (db, user, tenant, membership) that every service takes. A nonexistent tenant **or** a tenant the caller is not a member of is indistinguishable → 404 `NOT_FOUND` (docs/06 hidden-resource rule). `context.require_role("editor"|"admin")` enforces the docs/06 matrix hierarchically (viewer 1 → editor 2 → admin 3 → owner 4).

### Tenants (`app/tenants/`)
- `POST /api/v1/tenants` — session + CSRF; creator becomes owner; unique slug (auto-generated from the name, collision-safe suffix; validated shape); audit `tenant.created`.
- `GET /api/v1/tenants/{tenant_id}` — member-only.
- `GET /api/v1/me` (auth router) returns active memberships with tenant name/slug/role.

### Team management (docs/14 §19, owner/admin)
- `POST /tenants/{id}/invitations` — email + role + expiry 1–30 days (default 7). Response carries the one-time link `/accept-invite?token=…` **once**; only the SHA-256 hash is stored. Admin cannot mint owner invitations (403). Inviting an existing active member → 409 `ALREADY_MEMBER`.
- `GET /tenants/{id}/invitations` — pending list, optional `expired` flag, no tokens.
- `POST /tenants/{id}/invitations/{id}/resend` — replaces the token hash (old token stops working), refreshes expiry; 409 if used/revoked.
- `DELETE /tenants/{id}/invitations/{id}` — revoke; 409 if already accepted/revoked.
- `POST /api/v1/invitations/accept` — session + CSRF + one-time token; requires the session email to equal the invitation email (403 `INVITEE_EMAIL_MISMATCH`); handles expired (409 `INVITATION_EXPIRED`), used (409 `INVITATION_USED`), revoked (409 `INVITATION_REVOKED`), unknown token (404).
- `GET /tenants/{id}/members` (admin+); `PATCH /tenants/{id}/members/{user_id}` (role change), `DELETE` (remove): non-owners never touch owner rows (403); granting owner needs owner (403); demoting the last owner or owner leaving/removing when sole owner → 403 `LAST_OWNER` (count checked on the server); with a second owner, transfers/step-down work. Every privileged write writes an audit row (`member.role_changed` with from/to, `member.removed`).

### Bots (`app/bots/`)
- `POST /tenants/{id}/bots` (editor+) — draft status, empty validated config; audit `bot.created`.
- `GET /tenants/{id}/bots?include_archived=` — default list hides archived bots.
- `GET /tenants/{id}/bots/{bot_id}` — any member; foreign/unknown ids are plain 404 (tenant-scoped read).
- `PATCH /tenants/{id}/bots/{bot_id}` (editor+) — rename and partial config merge validated by `BotConfig` (assistant/business name, description, welcome EN/AR, opening questions ≤10×120, default language en|ar, support email/phone, hex colour, colour position left|right, handoff toggle, allowed domains as hostnames; unknown fields/keys rejected 422). Archived bots cannot be edited (409 `BOT_ARCHIVED`). Audit `bot.updated` (fields list).
- `DELETE /tenants/{id}/bots/{bot_id}` — **soft archive** (idempotent): status → archived, row and config kept; audit `bot.archived`.

All cookie-authenticated writes (incl. every command above) require the `X-CSRF-Token` double-submit header.

### Error contract
`{error:{code,message,request_id}}` from `app/core/errors.py`; codes used here: `NOT_FOUND`, `FORBIDDEN`, `LAST_OWNER`, `ALREADY_MEMBER`, `BOT_ARCHIVED`, `INVITATION_USED/EXPIRED/REVOKED`, `INVITEE_EMAIL_MISMATCH`, plus generic auth/CSRF/validation codes from P1-02.

## Evidence — exact commands and results (from `apps/api`)

| Command | Result |
|---|---|
| `ruff check . --fix` → `ruff check .` | "All checks passed!" |
| `ruff format .` → `ruff format --check .` | "46 files already formatted" |
| `mypy` (strict) | "Success: no issues found in 46 source files" |
| `python -m pytest` | "61 passed, 1 warning in 8.67s" |
| `docker build --quiet --target checks -f apps/api/Dockerfile …` | Built |
| `docker run --rm --network saas-chats-ai-dev_default -e TEST_DATABASE_URL=…@db:5432/chatbot_dev saas-chats-ai-api-checks` | ruff/format/mypy green; "61 passed, 1 warning" |

61 tests include from P1-03: full role matrix (owner/admin/editor/viewer × tenants/members/invitations/bots with exact expected codes), tenant A/B guessed-UUID isolation across bots/members/invitations (404 everywhere, bot data never leaks), invitation lifecycle (create → link shown once → accept → single-use → expired/revoked/unknown rejected → resend replaces token → stale token 404), email-mismatch 403, admin cannot mint/escalate owners or remove owners, last-owner protection (self-demote/leave blocked; allowed with second owner), member removal + audit assertions, bot create/list/get/patch/archive with config validation and soft-archive semantics, CSRF requirement on every write, plus regression of all P1-02 tests.

## Design notes recorded
1. Membership `status='revoked'` reserved; removal deletes the row (unique pair allows re-invite later).
2. `resend` resets expiry to the default 7 days from now and is blocked for used/revoked invitations.
3. Archived-bot editing returns 409 `BOT_ARCHIVED` (specific and actionable), archive is idempotent 200.
4. Bot configuration keys follow docs/04 (validated by Pydantic `BotConfig`); appearance semantics (colours, greeting strings) are enforced purely as shapes in P1 — actual widget behaviour arrives in P4.

## Limitations
1. Hosted CI still unrun (no push authorization).
2. `GET /me` is implemented twice as internal builders (auth router and invitations accept) — same response model, no behavioural risk; will consolidate if it becomes a maintenance point.
3. No pagination on members/bots lists yet (MVP scale); docs/05 requires "contracts must include pagination" when lists grow — revisit at P4 with the client list.

## Files
Created: `apps/api/app/core/{tenancy,audit}.py`, `apps/api/app/tenants/{__init__,schemas,service,router,payloads}.py`, `apps/api/app/bots/{__init__,schemas,service,router}.py`, `apps/api/tests/{helpers,test_tenants,test_bots,test_invitations,test_members}.py`, this report.
Modified: `apps/api/app/main.py` (routers).

Next: P1-04 (dashboard UI + Playwright E2E).
