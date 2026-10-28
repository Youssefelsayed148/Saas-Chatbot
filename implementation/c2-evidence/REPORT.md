# C2 A16 receiver — 2026-10-28

Isolated worktree: `ManyOsirisChat/.closeout-worktrees/c2`, branch `closeout/c2`,
base `205bdab` (`closeout/batch-c`, owner-approved A16 contract).
No commit, push, merge, deployment, provider call, real credential/environment
file access, or existing database/service access. Shared progress/contracts
are lead-owned and were not edited here.

## Files changed

- `apps/api/app/channels/events.py`: validates A16 identifiers, strips unknown
  erasure fields from stored payload, retains signed transport/dedupe behavior;
  existing dedupe queries now explicitly include authenticated tenant scope.
- `apps/api/app/channels/erasure.py` (new): tenant/connection/identity-scoped
  resolution, transactional erasure of the contact and all explicitly merged
  linked conversations/messages, payload purge, pending-job cancellation,
  privacy-safe audit, accounting trace scrubbing without refunding used quotas.
  Shared sorted per-identity advisory locks preserve unrelated contact throughput.
- `apps/api/app/channels/inbound.py`: dispatch A16 through durable existing
  inbound jobs; accepted erasure survives later connection revocation; missing
  erasure payload remains a visible failed request requiring operator action.
  Normal inbound refreshes after waiting for the erasure lock and checks fences.
- `apps/api/app/channels/outbound.py`: recipient lock/revalidation before the
  existing sender. HTTP/signing/retry implementation remains unchanged.
- `apps/api/app/db/models/channels.py` and new migration
  `0031_contact_erasure.py`: reversible tenant/connection-scoped replay fences,
  domain-separated SHA256 digest instead of raw external identity, server-time
  occurrence/receipt cutoffs. Fence cascades with connection/tenant deletion.
- `apps/api/app/db/models/chat.py`: nullable stable per-conversation
  `external_contact_id`, added by the same unshipped 0031 migration. No guessed
  migration backfill; explicit CRM merges cannot redirect a conversation's recipient.
- New `apps/api/tests/test_channel_erasure.py`: 23 erasure/recipient regressions.
- `test_channel_migrations.py`, `test_channel_outbound.py`,
  `test_channel_health.py`: only expected-head assertion/imports updated to
  require the actual single source head; substantive round-trip assertions kept.
  These and outbound locking were explicit lead-approved scope extensions.
- Evidence scripts, logs, XML, and independent aggregate in this directory.

## Tests added

Signed malformed input (five cases), generic auth rejection/header-body match,
paused acceptance, duplicate 202, revoked rejection and accepted-before-revoke
processing; tenant A/B plus same-tenant/same-external-id/different-connection
isolation; merged contacts; raw payload/job cleanup; missing identity; delayed
pre-erasure input versus genuine later recontact; stale claimed inbound and
outbound interleavings; rollback/retry after injected failure; missing-payload
operator failure; advisory-lock release and digest scoping; preservation of
message/token quota accounting while removing trace/customer references.

## Exact commands and outcomes

Commands ran from this worktree unless stated. Source edits used apply_patch;
Ruff formatted only assigned implementation/test files.

1. `git -C ../SAAS-chats-ai-phase6 worktree add .closeout-worktrees/c2 -b closeout/c2 closeout/batch-c`
   succeeded but the relative destination resolved under the SaaS checkout.
   Corrected with `git -C ../SAAS-chats-ai-phase6 worktree move
   'D:/Projects/Work Projects/The Osiris Labs/SAAS-chats-ai-phase6/.closeout-worktrees/c2'
   'D:/Projects/Work Projects/The Osiris Labs/ManyOsirisChat/.closeout-worktrees/c2'`:
   exit 0; existing checkout contents were not edited.
2. Initial default-sandbox Python write/native Ruff cache access were denied;
   the Python edit made no change. apply_patch and approved offline WSL checks
   were used instead. One inline quoted WSL command lost its directory quoting
   (`cd: /mnt/d/Projects/Work: No such file or directory`), exit 1; replaced by
   the retained script path, without inferring a check result.
3. Source command, repeated only after relevant source/test additions:

   ```powershell
   wsl -d Ubuntu -u root -- bash '/mnt/d/Projects/Work Projects/The Osiris Labs/ManyOsirisChat/.closeout-worktrees/c2/implementation/c2-evidence/check-source.sh'
   ```

   Before independent review, final exit 0: `10 files left unchanged`, `All checks passed!`,
   `Success: no issues found in 3 source files`. Script runs Ruff format/check
   on ten changed files and strict mypy on erasure/inbound/outbound. Earlier
   formatting-order/import findings were corrected. Full lint/types UNVERIFIED.
