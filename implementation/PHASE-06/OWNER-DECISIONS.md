# Owner decisions needed before the merge of `feature/phase-6-channels` to main

Prepared 2026-10-27 (close-out session 2). `DECISIONS.md` was NOT edited; nothing was merged; this is evidence and a recommendation only. Evidence references are to `implementation/PHASE-06/PROGRESS.md` (batches 1-5) and `implementation/PHASE-06-V2/PRE-EXISTING-FAILURES.md`.

Merge gate (DECISIONS.md, 2026-10-18): website MVP sign-off, P7 complete, a full green Playwright run, owner approval.

## B1 - Is a green full Playwright run a merge gate?

Question: the roadmap makes "full green Playwright" mandatory in P7-05 and before P6; does it also gate this merge?

Options
1. **Yes, gate on a fully green suite.** Fix or quarantine-by-fixing the 12 failing tests on main first.
2. **Gate on "no new failures versus main"** (the branch introduces none) and track the 12 as main-owned defects.

Evidence (batch 4b): full suite 162 passed, 12 failed in 16.5 min. The same 12 tests fail on clean `origin/main` d189893 (8 in `widget-streaming.spec.ts`, 2 in `overview.spec.ts` with 240 s timeouts, 1 each in `group-c-polish` and `knowledge`). All three channel specs pass. Root causes of the 12 were not investigated. Under option 1 the suite is not green today and the cause is main, so the merge cannot proceed until main is fixed.

Recommendation: option 2 for this merge (the branch is no worse than main on all 174 tests), but keep the literal "full green" requirement for P7-05 sign-off, and open a ticket on main for the 12. If you choose option 1, the work is on main's website specs, not on this branch.

## ADR-020 - Channel health degrades on retry-budget exhaustion (deviation from docs/17 section 6 wording)

Question: approve the built model (one message that exhausts its 6-attempt budget marks the connection degraded) or require the literal "5 consecutive failures" counter?

Options
a. **Approve as built.** No change.
b. Require a `consecutive_send_failures` column plus threshold and reset before staging (new migration after 0030, edits to accepted tests).

Evidence: unchanged since the ADR text. New in this session: the label rule for a 401 anywhere in the budget (A15, batch 2c) keeps the same trigger (budget exhaustion), only the reason string differs; `test_channel_outbound.py` 39 passed. Health is also refreshed by the 5-minute signed pull and shows `unknown/stale` after 15 minutes without a signal (see the ADR). Note: the ADR says "migration 0020 has unused head room"; that is stale, the chain is at 0030 now.

Recommendation: (a). The failure is already visible as a failed message, one healthy pull clears the flag, and (b) costs a migration and test churn for little extra safety. Revisit only if staging shows flapping.

## ADR-007 - Hosting, object storage, retention, data residency (OPEN)

Question: which hosting? Gates **staging and production only**, not this merge (DECISIONS.md 2026-10-18).

Options: see `implementation/PHASE-07/HOSTING-OPTIONS.md`; no provider is chosen anywhere in the repo.

Evidence: P7-05 restore drill, alert delivery and staging smoke test are all UNVERIFIED because they need a target (`PHASE-07/BACKUP-RESTORE.md`, `MONITORING-ALERTS.md`). Session environment note: pgvector 0.8.0 is required for hybrid retrieval to behave as tested (batch 1); whichever host is chosen must provide pgvector >= 0.8.0 (managed Postgres images often ship older).

Recommendation: decide before staging, not before the merge. Add "pgvector >= 0.8.0" to the hosting criteria.

## ADR-008 - Paid plans, payment provider, currencies (OPEN)

Question: billing model. Gates **paid plans only**.

Evidence: P7-02 quotas use PLACEHOLDER plan values that you have not approved (`app/quotas`); signup creates a Free PLACEHOLDER tenant.

Recommendation: leave OPEN for this merge; do not enable paid plans or publish the placeholder values to clients. Approve real quota values separately when billing is decided.

## Also needing you (not decisions in DECISIONS.md)

- **S10 is undefined** (batch 3a): please supply its text or declare it void.
- **`test_tone_prompt`** fails on main too: re-pin the hash (main-owned) or explain the template change.
- **P7 completion** (batch 4a): restore drill, independent security review, approved quota values, operations UI browser check, phase report and sign-off are missing.
- **Alembic drift ticket** (`TICKET-alembic-drift.md`): main-owned; recommended model-only fix.
- **Website MVP sign-off**: not something this session can evidence.
