# Codex Prompt Playbook — Copy/Paste Prompts

Version 1.0 | Use with 01_Master_Phased_Engineering_Plan.md and 03_New_Account_Handoff.md.

## Mandatory operating rules
Never paste the entire program into Codex as a single implementation command. Use prompt 00 for context, prompt 01 for P0, prompt 02 for P1 design, prompt 03 for one approved ticket, and phase prompts only after previous gates. Replace [PLACEHOLDERS] before use. Treat the source audit as static evidence; verify pinned SHAs and code before coding. Approval of architecture is not approval of code changes, deployments or spending.


## Prompt 00 — New ChatGPT account bootstrap

```text
You are the principal software architect and delivery lead for a multi-tenant AI Chatbot SaaS. Read all uploaded handoff documents in full before making any recommendation. The approved baseline is 01_Master_Phased_Engineering_Plan.md. Read the original static audit if uploaded, and validate any factual claim against pinned GitHub source. The products are website_chatbot and manyosiris: independent subscriptions, shared tenant identity and AI intelligence, one provisioning engine for self-service and platform-admin onboarding. Existing ManyOsirisChat remains an independent product. FIRST RESPONSE: (a) restate scope and immutable constraints, (b) show phase dependency plan and current status, (c) list unresolved decisions and P0 gates, (d) identify evidence gaps including retrivo_bot SHA, (e) prepare a concise plan for the next approved action. Do not change repositories or start coding. Never pretend the audit ran tests.
```

## Prompt 01 — P0 read-only validation

```text
Operate strictly READ-ONLY. Review pinned audit and all three repositories at recorded commits. Verify tracked secret exposure without printing values; test DSN safeguards; dangerous migration/test fixtures; auth/tenant risks; deployment config and known migration assumptions. Do not run test suites or scripts with side effects, rotate secrets, create branches or modify files. Produce an evidence ledger: finding ID, file:line, commit SHA, observed code, inferred risk, severity, proposed mitigation, owner action, acceptance test. Report missing exact SHA, unknown runtime state and explicit owner approvals required. End with P0 gate PASS/BLOCKED and a precise safe remediation plan; no implementation.
```

## Prompt 02 — P1 plan for Codex

```text
Architecture approved, P0 gate must be documented. Design P1 implementation without coding yet: monorepo boundaries; exact package tree; immutable migration sequence; tenants/users/memberships/product_grants; SKU-independent entitlements; OIDC issuer/subject; service auth; outbox/inbox; audit; composite FK and PostgreSQL RLS. Define FastAPI endpoints with Pydantic request/response/error schemas, permission matrix, DB transaction semantics, idempotency, tenant context and OpenAPI. Break into <=1-day Codex PRs with file paths, dependencies, tests, acceptance and rollback. Include malicious cross-tenant scenarios, disposable DB safety and CI gates. Flag OIDC/provider decisions as TBD rather than inventing. Request explicit implementation approval before edits.
```

## Prompt 03 — Codex execution contract — one approved ticket

```text
Implement ONLY ticket [TICKET_ID] from the approved plan in repository [REPO] on branch [BRANCH], after confirming the user has explicitly authorized these changes. First inspect current tree, git status and relevant files. Present minimal plan and expected changes. Respect all non-goals, tenant isolation and existing contracts. Never modify unrelated repositories, production resources, secrets, billing, deployment, or live data. Use disposable test DBs only. Write focused tests, migrations and docs. Run permitted checks, report exact commands and results, file diffs, risks and rollback. Stop if assumptions, schema drift, auth uncertainty or destructive operations arise; ask approval. Do not push, merge or deploy unless separately approved.
```

## Prompt 04 — P2 provisioning engine

```text
Design/implement only within explicitly approved P2 scope: one durable ProvisioningRequest orchestrator with self_service/admin_managed actor modes, same core state machine, product-specific step plans, per-step leases/heartbeat/fencing, idempotency key + payload hash, retries/backoff, compensation, outbox, reconciliation, observable progress. Support website-only, Many-only, and both. Never create a website crawl for Many-only. Produce schema, state diagram, API contracts, concurrency tests, duplicate webhook/retry tests and failure recovery proof. Do not treat UI redirects as payment authorization.
```

## Prompt 05 — P3 ingestion and RAG

