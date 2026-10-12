# PHASE-01 REPORT — Foundation (P1: users, tenants, bots)

Date: 2026-10-12. Status: ALL P1 TICKETS IMPLEMENTED AND LOCALLY VERIFIED. **STOPPED FOR OWNER SIGN-OFF** (the phase is complete only after the checklist below is signed off; no deployment, push or hosted-CI run has happened).

Branch: `feat/p1-01-foundation`. Local commits: P1-01 (pre-existing), P1-02, P1-03, P1-04 (see git log).

## What works end to end (owner-readable summary)

1. Open the web app, register, sign in, sign out. Wrong password → specific error; expired or revoked sessions → 401 and the dashboard pushes the user back to `/login`.
2. Create an organization — the creator is its owner with an auto-generated unique slug; switch between organizations from the top bar.
3. Create bots, rename them, edit their settings (assistant/business details, welcome EN/AR, opening questions, default language, support contacts, widget colour/position, handoff toggle, allowed domains), and archive them. Archived bots leave the default list, keep their config and can be listed via a toggle.
4. Owners/admins invite teammates with one-time links (token stored only as SHA-256 hash; shown once with a copy button). The invitee registers/logs in through the accept page and joins with the invited role. Links expire (default 7 days), work once and can be revoked or re-sent.
5. Tenant isolation: a user from org B who guesses an org-A id gets 404 on every endpoint (bots, members, invitations); viewers see read-only UI and the API rejects their writes; role/last-owner protections are enforced server-side and audited.
6. Nothing on screen is mocked: every list comes from the real FastAPI through a same-origin proxy.

Ticket reports with full evidence: `P1-02-REPORT.md`, `P1-03-REPORT.md`, `P1-04-REPORT.md`; toolchain: `P1-01-REPORT.md`.

## Verification evidence (final state)

| Check | Windows host | Linux container |
|---|---|---|
| `ruff check` / `ruff format --check` (apps/api) | All checks passed! / 46 files already formatted | same in checks image |
| `mypy` (strict; app + tests + alembic) | Success: no issues found in 46 source files | same |
| `pytest` | 61 passed, 1 warning | 61 passed, 1 warning |
| `npm run lint` (eslint --max-warnings 0) | exit 0 | — |
| `npm run format:check` | All matched files use Prettier code style! | — |
| `npm run typecheck` | next typegen ✓ + tsc exit 0 | — |
| `npx playwright test` (apps/web) | **5 passed** (real API on a disposable `chatbot_dev_e2e_test` DB) | — |
| Compose stack `up --build -d --wait` | db/api/web healthy; proxied register→me 201/200 via the web origin | — |

Disposable databases used by checks: `chatbot_dev_test`, `chatbot_dev_migration_test`, `chatbot_dev_e2e_test` (guard refuses anything not ending in `_test`). The dev database `chatbot_dev` carries the applied `0001_initial` migration plus one manual curl smoke account that was removed after the live test.

## Checklist status (implementation/PHASE-CHECKLISTS.md)

All P1 items are ticked with evidence as of this report. Remaining open item: **owner review and sign-off** (`- [ ] Phase report written; owner reviewed and signed off`).

## Status of agreed behaviours (docs/18, after P1)

- Register/login/logout/me with wrong-password and expired-session handling ✅
- Create/second org/switch ✅
- Create/rename/edit-settings/archive bots, archived bots hidden but kept ✅
- One-time invite links with expiry/single-use/revocation, accept flow, member roles/removal, viewer read-only UI + rejected writes ✅
- Cross-tenant ID guessing returns 404 ✅
- No fake data on screen ✅

## Limitations and open risks

1. **Hosted CI has never run** (no push/remote authorized; the workflow is updated to provision Postgres for both jobs but unexercised). The known npm dev-chain advisory GHSA-vfj7-8cjw-p6xm (braces) from P1-01 remains: lint-only dependency chain, zero production-audit vulnerabilities.
2. **Login rate limiter is in-process** (single uvicorn worker in P1). Multi-process deployments need the Postgres-backed counters planned for the widget phase (docs/14 §7).
3. **Emails/tokens are not hashed in URLs only by design decision**: the registration 409 reveals address existence (accepted docs/05 contract); tokens never appear in logs and invitation tokens are single-use — but there is no automated scan proving "no token in logs"; the guarantee comes from code (no logger calls). A dedicated log-scrubber arrives with P7 hardening.
4. **E2E expiry journey** relies on server-side revoked/logout paths; literal session-expiry is covered at the API test level, not in the browser.
5. The `memberships.status='revoked'` value is reserved but unused (removal deletes rows); revisit if suspension becomes a requirement.
6. Session rotation on login revokes only the presented token (per-browser); simultaneous logins on several devices legitimately coexist (documented in P1-02).
7. `Secure` cookie flag asserted for production settings (unit test) and observed over loopback HTTPS only in later phases; the local Compose smoke runs over HTTP on 127.0.0.1 (browser-trusted origin).
8. ADR-007 (hosting) is still OPEN — nothing was deployed anywhere, per the standing rules.

## Second-approval notes for the owner

- Docs followed: `docs/03`, `docs/04`, `docs/05` (phase-1 frozen contracts only — no proposal routes implemented), `docs/06` (role matrix), `docs/14 §19` (team invitations), `docs/18` (expected behaviour).
- No Meta/ManyOsirisChat code, no credentials committed, no push/merge/deploy, no paid APIs. Local Compose remains running (loopback ports 3000/8000/55432) for review: `docker compose --env-file .env -f infra/compose.yaml down` stops it, preserving the volume.
- Next phase per roadmap after sign-off: P2 Knowledge (P2-01 → P2-04).
