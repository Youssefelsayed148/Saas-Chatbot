# P7 operational runbook

Status: DRAFT for product/operations review. No environment has been deployed or
configured by this runbook. Complete ADR-007 before selecting production values.

## Start and health checks

1. Confirm the approved release commit, migration set, and rollback owner.
2. Confirm the target environment, secret source, database, object storage,
   public origins, and backup destination match the approved ADR-007 record.
3. Apply Alembic migrations using the release procedure against the intended
   environment. Verify API readiness, database connectivity, and worker heartbeat.
4. Check a test tenant end-to-end: sign in, create a bot, upload and ingest a
   small document, publish, send a widget message, inspect the inbox, and export
   tenant data. Use synthetic data only.
5. Review error rate, failed jobs, oldest queued job, storage use, and backup age.

## Incident handling

- **API unavailable:** check health/readiness, database reachability, recent
  release and migration, then roll back the application release if the approved
  rollback procedure permits it. Do not reverse a migration without a reviewed
  recovery plan.
- **Worker stalled:** inspect heartbeat and oldest queued/running job; check
  worker logs by job ID and tenant ID without logging message bodies or secrets.
  Retry only after identifying whether the handler is idempotent; use platform
  operations with a reason so the action is audited.
- **Quota exhaustion:** verify the measured counter and plan label. Do not change
  placeholder limits or grant an override without an approved reason and audit.
- **Suspected tenant exposure:** restrict affected access using the approved
  incident authority, preserve relevant audit/log evidence, identify tenant
  scope, and follow the approved notification and retention policy. Those
  policies require ADR-007 and owner review.
- **Data export/deletion:** verify the tenant identity and role; deletion requires
  the exact organization name and reason. Verify database cascade and storage
  cleanup evidence; local storage deletion is best-effort on OS unlink errors.

## Recovery and rollback

Use `BACKUP-RESTORE.md` only after the hosting, storage, retention, and data
residency decisions are approved. Never restore over a live database as a test.
Keep rollback of the application release separate from database rollback.

## Current limitations

- Hosting, object storage, retention, and data residency are OPEN under ADR-007.
- Backup/restore drill, production monitoring, incident notification policy, and
  independent security review are UNVERIFIED or pending.
- Many delivery health is P6 scope; no Many integration or channel delivery
  alert is represented as operational today.
- Placeholder plan limits and pricing are not approved commercial terms.
