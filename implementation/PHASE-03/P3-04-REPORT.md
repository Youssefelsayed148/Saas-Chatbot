# P3-04 REPORT — Playground UI + Playwright E2E

Date: 2026-10-13. Status: DONE, locally verified.

## Page `/app/[tenant]/bots/[botId]/playground`

- Thread view: visitor turns vs AI turns, AI text with `dir="auto"` (Arabic renders RTL), **citation chips** (chunk title + source_url link) from the stored citations, `needs_human` notice on failed turns, response time, **thumbs up/down per AI reply** (disabled after one rating — idempotency from P3-03).
- Send flow: 1000-char guarded input, disabled while sending, role rules — editor+ may chat, viewers see the read-only notice, no send button and a disabled input; server still 403s (belt and braces).
- Error states: `MODEL_NOT_CONFIGURED` → the controlled "not configured for this deployment" notice (no crash); API/401 plumbing identical to the dashboard client (session-expired redirect).
- Nav cross-links Settings ↔ Knowledge ↔ Playground on all three pages.

## Playwright E2E (`tests/playground.spec.ts`, real API + real worker + stub model)

1. `playground chat: grounded answer, citation, thumbs, thread persists` — register → org → bot → upload the fixture through the owner's request context → ingest (polled through the REAL DB worker to `succeeded`) → publish → open the playground → ask → the AI turn shows an extractive answer from the actual published knowledge with the citation chip (title + source URL) → thumbs up once → disabled after rating → reload → thread persists.
2. `an expired session pushes the playground back to login` — cleared cookies + protected URL → redirected to /login.
3. `viewer is read-only in the playground` — viewer invite → accept → open playground → read-only notice, no send button, disabled input.

The E2E API boots with `CHAT_STUB_MODEL=1` (the deterministic offline model — documented dev-only). No provider keys or paid calls in tests.

Harness change: `e2e-api-setup.ts` no longer silently reuses an already-running API on port 8000 — reuse is now opt-in via `E2E_REUSE_API=1` (a stale compose process masked a broken run during development; the guard refuses with instructions instead).

## Checks

`npm run format:check` / `lint` / `typecheck` green; Playwright **12 passed** (5 dashboard + 1 foundation + 3 knowledge + 3 playground). One leftover: the not-ready (503) state is asserted at the API level (P3-03 test) and covered visually by the UI branch; E2E runs with the stub model so the notice cannot fire there — kept as a design note, zero-cost to assert later against a no-key deployment.
