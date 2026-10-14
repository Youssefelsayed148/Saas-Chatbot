# Hosting options for ADR-007

Status: decision brief only. ADR-007 remains **OPEN**. No hosting provider,
region, account, cloud resource, or deployment has been selected or created.

## Current application shape

The repository runs PostgreSQL with pgvector, FastAPI, Next.js, and a worker from
the API codebase. Background jobs are stored in PostgreSQL. Knowledge files use
the `Storage` interface with a local-disk adapter. A multi-instance deployment
therefore needs shared durable object storage and coordinated database/object
backups. Hosting must support tenant data isolation, HTTPS, protected secrets,
health checks, migrations, logs without sensitive payloads, and recovery tests.

## Options to evaluate

| Option | Benefits | Decisions and risks to resolve |
|---|---|---|
| Single Linux VPS + Compose | Closest to current Compose topology; simplest deployment shape and likely low initial operational complexity | Single-host failure domain; operator owns patching, database HA, backup verification, firewall, secret handling, disk/storage growth, and restore. Shared object storage still needed for durable multi-instance growth. |
| Managed container/app hosting + managed PostgreSQL | Provider handles more runtime/database operations; independent scaling paths | Confirm worker support, pgvector/version compatibility, private networking, migration workflow, region/residency, backup restore access, object store, logs, and provider-specific lock-in/cost. |
| Cloud container/orchestration platform + managed PostgreSQL/object storage | More control over scaling, networking, and service isolation | Higher setup and operational burden; define network/IAM, secrets, observability, deployment rollback, worker scaling, data transfer, and costs. |

These are deployment patterns, not vendor recommendations. Compare real providers
after expected traffic, support capacity, residency needs, and budget are known.

## ADR-007 decisions required

1. Hosting model/provider and environment ownership.
2. Database provider/version, availability, backup/PITR, and migration/rollback
   procedure.
3. Object storage provider, encryption, lifecycle, migration from local storage,
   and deletion verification behavior.
4. Primary region and data residency requirements.
5. Retention periods for tenant data, audit events, backups, and logs.
6. RPO/RTO, restore drill cadence, monitoring destination, incident response and
   notification ownership.
7. Secret source/rotation, HTTPS gateway and trusted-proxy configuration.
8. Budget and who can approve recurring infrastructure spend.

## Gate

No deployment is authorized by this document. After the owner records ADR-007,
revisit the backup plan, monitoring thresholds, security review, and full green
Playwright requirement. P5-03, P5-05, phase sign-offs, and the P7 checklist remain
unticked. Stop here for product/owner review of ADR-007.
