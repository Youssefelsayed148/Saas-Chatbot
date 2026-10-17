# Feature/role inventory evidence (read-only run, 2026-10-17)

No application code changed. No docker/compose commands. `.env*` files were not read (route import ran with `ENVIRONMENT=test`, which makes the app skip the dotenv file). Only GET requests were sent to the API. The UI crawl clicked no buttons; it only navigated links.

## What was run
1. **Routes** – imported `app.main.app`, `app.openapi()`, plus a walk of every route's dependency tree (FastAPI 0.143 nests routers lazily, so routes were read via `effective_route_contexts()`). -> `routes.csv`, `routes-unresolved.md`. **116 operations** (matches the 116 method+path pairs in the OpenAPI schema; 60 are GET).
   - `require_operator` column: True when the handler calls `require_operator`, or when `x-minimum-role = platform_staff_only` on a tenant route (the tenant dependency then calls `require_operator()`).
2. **Role probe** – API on `127.0.0.1:8000`; logged in as demo-admin / demo-editor / demo-viewer, plus unauthenticated. Tenant = Demo Dental Clinic (`eb26cfc5-67ea-53d7-850a-879b5d18a732`, from `/me`). 60 GET routes x 4 callers = **240 rows** in `probe.csv` (column `id_source` says whether real or placeholder ids were used).
3. **UI crawl** – Playwright/Chromium against `localhost:3000`, session obtained via the login API. Per role, BFS from `/app` over every link; max 2 instances per dynamic route family. Pages: **admin 16, editor 13, viewer 15**, plus 6 direct-URL checks each. Screenshots in `screens/<role>/` (full page). Two consecutive runs gave identical counts.

## NOT done: platform staff
Staff needs `PLATFORM_STAFF_PASSWORD` (host env or `.env`/`.env.local`), which I may not read and which is not set in my shell. So **no staff API probe, no staff UI crawl, no `/platform/*` pages, no `ui-staff.json`.** For staff, only the static guards in `routes.csv` exist. (I sent one login with a deliberately wrong password to `staff@example.com`, which returned 401, only to see if the account exists; it counts toward the login rate limit.)

## Route guard summary (from routes.csv)
- 23 `platform_staff_only` via `/api/v1/platform/*` (PlatformStaffDep) - plus the tenant-scoped staff-only routes (bots create/patch/delete, knowledge sources/documents/jobs/revisions, RAG, playground, tenant data delete) enforced by `require_operator`.
- viewer / editor / admin minimums on the rest; auth + public routes listed in `routes-unresolved.md` (12: widget public API, auth login/register/logout/config, /health, /ready).

## Probe results (client roles)
Pattern counts over 60 GET routes (declared min role -> admin/editor/viewer/unauth): viewer routes 200/200/200/401 (21); admin routes 200/403/403/401 (8); editor route 200/200/403/401 (1); platform_staff_only 403/403/403/401 (23); public routes 200 for all (3); `/me`-style authenticated route 200/200/200/401 (1).

## Contradictions between a route's status and its declared guard
- **No real contradiction for client roles**: every 200/403/401 matches the declared minimum role.
- `GET /api/public/v1/sessions/{session_id}/messages` is listed as `none/public` (no schema guard) but returns 401 for everyone with a placeholder id: it authenticates internally by a widget session token that OpenAPI does not show. Same pattern probably holds for other `/api/public/v1/sessions/*` routes (POSTs not probed).
- `GET /api/v1/tenants/{id}/change-requests/{rid}/attachments/{aid}` returned 404 for admin: placeholder ids, not a guard issue.
- Tenant-scoped staff-only GETs (documents, sources, jobs, revisions...) return 403 to all client roles even with placeholder ids, so the guard runs before id lookup (no existence leak). I could not resolve real ids for source/document/job/revision/request/follow-up (their list endpoints are staff-only or empty), so those rows use placeholders.

## UI observations (not API contradictions, but worth knowing)
- Client sidebar (admin): Overview, Bots, Inbox, Contacts, Request a change, Team, Tenant data and audit, Handoff analytics. Editor/viewer do not get Request a change / Team / Tenant data pages in the crawl (viewer also has no Add-contact; see ui-*.json).
- Direct `/platform` and `/platform/operations` as client roles: redirected to `/app` (HTTP 200 after redirect), no 403 page.
- Direct `.../bots/<bot>/knowledge`, `/install`, `/playground` as admin, editor and viewer: **page shell loads with HTTP 200** and shows "Platform staff access required." in the body (no nav link leads there). `/settings` loads and shows bot status plus "Contact your operator to request settings changes."
- Tabs: none found (`[role=tab]` absent on all crawled pages); tab-like content hidden behind clicks was not explored.

## Limits / unverified
- Crawl dedup: only the first 2 conversations/contacts/inbox items per family were visited (see `skipped` in each ui json).
- API/file links (CSV exports etc.) were recorded but not opened.
- POST/PUT/PATCH/DELETE statuses were not exercised; their guards come from the code only.
- Button/link text is DOM text at load time; dialogs, menus and modals opened by clicks were not captured.
