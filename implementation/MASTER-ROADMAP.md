# Roadmap — 5 vertical-slice phases (+ optional integration)
Each phase ends with something a person can use. A phase is DONE only when its checklist in `PHASE-CHECKLISTS.md` is ticked with evidence and the owner signs off. No phase implies deployment approval.

## P1 Foundation — users, tenants, bots
Register/login, create organization, switch organizations, create/list/edit/archive bots, real dashboard. Alembic migrations, roles, tenant isolation tests.
Tickets: P1-01 toolchain (DONE) · P1-02 schema + auth · P1-03 tenants, roles, bot API · P1-04 dashboard UI + phase verification.
Gate: two tenants cannot see each other's data by guessing IDs; viewer cannot mutate; browser E2E creates tenant and bot.

## P2 Knowledge — get a client's data into the bot
Upload raw files (PDF, DOCX, TXT/MD, Q&A CSV) and/or import website pages; parse → chunk → dedupe → full-text index → draft revision → review → publish. Jobs run in the DB-backed worker. No embeddings (ADR-005); specs in `docs/14`.
Tickets: P2-01 knowledge schema (sources, documents, revisions, chunks with generated tsvector columns, jobs) + job queue/worker · P2-02 file upload, parsers, chunking, Q&A CSV import with error report · P2-03 indexing, dedupe, draft/publish/rollback · P2-04 URL import (static HTML) with SSRF guard · P2-05 knowledge UI.
Gate: re-ingesting is idempotent; failed job never changes published knowledge; two tenants with the same file/URL share nothing.

## P3 Chat — grounded answers
Keyword retrieval restricted to tenant + bot + published revision + language (with cross-language fallback); small-document expansion; ChatModel interface (free OpenRouter chain by default, OpenAI for paid plans); strict JSON answer contract with validated citations and abstention; rule-based routing; Arabic and English; playground; feedback; eval suite.
Tickets: P3-01 retrieval service · P3-02 chat service + provider interface + prompts + routing · P3-03 conversations, messages, feedback, usage events · P3-04 playground UI · P3-05 evaluation suite · P3-06 (optional, only if evals show recall gaps) semantic/hybrid upgrade.
Gate: eval targets in `docs/14 §10` met with real numbers recorded; cross-tenant retrieval test passes.

## P4 Widget and client experience
Public widget config + visitor sessions, embeddable iframe widget, allowed domains, rate limits, install page, conversations view, lead capture with consent, analytics (docs/14 §9).
Tickets: P4-01 public API + visitor sessions + abuse limits · P4-02 widget package · P4-03 appearance settings + install page · P4-04 conversations + leads · P4-05 analytics (docs/14 §9).
Gate: two independent test websites, two tenants, each only answers from its own knowledge.

## P5 Platform admin, quotas, onboarding-by-staff, hardening
Staff area (tenant list, job health, audited support actions), usage quotas, staff-initiated onboarding with data upload (same provisioning service as self-service), export/delete, backups, security review, staging readiness.
Tickets: P5-01 platform admin · P5-02 quotas + usage enforcement · P5-03 provisioning service (self-service + staff) · P5-04 data export/delete + audit review · P5-05 release readiness (staging, backups/restore drill, monitoring).
Gate: non-staff blocked from /platform; quota race test; restore drill passes; independent security review.

## P6 (optional, later) ManyOsirisChat integration
Separate design + ADR after P5 ships. Many stays a separate app/database; integration through a scoped API. See `docs/17`.

Paid billing: not scheduled (ADR-008).
