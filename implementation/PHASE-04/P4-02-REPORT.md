# P4-02 — Widget package (loader + sandboxed iframe UI, served by the web app)

## What was built

- **`packages/widget`** (`@chatbot/widget`): the embeddable loader
  (`src/loader.js`, plain ES2020, no build deps) — bubble button + versioned
  asset path `/widget/v1/loader.js` (served from `apps/web/public`) +
  sandboxed iframe `/widget/frame?locator=…`. **Registry entry
  `packages/widget` added to the npm workspaces with a regenerated
  `package-lock.json`** (no dependency changes beyond the workspace itself).
- Frame UI (`app/widget/frame/page.tsx`): loading / ready / typing /
  answer-with-citation-chips / no-knowledge / paused / not-ready / quota /
  rate-limited / network-error-with-retry states (docs/09), welcome message +
  opening-question chips, thumbs per answer, scroll-to-bottom, `dir` from bot
  settings (RTL), keyboard accessible (labels, focusable input, Escape closes
  via postMessage), localStorage-backed session for refresh recovery
  (silently refreshed on 401 — docs/09 "expired session recovered
  gracefully"). Talks to the REAL public API only (capability-token auth).
- **Scoped headers** (`next.config.ts`): `/widget/:path*` relaxes
  `frame-ancestors` to `http: https:` (client sites MUST be able to frame
  it), while the dashboard-wide rule keeps `frame-ancestors 'none'` (P2-00).
  Next 16 declares ALL matching rules and the LAST value of a header key
  wins — the widget rule therefore comes AFTER the global one; verified with
  live curl + the Playwright assertions (dashboard 'none' AND widget frame
  'http: https:' on the same server).
- postMessage protocol between loader and frame (locator handover, auto-
  height, brand sync so the bubble matches P4-03 settings, close on Escape).

## Evidence

- `apps/web/tests/security-headers.spec.ts` — dashboard frame-ancestors
  'none' + `/widget/frame` relaxed + loader asset served as JS (2 passed).
- `apps/web/tests/widget.spec.ts` — two TEST SITES (the sample-page helper
  with two different tenants' locators), each embeds the REAL loader snippet;
  tenant A's widget answers ONLY from tenant A's knowledge (7:00, not 9:00)
  and vice versa (2 passed incl. titles). The harness runs the REAL API +
  worker + web with `CHAT_STUB_MODEL=1` on a disposable `_test` DB.
- Frontend checks: eslint (react-compiler rules included), prettier,
  tsc-with-generated-routes all green.

## Notes / limitations recorded honestly

- The E2E "two sites" use the sample page helper on the SAME deploy origin:
  on a loopback-only test deployment Chrome's **Local Network Access** blocks
  cross-origin script loads into 127.0.0.1 (`...access the loopback address
  space...`). Real customer sites embed cross-origin from PUBLIC hosts —
  classic `<script src>` needs no CORS there — so this is a test-environment
  constraint, documented here. Cross-tenant *session/message* isolation is
  asserted at the API level (`tests/test_widget_public.py`: foreign session
  ids/tokens never cross).
- The iframe sandbox needs `allow-same-origin allow-scripts allow-forms` so
  the frame can talk to the public API same-origin; Chrome warns about the
  combination (documented in the loader). The frame exposes only public API
  surfaces — a scripted compromise reaches rabbits scoped to that session's
  capability token, not the dashboard (an API process boundary in production).
