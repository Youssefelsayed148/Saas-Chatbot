# P7 security review record

Status: internal source review checklist prepared; independent security review
OPEN and UNVERIFIED. This document does not constitute independent approval.

## Review scope and evidence to inspect

- Upload and ingestion: file limits, MIME/signature validation, chunked requests,
  storage-key generation, subprocess timeout, parser resource limits, and
  tenant-scoped source access.
- Authentication and CSRF: session creation/rotation/revocation, origin checks,
  cookie attributes, CSRF checks on writes, and signup replay behavior.
- Tenant isolation and RBAC: tenant A/B access for every new endpoint; viewer
  denial for each mutating or admin-only endpoint; hidden-resource 404 behavior.
- Prompt injection: retrieval/content boundaries and the rule that source text
  cannot override system instructions or trigger tool access.
- Export/delete: excluded credential hashes and capability tokens, tenant scope,
  exact-name confirmation, audit actor/reason, cascade behavior, and storage
  object deletion evidence.
- Platform operations: staff-only access, reason-required overrides, audit
  completeness, and measured-usage semantics.
- SSE and public widget: origin/CORS, capability-token scope, rate limits,
  output encoding, and sensitive-data exposure.
- HMAC channel endpoint: P6-only; review signed body, timestamp window,
  idempotency, replay protection, secret storage/rotation, and delegated mode
  before enabling Many integration.

## Findings and disposition

No independent reviewer has supplied findings for this P7 pass. Do not treat the
absence of findings here as a clean review. Record each finding with severity,
affected route/component, reproduction, owner, remediation commit, and retest
evidence. The known issues inventory remains authoritative for open product and
verification issues.

## Required sign-off

Independent reviewer, review date, scope/version, findings, remediation status,
and owner acceptance are pending. No phase checklist or sign-off was changed.
