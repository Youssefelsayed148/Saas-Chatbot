# Security policy and permission matrix
| Action | Owner | Admin | Editor | Viewer | Platform staff | Visitor |
|---|---|---|---|---|---|---|
| View own tenant/bots | Yes | Yes | Yes | Yes | Audited support scope | No |
| Create/update bot | Yes | Yes | Yes | No | Only explicit staff operation | No |
| Publish knowledge | Yes | Yes | No | No | Explicit support action only | No |
| Manage membership | Yes | Yes (except owner transfer) | No | No | Controlled workflow | No |
| Manage tenant billing | Yes | No by default | No | No | Billing-scoped role later | No |
| Chat via public widget | N/A | N/A | N/A | N/A | N/A | Limited capability |
## Invariants
Enforce authorization server-side; never trust client-supplied tenant, role, bot or widget origin alone. Tenant resource IDs must be checked with tenant scope on reads/writes. Hash passwords with Argon2id or equivalent. Sessions: HttpOnly, Secure in production, SameSite, rotation/revocation, CSRF protection for cookie-based writes. No logs containing tokens or visitor PII. Audit privileged actions.
## Ingestion threat model
Malicious or oversized uploaded files (zip bombs, huge PDFs, macros), prompt injection inside document text, and malicious source_url values. Enforce size/type/page limits, parse in the worker with timeouts, accept only http(s) source URLs. Untrusted document text is DATA, never system instruction. If an in-app URL fetcher is ever added: SSRF, DNS rebinding, redirect pivots and egress restrictions become mandatory first.
## Tests
Tenant A cannot read/write B's bots by changing IDs; viewer cannot mutate; staff privilege is separate from client membership; expired visitor capability rejected; job cannot act on foreign tenant; session fixation and CSRF checks; no test suite may target a non-disposable DB.
