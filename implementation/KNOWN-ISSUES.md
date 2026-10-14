# Known issues

Status: OPEN

- Handoff journey: visitor widget never shows the agent reply within 20s in `conversations.spec` — source: owner-provided issue list (2026-10-14); cause unknown.
- `widget.spec:146` is flaky with `ECONNRESET` — source: owner-provided issue list (2026-10-14).
- Unanswered-twice handoff reply uses orders/accounts wording — source: owner-provided issue list (2026-10-14).
- AI cost analytics unavailable because provider usage and pricing data are not stored — source: P7-01 implementation and `PROGRESS.md` (2026-10-14).
- P5-03, P5-05, and phase sign-off remain unticked — source: `implementation/PHASE-CHECKLISTS.md` (2026-10-14).
- P7-01 operations UI browser check is UNVERIFIED — source: owner instruction (2026-10-14).
- P7-02 plan quota values and sentiment cost cap are unspecified; implementation is blocked pending owner-defined values — source: `docs/13-SUBSCRIPTIONS-AND-USAGE.md` and `implementation/PHASE-CHECKLISTS.md` (2026-10-14).
- P2 parser timeout uses a worker thread; timing out the future does not stop the underlying parse operation — source: `apps/api/app/knowledge/ingest.py::parse_source` (2026-10-14 code inspection).