4. Snapshot/test commands (runner retained verbatim):

   ```powershell
   python implementation/c2-evidence/make_snapshot.py
   wsl -d Ubuntu -u root -- bash '/mnt/d/Projects/Work Projects/The Osiris Labs/ManyOsirisChat/.closeout-worktrees/c2/implementation/c2-evidence/run-tests.sh'
   ```

   Default related set: `tests/test_channel_erasure.py tests/test_channel_events.py
   tests/test_channel_outbound.py tests/test_channel_redrive.py
   tests/test_channel_migrations.py`. Every nested test invocation explicitly:

   ```sh
   APP_ENV=test TEST_DATABASE_URL="$TEST_DATABASE_URL" pytest "${tests[@]}" -q --junitxml="$evidence/tests.xml" >"$evidence/tests.log" 2>&1
   ```

   Initial setup: **66 errors before test bodies**, due to existing conftest
   feeding a percent-encoded socket URL into Alembic ConfigParser interpolation
   (`setup-failure.*`). Harness corrected to query-free explicit URL plus
   PGHOST/PGPORT, without modifying application/conftest behavior.

   First executed related set: **64 passed, 2 failed, 31.85 s**, exit 1
   (`attempt-1.*`); both failures were stale 0030 head assertions after adding
   0031. No erasure/sender behavior test failed in that run.
5. Focused command after new erasure tests and head fixes appended these args
   to the same runner: `tests/test_channel_erasure.py
   tests/test_channel_migrations.py
   tests/test_channel_outbound.py::test_send_migration_round_trip_and_unique_message_key`.
   **15 passed, 1 failed, 7.44 s**, exit 1 (`attempt-2.*`): the new claimed-send
   test lacked a helper import (lint also caught it). The shell sequence still
   reached pytest after that lint failure; neither command is claimed green.
6. Corrected helper import; ran only
   `tests/test_channel_erasure.py::test_claimed_send_revalidates_after_erasure_before_http`:
   **1 passed, 1.55 s**, exit 0 (`attempt-3.*`).
7. Self-review corrected accounting deletion to sanitized counter preservation;
   reran only `tests/test_channel_erasure.py`: **15 passed, 7.92 s**, exit 0
   (`attempt-4.*`). This was a new meaningful code change, not a broad-suite repeat.
8. Added missing-payload visibility regression; ran only
   `tests/test_channel_erasure.py::test_missing_erasure_payload_remains_visible_for_operator_action`:
   **1 passed, 1.74 s**, exit 0 (`attempt-5.*`).
9. Lead identified another stale health head assertion; corrected only that
   assertion/imports and ran only
   `tests/test_channel_health.py::test_poll_migration_round_trip_and_unique_live_job`:
   **1 passed, 0.43 s**, exit 0 (`attempt-6.*`).
