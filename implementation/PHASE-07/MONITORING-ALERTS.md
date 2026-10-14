# Monitoring and alert definitions

Status: proposed thresholds for owner/hosting review. Thresholds below are
initial operational targets, not claims about current production monitoring.

| Signal | Initial alert condition | Response |
|---|---|---|
| API health/readiness | 3 consecutive failed probes over 3 minutes | Check app, DB reachability, recent release, and migration state. |
| API server errors | 5xx rate above 2% for 5 minutes with at least 50 requests | Inspect request IDs and sanitized stack traces; do not log message bodies. |
| Worker heartbeat | No heartbeat for 2 minutes | Check worker process and DB connectivity; inspect oldest job. |
| Stuck jobs | Queued or running job older than 10 minutes | Inspect job type, attempts, worker heartbeat, and tenant-scoped error; retry only after review. |
| Failed jobs | More than 5% of jobs fail in 15 minutes, minimum 10 jobs | Group by job type and sanitized error; pause repeated unsafe retries. |
| Database capacity | Connection pool above 80% for 10 minutes | Inspect slow queries and pool saturation; scale only under approved hosting plan. |
| Disk/object capacity | Filesystem/object quota above 80% | Check growth and retention; preserve customer data. |
| Backup freshness | Last successful backup older than 26 hours | Escalate to operations owner and inspect backup job/provider status. |
| Quota counter | A tenant reaches 80% or 100% of an enforced plan limit | 80% warns; 100% blocks new work with the documented product behavior. |

Alert labels should include environment, service, release, request/job ID, and
tenant ID only where access controls permit. Exclude credentials, session tokens,
visitor capability tokens, message text, uploaded content, and full PII.

## Failed channel delivery

Many-backed channel delivery and connection health belong to P6 and are not
implemented in this release. When that integration exists, alert on failed
delivery attempts and stale connection health; thresholds and recovery ownership
must be agreed with Many and recorded before enabling the channel.

## Verification status

No production alert receiver, telemetry backend, or notification route has been
selected or configured. A staging smoke test and alert-delivery test remain
UNVERIFIED until ADR-007 is approved.
