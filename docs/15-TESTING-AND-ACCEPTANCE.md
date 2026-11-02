# Testing strategy and gates
Unit: auth, role checks, tenant filters, bot lifecycle, provisioning idempotency, chunk/citation logic. Integration: migrations from empty DB, concurrent writes, job claim/retry, API contract and quota enforcement. E2E: handoff and takeover (visitor, bot, agent, widget), contact/CRM flow, client admin onboarding, staff onboarding, source publish, widget chat, tenant separation. Contract (P6): fake ManyOsirisChat server, signature/timestamp/replay/duplicate/out-of-order events, delivery status ordering, window_closed handling. Security: malicious/oversized upload handling, prompt injection, CSRF, session expiration, public capability abuse, no test production DSN. Quality: Arabic/English answer sets, abstention and citation verification.

## Acceptance criteria added by the account/administration slices (S1–S4)
- **Closed registration (default):** with `self_serve_signup=false`, `POST /auth/register` without a valid invitation token returns 403 `INVITATION_REQUIRED`, the login screen shows no Register link, and `/register` states that registration is by invitation only. With the flag explicitly on, the P7 self-service flow still passes its suite.
- **Change password:** any signed-in user (client user or platform staff) changes their own password at `/account`; wrong current password → 400 `INVALID_CURRENT_PASSWORD` (throttled 5/300s per user, then 429), same-as-current → 400 `PASSWORD_UNCHANGED`, policy failure → 422; success revokes every other session, keeps the current session alive via rotation, and writes `auth.password_changed` with the user as actor; the old password then fails login and the new one succeeds. No password or hash appears in any response or log.
- **Staff-only enforcement:** platform endpoints return 403 to authenticated non-staff (tenant admin and tenant member) and 401 to anonymous callers; staff never borrow tenant roles and cannot impersonate.
- **Deactivation:** deactivating a user revokes all their sessions immediately; reactivation restores sign-in.
- **No cross-organization data:** every list is scoped so one organization's members/bots/audit never appear in another's.

Each ticket done only if implementation, tests, docs, acceptance evidence and limitations reported. No claim of green tests without exact commands/output. Phase gate requires independent review; no deployment without separate approval.

## How the suites are run (verified 2026-11-02)

Use a disposable PostgreSQL only; the suites create and truncate databases.

| Suite | Size and time observed | Needs |
| --- | --- | --- |
| API (`apps/api`, pytest) | 1,217 tests, about 42 minutes on a 2-CPU sandbox | PostgreSQL 16 with **pgvector 0.8 or newer** (hybrid retrieval uses `hnsw.iterative_scan`; with 0.6 about nine retrieval/embedding tests fail) and the `citext` extension. Set `ENVIRONMENT=test` and `TEST_DATABASE_URL` to a base URL; tests use `<name>_test`. |
| API migration guard (`tests/test_r19_index_migration.py`) | one test | `PGHOST` set to a Unix socket directory `/var/tmp/saas-*/<dir>`, `PGPORT`, and a base database name ending in `_test`. |
| Playwright (`apps/web`) | 177 tests in 39 files, about 6 minutes | The pinned Playwright browser build installed (`npx playwright install chromium`), `E2E_PYTHON` pointing at a Python with the API dependencies, and `TEST_DATABASE_URL`. The whole-run limit in `playwright.config.ts` is 30 minutes. |
| Scripts (`scripts/test_*.py`) | seconds | Python 3 only; `check_contract_copies.py` verifies the contract copies. |

Notes:

- The repo root for the test helpers is the directory containing `compose.yaml`.
- The evaluation test rewrites `implementation/PHASE-03/EVAL-REPORT.md` on every run; that folder is git-ignored.
- Hosted CI is configured in `.github/workflows/ci.yml`; local runs are the evidence recorded in `PROGRESS.md`.
- Last recorded results: full Playwright 177 passed on `main` at `ed965ab`; API 1,207 passed plus 10 environment-related failures that passed once pgvector 0.8.5 was installed (see `PROGRESS.md`).

