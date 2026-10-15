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

# terminal 3: web (proxies /api to http://127.0.0.1:8000 by default)
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

Logins are printed by the script: `demo-owner@example.com`, `demo-admin@example.com`, `demo-editor@example.com`, `demo-viewer@example.com`. For a `*_dev` database the password is `FakeDemoOnly!123`; for `*_demo` set `DEMO_SEED_PASSWORD` (8–128 chars) first.

## 4. Real model (OpenRouter) vs stub

Set these in your root `.env` (Compose passes them through) or in the shell for dev servers, then restart api **and** worker:

- `CHAT_OPENROUTER_API_KEY` — your OpenRouter key.
- `CHAT_FREE_MODEL_CHAIN` — model ids to use, **required**. With a key but an empty chain the factory returns no model and chat replies with the canned "not ready/busy" message. (Check `.env.example` / docs/14 for the list format.)
- `CHAT_STUB_MODEL` must be **unset or false**. When true it wins over any key and uses the offline extractive stub (it never calls a model; answers just echo the first evidence chunk). Docker Compose never passes `CHAT_STUB_MODEL`, so compose runs are never stubbed; dev-server shells may be, if you exported it earlier.

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
2. **Create a second bot** (or open the first bot). Bot > Settings: set status to Active.
3. **Upload knowledge.** Bot > Knowledge: the upload control is enabled right after signup (no reload). Upload a short `.md`/`.txt` with some facts (e.g. opening hours).
4. **Wait for ingestion.** The job moves queued > running > succeeded (needs the worker). Preview documents and chunks, then **Publish**.
5. **Chat in the widget.** Open the sample page URL with the bot's locator, click the bubble, ask about the uploaded facts. Expect a grounded answer with a citation; ask something off-topic and expect it to say it cannot confirm.
6. **Handoff.** In the widget ask for a human. In Dashboard > Conversations the thread appears as needing an agent: take over, reply, return it to the bot. Reply shows in the widget after reload.
7. **Contacts.** Submit the widget lead form (name, email, consent). Dashboard > Contacts lists the lead; open it and change its stage.
8. **Overview.** Bot > Overview: messages, conversations, widget opens and leads match what you just did; the unanswered list shows the off-topic question; leads CSV downloads.
9. **Invite a teammate.** Members > Invite (role editor). Copy the `/accept-invite?token=...` link, open it in a separate browser profile after registering with the invited email, accept. The teammate sees the tenant with editor rights.
10. **Hit a plan limit.** On the Free plan keep creating bots/invites until you get **429 QUOTA_EXCEEDED** with the plan message (Quota page shows usage). Accepting an invite you already hold must still work at the seat limit.
11. **Tenant isolation.** With a second account (another tenant), open the first tenant's URL: expect 404, not 403.
12. **Delete a tenant.** Owner > tenant data/settings > Delete: type the tenant name and a reason. Expect the tenant, its bots, knowledge and uploaded files to disappear and the owner to lose access.