10. Final self-review strengthened the fence cutoff to server processing time
    (a queued erasure request's older occurred_at cannot weaken protection).
    Ran only
    `tests/test_channel_erasure.py::test_missing_identity_is_success_and_delayed_input_is_fenced_but_new_recontact_allowed`:
    **1 passed, 1.32 s**, exit 0 (`attempt-7.*`). Source checks in step 3 passed.
11. `python implementation/c2-evidence/verify_evidence.py` independently parses
    initial chronological JUnit files: **71 unique related test cases, each latest
    outcome passing**, no latest failure/error/skip. This is an aggregate across
    attempts, **NOT a single green 71-test run**. `evidence-summary.json` maps
    each case to its latest evidence. `git diff --check`: exit 0.

## Independent-review corrections and focused verification

The read-only reviewer identified HIGH and MEDIUM defects before integration:

- HIGH: an admin merge could commit between erasure's final identity lookup
  and its unchecked contact row-lock query. Erasure could then report completion
  against the deleted source contact while leaving data on the merge target.
  Correction: identity lookup now reads scalar contact_id values to avoid stale
  ORM identity-map values; missing locked contact requires retry; mapping and
  the complete channel identity set are re-read and compared after the row lock,
  before any fence, purge, or completion audit. Two deterministic regressions
  execute the real admin merge route in another transaction at that exact gap:
  source moved away, and target gains another identity. Both first attempts
  remain uncompleted with no fence/audit, then retries erase the full merged contact.
- MEDIUM: the outbound recipient join could return multiple identities after
  a same-connection CRM merge, raising MultipleResultsFound or choosing the wrong
  person. Correction: persist the authoritative external recipient on each new
  channel conversation; resolve legacy rows only from a unique processed
  conversation-bound inbound event or a sole current identity. Ambiguous legacy
  rows fail closed with `channel_recipient_ambiguous` and no HTTP send.
- Related lock boundary: earlier-pending processing now requires the same
  external contact as the identity lock. A bound conversation/identity mismatch
  is generic signed 422 at intake; an already queued race is quarantined as
  `conversation_recipient_mismatch` before contact/message creation or AI.
  Three merged-recipient modes (bound, historical, ambiguous), queued/intake
  mismatch, and explicit 0031 column/fence downgrade/upgrade are covered.

Lead approved exclusive `models/chat.py` ownership and the nullable 0031 column.
The migration is unshipped; the runner recreates only this worker's synthetic
`many_test_c2_test` database so Alembic actually applies the expanded revision.
No stamping, create_all, shared or existing application database was used.

Exact focused command after source validation:

```powershell
python implementation/c2-evidence/make_snapshot.py
wsl -d Ubuntu -u root -- bash '/mnt/d/Projects/Work Projects/The Osiris Labs/ManyOsirisChat/.closeout-worktrees/c2/implementation/c2-evidence/run-tests.sh' tests/test_channel_erasure.py tests/test_channel_events.py::test_tenant_scoping_and_processed_job_rerun_are_idempotent tests/test_channel_events.py::test_inbound_dedupe_sanitization_and_origin_is_written_once tests/test_channel_outbound.py::test_success_duplicate_current_secret_rotation_and_no_text_logs tests/test_channel_outbound.py::test_paused_at_job_time tests/test_channel_outbound.py::test_job_unique_key_and_foreign_job_cannot_send tests/test_channel_migrations.py tests/test_channel_outbound.py::test_send_migration_round_trip_and_unique_message_key tests/test_channel_health.py::test_poll_migration_round_trip_and_unique_live_job
```

**32 passed, 0 failures/errors/skips, one dependency warning, 14.53 s; exit 0.**
Final log/XML are `tests.log` and `tests.xml`. Private PostgreSQL stopped.
Final `check-source.sh` exited 0: five files reformatted, six unchanged, two
import findings fixed with zero remaining; strict mypy succeeds for the three
changed service modules. It covers eleven changed source/test files.
`git diff --check` passes. Latest chronological JUnit aggregation now verifies
**78 unique related cases, each latest outcome passing**; it is not a single
green 78-case suite. No full API/Playwright suite was run; the owner explicitly
deferred full testing to a new session.

Environment for all executed tests: cached pinned Linux Python 3.12.16 venv
`/var/tmp/saas-closeout-tools/venv`; private PostgreSQL 18 with pgvector 0.8.1,
cluster `/var/tmp/saas-c2-20261028/pg`, Unix socket
`/var/tmp/saas-c2-20261028/socket`, port 55443, no TCP listener.
Explicit `TEST_DATABASE_URL=postgresql://postgres@/many_test_c2`; conftest
derives only disposable `many_test_c2_test`; migration-only fixtures use their
own `_test` databases within this private cluster. APP_ENV/ENVIRONMENT=test,
stub chat/embeddings, empty provider keys, loopback-only `unshare --net` namespace.
Host/database identity printed and cluster checked before pytest. No Redis is
used by this SaaS. Each runner stopped the private PostgreSQL cluster on exit.
Snapshot contains tracked API source plus assigned additions, never dotenv.
Generated ZIP removed after final validation; builder retained for reproduction.

## Open questions / risks

- New head is 0031. Lead must update C3 operational head references/source
  checks and integrate the migration before deployment. No deployment occurred.
- Fences are pseudonymous security records, not anonymous data. They retain
  only scoped digest/cutoffs until connection/tenant deletion. Privacy/runbooks
  should disclose replay-prevention retention. Sender occurrence times must
  retain their original truthful meaning; a newly signed future forged event
  is trusted-source misconduct, not ordinary replay.
- Per-identity locks cover channel worker processing/sends. Already in-flight
  remote requests cannot be recalled. Erasure waits for a sender holding its
  lock, then removes stored content and pending work. Genuine later customer
  recontact may create a fresh contact. Cross-process load/performance and real
  Many-to-SaaS integration remain UNVERIFIED.
- Erasure removes linked conversation records rather than retaining potentially
  identifying origin/session state; quota counters remain, with trace and
  message/conversation references removed. Explicitly merged contacts are erased
  together only within the authenticated tenant, as approved in A16.
- Downgrading 0031 drops replay protection. Pause channel processing before any
  separately approved rollback and follow the existing 0023/0024 constraints.
- Legacy ambiguous merged recipients require operator repair from verified
  connection/conversation identity evidence. No automatic migration backfill or
  arbitrary identity selection is performed. New conversations persist their
  stable recipient, which is removed with the conversation on erasure.
- Full API/Playwright suites and full lint/type checks remain for the lead's
  final integrated run. No full suite was run here.
