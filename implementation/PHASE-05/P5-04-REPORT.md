# P5-04 — Contacts and light CRM

## Built

- Tenant scoped contact list, create, update, profile, stage list/rename, CSV export, merge, and erasure routes.
- Profile includes channel identities, conversations, and internal notes in its timeline. Hidden foreign contacts return 404. Viewer members can read and export; editors can create and update; admins can rename stages, merge, and erase.
- Contact stages default to `new`, `qualified`, `customer`, and `lost`, with tenant editable names. Contacts support tags, per-channel consent, and at most 20 custom fields.
- Contact merge moves conversations and identities, combines tags/custom fields/consent, and records an audit event. Erasure always deletes identities and can erase messages in linked conversations when explicitly requested.
- Existing widget lead capture continues to create/update the tenant contact and record website consent. Added dashboard list and profile pages, CSV export, and a browser journey.

## Evidence

- API: `ruff check .`, `ruff format --check .`, `mypy`, and `pytest -q` all passed in the isolated API container using a fresh `_test` database. Result: 226 passed, one existing Starlette/httpx deprecation warning; strict mypy covered 127 source files.
- Web: lint, typecheck, Prettier, and Webpack production build passed.
- Playwright: `tests/contacts.spec.ts` passed (1 test) on Chromium against a fresh disposable database. Playwright configuration was temporarily adjusted to use the built Webpack bundle, then restored.
- API tests cover tenant A/B access, viewer permissions, duplicate contact values, the 20-field limit, profile timeline/identities, audited merge, export, and erasure. Existing widget lead tests verify consent capture.

## Limitations

- Contacts and CRM are not yet included in the phase owner sign-off. The full P5-03 handoff journey remains pending its final rerun.
- Sentiment is deferred to P7 plan quotas at the owner's direction; follow-ups and the remaining P5-05 analytics work are tracked separately.
