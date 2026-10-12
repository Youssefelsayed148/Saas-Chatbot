# Roadmap — 7 vertical-slice phases
Product: a Mojeeb-style website AI agent — trained on the client's own data, with a unified inbox, human handoff, light CRM and follow-ups. Website is the native channel; WhatsApp/Messenger/Instagram arrive through ManyOsirisChat (P6), which owns all Meta connectivity. Each phase ends with something a person can use. A phase is DONE only when its checklist in `PHASE-CHECKLISTS.md` is ticked with evidence and the owner signs off. No phase implies deployment approval.

**First sellable cut = end of P5** (website widget + inbox + CRM). P6 adds Meta channels. P7 makes it operable at scale.

## P1 Foundation — users, tenants, bots
Register/login, create organization, switch organizations, create/list/edit/archive bots, real dashboard. Alembic migrations, roles, tenant isolation tests.
Tickets: P1-01 toolchain (DONE) · P1-02 schema + auth · P1-03 tenants, roles, bot API · P1-04 dashboard UI + phase verification.
Gate: two tenants cannot see each other's data by guessing IDs; viewer cannot mutate; browser E2E creates tenant and bot.

## P2 Knowledge — get a client's data into the bot
Upload raw files (PDF, DOCX, TXT/MD with optional source-URL header, Q&A CSV, including the output folder of the staff website-to-knowledge skill); parse → chunk → dedupe → full-text index → draft revision → review → publish. Jobs run in the DB-backed worker. No embeddings (ADR-005); specs in `docs/14`.
Tickets: P2-01 knowledge schema + job queue/worker · P2-02 file upload, parsers, chunking, Q&A CSV import · P2-03 indexing, dedupe, draft/publish/rollback · P2-04 knowledge UI.
Gate: re-ingesting is idempotent; failed job never changes published knowledge; two tenants with the same file share nothing; citations link to the page's source_url.

## P3 Chat — grounded answers on a channel-agnostic conversation core
Keyword retrieval (tenant + bot + published revision + language, cross-language fallback, small-document expansion); ChatModel interface; strict JSON answer contract with validated citations and abstention; rule-based routing; Arabic and English; playground; feedback; eval suite. Conversation storage is channel-agnostic from the start (ADR-015, docs/14 §14).
Tickets: P3-01 retrieval service · P3-02 chat service + provider interface + prompts + routing · P3-03 contacts, conversations, messages (channel-agnostic), feedback, usage events · P3-04 playground UI · P3-05 evaluation suite · P3-06 (optional) semantic/hybrid upgrade — the owner decides at the P3 gate from the eval report, with Arabic/dialect cases weighted.
Gate: eval targets in `docs/14 §10` met with real numbers recorded; cross-tenant retrieval test passes.

## P4 Widget — the website channel
Public widget config + visitor sessions, embeddable iframe widget, allowed domains, rate limits, install page, conversations view, lead capture with consent (creates/updates the contact), basic analytics (docs/14 §9).
Tickets: P4-01 public API + visitor sessions + abuse limits · P4-02 widget package · P4-03 appearance settings + install page · P4-04 conversations + leads → contacts · P4-05 analytics.
Gate: two independent test websites, two tenants, each only answers from its own knowledge.

## P5 Inbox, handoff and light CRM — what makes it Mojeeb-like
Conversation state machine (mode ai/human, status open/waiting_human/resolved), handoff triggers, a unified inbox with live updates, human takeover and return-to-AI, assignment, internal notes, tags, contact profiles with stages and timeline, follow-ups, sentiment and handoff analytics. Specs: docs/14 §14–§17.
Tickets: P5-01 conversation state machine + handoff triggers + agent reply API (visitor sees agent messages in the widget) · P5-02 inbox API + SSE live updates + in-app notifications · P5-03 inbox UI (list, filters, thread, reply, takeover/return, assign, notes, tags) · P5-04 contacts + light CRM (profile, stage, tags, custom fields, timeline, merge, CSV export) · P5-05 follow-ups + sentiment + handoff/response-time analytics.
Gate: a visitor chats, the bot hands off, an agent takes over from the inbox and replies in the widget, then returns the chat to the bot; two tenants never see each other's conversations or contacts; viewers cannot reply.

## P6 ManyOsirisChat channel — WhatsApp, Messenger, Instagram
Signed two-way channel contract with ManyOsirisChat (ADR-017, docs/17, docs/14 §18). Inbound events become conversations through the same chat pipeline as the widget; replies, agent messages and follow-ups go out through Many; delivery status flows back. No Meta credentials or webhooks in this repo.
Tickets: P6-01 channel connections + HMAC signing/verification + event log · P6-02 inbound events → contact identities, conversations, AI/handoff pipeline · P6-03 outbound delivery, retries, delivery status, window/template errors in the inbox · P6-04 follow-ups and broadcasts through Many (owner-approved, template-based) · P6-05 contract tests against a fake Many, Many-side requirements, canary and rollback plan.
Gate: duplicate and out-of-order events are harmless; a bad signature is rejected; two tenants' connections never mix; a message sent from the inbox reaches a test number through Many (staging) with delivery status shown.
Prerequisite: Many exposes (or gets) the endpoints in docs/17 — tracked as a Many-repo workstream, not part of this repo.

## P7 Platform admin, quotas, onboarding-by-staff, hardening
Staff area (tenant list, job health, audited support actions), usage quotas (bots, seats, messages, channel connections), staff-initiated onboarding with data upload (website-to-knowledge skill output) via the same provisioning service as self-service, export/delete, backups, security review, staging readiness.
Tickets: P7-01 platform admin · P7-02 quotas + usage enforcement · P7-03 provisioning service (self-service + staff) · P7-04 data export/delete + audit review · P7-05 release readiness (staging, backups/restore drill, monitoring).
Gate: non-staff blocked from /platform; quota race test; restore drill passes; independent security review.

Paid billing: not scheduled (ADR-008). Voice/image messages: deferred past v1.
