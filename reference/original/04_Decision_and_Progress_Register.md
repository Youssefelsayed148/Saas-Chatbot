# Decision and Progress Register

## Decisions
| ID | Topic | Status | Choice | Date | Owner | Evidence |
|---|---|---|---|---|---|---|
| ADR-001 | Two independently subscribable products, shared tenant and AI | APPROVED | website_chatbot + manyosiris | 2026-10-12 | Product owner | Architecture approval |
| ADR-002 | One provisioning engine for both onboarding modes | APPROVED | Durable product-specific plans | 2026-10-12 | Product owner | Architecture approval |
| ADR-003 | New platform core, selective code reuse | APPROVED | No wholesale DB merge | 2026-10-12 | Product owner | Architecture approval |
| ADR-004 | OIDC provider | OPEN | TBD | | | |
| ADR-005 | Billing provider / Egypt merchant eligibility | OPEN | TBD | | | |
| ADR-006 | Hosting and data residency | OPEN | TBD | | | |
| ADR-007 | Embedding model, dimension and provider | OPEN | TBD | | | |

## Progress
| Phase | Status | Evidence | Gate | Next action |
|---|---|---|---|---|
| P0 | NOT VERIFIED | Static audit only | BLOCKED | Credential and environment evidence |
| P1 | PLANNED | Architecture spec | BLOCKED | P0 and scoped authorization |
| P2-P7 | PLANNED | Master plan | BLOCKED | Preceding phases |

## Per-ticket log template
Date / phase / ticket / repo SHA / branch / PR / changed files / test commands and outputs / migration ID / reviewer / deployment state / rollback / next action.
