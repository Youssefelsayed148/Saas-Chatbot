# Phase 5 report — Inbox, handoff, contacts, and follow-ups

**Status: blocked at the owner verification gate; not ready for sign-off.** The Linux API suite passes. The full Playwright suite, including the P5-03 visitor → waiting_human → agent reply → visitor sees it → return to AI journey, did not start because Windows returned `spawn EPERM`. The web production build was also blocked by `spawn EPERM`. P5-03 and P5-05 checklist items and all owner sign-off lines remain open.

## Built

- P5-01/02: conversation handoff and agent actions, visitor-visible agent replies, tenant-scoped inbox listing, unread/read state, notifications, and database-backed SSE.
- P5-03: inbox list and conversation thread UI with filters, live updates, notes, tags, assignment, reply, takeover, resolve, return-to-AI, citations, feedback, and role-aware controls. The required full handoff browser journey is present but unverified.
- P5-04: contact CRM as documented in `P5-04-REPORT.md`.
- P5-05: website follow-up scheduling/cancellation, durable delivery job, next-visit widget delivery, and tenant-scoped handoff/response-time/channel/status/sentiment/workload analytics.
- Per the owner decision dated 2026-10-14, P5 only aggregates sentiment values already present. Classification and cost caps move to P7-02; the analytics page says “Sentiment not measured yet” when there are no measured values.

## Verification evidence

- Linux API checks, fresh disposable database (the fixture-created database is named `p5_close_test_test`):
  - `docker run --rm --name p5-close-api-full --network saas-chats-ai-dev_default -e DATABASE_URL=postgresql://p5close:<temporary-test-password>@p5-close-db:5432/p5_close_test -e STORAGE_ROOT=/tmp/p5-test-storage -v "${PWD}:/workspace" -w /workspace/apps/api saas-chats-ai-p5-close-checks sh -lc 'ruff check . && ruff format --check . && mypy && pytest -q'` — EXIT 0. Ruff passed; 138 files formatted; mypy passed for 134 source files; `228 passed, 1 warning in 117.02s` (Starlette/httpx deprecation).
  - `docker run --rm --name p5-close-regression --network saas-chats-ai-dev_default -e DATABASE_URL=postgresql://p5close:<temporary-test-password>@p5-close-db:5432/p5_close_test -e STORAGE_ROOT=/tmp/p5-test-storage -v "${PWD}:/workspace" -w /workspace/apps/api saas-chats-ai-p5-close-checks sh -lc 'pytest -q tests/test_inbox_list.py tests/test_followups_analytics.py --tb=short'` — EXIT 0, `7 passed, 1 warning in 8.54s`. Includes all five inbox-list tests and regression coverage that a delivered follow-up appears once as the latest inbox message.
- Web checks:
  - `npm.cmd run lint --workspace apps/web` — EXIT 0.
  - `npx.cmd prettier --check app lib tests` from `apps/web` — EXIT 0.
  - `npm.cmd run typecheck --workspace apps/web` — EXIT 0; Next used its WASM SWC fallback.
  - `npm.cmd run format:check` — EXIT 1 because the repository-level check reports pre-existing `package.json` formatting. The web-only Prettier check above passed.
  - `npm.cmd run build --workspace apps/web -- --webpack` — EXIT 1, Next.js production build returned `spawn EPERM` during compilation.
  - With `DATABASE_URL` set to the disposable test base, `STORAGE_ROOT` set inside the workspace, and `CHAT_STUB_MODEL=1`, `npm.cmd test --workspace apps/web -- --reporter=line` — EXIT 1 before tests launched: Playwright returned `spawn EPERM`.

The earlier Windows API run reported `106 passed, 5 failed, 118 errors`, alongside denied pytest/cache and knowledge-storage writes. In the clean Linux container with test-only storage and a disposable `_test` database, all five inbox-list tests pass and the full API suite passes. No application failure was reproduced in that environment; the prior Windows result is not counted as a pass.

## Owner rerun required to pass the gate

Run from the repository root in an unrestricted PowerShell terminal. Enter a disposable PostgreSQL connection URL whose database name ends in `_test`; the E2E setup creates and migrates its separate `_e2e_test` database. No `.env` values or model keys are needed.

```powershell
$env:DATABASE_URL = Read-Host 'Disposable PostgreSQL connection URL (database name must end in _test)'
$env:STORAGE_ROOT = Join-Path $PWD '.test-storage'
$env:CHAT_STUB_MODEL = '1'
npm.cmd test --workspace apps/web -- --reporter=line
```

The Playwright config is restored to its original build-and-start command: `npm run build && npm run start -- --port 3100`.

## Limitations

- The full Playwright suite and the P5-03 handoff journey remain unverified; owner rerun required before closing P5.
- Hosting (ADR-007) remains open. Nothing was deployed.
- Follow-ups are website-only and appear when the visitor next reads widget history. No Meta/Many code was added.
- No `.env` file or API key was read, printed, or logged. No paid API, cloud resource, deployment, push, or production database was used.
