# P2-00 REPORT — P1 carry-overs

Date: 2026-10-12. Status: DONE, locally verified (Linux container + Windows host).

## Security headers (apps/web)

`apps/web/next.config.ts` adds to every Next-served path:

- `Referrer-Policy: no-referrer`
- `X-Content-Type-Options: nosniff`
- `Content-Security-Policy: frame-ancestors 'none'` (the dashboard must not be framable; the P4 widget frame page will need its own scoped set and does not exist yet)

`poweredByHeader: false` keeps the `X-Powered-By` header off.

Evidence:

1. Playwright test `apps/web/tests/security-headers.spec.ts` asserts all three headers on `/`, `/login` and `/register` against the real Next server started by the E2E webServer — passed (part of the 9-test Playwright run).
2. Live curl proof against the running Compose stack (loopback 3000):
   `Referrer-Policy: no-referrer`, `X-Content-Type-Options: nosniff`, `Content-Security-Policy: frame-ancestors 'none'` on both `/` and `/login`.

Limitation found and documented: Next.js `headers()` does not attach these headers to the responses of the **external rewrite** that proxies `/api/*` to the FastAPI process (the API's own response wins). In production the single gateway in front of web+api adds them (ADR-003 same-origin deployment); the FastAPI surface is not browser-navigated. Recorded as a limitation in PHASE-REPORT.md.

## Invitation double-accept race

- Fix: `TenantService.accept_invitation` now takes the invitation row `FOR UPDATE`, so two concurrent accepts serialise; the second sees `accepted_at` set and gets 409 `INVITATION_USED` instead of racing to a duplicate membership/500.
- Test: `tests/test_invitations.py::test_invitation_double_accept_race_exactly_one_succeeds` — two threads with a barrier fire two concurrent accepts of one token through the API; asserted exactly one 200 + one 409, exactly one membership row and exactly one `invitation.accepted` audit event. Passed.

## Carried P1 limitations (per the ticket, restated in PHASE-REPORT.md)

- Hosted CI has never run (no push/remote authorised; workflow exists and is updated as part of P2 code changes but remains unexercised).
- Login rate limiter is still the in-process fixed-window limiter (single uvicorn worker in this phase); Postgres-backed counters arrive with the widget phase (docs/14 §7).

## Exact commands (Linux container, Windows host)

- Linux: `ruff check .` / `ruff format --check .` / `mypy` / `python -m pytest -q` → all green (123 passed).
- Windows host: same four commands with the repository `.venv` → all green.
- `npm run lint` / `npm run typecheck` / `npm test` (Playwright, 9 passed) on the Windows host (node 24.19.0).
