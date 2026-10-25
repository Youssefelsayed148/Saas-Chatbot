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
| ADR-021 | Staff-managed accounts: registration closed by default (`self_serve_signup=false`), invitations for existing users only, staff-set/generated passwords, self-service change-password with session revocation, no email/SMS/WhatsApp reset, Google sign-in deferred (ADR-020 reserved by Phase 6) | Approved 2026-10-21 (website MVP account slices S1–S4) |

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

## 2026-10-21 — ADR-021: Staff-managed accounts (website MVP account slices S1–S4)
Approver: product owner (slice prompts S1–S4, "GO" confirmations 2026-10-21). Decision:
- Registration is CLOSED by default: `self_serve_signup=false` hides the Register link on /login, `/register` states registration is by invitation only, and `POST /auth/register` without a valid invitation token returns 403 `INVITATION_REQUIRED`. The P7 self-service provisioning path remains in the codebase, exercisable only with the flag explicitly on.
- Invitations target EXISTING users only (`404 USER_NOT_FOUND` otherwise); platform staff create client accounts with staff-set or generated passwords (shown once at issuance).
- Any signed-in user changes their own password (`POST /auth/change-password`): current password verified (400 `INVALID_CURRENT_PASSWORD`), same-as-current rejected (400 `PASSWORD_UNCHANGED`), shared 8–200 policy (422), failed current-password attempts throttled per user (5 per 300 s window → 429); success revokes all OTHER sessions, rotates the current one, and audits `auth.password_changed`.
- Staff password reset and account deactivation revoke ALL of the user's sessions; deactivation blocks further sign-in until reactivation.
- NO email/SMS/WhatsApp password reset or recovery code exists anywhere; no email provider.
Rejected alternatives: open self-service signup as the default (rejected: the product sells staff-onboarded clients); email/SMS/WhatsApp reset (rejected: no provider, Many owns Meta channels); keeping the old pre-S2 register-with-invite flow for new invites (superseded: staff-created accounts first). Impact: docs/02, 04, 05, 11, 12, 14 §19, 15, 18; staff flows in /platform.
Deferred with design on record — Google sign-in (S5): account linking while logged in, matching by Google `sub` claim; no Google UI or placeholder was built in the MVP. ADR-020 is reserved by the Phase 6 channels branch; the next free number after this entry is ADR-022.

## 2026-10-25 — ADR-013 note: Premium model gpt-4.1-nano replaced by gpt-5.4-nano
Approver: product owner (batch R3c instruction). OpenAI deprecated `gpt-4.1-nano`: its API now answers 404 `model_not_found`, so every Premium turn ended with the busy reply. Verified replacement from the owner's own stack: `gpt-5.4-nano` answers 200 with temperature 0.2 and JSON mode. Runtime default `chat_openai_model`, `.env.example` and the tier mapping now name `gpt-5.4-nano`; the owner's `.env.local` is managed by the owner. Models that reject `temperature`/`max_tokens` (for example `gpt-5-nano`, 400 "only the default temperature") are handled by the existing one-shot compat retry, not by model-name logic. Cost of `gpt-5.4-nano` stays "Unmeasured": the repo has no price table and OpenAI does not return a cost field. Alternatives: pinning `gpt-5-nano` (rejected: rejects the sampling parameters); leaving the default empty (rejected: Premium has no model unless the host sets one). Impact: configuration defaults and test fixtures only.
