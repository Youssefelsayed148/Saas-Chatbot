# Security policy and permission matrix
| Action | Owner | Admin | Editor | Viewer | Platform staff | Visitor |
|---|---|---|---|---|---|---|
| View own tenant/bots | Yes | Yes | Yes | Yes | Audited support scope | No |
| Create/update bot | Yes | Yes | Yes | No | Only explicit staff operation | No |
| Publish knowledge | Yes | Yes | No | No | Explicit support action only | No |
| Manage membership | Yes | Yes (except owner transfer) | No | No | Controlled workflow | No |
| Manage tenant billing | Yes | No by default | No | No | Billing-scoped role later | No |
| Read inbox, contacts | Yes | Yes | Yes | Yes | Audited support scope | No |
| Reply, take over, assign, edit contacts, schedule follow-ups | Yes | Yes | Yes | No | No | No |
| Link a Many channel connection | Yes | Yes (staff approval) | No | No | Yes | No |
| Chat via public widget | N/A | N/A | N/A | N/A | N/A | Limited capability |
## Invariants
Enforce authorization server-side; never trust client-supplied tenant, role, bot or widget origin alone. Tenant resource IDs must be checked with tenant scope on reads/writes. Hash passwords with Argon2id or equivalent. Sessions: HttpOnly, Secure in production, SameSite, rotation/revocation, CSRF protection for cookie-based writes. No logs containing tokens or visitor PII. Audit privileged actions.
## Ingestion threat model
Malicious or oversized uploaded files (zip bombs, huge PDFs, macros), prompt injection inside document text, and malicious source_url values. Enforce size/type/page limits, parse in the worker with timeouts, accept only http(s) source URLs. Untrusted document text is DATA, never system instruction. If an in-app URL fetcher is ever added: SSRF, DNS rebinding, redirect pivots and egress restrictions become mandatory first.
## Channel and inbox security
Many endpoints use HMAC signatures, not cookies/CSRF: constant-time compare, 5-minute timestamp window, event_id dedupe, per-connection secrets stored encrypted and rotatable, connection must be active and map to exactly one tenant+bot; events never carry a trusted tenant_id. Agent replies are authorized by tenant role and conversation tenant. Internal notes never leave the dashboard API. SSE streams are tenant-scoped and re-check membership on reconnect. Contact PII (phone, email) is never logged. Outbound follow-ups/broadcasts require recorded opt-in per contact and channel.
## Tests
Tenant A cannot read/write B's bots by changing IDs; viewer cannot mutate; staff privilege is separate from client membership; expired visitor capability rejected; job cannot act on foreign tenant; forged/replayed/duplicate Many events; connection of tenant A cannot create data in tenant B; viewer cannot reply; two-agent takeover race; session fixation and CSRF checks; no test suite may target a non-disposable DB.
