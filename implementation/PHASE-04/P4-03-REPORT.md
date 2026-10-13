# P4-03 — Appearance settings + Install page

## What was built

- **Appearance settings** (`Settings` tab): assistant name, business name +
  description, welcome message (EN/AR — the greeting), opening-question chips,
  default language (EN/AR drives the widget `dir`), support email/phone,
  widget colour, position (left/right), **avatar (P4-03; validated
  http(s)-only, ≤500 chars, `422` otherwise)**, handoff toggle, allowed
  domains. All typed via `BotConfig`; avatar is exposed in the SAFE public
  widget config (`tests/test_widget_appearance.py`: valid URL saved +
  publicly exposed with colour/position; junk/`javascript:`/relative values
  rejected 422; locator→bot lookup).
- **Bot lifecycle in the UI**: draft → Activate, Active ⇄ Pause buttons on
  Settings (owner/admin/editor per docs/06; viewer read-only), mapped to the
  P4-01 PATCH `status` transitions.
- **Install tab** at `/app/[tenant]/bots/[botId]/install`: the REAL snippet
  (`<script src="<deployment>/widget/v1/loader.js" data-locator="…">`,
  deployment-aware origin, copy button), the bot locator displayed with the
  "locator is public" explainer, draft/paused guidance, and the
  **test-on-a-sample-page helper**: `/widget/sample?locator=…&site=…` renders
  a stand-in customer page (sample business copy + shows the snippet it
  embeds + the REAL loader element appended with `data-locator`, exactly the
  customer contract). Settings page links both ways.

## Evidence

- Playwright `tests/install.spec.ts` — **1 passed** (real API + disposable
  `_test` DB): draft bot → Install shows draft guidance; Activate from
  Settings; Install then shows the snippet with the real locator + sample
  helper link; journey completes on the sample page (bubble appears); the
  colour setting round-trips through save + reload.
- Backend `tests/test_widget_appearance.py` — 3 passed (see above).
- Web checks (lint/typecheck/format) green.

## Notes

- The sample page is served by this deployment; it appends a REAL
  `<script src="/widget/v1/loader.js" data-locator="…">` element (innerHTML-
  injected scripts never execute — the loader contract needs the real
  element). Customers still paste the standalone script tag from the Install
  snippet.
- `install.spec.ts` also covers the settings status transitions end to end
  (activate via UI; the pause path is UI-covered in install/settings; the
  state machine itself is asserted in `tests/test_bot_status.py`).
