# AI Chatbot SaaS — Master Product & Engineering Plan

Version: 1.0 | 12 October 2026 | Status: ARCHITECTURE APPROVED; IMPLEMENTATION NOT AUTHORIZED BY THIS DOCUMENT

## Purpose and portability
This is the durable source-of-truth handoff for a new ChatGPT account and Codex. Read with 02_Codex_Prompt_Playbook.md, 03_New_Account_Handoff.md and the original full static audit. This document is a plan, not evidence that software was implemented or tested.

## Mission
Build a secure multi-tenant Website Chatbot SaaS with website ingestion, bilingual grounded RAG, embeddable widget, customer dashboard, platform admin, subscriptions, and integration with independently subscribable ManyOsirisChat. Both products share canonical tenant identity and authorized AI intelligence; each keeps product-specific permissions, channel operations and billing state.

## Audited repositories and provenance
- https://github.com/Youssefelsayed148/ManyOsirisChat — pinned audit commit: 5cc60c731c72cdd4697b8df220536c6eaf335dd8
- https://github.com/Youssefelsayed148/retrivo_bot — IMPORTANT: obtain the exact pinned commit from the original audit before any coding; not reliably available in this handoff context.
- https://github.com/Youssefelsayed148/rabbit_hole_chatbot — pinned audit commit: a4fedcc7434105d48e616eb5950605f42ffee96e
Original audit reports 628 tracked files and distinguishes focused semantic tracing, structural static scan and artifact inventory. No application test suite was executed as part of that audit. Re-verify current HEAD and licensing; do not claim all files were manually line-by-line validated.

## Product invariants
1. Two independent products: website_chatbot and manyosiris; neither subscription requires the other.
2. Canonical tenant UUID; explicit membership, product grants and verified resource ownership. Existing Many workspaces map explicitly to tenants; never merge by email/domain.
3. One durable provisioning engine for self-service and platform-admin onboarding, with separate actor authorization and audit trails.
4. Tenant scope enforced in API, DB composite FKs/RLS, retrieval, storage, cache, queues, webhooks, analytics, exports and background workers.
5. Shared AI runtime, but channel-specific policy, action permissions, consent, messaging windows, and handoff.
6. Staged, immutable knowledge revisions; atomic publication; provenance/citations; tenant-bounded hybrid retrieval.
7. Existing Many owns Meta webhooks, campaigns, conversations, delivery and human takeover; integration through authenticated API/events, never direct DB access.
8. No per-tenant deployment in V1. Dedicated tenant deployments deferred.
9. No production changes, commits, deployment or credential manipulation without separate explicit approval.

## Baseline architecture
Monorepo chatbot-saas: apps/client-dashboard, apps/platform-admin, apps/widget; services/control-plane and services/ai-platform; workers/provisioning and workers/ingestion; packages/api-contracts, ui, integration-sdk; integrations/manyosirischat; infrastructure/docker, migrations, monitoring; tests/tenant-isolation, provisioning, security, integration; docs/architecture, decisions, runbooks. Backend FastAPI; Next.js/React/TypeScript; PostgreSQL+pgvector; Redis for ephemeral coordination; durable job/outbox state in Postgres; object storage for source artifacts. Logical DB boundaries: control plane, chatbot knowledge/runtime, legacy Many. Isolated browser crawler with enforced outbound egress policy. Versioned iframe widget loader.

## Source code reuse policy
ManyOsirisChat: preserve/refactor Meta adapters, outreach consent, delivery, existing workspace models and tests; replace inconsistent global authorization and direct inline AI with scoped adapters. Retrivo: selectively port admin workflows, document parsers, widget UX, analytics; replace single-client schema, in-process jobs, unsafe browser-fetch executor, contextual global cache. Rabbit Hole: reuse grounded answer/citation validation, provider abstraction, hybrid RRF and Arabic tests; refactor global tables/locks, brand prompts and retention. Never copy brand data packs or credentials. Check repository ownership/license before redistribution.

