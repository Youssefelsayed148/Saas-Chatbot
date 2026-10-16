# Functional requirements — normative backlog
IDs are durable. Priority: M = MVP required, L = later, D = decision pending.
| ID | Priority | Requirement | Verification |
|---|---|---|---|
| FR-001 | M | Email/password signup/login/logout/reset; secure session lifecycle | Unauthorized and expired sessions rejected |
| FR-002 | M | Organizations with admin, editor, viewer memberships; one user may belong to multiple | Membership tests and org switching |
| FR-003 | M | Tenant-scoped bots: draft, active, paused, archived; configuration versioning | CRUD, permissions and audit tests |
| FR-004 | M | Both self-service and staff onboarding call ONE backend provisioning application service | Same resulting resources, distinct actor audit |
| FR-005 | M | Website content onboarding through prepared files (staff skill output: Markdown pages with source URLs + Q&A CSV); source status and error diagnostics | Fixture folder uploads, citations link to source_url, bad files give clear errors |
| FR-006 | M | Safe extraction, deduplication, chunking, full-text indexing and staged revisions | Repeated crawl is idempotent |
| FR-007 | M | Explicit publish/rollback of knowledge revision | In-flight chats see one coherent revision |
| FR-008 | M | Keyword-first RAG answers restricted to published tenant/bot knowledge with validated citations and abstention | Cross-tenant retrieval and hallucination evaluation |
| FR-009 | M | Arabic and English questions, Unicode handling and RTL presentation | Bilingual test corpus |
| FR-010 | M | Installable website widget, configurable appearance, allowed-domain policy and abuse limits | Two independent websites smoke test |
| FR-011 | M | Visitor sessions, chat history, streaming or graceful nonstreaming fallback | Session ownership/expiration tests |
| FR-012 | M | Client dashboard: bot setup, sources, test chat, installation, conversation overview | E2E role-specific workflows |
| FR-013 | M | Platform dashboard: tenant overview, bot/job health, scoped support actions, audit trail | Staff-only permission tests |
| FR-014 | M | Leads/contact capture with explicit consent and configurable retention | Consent and deletion tests |
| FR-015 | M | Usage metering and enforceable quotas by tenant/bot | Concurrency and quota boundary tests |
| FR-016 | L | Paid subscription checkout, renewals, cancellation and webhooks | Provider-specific contract tests |
| FR-017 | M | Human handoff and unified inbox: automatic handoff triggers, takeover/return/resolve, assignment, notes, tags, live updates, agent replies visible in the widget (docs/14 §15–§16) | Handoff end-to-end E2E; viewer cannot reply; two-agent takeover race |
| FR-018 | M | ManyOsirisChat channel integration (P6): signed two-way contract, WhatsApp/Messenger/Instagram conversations through Many, delivery status, no Meta code here (docs/17) | Contract tests with fake Many, signature/replay/duplicate tests, tenant mixing tests |
| FR-020 | M | Raw-data onboarding: upload PDF/DOCX/TXT/CSV/MD files, parsed and indexed into a bot's draft knowledge | Fixture files indexed; unsupported/oversized files rejected with clear error |
| FR-021 | M | Client analytics: conversations, questions asked, unanswered questions, citations, usage (measured, never fabricated) | Counts match stored events |
| FR-022 | M | Q&A CSV import (question, answer, topic, priority) with template download and row-level error report | Valid rows indexed as single chunks; invalid rows listed with reasons |
| FR-023 | M | Per-answer thumbs feedback; unanswered-question list for clients | Feedback stored once per message; unanswered list matches can_answer=false turns |
| FR-019 | M | Safe data export/delete with tenant verification and audit | Authorized vs unauthorized requests |
| FR-024 | M | Channel-agnostic contacts, conversations and messages (channel, sender_type, delivery status) | Same pipeline serves widget and Many events |
| FR-025 | M | Light CRM: contact profile, stage, tags, custom fields, timeline, merge, consent per channel, CSV export, erasure | CRM E2E; erase removes identities and messages |
| FR-026 | M | Follow-ups: scheduled messages by user or rule; website delivery on next visit; Meta channels only with recorded opt-in | Job tests; no send without opt-in |
| FR-027 | M | Sentiment label per conversation and handoff/response-time analytics (measured) | Aggregates match stored data |
| FR-029 | M | Client dashboard per chatbot (overview, inbox, contacts, knowledge, playground, settings, install, channels, follow-ups) — docs/10 | Role-specific E2E; per-bot numbers never mix bots |
| FR-030 | M | Platform admin console to manage all clients: list, detail, staff onboarding (P4-06); operations, plans, platform analytics, audit review (P7) — docs/11 | Staff-only tests; reason + audit on every support action |
| FR-028 | L | Voice/image messages, email notifications, deals with amounts, automation builder | Not in v1 |

## Requirement discipline
No inferred functionality is approved merely because it appears in an old document or another product. UI must use real API data; no fake success states. All write APIs must validate inputs, permissions, quotas and tenant scope. Open choices appear in `DECISIONS.md`.
