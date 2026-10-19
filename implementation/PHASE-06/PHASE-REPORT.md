# Phase 6 report

Status: tickets P6-05, P6-05b and P6-06 are built and verified on
`feature/phase-6-channels` in the phase worktree. NOT mergeable: the owner has
not signed off, P7 is incomplete, no staging canary has been run, and the
Many-side delegated mode does not exist yet. See "Remaining gaps" below.

| Ticket | Result | Commits |
|---|---|---|
| P6-00–02 | Done in existing branch history | through `e0c5526` |
| P6-03 | Backend accepted on verification evidence (P6-03 status in PROGRESS.md); delivery UI verified by Playwright + unit tests | historical |
| P6-05 | Done: health pull/push, poll job, staleness, staff Channels UI, client Overview card | `5eba256` + `c1c20f7` |
| P6-05b | Done: unified inbox (channel filter/badges/connection names) + insights by channel + contacts channels | `6996132` + `398ed3c` |
| P6-06 | Done: docs/17 v1 contract suite (17 tests) + docs (docs/16 runbook, docs/17 deviation note, ADR-020), PHASE-REPORT reconciled | `a9a7066` + docs commit |
| P6-02b | Optional, not built (campaign opening message is displayed only, D7 display-only) | — |
| P6-04 | Not built, per instruction (follow-ups/broadcasts deferred) | — |

The earlier STOPPED finding (corpus fixture `KNOWLEDGE_EMPTY` at baseline) was
environmental; the Step 1 gate after the clean restart recorded 102 passed × 2
rounds and P6-05 closed it (PROGRESS.md).

## Remaining gaps (honest list)

1. **"No AI fallback" is a Many-side rule** (docs/17 §1.4 item 4). This repo
   cannot prove Many's behavior. SaaS-side evidence is only that a message
   that exhausts its retry budget fails with `many_unreachable` and no
   alternate send path exists (`test_channel_contract.py::test_e3_...`).
   Verifying Many's responsibility needs the Many workstream tests
   (MANY-AGENT-PROMPT.md item 1 / 12.5 test list).
2. **No staging end-to-end with a real test number.** The canary in docs/16 is
   a plan; it needs owner approval, ADR-007 hosting, and Many-side delegated
   mode. The E2E here is inbound-only against the fake peer: the SaaS pins
   outbound DNS to global IPs, so the e2e cannot receive SaaS→Many sends; that
   leg is covered by the FakeMany transport tests instead.
3. **Contract scope:** the FakeMany suite pins docs/17 v1 (signing, skew,
   dedupe, paused, revoked, pull, retries, statuses) but cannot pin Many-side
   behaviors (forwarding retries up to 24 h, heartbeat interval, Meta error
   mapping) — they are handover requirements, not SaaS tests.
4. **ADR-020 needs owner sign-off** (retry-budget exhaustion vs the literal
   consecutive-failure wording in docs/17 §6). The built behavior is
   documented in docs/17 and DECISIONS.md; changing it later is small and
   reversible.
5. **Website tests were not touched**, but the Playwright env now exposes
   `E2E_WEB_PORT` and sets `ENVIRONMENT=test` on the spawned worker (harness
   fixes without behavior change to accepted suites).
6. **Owner-known open items** from PLAN §9 stand (rate limit values, reply
   length constants per channel, whether P6-02b should still be built).
7. **No merge claim:** merge gates remain the PLAN §1 rules (website MVP
   sign-off, P7 completion, full green Playwright + owner approval, then
   `git merge --no-ff`).

## Playwright delivery states covered (P6)

- Staff Channels page lifecycle at 360px + RTL (create, pause/resume, AI
  toggle, rotate, revoke) — `channels.spec.ts` (commit `c1c20f7`).
- Inbound leg with fake Many: signed campaign event → thread with channel
  badge, "From campaign: Spring", pending delivery, client Overview card —
  `channels.spec.ts`; delivery states pending→delivered in
  `channel-delivery.spec.ts` and the unit suite — same commit.
- Mixed-channel inbox + insights + contacts at 360px + RTL (badges, filter,
  campaign note, connection note, insights table/campaign list match) —
  `channel-insights.spec.ts` (commit `398ed3c`).

## Verification summary

Exact commands and counts per ticket are in PROGRESS.md:
- Step 1 gate after clean restart: 14 baseline files × 2 rounds = 102 passed
  each round; channel suites 63; startup guard 8; digest 1.
- P6-05: health file 9; channel suites 73 total; frontend unit 14/14; lint +
  typecheck exit 0; two Playwright runs green.
- P6-05b: API 9 new; affected suites unchanged (6/5/1/5/16/6); node unit 8+14;
  lint/typecheck exit 0; new Playwright spec 1 passed.
- P6-06: contract suite 17; channel suites 7+1+12+28+16+9+17 = 90; final
  massive re-run recorded below in PROGRESS.md (final verification section).

Not mergeable until: owner sign-off on ADR-020 + P6-05b scope, P7 completion,
full green Playwright on the final head, staging canary with the Many side in
delegated mode, and explicit owner approval.
