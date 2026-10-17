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

---
# Follow-up run: staff part (2026-10-17)

Staff login `staff@example.com` / `12345678` (throwaway dev credential supplied by the owner) returned **200** on the single attempt (`is_platform_staff: true`, **no memberships**; the Demo Dental Clinic tenant `eb26cfc5-...` was found via `GET /api/v1/platform/tenants`). Bot: `70417b12-544b-5480-b945-b5cfcecb4332`, widget locator `4a23ecbc913948dc83466ec4a5f301ba`. No application code changed, no docker, no `.env*` read, no push, no tags.

## New files
- `probe-staff.csv` - staff on all 60 GET routes (real ids where found): **57x 200, 2x 404, 1x 401**.
- `probe-realids.csv` - the 7 routes that used placeholder ids in `probe.csv`, re-probed for admin / editor / viewer / staff / unauthenticated (35 rows). Real ids now resolved for source, document, job, revision, bot, widget locator. **Still placeholder** (no such data exists in the demo tenant, or cannot be obtained without a POST): `request_id` (no change requests or onboarding requests exist), `attachment_id`, `follow_up_id` (none), widget `session_id` (needs a session token from a POST).
- `ui-staff.json` - staff crawl: **26 pages + 6 direct-URL checks**; screenshots in `screens/staff/` (33 files).
- `ui-clicks.json` - click pass for **staff (22 pages)** and **admin (members, data, requests)**; screenshots in `screens/*/clicks/ (filenames shortened: tenant -> T, bot -> BOT, ids -> first 8 chars, because of the Windows path limit)`.
- Updated: this README. Crawl dedup unchanged (max 2 instances per dynamic family; CSV/API links not opened).

## Staff probe vs guards: contradictions
**None.** Staff gets 200 on every `platform_staff_only` and tenant-scoped route that has data; admin/editor/viewer get 403 and unauthenticated 401 on the same routes with real ids (documents/chunks, jobs/{id}, sources/{id} re-checked with real ids; widget config is public and 200 for all). The staff 404/401 rows are expected: `/platform/onboarding/{request_id}` (no onboarding requests exist), change-request attachment (none exist), public session messages (needs a session token, authenticates internally as noted above).
Note: `/data/export` is declared `admin` and staff passes it (staff bypasses tenant role checks by design, `require_role`).

## Staff UI: what the requested pages show
- **`/app` empty state (staff has no membership):** heading "Your organizations", text "Your account needs an invitation to join an organization." Sidebar has two tabs: "Organizations" (-> `/app`) and "Platform admin" (-> `/platform`). Header still shows an "Organization / Switch organization" select (empty) and "Search pages".
- **"Platform admin" sidebar tab** is just a link to `/platform`. The platform area has its own sidebar ("Platform administration"): Clients (`/platform`), Change requests, Operations, "Client workspaces" (-> `/app`).
- **Clients page `/platform`:** "Platform - clients", "Platform staff console - Operations, analytics, and audit review", search + status filter (All/active/archived), table (Client, Plan, Status, Bots, Seats, Messages this month, Last activity) with one row "Demo Dental Clinic, business, active, 1, 3, 5", and an "Onboard a new client" form (Client name, Admin email (one-time invite link, no email), Bot name, optional website-to-knowledge skill files; button "Onboard client").
- **`/platform/clients/<id>`:** bots list with "Pause bot", plan assignment (plan label + reason, "Save plan"), quota overrides JSON ("Save override with reason"), failed jobs ("No failed jobs."), members, recent audit, links "Operate bots" and "Organization data and deletion".
- **`/platform/operations`:** provisional quota limits table (free/starter/pro/business), platform analytics, job queue (reembed_backfill, completed, Retry/Cancel disabled until a reason is typed), audit review search.
- **`/platform/change-requests`:** "Operator change queue - No change requests yet."
- **Bot pages for staff** have an extra bot sub-nav (Overview, Conversations, **Knowledge, Playground, Settings, Install**) that client roles do not get: Knowledge (upload/ingest, jobs, documents and chunks, published/draft knowledge), Playground (messages + answer traces), Settings (bot fields, allowed domains, Pause bot, AI tier Standard/Premium, retrieval mode, active embedding model, embedding backfill), Install (script tag, sample page link). The Analytics page additionally shows staff-only "AI costs and limits" with "Save AI limits" / "Reset to plan defaults".
- No `[role=tab]` elements exist anywhere (staff, admin, or client roles), so there are no tabs to open.

## Click-level pass (nothing submitted)
Every `POST/PUT/PATCH/DELETE` to `/api/` was aborted inside the browser (15 attempts blocked on the staff run, 2 on the admin run; none reached the server). Verified afterwards: the bot is still `active` (updated_at unchanged, `2026-10-15T11:11:29Z`) and the tenant still has 3 members.
- **Modals/dialogs found:** (1) the global "Go to a page" command palette (button "Search pages", Ctrl/Cmd-K) on every page; (2) contact detail "Erase contact" -> dialog "Erase this contact? ... Also erase messages in this contact's conversations - Cancel / Confirm erasure". Nothing else opens a dialog.
- **Destructive buttons with NO confirmation dialog** (they fire the request immediately; blocked here): members "Remove" (admin and staff), conversation "Delete" (bot conversations page, 6 rows), "Pause bot", "Start embedding backfill", "Save settings", "Save AI limits" / "Reset to plan defaults". Contact erase is the only one with a confirm step.
- Buttons that expand inline content: knowledge accordions (Opening hours / Pricing / Booking / Location); "Retry" on a completed knowledge job.
- Disabled until input: Upload, Ingest files, Send (playground), Create contact, Submit request, Merge into selected contact, Retry/Cancel on operations, Save override, Schedule organization deletion.

## Contradictions / side effects to flag
- **A GET has a write side effect:** `GET /api/v1/tenants/{id}/data/export` (and the UI "Download export" button) writes a `tenant.data.exported` audit row each time. My probes and click passes called it several times (visible in the tenant audit list at 2026-10-17 00:43, 01:03, 01:07, 01:11). These audit rows are the only database changes made by this inventory; the earlier "only GET" statement is true at the HTTP-verb level but the export GET is not side-effect free.
- Direct URLs `knowledge/install/playground` for client roles: the page shell is reachable (HTTP 200) with in-page "Platform staff access required." (earlier finding; API guards are correct).

## Staff-visible elements that look leftover, unused or inconsistent
- Sidebar icon for "Change requests" (platform) and "Request a change" (client) renders as a bare `?` glyph; looks like a placeholder icon.
- `/widget/sample?locator=...&site=custom` is a "Store A (sample site)" demo page shipped in the app, linked from Install.
- Provisional text: Operations banner "These values are for verification. Pricing and final plan limits are still under review", and "AI cost is not reported because provider token usage and price data are not stored".
- Staff on `/app/<tenant>/...` sees client-oriented pages ("Request a change" with a disabled "Submit request", "Team" invite/remove, "Create contact") although staff is not a member.
- "Retry"/"Cancel" are offered on an already completed job (operations table and knowledge Jobs list).
- Header "Organization / Switch organization" select is present but empty on `/app` and `/platform` for staff.
- All pages share the same `<title>` "Website Chatbot SaaS" (no per-page titles).
- The demo tenant still lists `demo-owner@example.com` as an admin member on the client detail page (DEMO-SEED.md says that login is retired).

## Unverified
- Anything behind a mutation: results of Pause/Save/Delete/Onboard/Retry flows were not executed (requests blocked).
- Staff views of other tenants (none exist).
