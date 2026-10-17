# Manual test: run it locally

Local, loopback-only. Run commands from the repo root in PowerShell unless noted. Never paste `.env` contents or keys anywhere.

## 1. Bring up the stack

Prerequisites: Docker Desktop, Node 24, and the repo `.venv` (Python). `.env` exists at the repo root (copy `.env.example` once, set a local DB password).

### Option A: everything in Docker Compose (db, api, worker, web)

```powershell
docker compose --env-file .env -f infra/compose.yaml up -d --build
docker compose --env-file .env -f infra/compose.yaml ps        # wait for "healthy"
```

Compose has no migrate service. Run migrations once from the host against the published DB port (55432):

```powershell
cd apps/api
$env:DATABASE_URL = "postgresql://<POSTGRES_USER>:<POSTGRES_PASSWORD>@127.0.0.1:55432/<POSTGRES_DB>"
..\..\.venv\Scripts\python.exe -m alembic upgrade head
```

(Fill the three placeholders from your own `.env`; do not echo the file.) Stop with `docker compose --env-file .env -f infra/compose.yaml down` (add `-v` to wipe data).

### Option B: db in Docker, api/worker/web as dev servers (hot reload)

```powershell
docker compose --env-file .env -f infra/compose.yaml up -d db
$env:DATABASE_URL = "postgresql://<POSTGRES_USER>:<POSTGRES_PASSWORD>@127.0.0.1:55432/<POSTGRES_DB>"

# terminal 1: migrate, then API
cd apps/api
..\..\.venv\Scripts\python.exe -m alembic upgrade head
..\..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# terminal 2: worker (ingestion + background jobs; needed for knowledge to finish)
cd apps/api
..\..\.venv\Scripts\python.exe -m app.worker

# terminal 3: web (start in a fresh terminal at the repo root)
cd apps/web
npm.cmd run dev
```

Set the same `DATABASE_URL` (and any `CHAT_*` variables from section 4) in terminals 1 and 2. Uploaded files are stored under `STORAGE_ROOT`; API and worker must share it (default is fine when both run on the host).

## 2. URLs

| What | URL |
| --- | --- |
| Dashboard (register / login) | http://127.0.0.1:3000/register, http://127.0.0.1:3000/login |
| Bot list after login | http://127.0.0.1:3000/app/`<tenant_id>`/bots |
| Widget sample page | http://127.0.0.1:3000/widget/sample?locator=`<widget_locator>`&site=store |
| API docs (Swagger) | http://127.0.0.1:8000/docs |
| Health / readiness | http://127.0.0.1:8000/health (`ok`), http://127.0.0.1:8000/ready (`ready` when the DB is reachable) |

The bot's `widget_locator` is shown on its Install tab (or in `GET /api/v1/tenants/<tenant_id>/bots/<bot_id>`).
Quick check: `.venv\Scripts\python.exe scripts/smoke_local.py` (health, ready, web assets).

## 3. Demo data

Fictional dental-clinic tenant with a bot, published knowledge, contacts and conversations. It refuses any database whose name does not end in `_dev` or `_demo`. Migrations must already be applied. Safe to re-run (a completed seed is left unchanged).

```powershell
cd apps/api
$env:DATABASE_URL = "<same dev URL as above>"
..\..\.venv\Scripts\python.exe -m scripts.seed_demo
```

Logins are printed by the script: `demo-admin@example.com`, `demo-editor@example.com`, `demo-viewer@example.com`. For a `*_dev` database the password is `FakeDemoOnly!123`; for `*_demo` set `DEMO_SEED_PASSWORD` (8–128 chars) first.

## 4. Real model (OpenRouter) vs stub

Set these in your root `.env` (Compose passes them through) or in the shell for dev servers, then restart api **and** worker:

- `CHAT_OPENROUTER_API_KEY` — your OpenRouter key.
- `CHAT_FREE_MODEL_CHAIN` — model ids to use, **required**. With a key but an empty chain the factory returns no model and chat replies with the canned "not ready/busy" message. (Check `.env.example` / docs/14 for the list format.)
- `CHAT_STUB_MODEL` must be **unset or false**. When true it wins over any key and uses the offline extractive stub (it never calls a model; answers just echo the first evidence chunk). Docker Compose passes `CHAT_STUB_MODEL=${CHAT_STUB_MODEL:-false}` to api and worker, so compose runs are stubbed only if you set it in `.env` or your shell; dev-server shells may be too, if you exported it earlier.

