# Decision register
Change a decision only by adding a dated entry below with rationale, alternatives, impact and approver. Never treat a proposed choice as approved.

| ID | Decision | Status |
|---|---|---|
| ADR-001 | Build brand-new independent SaaS; Retrivo and Rabbit Hole are references only | Confirmed by user |
| ADR-002 | ManyOsirisChat integration after the standalone product is complete | Confirmed by user |
| ADR-003 | Modular monolith: Next.js/React/TypeScript, FastAPI, PostgreSQL + pgvector | Approved 2026-10-12 |
| ADR-004 | Auth: built-in server-side cookie sessions, Argon2id hashing, CSRF protection. No email provider or password reset in MVP (reset deferred) | Approved 2026-10-12 |
| ADR-005 | Embedding model + vector dimension | OPEN — decide in P2-01 after inspecting Retrivo's embedding code. Direction: avoid paid embedding APIs (local model or Ollama) |
| ADR-006 | Crawler limits / robots policy / ownership verification | OPEN (decide in P2-04) |
| ADR-007 | Hosting, object storage, retention, data residency | OPEN (before staging, P5-05) |
| ADR-008 | Paid plans, payment provider, currencies | OPEN (not in this roadmap; after P5) |
| ADR-009 | Roles: owner / admin / editor / viewer per tenant, plus `users.is_platform_staff` flag for platform area | Approved 2026-10-12 |
| ADR-010 | Tenant isolation: app-layer tenant checks in every service + composite FKs `(tenant_id, id)`; no Postgres RLS in MVP | Approved 2026-10-12 |
| ADR-011 | Background jobs: durable `jobs` table in Postgres (atomic claim with lease + retry), run by `python -m app.worker` from the SAME api codebase/image. No separate worker app, no Redis | Approved 2026-10-12 (proposed by Claude; confirmed with roadmap) |
| ADR-012 | Reuse policy: owner owns Retrivo and Rabbit Hole, so no license review. Each port is recorded in `docs/14-REPOSITORY-REUSE-MATRIX.md` (source file, what, decision port/adapt/rewrite). Port logic, not schema, branding or global state | Approved 2026-10-12 |

## 2026-10-12 — ADR-003 approval
Approver: product owner. Rationale: one standalone deployment with clear module boundaries and tenant isolation, minimal infrastructure. Alternatives: historical multi-service control plane and cross-product architecture rejected for MVP. Impact: `apps/web`, `apps/api`, local Compose PostgreSQL.

## 2026-10-12 — Roadmap simplification and ADR-004/009/010/011/012
Approver: product owner ("accept all defaults"; roadmap reviewed in session). Rationale: V2 had 8 phases with plumbing (platform admin, provisioning boundary, separate worker app) ahead of any chat value. New roadmap is 5 vertical-slice phases (see `implementation/MASTER-ROADMAP.md`); ManyOsirisChat integration is the optional phase after. Alternatives: Postgres RLS (rejected for MVP: operational overhead, tests still required), external auth provider (rejected: no requirement), Redis queue (rejected: Postgres jobs suffice). Impact: P1 now has 3 tickets; knowledge, chat, widget and dashboard come before platform admin.

## 2026-10-12 — P1-01 tooling
npm workspaces with exact versions + lockfile; Python 3.12 venv with pinned requirements; ESLint/Prettier/TypeScript, Ruff/mypy; pytest; Playwright Chromium smoke test.
