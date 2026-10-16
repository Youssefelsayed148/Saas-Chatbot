Run from `apps/api`: `python -m scripts.seed_demo` after applying existing Alembic migrations.
Set `DATABASE_URL` explicitly to PostgreSQL ending `_dev` or `_demo`; test, production-like, and non-development targets are refused.
Set `DEMO_SEED_PASSWORD` (8–128 characters); `_dev` alone permits the fake default `FakeDemoOnly!123`; optionally set `STORAGE_ROOT`.
Creates Demo Dental Clinic (Business PLACEHOLDER), three `demo-{admin,editor,viewer}@example.com` client logins, an active FAQ bot, three contacts and six fictional inbox threads including Arabic.
Re-running preserves existing demo edits and logins; a different password or conflicting identity is refused; no model/API calls, database creation or migrations are performed.

Migration 0013 maps old owner roles to admin and retires the shipped demo-owner login, preserving its historical identity references. Use demo-admin@example.com. No client demo account is platform staff; use a separately provisioned staff account for bot controls.
