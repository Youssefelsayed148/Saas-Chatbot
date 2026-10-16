# Platform admin console — manage all clients (ADR-018)
Separate route group `/platform`, protected by the server-validated `users.is_platform_staff` flag (never a tenant role). Any cross-tenant operation needs actor attribution, a reason and narrow authorization. No impersonation or arbitrary edits. Built in two steps.
## Basics — P4-06 (so first clients can be onboarded)
- **Clients list:** every tenant with plan label, status, bot count, seat count, message usage this month, last activity; search and filter.
- **Client detail:** bots and their status, knowledge/revision and failed-job summary, members and roles, recent audit events, usage so far.
- **Staff onboarding:** one form calling the shared `ProvisioningService` — tenant + admin one-time invite link (no email provider, ADR-004) + bot + optional upload of the website-to-knowledge skill output. Idempotency-Key; durable request record with progress and retry; actor recorded in audit.
## Advanced — P7 (all P7 tickets complete before P6)
- **Operations:** job queue health, retry/cancel job, failed SaaS jobs, stuck conversations, pause bot (reason required); channel delivery and Many connection health/secret rotation are implemented with the Many contract in P6.
- **Plans and quotas:** assign a plan label, see who is near a limit (bots, seats, messages, contacts, connections); P7-02 enforces quotas and runs sentiment within its quota/cost cap.
- **Platform analytics:** total tenants, bots, conversations, messages, handoff rate, AI usage and estimated cost per client.
- **Audit review:** searchable audit trail of staff and tenant privileged actions (P7-04).
- P7-01 through P7-05, including release readiness and a full green Playwright run, are required before P6 starts. P6 contains only Many-dependent channel integration and operations.
- Later: billing support once a provider is approved (ADR-008).
## Tests
Non-staff get 403/404; staff flag is separate from tenant roles; every support action requires a reason and writes an audit row; double submit of onboarding creates one tenant.