## Known static-audit risks requiring validation
P0: credential-like tracked file; Many global/unscoped resource access; test database destructive fixtures; unsafe config defaults. Before ingestion: crawler SSRF/subresource/DNS rebinding. Reliability: webhook ACK before durable dispatch; AI duplicate delivery; non-atomic usage counters; Retrivo staged publish absent; ingestion worker loss; embedding dimension/model mismatch. Security: session capability ownership, cross-tenant cache keys, OIDC service auth, tenant-scoped vector and SQL paths. These are source-review findings and inferred impact, not independently demonstrated exploits.

## Delivery phases

### P0 — Evidence, safety and baseline
**Scope:** Inventory tracked credentials without printing values; owner rotates any live exposures; validate safe test DSNs; capture backups, migrations, deployment state, licenses, repo SHAs; reconcile audit findings against latest HEAD.

**Exit gate:** Secret disposition signed off; no production DB reachable from tests; pinned SHA ledger; documented restore strategy.

**Guardrail:** Read-only until separately authorized. Never print secrets, run destructive fixtures, or modify legacy repos.

### P1 — Canonical tenant and product foundation
**Scope:** Initialize new monorepo; identity provider integration; tenants/users/memberships/product grants; independent SKUs and entitlements; PostgreSQL migration chain, composite FKs/RLS; service auth, audit events, outbox/inbox, CI. Define Many mapping contract without changing Many.

**Exit gate:** Two tenants demonstrably isolated at API/SQL/worker/cache layers; each SKU independently enabled; fresh migrations and replay tests pass.

**Guardrail:** No production integration, billing charge, or legacy mutation.

### P2 — Unified provisioning engine
**Scope:** Single ProvisioningRequest state machine for self-service and platform-admin modes; durable step records, idempotency keys/payload hashes, lease/fence/retry/compensation; product-specific step plans, invitations and domain challenges.

**Exit gate:** Repeated/concurrent requests yield one resource; both modes share engine; failed steps recover; Many-only needs no website.

**Guardrail:** No ad hoc onboarding scripts; no per-client application deployment.

### P3 — Safe ingestion and shared AI
**Scope:** Isolated crawler and egress deny rules; sitemap/link discovery, bounded parsing and artifacts; versioned documents, embedding profiles, pgvector/FTS hybrid retrieval, staged revisions, publication gate; agent configs, citations, refusal, usage reservations. Adapt selected Rabbit/Retrivo modules with tests.

**Exit gate:** SSRF suite, revision rollback, tenant/revision scoped retrieval, Arabic/English eval, cost limits and crash recovery pass.

**Guardrail:** Do not import global single-tenant tables or brand seed content.

### P4 — Website Chatbot MVP
**Scope:** Public widget locator, iframe loader, visitor capabilities, SSE chat, leads/consent, handoff, tenant dashboard, knowledge review, widget installation, admin support operations.

**Exit gate:** Two unrelated live staging tenants install widgets with no per-client deploy; session and content isolation, mobile/RTL/a11y tests pass.

**Guardrail:** Public widget key is not a secret; no cross-tenant admin access.

### P5 — Billing and platform operations
**Scope:** Choose payment provider after Egypt merchant/recurring/currency verification; checkout adapter, signed webhook inbox, subscription state reconciliation, grace/proration/cancellation, usage reports, platform administration, telemetry, alerts.

**Exit gate:** Replay/out-of-order/refund/cancel tests pass; website-only cancellation never disables Many; reconciliation and alerts verified.

**Guardrail:** Do not trust checkout return URL as proof of payment.

### P6 — ManyOsirisChat integration
**Scope:** Map legacy workspace IDs to canonical tenants; secure channel ownership, scoped authorization; AI service adapter; channel-specific permissions and knowledge mapping; webhook outbox, delivery intents, human takeover, quota; shadow/canary rollout.

**Exit gate:** No tenant crossing; Meta delivery, consent and takeover semantics preserved; retry/duplicate and rollback tests pass.

**Guardrail:** No direct cross-product DB queries; no broad legacy rewrite.

