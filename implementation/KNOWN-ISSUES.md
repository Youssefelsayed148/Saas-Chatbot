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
- API integration tests for P7-02/P7-03/P7-04 and the P2 upload regressions remain UNVERIFIED until run against an explicitly configured disposable PostgreSQL URL — source: this run's pytest setup error and `apps/api/tests/conftest.py::_base_database_url` (2026-10-14).
- P7-05 backup/restore drill is UNVERIFIED; hosting, backup target, and RPO/RTO depend on open ADR-007 — source: `implementation/PHASE-07/BACKUP-RESTORE.md` and `DECISIONS.md` ADR-007 (2026-10-14).
- Independent P7 security review is pending; no independent reviewer has supplied findings or sign-off — source: `implementation/PHASE-07/SECURITY-REVIEW.md` (2026-10-14).
- Full Playwright suite is UNVERIFIED; existing browser failures were not chased per owner instruction — source: `implementation/PHASE-CHECKLISTS.md` P7-05 and owner instruction (2026-10-14).
- Production alert receiver and alert-delivery test are UNVERIFIED pending hosting selection — source: `implementation/PHASE-07/MONITORING-ALERTS.md` (2026-10-14).