Confirm which model is active (prints only the class name, never the key), run in the same environment as the API:

```powershell
cd apps/api
..\..\.venv\Scripts\python.exe -c "from app.chat.models import default_model; m=default_model(); print(type(m).__name__ if m else 'None (not ready)')"
```

- `OpenAICompatibleModel` = real provider is wired.
- `ExtractiveStubModel` = stub is on; unset `CHAT_STUB_MODEL`.
- `None (not ready)` = key or model chain missing.

Behavioural check: ask something paraphrased in the widget. A real model rewrites the knowledge in its own words; the stub returns the evidence text nearly verbatim. Requests spend real quota on your OpenRouter account.

## 5. Manual test checklist (12 steps)

Use the seeded demo tenant for steps 7–8 if you want data already there; otherwise use the fresh tenant from step 1.

1. **Sign up.** `/register`: organization name, first bot name, email, password. You land on `/app/<tenant>/bots` with one bot, and the plan is Free.
2. **Operator setup.** Sign in as platform staff and open the target client from /platform. Open its bot > Settings and activate it. Client roles cannot create, archive or edit bots.
3. **Upload knowledge as staff.** Bot > Knowledge: upload a short `.md`/`.txt` with facts (e.g. opening hours). Client roles request changes; knowledge and document status are operator-only.
4. **Wait for ingestion.** The job moves Queued > Processing > Completed (raw states pending > running > succeeded) (needs the worker). Preview documents and chunks, then **Publish**.
5. **Chat in the widget.** Open the sample page URL with the bot's locator, click the bubble, ask about the uploaded facts. Expect a grounded answer with a citation; ask something off-topic and expect it to say it cannot confirm.
6. **Handoff.** In the widget ask for a human. In Workspace > Inbox the thread shows Waiting for human: choose Take over, send a reply, then Return to AI. The reply appears in the widget through polling; it also remains after reopening.
7. **Contacts.** Submit the widget lead form (name, email, consent). Dashboard > Contacts lists the lead; open it and change its stage.
8. **Overview.** Bot > Overview: messages, conversations, widget opens and leads match what you just did; the unanswered list shows the off-topic question; leads CSV downloads.
9. **Invite a teammate.** Team > Create invite link (role editor). Copy the `/accept-invite?token=...` link, open it in a separate browser profile after registering with the invited email, accept. The teammate sees the tenant with editor rights.
10. **Hit a plan limit.** Staff bot creation and admin invitations enforce plan limits with 429 QUOTA_EXCEEDED. Accepting an already-reserved invitation must work at the seat limit.
11. **Tenant isolation.** With a second account (another tenant), open the first tenant's URL: expect 404, not 403.
12. **Delete a tenant as staff.** Tenant data and audit > Schedule organization deletion: supply a meaningful reason and exact name, then enter the name again in the counts popup. Cancel sends no mutation. Access is disabled immediately; tenant rows and storage remain until the configurable grace period elapses (default 30 days).


## 6. Redesigned UI checks

- Sidebar Overview opens `/app/<tenant>`; Bots, post-login and organization switching still use `/app/<tenant>/bots`. Tenant Overview is read-only. The first-bot checklist derives published knowledge from revisions; installation is not claimed.
- The top bar shows Client workspace, tenant name and role. `/platform` has a distinct Platform admin shell. Staff can operate a target client?s bots without tenant membership; inbox actions require a client membership.
- Appearance follows the system initially; a manual choice persists per viewer in this browser. Check both themes, a second signed-in viewer and storage-disabled behavior.
- Ctrl/Cmd+K opens page navigation. Search, use arrow keys/Enter and Escape; focus returns to the trigger. It never executes mutations. At 360px, open the mobile navigation drawer and dismiss it with Escape.
- Archive opens a cancelable confirmation. Tenant deletion still requires exact name/reason. Contact erasure has an explicit optional message-erasure checkbox. Cancel any dialog and verify no mutation occurs.
- Inbox filters have separate labels/controls and removable chips. Search and Status stay visible; open More filters for Mode, Channel, Assignee, Tag and Unread. Escape closes the advanced controls. Check status, mode, channel, assignee, tag, unread and search; direct `?status=waiting_human` links still work. Desktop shows list/thread together; mobile keeps list-to-thread navigation.
- In an Arabic row, check message direction, unread dot/count, status badge, tags and timestamp. Verify Arabic/English mixed messages in chat bubbles, keyboard focus and expandable sources. Viewers see no reply, takeover, resolve, assignment, note or tag mutation controls.
- At 360x800 and 1440x900, verify no horizontal page scrolling, including tables, forms, snippets and dialogs. Check visible focus and reduced-motion preference. Widgets retain bot color/placement/language from existing config only.
- Verify widget 429 server text is displayed verbatim; do not substitute or translate it. Test lead consent, failure/retry, handoff and reopening history.
- Automated screenshots are saved under `implementation/ui-screens/` after the final two successful full browser runs. Large images are not committed.


