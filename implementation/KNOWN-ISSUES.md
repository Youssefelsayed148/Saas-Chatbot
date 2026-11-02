# Known issues

Reviewed 2026-11-02. The original list dated 2026-10-14; items answered by the Nov 2026 test runs are marked and kept in the resolved list. Everything else is still open. The previous version is `git show ed965ab:implementation/KNOWN-ISSUES.md`.

## Open

- **Phase sign-off:** P5-03, P5-05 and the P5 phase sign-off are unticked in `implementation/PHASE-CHECKLISTS.md` (owner decision; the P5 browser gate was deferred by the owner).
- **Handoff journey in a real browser:** the widget/browser root cause of the earlier handoff report was never established. It has not been reproduced: the Playwright handoff and widget specs pass in the full run of 2026-11-02. `?debugWidget=1` logs poll status and sender types without message text. Close this after an owner browser check.
- **AI cost analytics:** unavailable because provider pricing is not stored. Provider-returned usage is recorded when available (`docs/13-SUBSCRIPTIONS-AND-USAGE.md`).
- **Quotas and pricing:** quota values are placeholders and pricing is TBD (ADR-008).
- **Tenant deletion:** uploaded files are removed through the storage interface, whose local delete is best-effort if the OS refuses `unlink` (`apps/api/app/knowledge/storage.py`, `LocalStorage.delete`).
- **Backup and restore drill:** not yet performed. Hosting is decided (ADR-007: existing VPS, Docker, `scripts/deploy.sh`, `deploy/backup.sh`); the drill, backup target and RPO/RTO still need owner review. See `docs/operations/BACKUP-RESTORE.md` and `DEPLOY.md`.
- **Independent security review:** pending; no reviewer sign-off (`docs/operations/SECURITY-REVIEW.md`).
- **Alert receiver:** the production alert receiver and an alert-delivery test have not been verified (`docs/operations/MONITORING-ALERTS.md`).
- **Demo seed integration:** guard and password tests pass offline; the idempotency, cross-tenant preservation, collision and storage-rollback checks against a disposable PostgreSQL have not been recorded (`implementation/DEMO-SEED.md`).
- **P7-01 operations UI:** no recorded manual browser check (the Playwright run covers the flows it contains).
- **Live delegation:** only one WhatsApp round trip has been observed with the Many side; the remaining live checks are tracked in the Many repository.

## Resolved

- 2026-11-02: **Full Playwright suite** was UNVERIFIED; it now passes (177 passed on `main` at `ed965ab`).
- 2026-11-02: **API integration tests** were UNVERIFIED without a disposable PostgreSQL; the full suite has been run (see `PROGRESS.md`). Nine tests need pgvector 0.8 or newer and one needs the socket guard described in `docs/15-TESTING-AND-ACCEPTANCE.md`.
- 2026-10-14: **P2 parser timeout** now runs in a spawned subprocess terminated at the wall-clock limit (regression test added).
- **Unanswered-twice handoff wording** now uses generic human-assistance wording in both languages (API regression assertion).
