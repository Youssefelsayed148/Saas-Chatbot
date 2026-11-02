# Build history (summary)

This page replaces the working records of the build: the 3,904-line progress log, the per-ticket and per-phase reports, UI plans and prompts, the RAG stage reports, the Oct 2026 close-out plan and review logs, 200 files of test evidence and 12 MB of inventory data. They were deleted in the Nov 2026 docs cleanup. Everything is recoverable from git at commit `ed965ab`, for example `git show ed965ab:PROGRESS.md`.

Current status is in [../PROGRESS.md](../PROGRESS.md). Decisions are in [../DECISIONS.md](../DECISIONS.md) (ADR-001 to ADR-024).

## What was built

The product is a multi-tenant website chatbot: a business adds its data, publishes an AI agent, installs one script tag, and runs conversations through an inbox with human handoff, a light CRM and follow-ups. WhatsApp, Messenger and Instagram arrive through ManyOsirisChat, which owns all Meta connectivity (ADR-002).

| Phase | Delivered | Where it is described now |
| --- | --- | --- |
| P1 Foundation | Users, sessions, tenants, roles, bots, tenant isolation (composite foreign keys), dashboard shell, Alembic | `docs/03`, `docs/04`, `docs/06` |
| P2 Knowledge | Upload and parse PDF, DOCX, TXT/MD and Q&A CSV; chunk, dedupe, full-text index; draft, review, publish and roll back revisions; DB-backed job worker | `docs/08`, `docs/14` |
| P3 Chat | Grounded answers with validated citations and abstention, provider interface, Arabic and English, playground, feedback, evaluation suite; later the hybrid RAG upgrade (ADR-019) | `docs/07`, `docs/RAG-PLAN-v2.md`, `docs/rag-phase/` |
| P4 Widget | Public widget and visitor sessions, allowed domains, install page, conversations and lead capture, per-bot dashboard with analytics, basic platform console | `docs/09`, `docs/10`, `docs/11` |
| P5 Inbox and CRM | Handoff state machine, unified inbox with live updates, takeover and return to AI, assignment, notes, tags, contact profiles, follow-ups | `docs/14` section 14 to 17, `docs/18` |
| P7 Admin and hardening | Platform operations, plans and quotas, staff-managed accounts (ADR-021), export and deletion, release readiness | `docs/11`, `docs/13`, `docs/operations/` |
| P6 Channel | Signed two-way contract with ManyOsirisChat (ADR-017, contract v1.1 per ADR-023), channel connections and secrets, inbound events, outbound delivery and status, health model (ADR-020), A16 erasure (migration `0031`) | `docs/17`, `docs/16` |

Later work: the UI redesign and polish track (ADR-022), RAG hardening batches H1 to H5, and the Oct 2026 close-out for Meta approval.

## Test and review results recorded along the way (historical)

- 2026-10-26: stale tests repaired; hybrid retrieval confirmed working on pgvector 0.8.x (the earlier failures came from a test database without the right extension version).
- 2026-10-28/29 close-out: full API baseline 1,208 passed and 8 failed on stale fixtures at `86c992d` (all eight fixed in test code only); full Playwright 176 passed at `88599d7` (gate D1 met); migrations empty-to-head and 0022-to-head rehearsed; sole head `0031_contact_erasure`; the A16 receiver, tenant A/B matrix and CSV safety cases passed.
- Not proven then: deployed rebuild, hosted CI, live Meta, a real Many-to-SaaS round trip.

## Where removed material was

| Removed | Recover with |
| --- | --- |
| `PROGRESS.md` (old log) | `git show ed965ab:PROGRESS.md` |
| `README_START_HERE.md`, `NEW_CHAT_BOOTSTRAP.md` | `git show ed965ab:<name>` (their useful content is now in `README.md` and `docs/README.md`) |
| `implementation/PHASE-01` to `PHASE-06`, `RAG-PHASE-02`, ticket and phase reports | `git show ed965ab:implementation/<path>` |
| `implementation/` plans and reports (close-out plan, reviews, UI plans and prompts, staff S2/S3, RAG hardening, website MVP close-out, feature inventory) | same |
| `implementation/inventory-data`, `c1-c3`, `c2`, `c4-c5` evidence, `closeout`, `integration-evidence` (about 13 MB) | same |
| `implementation/PHASE-06-V2` working files (the contract files stay, see below) | same |
| `saas-full-test-evidence/` (200 files) | `git show ed965ab:saas-full-test-evidence/<path>` |
| `reference/original/` (historical V1 handoff) | `git show ed965ab:reference/original/<path>` |
| `docs/rag-phase` stage reports, code review, final report; `docs/RAG-PHASE-PROMPT-v2.md`; `docs/phase4report.md` | `git show ed965ab:docs/<path>` |
| `implementation/PHASE-07/HOSTING-OPTIONS.md` | hosting was decided in ADR-007 (existing VPS) |

Kept on purpose: the contract copies `docs/17` and `implementation/PHASE-06-V2/` (delta, hash file and the `many-pack` copies), which `scripts/check_contract_copies.py` checks against the Many repository's copies.