### P7 — Migration, launch and hardening
**Scope:** Client ownership inventory; approved data/config migration to draft knowledge revisions; backup/restore, rollback, load/latency/cost, retention/deletion, incident response, runbooks, canary launch.

**Exit gate:** Restore rehearsal, SLO baseline, threat model, privacy/retention controls, client-by-client acceptance and rollback verified.

**Guardrail:** No broad production cutover without explicit approval.

## Database ownership and minimum schema
Control plane: tenants, users(issuer+subject), memberships, product_grants, invitations, product_catalog, plans/prices, billing_customers, subscriptions/items, entitlements, tenant_product_instances, provisioning_requests/steps, service_principals/secret_refs, audit_events, billing_webhook_inbox, outbox_events/consumed_events.
AI: tenant_registry, bots, bot_config_versions, domains, widget_installations, visitor_sessions, conversations/messages/citations, feedback/leads/handoffs, sources, crawl_jobs/pages, documents/document_versions, embedding_profiles, index_revisions/revision_documents, chunks, ai_turns/retrieval_runs/generation_runs, usage_reservations/ledger/budget_periods, connector_configs.
Many: existing operational DB remains independently migrated, with workspace→tenant mapping and scoped accounts/campaigns/conversations. Every child FK carries tenant_id where feasible. Runtime RLS role is not owner and cannot bypass RLS; transaction-local tenant context. Do not create schemas at API startup.

## API contracts to implement and version
GET /v1/me/tenants; POST /v1/tenants; GET /v1/tenants/{tenant}/products; GET /v1/tenants/{tenant}/entitlements; POST /v1/tenants/{tenant}/provisioning-requests (Idempotency-Key); GET /v1/tenants/{tenant}/provisioning-requests/{id}; POST /v1/tenants/{tenant}/bots; POST /v1/tenants/{tenant}/sources; POST /v1/tenants/{tenant}/ingestion-jobs; POST /v1/tenants/{tenant}/revisions/{id}/publish; GET /public/v1/widgets/{locator}/config; POST /public/v1/widgets/{locator}/sessions; POST /public/v1/conversations/{id}/messages; POST /v1/tenants/{tenant}/billing/checkout; POST /webhooks/billing/{provider}; POST /internal/v1/ai/turns. Exact OpenAPI definitions and error models are P1/P2 deliverables, not established contracts.

## P1 ticket queue
FND-001 monorepo/CI skeleton; FND-002 control-plane FastAPI; FND-003 immutable migrations; FND-004 OIDC identity; FND-005 memberships/RBAC; FND-006 independent entitlements; FND-007 composite FK/RLS; FND-008 outbox/audit; FND-009 adversarial isolation and migration CI. Definition of done: code, tests, migrations, docs, threat notes, acceptance evidence, and reviewer approval. No P2 until two tenant fixtures cannot cross-access data in API/DB/jobs/cache.

## Engineering workflow with Codex
Each phase: (1) read source-of-truth and pin SHAs; (2) plan exact file changes and tests; (3) obtain user approval for implementation; (4) work in isolated branch/new repo only within approved scope; (5) write migration/test before behavior; (6) execute tests against disposable resources; (7) provide diff summary, tests, risks, rollback; (8) request merge/deploy approval. Never claim success without command output. Avoid editing legacy repos until explicitly approved.

## Decisions still open
OIDC provider, hosting and managed Postgres, object storage, initial LLM/embedding provider/model/dimension, Egypt-compatible recurring billing provider, plan/trial/quotas/grace, legal privacy/retention/data residency, staff support access, source crawl limits and robots policy, existing customer ownership mapping, SLOs and budgets. These are implementation blockers for their relevant phases; do not invent decisions.

## Source of truth precedence
1. User's latest explicit approvals and restrictions; 2. this approved architectural baseline; 3. original pinned audit and actual source at pinned SHAs; 4. current source after explicit review; 5. assumptions marked TBD. If sources conflict, document an ADR and ask before irreversible choices.
