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
| ADR-009 | Client roles: admin / editor / viewer; independent `users.is_platform_staff` controls bots and operator actions | Revised 2026-10-16 (explicit owner change note; dated entry below) |
| ADR-010 | Tenant isolation: app-layer tenant checks in every service + composite FKs `(tenant_id, id)`; no Postgres RLS in MVP | Approved 2026-10-12 |
| ADR-011 | Background jobs: durable `jobs` table in Postgres (atomic claim with lease + retry), run by `python -m app.worker` from the SAME api codebase/image. No separate worker app, no Redis | Approved 2026-10-12 (proposed by Claude; confirmed with roadmap) |
| ADR-012 | Retired: no reference-repo inspection in the build. Retrieval/ingestion/analytics behaviour is specified by the owner in design review and recorded in docs/07, docs/08 and docs/14 | Approved 2026-10-12 |
| ADR-013 | Chat model strategy | Approved 2026-10-12: provider interface; free OpenRouter models with fallback chain by default; OpenAI API models for paid clients (configured per plan) |
| ADR-014 | Language handling | Approved 2026-10-12: same-language retrieval first, fall back to bot primary language; answer in visitor language |
| ADR-015 | Product scope (Mojeeb-style): website AI chatbot + unified inbox with human handoff + light CRM + follow-ups. Conversation core is channel-agnostic from P3 (contacts, conversations with `channel`, messages with `sender_type`) so Many channels plug in without a rewrite | Approved 2026-10-12 |
| ADR-016 | Handoff and inbox: conversation `mode` (ai/human) and `status` (open/waiting_human/resolved); AI is silent in human mode; roles reuse ADR-009 (admin/editor reply, viewer reads; ADR-009 revised 2026-10-16); dashboard live updates by SSE that polls the DB cursor (works with several API processes); widget polls; in-app notifications only (no email provider, ADR-004). Voice/image messages deferred | Approved 2026-10-12 |
| ADR-017 | ManyOsirisChat channel contract: HMAC-SHA256 signed JSON both ways, per-connection secret, timestamp window, idempotent event ids, async processing via jobs. Many owns Meta tokens, webhook verification, 24-hour window and templates; the SaaS owns bot, conversation, inbox and CRM for linked connections. Mapping (tenant+bot to Many channel) is explicit and staff-created. Many must run linked connections in "delegated" mode (no bot or takeover of its own). Spec in docs/14 §18 and docs/17 | Approved 2026-10-12 (delegated-mode assumption to confirm when Many's side is designed) |
| ADR-018 | Two dashboards: (1) client dashboard per chatbot (overview, inbox, contacts, knowledge, playground, settings, install, channels, follow-ups, team) and (2) platform admin console for staff to manage all clients. A basic admin console (client list, client detail, staff onboarding through the shared ProvisioningService) is built in P4 so first clients can be onboarded; quotas, platform analytics, connection health and audit review follow in P7 | Approved 2026-10-12 |
| ADR-019 | Hybrid RAG retrieval, embeddings and relevance gate; docs/RAG-PLAN-v2.md plus execution overrides | Approved RAG phase; renumbered 2026-10-16 by owner request |
| ADR-020 | Channel health degradation model: retry-budget exhaustion instead of a consecutive-failure counter; cleared by a newer health signal; one failed send can flip health. Recorded as a deviation against docs/17 §6 / PLAN D10 wording during P6-06 | Proposed by agent 2026-10-19 on the P6 branch evidence; owner sign-off pending |
| ADR-021 | Channel contract v1.1 adopted (delta A1-A13: channel must match connection, status duty and `unconfirmed`, Meta error-code table, byte-aware splitting, forwarding scope, ordering, flood guard, mandatory health endpoint, clock clamp, campaign origin, rotation, delegation off). Spec in docs/17 section 11 | Approved 2026-10-26 (owner, by issuing SAAS-REBUILD-PROMPT) |

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

## 2026-10-14 — Sentiment classification deferred to P7-02
Approver: product owner (decision recorded in the current instruction). Rationale: build sentiment classification together with P7-02 quotas so plan-based cost caps are enforced transactionally. Alternatives: implement the model job and cost caps in P5-05 (deferred). Impact: P5-05 may show only an aggregate of sentiment values already present; it must say “Sentiment not measured yet” when no results exist. P7-02 will add the sentiment job on the free ChatModel chain with a plan quota and aggregate-only use.


## 2026-10-16 ? ADR-009 revised: client roles and operator control
Approver: product owner, explicit Phase 1 change note. Client roles are admin/editor/viewer; migrate owner to admin. Only is_platform_staff controls bots, knowledge and playground or deletes organizations, with no tenant-membership requirement for those operations. Admins manage client administration and submit change requests; editors operate inbox/CRM; viewers read inbox/insights. Last-admin checks retain tenant locking; ownership transfer is removed. Organization deletion is immediate disablement followed by configurable delayed purge (30 days default), with a tenant-independent deletion ledger and storage cleanup. Alternatives: client-controlled bots and immediate hard deletion rejected by owner. Current matrix and contracts: docs/06. This supersedes older role wording in historical phase reports and ADR-016/018 where inconsistent. Hosting/billing OPEN decisions remain unchanged.


## 2026-10-16 - ADR-019: RAG identifier and calibration defaults
Approver: product owner, explicit final-fixes request. The RAG decision previously
labelled ADR-008 in the RAG plan is now ADR-019 (previously unused). Billing
ADR-008 stays OPEN and unchanged. ADR-019 supersedes ADR-005's keyword-only
restriction for this approved hybrid phase. Default embeddings are
`openai:text-embedding-3-large`, 1024 dimensions; Ollama remains optional.
The OpenAI cosine 0.50 OR FTS 0.01 row is **UNTUNED, pending owner calibration**.
Unknown models accept only FTS evidence. Calibration sweeps cosine/FTS floors
and minimum matched content terms, and never applies recommendations automatically.
Alternatives: unavailable local Ollama as default and threshold inheritance across
models rejected. Impact: runtime defaults, demo corpus and owner calibration tooling;
no real calls, merge, tag, deployment or hosting/billing decision authorized.

## 2026-10-18 - Phase 6 isolated build and delegated mode
Approver: product owner. Rationale: build P6 on `feature/phase-6-channels` in an isolated worktree while website MVP testing continues. Alternatives: wait for website closeout before starting P6 (deferred for the build, retained as a merge gate). Impact: P6 may be built locally in parallel; merge remains gated on website MVP sign-off, completion of P7, and a full green Playwright run, followed by owner approval. ADR-017 delegated mode is decided, not an assumption: Many forwards all inbound messages for delegated channels and does not run its own AI or takeover controls; the SaaS owns reply generation and handoff. ADR-007 hosting and ADR-008 billing remain OPEN and gate staging and paid plans only, not this isolated branch.

## 2026-10-19 - ADR-020: channel health degradation is retry-budget exhaustion (P6-06 deviation record)
Approver: pending owner sign-off (recorded by the P6-06 agent run so the built
behaviour and the spec cannot drift silently). docs/17 §6 and PLAN D10 said
"consecutive outbound failures (default 5) set degraded many_unreachable". The
built implementation (accepted at P6-03 and kept for P6-05b) has no
consecutive-failure counter column: a single message that exhausts its retry
budget (6 attempts, exponential backoff, roughly 10 minutes) marks the
connection degraded with reason `many_unreachable` (evidence:
`apps/api/tests/test_channel_outbound.py::test_retry_exhaustion` and
`tests/test_channel_contract.py::test_e1_...`). Alternatives: add a
`consecutive_send_failures` counter plus a threshold reset (rejected for now:
new migration column, extra reset logic, and accepted P6-03 tests would need
editing). What clears the degraded state: any newer health signal — a
successful §5.2 pull ("Check now" or the 5-minute poll job) or a newer
`channel.status` push — overwrites the row per the newer-occurred_at rule;
staleness AFTER 15 minutes without signal shows `unknown/stale` at read time
without rewriting the row. One message CAN flip health to degraded, and one
newer signal CAN clear it; a per-message flip is loud enough because the
failure is already user-visible as a failed message in the inbox. If the owner
prefers the literal consecutive-failure model, migration 0020 has unused head
room and the change is small — decide before staging.

## 2026-10-26 - ADR-021: contract v1.1 adopted
Approver: product owner, by issuing implementation/PHASE-06-V2/SAAS-REBUILD-PROMPT.md. Rationale: the Phase 6 review (REVIEW-REPORT.md) found gaps between contract v1 and the Many code (C1-C8) and SaaS defects (D1-D13); the delta A1-A13 closes the contract side. Alternatives: keep v1 and patch per defect (rejected: Many-side behaviour such as status duty, forwarding scope and error mapping would stay undefined). Impact: docs/17 gains section 11; the fake Many and contract suite pin A1-A13; Many implements the same delta in its own repo. ADR-020 (health degradation model) is NOT covered by this approval and remains awaiting owner sign-off; its text is prepared in R-05.
