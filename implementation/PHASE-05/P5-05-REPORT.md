# P5-05 — Follow-ups and analytics

## Built

- Tenant-scoped website follow-up scheduling and cancellation backed by durable worker jobs. A ready follow-up appears once in the visitor's next widget history read; there is no unsolicited push.
- Tenant-scoped measured analytics for handoff rate, first human reply time, conversations by channel, open/resolved state, existing sentiment values, and agent workload.
- Added Alembic migration `0009_follow_ups`, API, worker, widget-history, contact profile, and analytics UI integrations.
- Sentiment classification and plan cost caps are deferred to P7-02 by the owner decision dated 2026-10-14. The P5 UI reports “Sentiment not measured yet” when the aggregate is empty.

## Verification

- Linux full API checks on a disposable `_test` database: Ruff passed; 138 files formatted; mypy passed (134 source files); `228 passed, 1 warning` (Starlette/httpx deprecation). Exact command and output are recorded in `PROGRESS.md`.
- Linux focused regressions: `pytest -q tests/test_inbox_list.py tests/test_followups_analytics.py --tb=short` — EXIT 0, `7 passed, 1 warning in 8.54s`. The additional assertion checks that the one-time delivered follow-up is the inbox's latest message and is returned exactly once.
- Web lint, web Prettier check, and typecheck passed. The production build and Playwright suite could not run to completion in this Windows sandbox (`spawn EPERM`); see the phase report for the exact owner-run command.

## Limitations

- P5-05 remains unticked until the required phase browser gate passes.
- Classification is not implemented in P5. Analytics only aggregates stored values; P7-02 owns the quota-capped sentiment job.
- Delivery is website-only and occurs on the next widget history read. No Meta/Many sending is implemented here.
