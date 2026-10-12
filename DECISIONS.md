# Decision register
Change a decision only by adding a dated entry below with rationale, alternatives, impact and approver. Never treat a proposed choice as approved.

| ID | Decision | Status |
|---|---|---|
| ADR-001 | Build a brand-new independent SaaS from scratch; no other repo is a dependency | Confirmed by user |
| ADR-002 | ManyOsirisChat is the Meta channel provider (WhatsApp, Messenger, Instagram). It stays a separate app/database. This SaaS never talks to Meta directly; it exchanges signed messages with Many through a channel contract built in P6 (after the website product works end to end) | Revised 2026-10-12 (owner: SaaS serves website clients, Many provides Meta connections) |
| ADR-003 | Modular monolith: Next.js/React/TypeScript, FastAPI, PostgreSQL (pgvector-capable image; extension unused until the optional semantic upgrade) | Approved 2026-10-12 |
| ADR-004 | Auth: built-in server-side cookie sessions, Argon2id hashing, CSRF protection. No email provider or password reset in MVP (reset deferred) | Approved 2026-10-12 |
| ADR-005 | Retrieval/embeddings | RESOLVED 2026-10-12: keyword-first (Postgres full-text), no embeddings or vector column in MVP; optional hybrid/semantic upgrade later, gated by eval results (see docs/14) |
| ADR-006 | Website ingestion | RESOLVED 2026-10-12: no in-app crawler in the MVP. Website content is collected by a staff-run AI skill that outputs Markdown pages (with source URLs) and a Q&A CSV, uploaded as files (docs/14 §13). An isolated in-app importer may be proposed later |
| ADR-007 | Hosting, object storage, retention, data residency | OPEN (before staging, P5-05) |
| ADR-008 | Paid plans, payment provider, currencies | OPEN (not in this roadmap; after P5) |
| ADR-009 | Roles: owner / admin / editor / viewer per tenant, plus `users.is_platform_staff` flag for platform area | Approved 2026-10-12 |
| ADR-010 | Tenant isolation: app-layer tenant checks in every service + composite FKs `(tenant_id, id)`; no Postgres RLS in MVP | Approved 2026-10-12 |
| ADR-011 | Background jobs: durable `jobs` table in Postgres (atomic claim with lease + retry), run by `python -m app.worker` from the SAME api codebase/image. No separate worker app, no Redis | Approved 2026-10-12 (proposed by Claude; confirmed with roadmap) |
| ADR-012 | Retired: no reference-repo inspection in the build. Retrieval/ingestion/analytics behaviour is specified by the owner in design review and recorded in docs/07, docs/08 and docs/14 | Approved 2026-10-12 |
| ADR-013 | Chat model strategy | Approved 2026-10-12: provider interface; free OpenRouter models with fallback chain by default; OpenAI API models for paid clients (configured per plan) |
| ADR-014 | Language handling | Approved 2026-10-12: same-language retrieval first, fall back to bot primary language; answer in visitor language |
| ADR-015 | Product scope (Mojeeb-style): website AI chatbot + unified inbox with human handoff + light CRM + follow-ups. Conversation core is channel-agnostic from P3 (contacts, conversations with `channel`, messages with `sender_type`) so Many channels plug in without a rewrite | Approved 2026-10-12 |
| ADR-016 | Handoff and inbox: conversation `mode` (ai/human) and `status` (open/waiting_human/resolved); AI is silent in human mode; roles reuse ADR-009 (owner/admin/editor reply, viewer reads); dashboard live updates by SSE that polls the DB cursor (works with several API processes); widget polls; in-app notifications only (no email provider, ADR-004). Voice/image messages deferred | Approved 2026-10-12 |
| ADR-017 | ManyOsirisChat channel contract: HMAC-SHA256 signed JSON both ways, per-connection secret, timestamp window, idempotent event ids, async processing via jobs. Many owns Meta tokens, webhook verification, 24-hour window and templates; the SaaS owns bot, conversation, inbox and CRM for linked connections. Mapping (tenant+bot to Many channel) is explicit and staff-created. Many must run linked connections in "delegated" mode (no bot or takeover of its own). Spec in docs/14 §18 and docs/17 | Approved 2026-10-12 (delegated-mode assumption to confirm when Many's side is designed) |
| ADR-018 | Two dashboards: (1) client dashboard per chatbot (overview, inbox, contacts, knowledge, playground, settings, install, channels, follow-ups, team) and (2) platform admin console for staff to manage all clients. A basic admin console (client list, client detail, staff onboarding through the shared ProvisioningService) is built in P4 so first clients can be onboarded; quotas, platform analytics, connection health and audit review follow in P7 | Approved 2026-10-12 |

## 2026-10-12 — ADR-003 approval
Approver: product owner. Rationale: one standalone deployment with clear module boundaries and tenant isolation, minimal infrastructure. Alternatives: historical multi-service control plane and cross-product architecture rejected for MVP. Impact: `apps/web`, `apps/api`, local Compose PostgreSQL.

## 2026-10-12 — Roadmap simplification and ADR-004/009/010/011/012
Approver: product owner ("accept all defaults"; roadmap reviewed in session). Rationale: V2 had 8 phases with plumbing (platform admin, provisioning boundary, separate worker app) ahead of any chat value. New roadmap is 5 vertical-slice phases (see `implementation/MASTER-ROADMAP.md`); ManyOsirisChat integration is the optional phase after. Alternatives: Postgres RLS (rejected for MVP: operational overhead, tests still required), external auth provider (rejected: no requirement), Redis queue (rejected: Postgres jobs suffice). Impact: P1 now has 3 tickets; knowledge, chat, widget and dashboard come before platform admin.

## 2026-10-12 — P1-01 tooling
npm workspaces with exact versions + lockfile; Python 3.12 venv with pinned requirements; ESLint/Prettier/TypeScript, Ruff/mypy; pytest; Playwright Chromium smoke test.

## 2026-10-12 — Retrieval, model and language decisions (ADR-005/006/013/014)
Approver: product owner, after reading Rabbit Hole and Retrivo in design review. Rationale: Rabbit Hole proves keyword-only Postgres search plus a free model is enough for a grounded EN/AR assistant without embedding API cost; Retrivo contributes parsing, chunking, Q&A CSV onboarding and analytics. Alternatives: hybrid from day one (deferred, eval-gated), free-only or Ollama-only models, strict same-language retrieval, headless-browser scraping in P2 (all rejected for MVP). Details: docs/14-AGREED-BUILD-SPECS.md.

## 2026-10-12 — Website content via staff skill (ADR-006)
Approver: product owner. Rationale: removes the largest security surface (SSRF, hostile sites, JS rendering) from the product and lets an AI curate relevant content with a human review. Alternatives: guarded in-app crawler (deferred), headless browser in the app (rejected for MVP). Impact: P2 loses the URL-import ticket; clients cannot self-serve website import; website onboarding and refreshes are staff-run.

## 2026-10-12 — Re-scope around the Mojeeb-style product (ADR-002 revised, ADR-015/016/017)
Approver: product owner ("this saas will be for the websites clients deployment ... connected to manyosiris chat to get it connected to usage of meta connections"). Rationale: the product the owner wants to sell is a website-first conversational CRM (AI agent trained on client data, unified inbox, handoff, CRM, follow-ups); Meta connectivity already lives in ManyOsirisChat, so duplicating it here would add Meta app review, webhook and window logic for no gain. Alternatives: build Meta adapters inside this SaaS (rejected: duplicates Many); fork an open-source inbox/agent platform (rejected: ChatbotX is vector-only with no Arabic or keyword search and carries a large workspace platform; Chatwoot is a possible inbox reference but would add a second stack). Impact: roadmap becomes 7 phases (P5 Inbox/handoff/CRM, P6 ManyOsirisChat channel, P7 platform/quotas/hardening); P3-03 schema is channel-agnostic; no Meta code or credentials in this repo. First sellable cut = end of P5 (website widget + inbox + CRM); WhatsApp/Messenger/Instagram arrive with P6.

## 2026-10-12 — Client dashboard per bot and admin console (ADR-018)
Approver: product owner ("a dashboard for the client per chatbot and one for the admins to manage all clients"). Rationale: the admin area was one late ticket (P7) but clients must be onboarded long before; the per-bot view was scattered. Alternatives: keep admin in P7 (rejected: onboarding would be manual SQL). Impact: P4 gains P4-06 (admin console basics + staff onboarding via ProvisioningService); P7-01/P7-03 narrow to advanced operations, quotas, platform analytics and self-service hardening.
