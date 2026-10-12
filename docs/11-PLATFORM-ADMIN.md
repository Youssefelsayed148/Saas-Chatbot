# Platform admin console — manage all clients (ADR-018)
Separate route group `/platform`, protected by the server-validated `users.is_platform_staff` flag (never a tenant role). Any cross-tenant operation needs actor attribution, a reason and narrow authorization. No impersonation or arbitrary edits. Built in two steps.
## Basics — P4-06 (so first clients can be onboarded)
- **Clients list:** every tenant with plan label, status, bot count, seat count, message usage this month, last activity; search and filter.
- **Client detail:** bots and their status, knowledge/revision and failed-job summary, members and roles, recent audit events, usage so far.
- **Staff onboarding:** one form calling the shared `ProvisioningService` — tenant + owner one-time invite link (no email provider, ADR-004) + bot + optional upload of the website-to-knowledge skill output. Idempotency-Key; durable request record with progress and retry; actor recorded in audit.
## Advanced — P7
- **Operations:** job queue health, retry/cancel job, failed deliveries, stuck conversations, Many connection health (last event, failures), secret rotation, pause bot or connection (reason required).
- **Plans and quotas:** assign a plan label, see who is near a limit (bots, seats, messages, contacts, connections).
- **Platform analytics:** total tenants, bots, conversations, messages, handoff rate, AI usage and estimated cost per client.
- **Audit review:** searchable audit trail of staff and tenant privileged actions.
- Later: billing support once a provider is approved (ADR-008).
## Tests
Non-staff get 403/404; staff flag is separate from tenant roles; every support action requires a reason and writes an audit row; double submit of onboarding creates one tenant.
