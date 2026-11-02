# Documentation index

Maintained documents for the Website Chatbot SaaS. The Many app (ManyOsirisChat) has its own index in its repository. Each topic has one home; if you find the same fact in two places, fix one and link to it. Source-of-truth order (from `AGENTS.md`): latest instruction, then `docs/`, then `DECISIONS.md`, then the code and tests.

Updated 2026-11-02. Superseded build and close-out records were removed and are summarised in [HISTORY.md](HISTORY.md); everything removed is recoverable with `git show ed965ab:<path>`.

## Product and design (numbered; code comments cite these numbers, so do not renumber)

| Doc | Topic |
| --- | --- |
| [00](00-PRODUCT-VISION.md), [01](01-FUNCTIONAL-REQUIREMENTS.md), [02](02-USER-JOURNEYS.md) | Vision, requirements, journeys |
| [03](03-SYSTEM-ARCHITECTURE.md) | Architecture (modular monolith) |
| [04](04-DATABASE-DESIGN.md) | Database: design narrative plus a generated schema reference (31 tables) |
| [05](05-API-CONTRACTS.md) | REST API: design narrative plus a generated index of all 152 operations |
| [06](06-AUTHORIZATION-AND-SECURITY.md) | Authorization and security policy |
| [07](07-CHATBOT-AND-RAG-DESIGN.md), [08](08-INGESTION-PIPELINE.md), [14](14-AGREED-BUILD-SPECS.md) | Chat engine, ingestion, agreed build specs |
| [09](09-WIDGET-SPECIFICATION.md), [10](10-CLIENT-DASHBOARD.md), [11](11-PLATFORM-ADMIN.md) | Widget, client dashboard, platform console |
| [12](12-ONBOARDING-AND-PROVISIONING.md), [13](13-SUBSCRIPTIONS-AND-USAGE.md) | Provisioning, plans and usage |
| [15](15-TESTING-AND-ACCEPTANCE.md) | Testing strategy and **how the suites are run** |
| [16](16-DEPLOYMENT-AND-OPERATIONS.md) | Environments and the ManyOsirisChat channel runbook |
| [17](17-MANYOSIRISCHAT-CHANNEL-INTEGRATION.md) | The signed channel contract (identical copy in the Many repo; do not edit without changing both) |
| [18](18-EXPECTED-BEHAVIOUR.md), [19](19-CHATBOT-STRATEGY-AND-MANYOSIRISCHAT-PLAN.md) | Expected behaviour, strategy record |

## Run and operate

| Doc | Topic |
| --- | --- |
| [../README.md](../README.md) | What it is, structure, local start |
| [LOCAL-DEVELOPMENT.md](LOCAL-DEVELOPMENT.md) | Local commands and troubleshooting |
| [../DEPLOY.md](../DEPLOY.md) | VPS deployment, rolling back, restore (the live procedure) |
| [operations/](operations/RUNBOOK.md) | Draft runbook, backup and restore plan, monitoring and alerts, security review record (drafts from before the hosting decision) |
| [../implementation/MANUAL-TEST.md](../implementation/MANUAL-TEST.md), [DEMO-SEED.md](../implementation/DEMO-SEED.md) | Manual test and demo data |

## RAG

| Doc | Topic |
| --- | --- |
| [RAG-PLAN-v2.md](RAG-PLAN-v2.md) | Hybrid retrieval plan (ADR-019) |
| [rag-phase/THRESHOLDS.md](rag-phase/THRESHOLDS.md), [LIMITS-AND-METERING.md](rag-phase/LIMITS-AND-METERING.md), [OWNER-CHECKS.md](rag-phase/OWNER-CHECKS.md) | Relevance thresholds, limits and metering, owner calibration checks |
| [rag-phase/EXECUTION-OVERRIDES.md](rag-phase/EXECUTION-OVERRIDES.md), [DEFERRED-REVIEW.md](rag-phase/DEFERRED-REVIEW.md) | Owner-approved overrides, deferred review findings |

## Project control

| Doc | Topic |
| --- | --- |
| [../AGENTS.md](../AGENTS.md), [../CLAUDE.md](../CLAUDE.md) | Binding rules for coding agents |
| [../DECISIONS.md](../DECISIONS.md) | Decision register (ADR-001 to ADR-024) |
| [../PROGRESS.md](../PROGRESS.md) | Current status and verified results |
| [../implementation/KNOWN-ISSUES.md](../implementation/KNOWN-ISSUES.md) | Open and resolved issues |
| [../implementation/MASTER-ROADMAP.md](../implementation/MASTER-ROADMAP.md), [PHASE-CHECKLISTS.md](../implementation/PHASE-CHECKLISTS.md), [AGENT-PROMPTS.md](../implementation/AGENT-PROMPTS.md) | Phase roadmap, checklists, agent prompts (referenced by `AGENTS.md`; candidates to retire once the phase-gate workflow ends) |
| [../implementation/ROLE-MATRIX.md](../implementation/ROLE-MATRIX.md) | Dashboard role matrix |
| [HISTORY.md](HISTORY.md) | Build history and where removed material is |
