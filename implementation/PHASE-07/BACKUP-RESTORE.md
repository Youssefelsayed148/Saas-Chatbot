# Backup and restore plan

Status: procedure defined; successful restore drill UNVERIFIED. ADR-007 must
choose the database provider, object store, region, retention period, encryption,
and recovery objectives before configuring backups.

## Data that must be recover together

- PostgreSQL database, including tenant rows, audit rows, job state, and
  knowledge metadata.
- Uploaded source objects from the selected `Storage` adapter.
- Application configuration and migration history, excluding secrets from
  source control and logs.

Database and uploaded-object snapshots must have coordinated timestamps or an
explicit consistency strategy. A database-only restore can leave source rows
pointing at missing files; an object-only restore can leave unreferenced files.

## Proposed controls (owner review required)

- Encrypted backups in a separately controlled account/location from the live
  environment; least-privilege backup and restore identities.
- Daily database and object backups, with point-in-time recovery if supported by
  the selected provider. Proposed initial retention: 30 daily copies, subject to
  ADR-007 and applicable retention requirements.
- Alert when the last successful backup exceeds 26 hours or a scheduled backup
  fails. Record backup ID, timestamp, scope, encryption status, and restore test.
- Restrict restore access; log access and periodically verify that a backup can
  be decrypted and restored.

## Safe disposable restore drill

1. Obtain a named disposable restore database and isolated storage directory.
   Confirm both are empty or explicitly disposable before use.
2. Select a synthetic fixture snapshot. Never use production customer content in
   an unapproved test environment.
3. Restore the database and corresponding object snapshot to those disposable
   targets. Do not use the live database URL or shared development database.
4. Apply no migrations until the restored revision is recorded. Then verify
   Alembic revision, tenant counts, representative source/object checksums,
   tenant export, widget read, and audit trail.
5. Record elapsed restore time, missing objects, row counts, checksums, and
   cleanup. Delete only the explicitly named disposable targets after review.

## Evidence

- Drill status: **UNVERIFIED**; no disposable target was configured for this
  release-readiness pass, and no database was modified.
- RPO/RTO: **TBD by ADR-007 and owner review**.
- Provider-specific backup commands and credentials: **TBD after ADR-007**.
