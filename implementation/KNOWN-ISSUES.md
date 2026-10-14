# Known issues

Status: OPEN

- Handoff journey: visitor widget never shows the agent reply within 20s in `conversations.spec` — source: owner-provided issue list (2026-10-14); cause unknown.
- `widget.spec:146` is flaky with `ECONNRESET` — source: owner-provided issue list (2026-10-14).
- Unanswered-twice handoff reply uses orders/accounts wording — source: owner-provided issue list (2026-10-14).
- AI cost analytics unavailable because provider pricing data is not stored; provider-returned usage is recorded when available — source: P7-02 implementation and `docs/13-SUBSCRIPTIONS-AND-USAGE.md` (2026-10-14).
- P5-03, P5-05, and phase sign-off remain unticked — source: `implementation/PHASE-CHECKLISTS.md` (2026-10-14).
- P7-01 operations UI browser check is UNVERIFIED — source: owner instruction (2026-10-14).
- Quota values are placeholders, pricing TBD — source: owner decision and `docs/13-SUBSCRIPTIONS-AND-USAGE.md` (2026-10-14).
- RESOLVED 2026-10-14: P2 parser timeout now runs in a spawned subprocess and terminates the process at the configured wall-clock limit; regression test added but unverified pending disposable test DB — source: `apps/api/app/knowledge/ingest.py::parse_source` and `apps/api/tests/test_knowledge_parsers.py::test_parse_subprocess_is_terminated_at_timeout`.
- Tenant deletion cleans uploaded files through the current storage interface, whose local delete is best-effort if the OS refuses unlink — source: `apps/api/app/knowledge/storage.py::LocalStorage.delete` (2026-10-14 code inspection).
