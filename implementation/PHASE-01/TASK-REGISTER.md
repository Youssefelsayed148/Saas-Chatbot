# Phase 1 ticket register
| Ticket | Name | Dependencies | Status |
|---|---|---|---|
| P1-01 | Repo and toolchain | none | DONE (see P1-01-REPORT.md; hosted CI not run) |
| P1-02 | Schema, migrations, auth | P1-01 | DONE LOCALLY (see P1-02-REPORT.md) |
| P1-03 | Tenants, roles, bot API | P1-02 | DONE LOCALLY (see P1-03-REPORT.md) |
| P1-04 | Dashboard UI + Phase 1 verification | P1-03 | DONE LOCALLY (see P1-04-REPORT.md; Playwright 5 passed against the real API) |

Phase verification: implementation/PHASE-01/PHASE-REPORT.md. Awaiting owner sign-off.

Note (structure deviation recorded): modules live at `apps/api/app/{auth,tenants,bots}/` (not `app/modules/...`) and tests are flat under `apps/api/tests/` with `__init__.py`; behaviour and coverage match the spec.