## Phase 1 roles and operator control ? 2026-10-16

Apply migration 0013 before testing. The client demo logins are demo-admin, demo-editor and demo-viewer; demo-owner is retired. Use a separate staff account for operator actions. The client admin never becomes platform staff by changing a tenant role. Onboarding uses `admin_email`/`admin_invite` and grants the client admin role, never platform staff. Historical owner audit actions remain readable.

1. With signup disabled, POST registration without an invite, with a forged/expired/revoked/used token, or with a token for another email: 403 and no new user. A valid matching token registers, then accepts once.
2. Admin can manage members/invitations and audit/exports/CSVs. Promote another admin before demoting/removing the current admin. Demoting/removing the sole admin returns LAST_ADMIN. No ownership-transfer UI or endpoint exists.
3. All client roles see no knowledge, document status, Install snippet or settings controls. Guess their URLs and verify server restrictions; bot responses omit configuration and locator for all client roles.
4. Client roles receive 403 for knowledge reads (sources/detail/template, jobs/detail, documents/chunks, revisions), upload/ingestion/job cancel/retry/publish, bot PATCH, playground/feedback and organization deletion. Staff without membership in the target client performs these through the scoped API or links from platform client detail.
5. Editor can reply, take over/return/resolve/assign, tag/note, schedule follow-ups and create/edit contacts. Assignment choices use the editor-accessible assignees endpoint. Admin alone can configure stages, merge/delete contacts or delete conversations. Viewer cannot mutate, including read markers.
6. Admin opens Request a change, chooses a type, supplies text and optionally attachments. Confirm it appears with pending status. A separate staff account opens /platform/change-requests, downloads evidence and triages. Refresh the admin list to see the updated status. A deletion request only creates a request; staff must execute the deletion separately.
7. Staff opens Organization data and deletion. Confirm the popup shows resource counts and requires the exact organization name. Mismatched case/whitespace returns 422 at the API. Successful deletion immediately disables bots/widget and existing client sessions; a new login cannot access the organization. Grace defaults to 30 days, configurable with ORG_DELETION_GRACE_DAYS. Only use a disposable test organization to exercise expiry/purge; verify knowledge and request attachment storage is cleaned and the independent ledger survives.
8. Keep tenant A/B guessed-ID checks. Channel connections and per-channel analytics filtering are deferred to Phase 3 per this change note. If Playwright sees ECONNRESET, record the spec name and failure; do not change the flake handling in this scope.

- Verify client inbox/conversation views and visitor widget turn/history show no citations or source links. Client exports retain operational data but exclude knowledge, bot configuration and citations. Staff retain knowledge and install access.


## Group C safety and polish
- On an active bot, change widget colour/position and click **Save settings**. Reload the public widget config: the changes apply live, without a draft/publish step.
- Cancel each member Remove, conversation Delete, Pause bot (both pages), embedding backfill and Reset to plan defaults dialog; verify no write occurs. Confirm each and verify the intended write.
- Audit review displays historical owner and new admin invitation/assignment actions; search either vocabulary and verify tenant isolation.
- Failed jobs show Retry only; queued/running jobs show Cancel only; succeeded/cancelled jobs show neither action in both lists.
- Check page titles, change-request icons, favicon and the contact Conversation dropdown middle dots.
- `/widget/sample` renders only for authenticated platform staff; anonymous and client roles receive a server redirect without the sample body.
