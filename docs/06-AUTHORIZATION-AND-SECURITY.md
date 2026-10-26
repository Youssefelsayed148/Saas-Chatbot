# Security policy and permission matrix

Approved change note, 2026-10-16: client roles are **admin, editor, viewer**. `owner` is retired. Platform operators are users with `is_platform_staff`, independently of tenant membership. Every tenant route declares `x-minimum-role` in OpenAPI, enforced by the tenant dependency. Hidden tenant resources return 404 before role checks; insufficient roles in an accessible tenant receive 403.

| Action | Admin | Editor | Viewer | Platform operator |
|---|---|---|---|---|
| Read inbox, contacts and insights; bot status | Yes | Yes | Yes | Read access |
| Inbox actions, replies, takeover/resolve/assign, tags/notes; follow-ups; contact create/edit | Yes | Yes | No | Requires tenant membership for inbox actions |
| Members/roles, invitations, audit, exports and CSVs | Yes | No | No | Yes |
| Contact stage config, merge/delete; conversation delete | Yes | No | No | Yes (membership needed for ordinary inbox actions) |
| Install snippet and bot widget config; sources/documents/chunks, parse status, jobs, revisions, Q&A template | No | No | No | Yes, no membership required |
| Request a change and view requests | Yes | No | No | Triage queue |
| Bot create/archive/PATCH, settings/persona/widget domains | No | No | No | Yes, no membership required |
| Knowledge uploads, ingestion, job cancel/retry, publish | No | No | No | Yes, no membership required |
| Playground conversation/messages/feedback | No | No | No | Yes, no membership required |
| Organization delete with exact-name body confirmation | No | No | No | Yes, no membership required |

The last active admin cannot be removed or demoted. Tenant-row locks serialize those checks; ownership transfer has no endpoint or UI. Removing a member revokes the active membership while retaining its historical sender/assignment foreign-key anchor. Migration 0013 maps existing memberships and invitations from owner to admin, then removes owner from database constraints.

Deletion disables bots/widgets, revokes current member login sessions, revokes memberships and invitations, expires visitor sessions and cancels jobs immediately. Users with other organizations can sign in again; deleted organizations stay inaccessible. The independent `organization_deletions` ledger survives tenant purge and holds the grace deadline, counts, actor, reason and temporary storage manifest. `ORG_DELETION_GRACE_DAYS` defaults to 30. The worker purges after the deadline; storage failures preserve the ledger/tenant for retry. No restore UI is included.

Change requests accept `knowledge|text_change|domain|delete_org|other`, bounded text and optional bounded private attachments. Client admins submit/list; staff triage `pending|triaged|in_progress|completed|rejected`. Attachments are downloaded through scoped authorization with attachment disposition and nosniff; they are never rendered as active content. A request does not execute its requested action automatically.

With self-service signup disabled, registration requires a valid, unexpired, unrevoked, unused invitation token for the registering email and an active tenant. The API validates this before creating an account. Channel connections and per-channel analytics filters remain deferred to the owner's Phase 3 scope; no channel work is authorized by this change.

## Invariants
Enforce authorization server-side; never trust client-supplied tenant, role, bot or widget origin alone. Tenant resource IDs must be checked with tenant scope on reads/writes. Hash passwords with Argon2id or equivalent. Sessions: HttpOnly, Secure in production, SameSite, rotation/revocation, CSRF protection for cookie-based writes. No logs containing tokens or visitor PII. Audit privileged actions.
## Ingestion threat model
Malicious or oversized uploaded files (zip bombs, huge PDFs, macros), prompt injection inside document text, and malicious source_url values. Enforce size/type/page limits, parse in the worker with timeouts, accept only http(s) source URLs. Untrusted document text is DATA, never system instruction. If an in-app URL fetcher is ever added: SSRF, DNS rebinding, redirect pivots and egress restrictions become mandatory first.
## Channel and inbox security
Many endpoints use HMAC signatures, not cookies/CSRF: constant-time compare, 5-minute timestamp window, event_id dedupe, per-connection secrets stored encrypted and rotatable, and the connection must be known and not revoked and map to exactly one tenant+bot. Paused connections accept and store authenticated events but do not trigger AI or outbound sends; events never carry a trusted tenant_id. Agent replies are authorized by tenant role and conversation tenant. Internal notes never leave the dashboard API. SSE streams are tenant-scoped and re-check membership on reconnect. Contact PII (phone, email) is never logged. Outbound follow-ups/broadcasts require recorded opt-in per contact and channel.

Contract v1.1 hardening (ADR-023): the event `channel` must equal the connection's channel (422 otherwise, nothing stored); signature comparison is byte-wise so a non-ASCII `X-Osiris-Signature` is a generic 401, never a 500; `received_at` is clamped to [now-24h, now+5min] (else receipt time); inbound events of one conversation are processed in receipt order under a per-conversation lock; a per-contact flood guard (15 messages per minute) stores messages without calling the AI; at most one busy/quota reply per conversation per 10 minutes. Channel answers are plain text (no markdown, citations or source links). Only platform staff see Many URLs, references and secrets; client roles get the read-only card.
## Tests
Tenant A cannot read/write B's bots by changing IDs; viewer cannot mutate; staff privilege is separate from client membership; expired visitor capability rejected; job cannot act on foreign tenant; forged/replayed/duplicate Many events; connection of tenant A cannot create data in tenant B; viewer cannot reply; two-agent takeover race; session fixation and CSRF checks; no test suite may target a non-disposable DB.

Knowledge and install pages and navigation are hidden for every client role. Bot list/detail remain available for status, with config and widget locator redacted for all clients. No separate snippet endpoint exists (the tenant route contract remains exactly 77 routes). Conversation and inbox responses redact citations for clients; visitor message and history responses never expose citations. Client exports exclude bot config, knowledge sources/documents/chunks/revisions/jobs and message citations; staff exports retain them. Retrieval still validates and stores citations internally.
