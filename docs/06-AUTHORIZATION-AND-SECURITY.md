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
SSRF against metadata/internal addresses, DNS rebinding, redirect pivots, browser subresource fetches, malicious documents, prompt injection and oversized responses. Require network-layer egress restrictions in addition to URL validation; enforce limits on time, bytes, pages and redirects. Untrusted website text is DATA, never system instruction.
## Tests
Tenant A cannot read/write B's bots by changing IDs; viewer cannot mutate; staff privilege is separate from client membership; expired visitor capability rejected; job cannot act on foreign tenant; session fixation and CSRF checks; no test suite may target a non-disposable DB.