```text
Design/implement approved P3 only: isolated crawler with network egress policy against SSRF, DNS rebinding, redirects and browser subresources; bounded sitemap/link traversal; safe parsers; incremental hashes; durable ingestion; staged immutable knowledge revisions and atomic publication; tenant/revision-filtered pgvector+FTS retrieval; evaluated Arabic/English grounding, citations, safe abstention, provider abstraction, usage reservation. Compare Rabbit Hole and Retrivo file-level modules before porting. Prohibit global deletes/locks, unsafe brand seed data and direct runtime schema creation. Provide adversarial tests and evaluation report.
```

## Prompt 06 — P4 widget and client experience

```text
Design/implement approved P4 only: iframe-based versioned widget loader, public bot locator and scoped visitor session capability, origin checks as browser signal (not authentication), abuse controls, SSE streaming and validated citations, Arabic/RTL/mobile/accessibility, tenant dashboard for bot setup, source status, publishing, leads, analytics and installation. Include exact permissions, E2E tests with two simultaneous tenants/widgets, no private config in public endpoint, and no per-client deployment.
```

## Prompt 07 — P5 subscriptions and operations

```text
Design P5 billing/provider adapter, but do not choose or activate a payment processor without owner confirmation of merchant eligibility in Egypt, recurring payments, currencies, invoicing and compliance. Implement only approved scope: independent website_chatbot and manyosiris entitlements, trial/grace/cancellation, signed raw-body webhook inbox, idempotency and reconciliation, product-attributed usage, staff-audited admin operations and alerts. Test replay/out-of-order/cancel/refund; prove cancelling one product does not disable the other. No live charges or webhook registration without approval.
```

## Prompt 08 — P6 ManyOsirisChat integration

```text
Plan and implement only approved P6 changes after pinned-source revalidation. Keep ManyOsirisChat separate. Create explicit workspace→canonical tenant mapping, scope all relevant routes, queries, workers, exports, cache and channel ownership. Use authenticated internal AI API and tenant-bound channel→bot mapping; preserve Meta signature verification, consent, template windows, campaigns, handoff and delivery states. Add transactional outbox/inbox and ambiguous-send reconciliation. Stage via feature flag/shadow traffic/canary, with contract, isolation, duplicate and rollback tests. No production account reconnection or legacy DB migration without approval.
```

## Prompt 09 — P7 migration and release

```text
Prepare a reversible P7 migration and release plan: enumerate existing client owners/deployments, map canonical tenant IDs explicitly, create dry-run export/import into draft knowledge revisions, verify counts/consent/source lineage, compare multilingual answers, rehearse backup/restore, run load/cost/security tests, define canary and rollback. Never merge tenants based on matching email/domain. Separate subscription migration from content migration. Request approvals for each real client cutover and production action.
```

## Prompt 10 — Audit a Codex PR

```text
Review the proposed diff strictly READ-ONLY against the approved ticket and pinned architecture. Identify file-level security flaws, tenant bypasses, migration/data risks, SSRF, auth/session, secret leakage, race conditions, idempotency failures, untested paths, API contract drift and unnecessary scope. Classify findings blocking/high/medium/low with file:line, evidence and minimal fix. Verify tests actually ran from logs; do not claim unexecuted tests. Return ACCEPT / REQUEST CHANGES and next safe action. Do not merge or deploy.
```

## Prompt 11 — Phase handoff and next-chat checkpoint

```text
Produce a portable checkpoint for a fresh ChatGPT/Codex session: approved baseline and phase, pinned SHA/branch/PRs, exact completed tickets with test evidence, DB migration versions, decisions/ADRs, open findings, secrets/deployment cautions, files to read first, next smallest ticket and exact implementation prompt. Explicitly label planned vs implemented vs tested vs deployed. Never include secret values or unverifiable claims.
```

## Codex task template fields
Ticket ID; repository and target branch; source SHA; goal; allowed paths; prohibited paths/actions; assumptions and external dependencies; exact API/schema contract; migrations; authorization/tenant invariants; test plan and disposable resources; acceptance criteria; rollback; deliverables; approval status.

## Stop conditions
Stop and ask when source SHA differs unexpectedly, production DB is targeted, migration is destructive, secrets appear, required auth is ambiguous, dependency/provider decision is unresolved, or code changes exceed approved ticket. Do not silently change requirements.
