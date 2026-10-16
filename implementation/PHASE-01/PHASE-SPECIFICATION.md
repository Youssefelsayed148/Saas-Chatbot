# Phase 1 — Foundation (exact scope)
## Outcome
A developer runs web, API and DB locally. A user registers, logs in/out, creates an organization, switches between organizations they belong to, and creates/lists/edits/archives bots. Every displayed record comes from the real API. DB is built from scratch by Alembic. Tenant isolation and role rules are proven by tests.
## Tickets
| Ticket | Scope | Exit gate |
|---|---|---|
| P1-01 | Toolchain, Compose, health/ready, CI (DONE) | see P1-01-REPORT.md |
| P1-02 | SQLAlchemy 2 + Alembic; tables `users`, `sessions`, `tenants`, `memberships`, `bots`, `audit_events`; Argon2id; register/login/logout/me with cookie sessions + CSRF; `is_platform_staff` column (unused yet) | Upgrade/downgrade on disposable DB; constraint tests; valid/invalid/expired/revoked session tests; no secrets in logs |
| P1-03 | Tenant create/get/list-mine; membership roles; role dependency; bot create/list/get/update/archive (soft) with audit; stable error format | Role matrix tests (admin/editor/viewer and independent platform staff); tenant A/B isolation by guessed UUID returns 404; validation tests |
| P1-04 | Next.js: register, login, org selector/creation, bots list/create/edit/archive, role-aware UI, loading/error/empty states; Playwright E2E; phase verification report | Browser E2E creates tenant + bot against the real API; no mocked data in UI; all checks pass; owner sign-off |
## Directory contract (additions to P1-01)
`apps/api/app/modules/{auth,tenants,bots}/` each with `models.py, schemas.py, service.py, router.py`; `apps/api/app/db/{base.py,session.py}`; `apps/api/alembic/`; `apps/api/tests/{unit,integration}/`. Services receive tenant context explicitly; routers contain no business logic.
## Non-goals
Password reset/email, platform admin UI, provisioning service, worker, ingestion, AI calls, widget, billing, RLS.
## Rules
Soft archive only (no hard delete). Never accept `tenant_id` from a request body as authority — it comes from the URL path and is checked against the caller's membership. Tests run only against a disposable DB (guard: refuse to run unless the DB name ends with `_test`).
