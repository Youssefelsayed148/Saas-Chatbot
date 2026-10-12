# Repository agent rules
Clean independent SaaS (modular monolith). Source of truth: latest user instruction > docs/ > DECISIONS.md (approved ADRs) > actual repo code/tests > reference/original (historical only).
- Follow implementation/MASTER-ROADMAP.md; work phase by phase, tickets in order; stop at each phase gate for owner sign-off. Prompts: implementation/AGENT-PROMPTS.md. Checklists: implementation/PHASE-CHECKLISTS.md. Expected behaviour: docs/18-EXPECTED-BEHAVIOUR.md.
- Tenant scope on every tenant-owned query and endpoint; hidden resources return 404; add tenant A/B tests.
- Typed contracts, Alembic migrations (never create_all), tests with every ticket. Use only disposable test databases.
- Retrivo/Rabbit Hole are read-only references: port logic, record it in docs/14, never copy data, credentials or branding.
- Protect credentials. No push, merge, deploy, paid API calls or cloud resources without separate approval.
- Never fabricate test results; record exact commands and outcomes in PROGRESS.md. Stop on blocking ambiguity or an OPEN decision in DECISIONS.md.
