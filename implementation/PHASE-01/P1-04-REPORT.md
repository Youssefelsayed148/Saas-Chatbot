# P1-04 — Dashboard UI + E2E

Date: 2026-10-12. Status: IMPLEMENTED AND LOCALLY VERIFIED. Awaiting owner review as part of the P1 gate.

Branch: `feat/p1-01-foundation` (local commit only; no push/merge/deploy).

## Built

### Web dashboard (Next.js 16 App Router, client components, real API only)
- Typed API client `lib/api.ts` — all contracts of P1-02/P1-03 (register/login/logout/me, tenants, bots incl. config patch/archive, members, invitations incl. accept). Same-origin `/api/v1/*` proxy via `next.config.ts` rewrites (no CORS; cookies stay first-party; Compose points the proxy at `http://api:8000` through a build arg, local dev defaults to `http://127.0.0.1:8000`). CSRF token read from the cookie (plus `Set-Cookie` header fallback captured right after login) and sent as `X-CSRF-Token` on every write. Global `session-expired` event → provider redirects protected pages to `/login?next=…` (open-redirect-safe).
- Pages (`app/…`, loading / empty / error states everywhere, role-aware controls):
  - `/register`, `/login` — validation errors surfaced (specific messages from the stable error contract), password ≥ 8 hint, redirect target honoring `?next`.
  - `/app` — organization selector/list (from `/me`), create form; empty state for new accounts; unauthenticated users are pushed to login.
  - `/app/[tenant]/bots` — list with status, `Show archived bots` toggle (default list hides archived), create (editor+) with read-only note for viewers, Archive button per row.
  - `/app/[tenant]/bots/[botId]/settings` — rename + full config form (assistant/business name, description, welcome EN/AR, opening questions, default language, support email/phone, hex colour, position, handoff toggle, allowed domains); viewers get a read-only view; archive button with explanation; archived bots reject editing (409 surfaced).
  - `/app/[tenant]/settings/members` — invite form (email + role; owner extra role option) producing a copyable one-time link (shown once), pending invitations with resend/revoke and expired flags, members table with role selects (owner rows protected), remove buttons, self marker, last-owner rules surfaced in the helper text; non-admins get a clear explanation instead of the tables.
  - `/accept-invite?token=…` — visitors see sign-in/register links carrying the return path, signed-in users see a confirm button, success shows the joined org; API error codes (expired/used/revoked/email mismatch) are displayed verbatim.
- Top bar with org switcher (`/app/[tenant]/*` pages), dashboard link, email display, Sign out.

### E2E infrastructure (Playwright)
- `playwright.config.ts`: single worker; `globalSetup` (`tests/e2e-api-setup.ts`) boots the **real FastAPI** on port 8000 against a disposable `chatbot_dev_e2e_test` database (derived and guarded to end in `_test`), runs `alembic upgrade head` first, reuses an already-healthy API if present; `globalTeardown` stops the spawned server. Credentials come from `DATABASE_URL` or the repo `.env`.
- `tests/dashboard.spec.ts` (5 tests total incl. the P1-01 foundation smoke):
  1. register → create organization → create bot → archive → archived toggle list → sign out (all real API).
  2. second browser context: an uninvited user opening the first user's org URLs gets the API's 404 surfaced by the UI and never sees the foreign org name.
  3. owner invites editor + viewer; the editor registers through `/accept-invite`, accepts, lands in the dashboard, creates a bot (editor-rights).
  4. sign-out revokes the session and `/app` falls back to `/login`.
  5. (P1-01) landing page smoke.

## Evidence — exact commands and results

Windows host, from the repository root unless stated:

| Command | Result |
|---|---|
| `npm run lint` | exit 0 (eslint --max-warnings 0) |
| `npm run format:check` | "All matched files use Prettier code style!" |
| `npm run typecheck` | "Generating route types… ✓ Types generated successfully" then tsc exit 0 |
| `npx playwright test` (apps/web) | "5 passed (51.2s)" — includes API boot, migrations on the disposable e2e DB and the journeys above; repeated after fixes with the same outcome |
| Backend regression (after infra changes): `ruff check .` / `ruff format --check .` / `mypy` / `pytest` (apps/api) | All green: "All checks passed!", "46 files already formatted", "Success: no issues found in 46 source files", "61 passed, 1 warning in 9.09s" |
| `docker compose --env-file .env -f infra/compose.yaml config --quiet` | valid, no secrets printed |
| `docker compose --env-file .env -f infra/compose.yaml up --build -d --wait` | db + api + web all healthy on loopback 55432/8000/3000 |
| Proxied smoke via the web origin: `POST /api/v1/auth/register` then `GET /api/v1/auth/me` with the cookie jar | 201 then 200 (session + csrf cookies set on the web origin; proxy target baked as `http://api:8000`) |
| `GET http://127.0.0.1:3000/api/v1/auth/me` without a session | stable 401 `{error:{code:"UNAUTHENTICATED",…}}` surfaced through the proxy |

The one pytest warning remains the known Starlette↔httpx TestClient deprecation tracked since P1-01.

## Design notes recorded
1. Next.js rewrites are baked at build time: compose passes `API_PROXY_TARGET` as a Docker build arg; local dev/Playwright uses the default 127.0.0.1:8000. Documented in the Dockerfile.
2. The Playwright global setup reuses a running API on port 8000 (dev convenience); it never talks to a database whose name does not end with `_test`.
3. `SessionProvider` lives in the root layout; protected pages redirect on a returned-null session (including expired/invalid ones) — `session-expired` events from mid-session 401s route through `?next`.
4. The invitation link is shown once with a copy button; there is intentionally no in-app auto-accept (a possibly wrong e-mail should confirm first, then accept).

## Limitations
1. Hosted CI still unrun (no push authorization); the frontend job now provisions Postgres + DATABASE_URL so the E2E journey would work there too.
2. The E2E "expired session" journey exercises the revocation/redirect path (logout server-side revocation) rather than literal token expiry; expiry itself is covered by API tests (P1-02).
3. The E2E database (`chatbot_dev_e2e_test`) keeps its rows between runs (disposable-by-name, local only); teardown stops the server but does not drop the database (a later step may clean it in P2 when the worker needs the same pattern).
4. Role-aware visibility relies on the membership role from `/me`; the server remains the authority (API tests prove 403 for under-privileged writes).

## Files
Created: `apps/web/lib/{api.ts,session.tsx,ui.tsx,app-header.tsx}`, `apps/web/app/{login,register,accept-invite}/page.tsx`, `apps/web/app/app/{layout.tsx,page.tsx}`, `apps/web/app/app/[tenant]/bots/page.tsx`, `apps/web/app/app/[tenant]/bots/[botId]/settings/page.tsx`, `apps/web/app/app/[tenant]/settings/members/page.tsx`, `apps/web/tests/{dashboard.spec.ts,e2e-api-common.ts,e2e-api-setup.ts,e2e-api-teardown.ts}`.
Modified: `apps/web/{app/layout.tsx,app/page.tsx,app/globals.css,tsconfig.json (paths),next.config.ts (rewrites),package.json (unchanged scripts),playwright.config.ts,Dockerfile}`, `infra/compose.yaml` (web build arg), `.github/workflows/ci.yml` (frontend Postgres service).

Next: phase verification + PHASE-REPORT and owner sign-off.
