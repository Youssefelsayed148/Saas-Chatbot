# Close-out plan: ManyOsirisChat + SaaS chatbot (Meta approval and healthy delegation)

Written 2026-10-28 for the owner. Same file lives in both repos (SaaS: `implementation/CLOSEOUT-PLAN.md`, Many: `docs/saas-delegation/CLOSEOUT-PLAN.md`); keep them identical.

Repos and branches
- Many: integrated `.closeout-worktrees/batch-b`, `closeout/batch-b`, application commit `6dc4bb9bc7a30735f994cad25c2a0cbdd91cd6cf` (2026-10-29); handoff documentation follows. Reviewed Batch T/A5 corrections and CSV workspace fix committed; R1 implemented locally. See PROGRESS.md.
- SaaS: integrated .closeout-worktrees/batch-c, closeout/batch-c. Full API baseline 86c992d: 1208 passed / 8 fixture failures, all resolved by affected reruns. Test-only fixes ce1532a and 88599d7. Final full Playwright at 88599d7: 176/176 passed, D1 MET. Neither application branch was merged by this testing session.
- Contract source of truth: SaaS `implementation/PHASE-06-V2/many-pack/CONTRACT-V1.md` + `CONTRACT-V1.1-DELTA.md`, copied byte-for-byte into Many (`CONTRACT.sha256`).

## Owner decisions recorded

| # | Decision | Status |
|---|---|---|
| D1 | B1: a **green Playwright run is required** before the SaaS merges to main | Decided; local gate MET 2026-10-29: 176/176 at 88599d7; owner merge approval remains separate |
| D2 | Hosting (ADR-007): the SaaS is **already deployed** (VPS, Docker, Caddy, `scripts/deploy.sh`). Close-out only **rebuilds** it. Record ADR-007 as decided | Decided (owner); ADR-007 hosting text recorded in C1; runtime rebuild pending |
| D3 | Deletion across both apps | Recommendation accepted by owner; A16 text approved 2026-10-28; implementation verification pending |
| D4 | Screencasts show Many's native flows per permission plus one delegated conversation; privacy discloses the SaaS | Owner follows recommendation; confirm evidence/recording text before publication |
| D5 | Instagram unsupported-message forwarding for delegated accounts (`59d3442`) | CONFIRMED (owner, 2026-10-28): keep commit `59d3442` |
| D6 | Expired Meta token file ("popeye access token.txt") | Owner: ignore |

## D3 review: what happens today with deletion

Many (`backend/app/api/routes_instagram.py:210`, `routes_facebook.py:283`, `routes_whatsapp.py:279`)
- `DELETE .../accounts/{id}` (disconnect) only sets status `disconnected` and marks tokens `expired`. Encrypted tokens stay in the database.
- `DELETE .../accounts/{id}/hard` (Instagram) deletes leads, messages, comments, campaigns, tokens and the account. Its documented FK map has no conversations, `saas_forward_events`, `saas_outbound_messages`, `webhook_events` raw payloads, or WhatsApp/Facebook equivalents. `conversations.lead_id` is a non-null FK, so this probably fails or leaves orphans when conversations exist. **Needs a test to prove it (A4).**
- There is no end-customer deletion route, no deauthorize callback, no data-deletion callback. The privacy page promises email-based deletion within 30 days with no code behind it.
- `saas_forward_events` clears failed payloads after 7 days and removes rows after 30; `webhook_events` raw bodies have no purge found.

SaaS (`apps/api/app/contacts/router.py:425`, `tenants/deletion.py`)
- `DELETE /contacts/{id}?erase_messages=` exists but needs an admin staff session plus CSRF. Many cannot call it.
- Channel event payloads are purged by the A14 retention job (tenant cutoff and 30 days), not on erasure.
- Whole-tenant deletion exists and purges storage.

Gap: a person who asks Many to delete their data gets deleted in Many only if an operator does it by hand, and the SaaS copy is never touched.

Recommendation
1. Meta **deauthorize callback** (`signed_request` verified with the app secret): disconnect the account(s) of that Meta user, delete their stored tokens, turn delegation off for those channels. Idempotent, always returns 200 after verification.
2. Meta **data-deletion callback** returns `{url, confirmation_code}` pointing at a public status page. It covers the connecting business admin's stored data (tokens, profile, accounts).
3. **End-customer erasure** (people who messaged a business): one admin action in Many by channel + external id, deleting lead, conversations, messages, raw webhook payloads and queued `saas_forward_events`. For delegated channels it also queues a signed **`contact.erasure`** event (contract amendment A16: `connection_id`, `external_contact_id`, `event_id`). The SaaS receiver validates it like any event, finds the contact through the connection's tenant and identity, deletes contact + messages + stored `channel_events` payloads for that identity, audits it, returns 202; Many retries like other events.
4. Interim until A16 ships: operator runbook (email → Many erase → SaaS admin `erase_contact` with `erase_messages=true`) written into the privacy page process and `docs/`.
5. Make the 30-day promise real: add a scheduled purge of `webhook_events` raw bodies and report counts.

## Ranked backlog (P0 blocks approval or safe go-live)

| ID | Pri | Item | Repo | Batch |
|---|---|---|---|---|
| R1 | P0 | [x] Local owner-approved identity policy/schema and two-phase FB/WA erasure implemented; typed unresolved provider context, scoped callbacks and migration 0030. R1-IMPLEMENTATION.md records 38 final R1-only passes, 62 related passes, migration/drift evidence and limits. Full clean-head integration, staging and unresolved-identity operator remediation remain UNVERIFIED | Many | B |
| R2 | P0 | IMPLEMENTED: A16 producer/receiver, hashed dedupe, runbooks; Many 87 / SaaS 78 distinct latest targeted passes. Full integrated/live verification pending; Many in-flight quiescence remains operational requirement | Many + SaaS | B, C |
| R3 | P0 | Draft policies implemented in both apps with processor/retention/erasure wording; targeted type/browser checks pass. Owner publication review pending | Many + SaaS | B, C |
| R4 | P0 | [x] Local rebuild source readiness verified: six C3 source checks within 23 passing script checks, API/worker key passthrough, fail-closed backup, public URL and worker wiring; three fresh migration rehearsals and clean drift. Runtime rebuild UNVERIFIED | SaaS | C |
| R5 | P0 | D1 MET: full Playwright 176/176 at 88599d7. Phase 6 merge to main remains OPEN, owner approval required; no merge executed | SaaS | C |
| R6 | P0 | Business Verification + Tech Provider status (long lead; **start now**) | Meta | E (start day 1) |
| R7 | P0 | Meta dashboard settings and real permission sets for Facebook and WhatsApp; remove `pages_manage_engagement` | Meta | E |
| R8 | P0 | [x] Local A5: owner approved v26.0 after Meta official SDK evidence; config/examples/docs updated, all version pins reviewed and 237 related tests pass. Public changelog remains inaccessible; live compatibility/dashboard settings UNVERIFIED (a5-closeout-evidence) | Many | A |
| R9 | P0 | [x] Fresh Batch T empty-to-head, 0022-to-head, downgrade-to-0022/reupgrade pass. Initial Alembic drift corrected by registering processed-event metadata/index; fresh alembic check passes (t-closeout-evidence) | Many | A, T |
| R10 | P0 | Full backend at e284afd: 911 passed, 0 failed/errors/skipped. Subsequent metadata/fixture corrections: 10 focused backend and 29 script tests pass. Final post-implementation full suite remains pending at A5 stop | Many | A, T |
| R11 | P1 | [x] T1 fixes committed as ed91c04; A1 rerun: 418 passed, 0 failures/errors/skips (a1-evidence/tests.xml) | Many | A |
| R12 | P1 | [x] D5 CONFIRMED by owner (2026-10-28): keep `59d3442`, Instagram unsupported-message forwarding for delegated accounts. Full-suite verification remains required | Many | A |
| R13 | P1 | [x] Raw forwarding headers ignored; explicit proxy peers replace wildcard (25 focused pytest tests; A6 review) | Many | A |
| R14 | P1 | [x] UTF-8 byte compare_digest with rejection/call regression tests (A6 evidence) | Many | A |
| R15 | P1 | [x] Read-only selected-channel HTTPS/secret-presence/enabled checks + independent beat observation (20 canary tests; A7 review) | Many | A |
| R16 | P1 | Canary on staging with rotation drill, replay, 429, expiry, take-over, rollback | Both | D |
| R17 | P1 | [x] Local review/policy text states business-support AI disclosure, 24 h messaging rule, existing WA free-entry exception, no human-agent tag and local rejection outside the applicable window. R17-B4-IMPLEMENTATION.md: policy tsc/lint and nine UNVERIFIED D4 evidence rows. Owner publication/recordings pending | Many/Meta | B, E |
| R18 | P1 | [x] Local test repairs verified: full API baseline 1208 pass / 8 stale-fixture failures; all eight pass in 94 distinct affected cases. Final full Playwright 176/176; Ruff, formatting, full mypy, frontend checks/build pass. No second full API green-run claim. Evidence: batch-c/saas-full-test-evidence/README.md | SaaS | C |
| R19 | P2 | [x] Local fixes/verification: Many model registry/index alignment and CSV formula output guard (3 related + 8 expanded CSV passes); SaaS existing phone guard/index/model alignment verified by 41 tests and actual index roundtrip/clean drift. No current S10; both manual CI YAMLs parse/static-check only. R19-VERIFICATION.md records limits; legacy Many CSV workspace leak proven and fixed (14 CSV passes, 2026-10-29); latest SaaS full run plus affected repairs and 176/176 full Playwright are recorded in batch-c/saas-full-test-evidence; hosted CI remains UNVERIFIED. webhook_unhealthy stays provider-global | Both | A, C, T |

## Batches

Order: A, B, C may run in parallel (different files; B and C touch only the contract amendment together, owned by C-lead). D needs A, B, C. E recording needs D. F needs E. R6 starts immediately and is owner-run.

### Batch A: Many integrity (Many repo)
Tickets
- A1 commit T1 fixes (R11). Re-run `tests/test_saas_*.py`.
- A2 guard migration 0019 (idempotent add column/constraint, verify type/default, no-op on correct DBs); verify empty→head, 0022→head, downgrade/upgrade (R9).
- A3 repair the 13 fixtures (6 webhook processing, 3 message retry, 4 private reply), the 8 token-refresh fixtures, remaining stale assertions in `t0-evidence/FAILURES.md` (R10).
- A4 add a hard-delete test with conversations present; fix whatever it proves (R1/R2 dependency).
- A5 Graph version bump after checking Meta changelog (R8): config, tests, docs.
- A6 forwarded-IP trust and verify-token `compare_digest` (R13, R14).
- A7 preflight delegation checks (R15).
- A8 [x] D5 CONFIRMED by owner (2026-10-28): keep commit `59d3442` (Instagram unsupported-message forwarding for delegated accounts).
Gate A: D5 owner decision is resolved (CONFIRMED: keep `59d3442`); this does not close the gate. Full Many suite results must be listed (pass count, every remaining failure explained), with migration evidence and nothing pushed.

Full-suite checklist:
- [ ] `backend/tests/test_saas_unsupported_instagram.py` must pass in the final full backend suite; record its result in the suite evidence. No new test run or passing result is claimed by this documentation update.

### Batch B: Meta compliance, Many side (Many repo)
- B1 deauthorize + data-deletion callbacks, `signed_request` verification, status page, tests (R1).
- B2 end-customer erasure service + admin route + `webhook_events` purge task; delegated channels queue `contact.erasure` (R2). Blocked on C2 for the receiver, but the Many half can be built against the fake SaaS.
- B3 privacy and terms rewrite (SaaS processor, retention reality, deletion routes, 24 h window, AI disclosure) (R3, R17).
- [x] B4 local review pack and policy consistency updated after R1 f3a7de0; source-backed delegation/A16/callback/retention text and nine UNVERIFIED permission evidence rows. Policy tsc/lint pass; R17-B4-IMPLEMENTATION.md. Owner publication and D4 recordings pending.
Gate B: owner reads policy text; callback tests green; contract amendment text agreed.

### Batch C: SaaS readiness (SaaS repo)
- C1 record ADR-007 as decided (VPS/Docker/Caddy) in `DECISIONS.md`; no code.
- C2 contract A16 `contact.erasure`: receiver, tenant-scoped erase by identity, payload purge, audit, tests with tenant A/B; update contract copy and `CONTRACT.sha256` in both repos (owner of the contract text for both repos).
- C3 rebuild readiness (R4): add `CHANNEL_SECRET_ENCRYPTION_KEYS` to `.env.production.example` and `DEPLOY.md` (generation command, never print), confirm worker covers channel health and outbound jobs, migration plan 0022→0030 with pre-deploy dump, rollback note (migrations 0023/0024 roll back by pausing, per docs/16).
- C4 triage the 2 API and 12 Playwright failures; fix or document each; run the **full Playwright suite green** (D1) (R5, R18).
- C5 P2 follow-ups (R19) and SaaS privacy/terms wording as processor (R3).
- C6 merge plan: rebase or merge `origin/main`, rerun everything, then request owner sign-off to merge. **No merge without sign-off.**
Gate C: green Playwright log, migration rehearsal on a disposable DB, owner sign-off to merge.

### Batch D: Staging canary (both, live; owner approval per live action)
Follow `docs/saas-delegation/CANARY.md`. Add: erasure end-to-end (Many → SaaS), deauthorize callback with a test user, rotation drill both directions, failed-event replay, `channel.status` and heartbeat, nginx 429, take-over block, rollback by disabling delegation. Record exact commands and outcomes. Gate D: evidence file signed off.

### Batch E: Meta dashboard and evidence (owner + one agent)
Settings checklist (pack section 6), permission sets confirmed from the dashboard, webhook field subscriptions, deletion/deauth URLs, reviewer accounts, screencasts with `META_MOCK_PRIVATE_REPLIES=false` and one real call per permission. D4 confirmed here. Gate E: checklist ticked, owner approves recordings.

### Batch F: Submit and go live
Submit, answer reviewer questions, after approval enable delegation per channel (WhatsApp first), monitoring and rollback runbook. Gate F: Meta approval.

## How to run this with subagents

The lead is the main Claude session. It owns the plan, merges results, and talks to the owner. Workers are subagents started by the lead, one per ticket group, only after the owner says go for that batch.

Rules for every worker
1. Read first: repo `AGENTS.md` or `CLAUDE.md`, this file, the contract files, and the files named in the ticket.
2. Work in an isolated git worktree of the right repo (`isolation: "worktree"`) on a branch named `closeout/<ticket>`; never touch the main checkout, never push, merge, deploy, call Meta/OpenAI/SaaS, or use paid APIs.
3. Own only the files listed for the ticket. If a change is needed elsewhere, report it instead of making it.
4. Tests: disposable databases only. Many tests use the T0 harness (`docs/saas-delegation/t0-evidence/harness/`); **give each worker its own database name** (`many_test_<ticket>`) so parallel runs do not clobber each other, and one Redis namespace per run. SaaS tests use their own throwaway DB per worker.
5. Never fabricate results. Report exact commands, counts and failures; mark anything not run as UNVERIFIED.
6. Final report format: files changed, tests added, command + outcome, open questions, risks. Do not commit unless the ticket says so.

Suggested parallel groups
- Group 1 (Many, files: migrations, tests/conftest, failing test files): A2, A3, A4.
- Group 2 (Many, files: config, middleware, preflight, webhook route): A5, A6, A7.
- Group 3 (Many, files: callbacks, privacy/terms pages, review pack): B1, B3, B4.
- Group 4 (Many, files: erasure service, purge task): B2.
- Group 5 (SaaS, files: channels receiver, contacts erasure, contract docs): C2.
- Group 6 (SaaS, files: deploy docs, env example, decisions): C1, C3.
- Group 7 (SaaS, files: tests and web): C4, C5.
- Groups 1 to 7 do not share files, so they can run together. B2 and C2 meet at the contract; the lead writes the A16 text first, then starts both.
- Reviewer agent (read-only) after each batch: re-verifies the batch's claims against the code and the evidence before the owner gate.

Lead responsibilities
- Write the A16 contract text and update both contract copies and `CONTRACT.sha256` in one step.
- Merge worker branches into the batch branch in order, rerun the batch tests, update `PROGRESS.md` in each repo, then stop for the owner gate.
- Keep this file's backlog table current; tick an item only with evidence.

## Current owner execution update - 2026-10-28

This update supersedes earlier requirements to wait for a separate go or stop
at every batch gate: proceed through all batches autonomously, run related
checks for each change, and run the full suites once after local integration.
Repeat tests only when new changes or failures justify it. It does not authorize
pushes, main merges, deployment, live sends, paid calls, authenticated external
service calls, or cloud resources. Public Meta documentation lookup is approved.
D5 was deferred in this earlier update; superseded by the 2026-10-28 owner decision: CONFIRMED, keep `59d3442`.
A16 approved by owner and adopted locally in synchronized contracts/manifests.
Text: Many `docs/saas-delegation/A16-PROPOSED.md` (historic name; ADOPTED status).
Many commit bfb1cc8, SaaS batch-c205bdab; producer/receiver verification pending.

Starting-state correction: Many was clean at 13c7873; T0?T6 are already
committed and pushed (owner clarification), and T1 fixes are in ed91c04.
SaaS phase6 was clean at 5fa72f7. A1 rerun passed 418 tests, with no
failures/errors/skips, 92.99 seconds. See Many PROGRESS.md and a1-evidence.
No duplicate T1 code commit is required.

Groups 1/2/6 started first, isolated branches closeout/a2-a4, closeout/a5-a7,
closeout/c1-c3. Group 6 ownership additionally includes compose.prod.yaml and
scripts/deploy.sh because inspection found missing API/worker key passthrough
and a deployment script that only warned on a failed predeploy backup. Runtime
rebuild/deployment remains UNVERIFIED and unapproved. Shared progress, plan,
contract adoption and integrations belong to the lead. Initial read-only review
found one A2 SQL-literal normalization defect, fixed and regression-tested; final
review found no remaining blocking/high/medium issues in A2?A4/A6?A7/C1/C3.
Worker commits: Many afb604f and 6e80eaa, SaaS3347a02. Integrated local batch
branches: Many closeout/batch-a0ca1c67, SaaS closeout/batch-c216a4f0.
No full integrated suite yet; no main merge, push, deployment or live call.
B1/B3/B4 worker completed related callback, migration and two-page TypeScript
checks; B1 remains PARTIAL. Lead additionally fixed CLI initialization exception
sanitization (1 focused test passed) and named upsert-constraint/index drift
validation (5 standalone migration assertions passed). Independent review of
these new changes is pending. B2/C2 and C4/C5 subsequently completed; final update below supersedes this intermediate state.
Owner approved shared dedupe-key hashing plus migration to remove legacy raw
IDs/fallback text without an Instagram dispatch/send-handler refactor. Worker
implementation and focused replay/privacy tests subsequently passed; full
integrated/live verification remains pending.

The synchronized SaaS plan copy is in SAAS-chats-ai/implementation, not the
SAAS-chats-ai-phase6 checkout. Keep the two existing copies byte-identical.

## Final implementation handoff - 2026-10-28

Latest owner instruction: finish the three remaining implementations, then give
an exact prompt for full testing in a NEW SESSION. No full integrated suites
were run after this instruction. The three fixes are complete and reviewed:
hashed processed keys/migration0029; erasure race/recipient safety with SaaS0031;
and the remaining knowledge/overview Playwright repairs.

Final independent review: no remaining blocking/high/medium findings in reviewed
scope. Many B2 focused10+3 passes,87distinct latest passing cases; SaaS C2 final
32focused passes,78distinct latest passing cases; C4/C5 API31passes and17distinct
latest targeted Playwright passes. These are iterative targeted results, not
full green suites. Evidence and remaining limits: FINAL-IMPLEMENTATION-REVIEW.md.

Integrated application bases: Many closeout/batch-b33bde97, SaaS
closeout/batch-c1ee703e; only final lead documentation/source-check updates follow.
Full testing prompt: Many docs/saas-delegation/TESTING-HANDOFF.md. Single source
migration heads: Many0029_hash_processed_event_keys; SaaS0031_contact_erasure.

At this handoff, OPEN items included D5 (owner deferred; now superseded by CONFIRMED: keep `59d3442`), A5 primary Graph-version evidence (official429),
R1 automatic Meta admin mapping/full FBWA admin erasure, full integrated suites,
D1 full Playwright gate, staging/live canary, owner-run Meta verification/settings,
main merge/rebuild/deployment/submission approvals. No release gate is closed by
targeted tests. No push, main merge, deployment, live send or paid call occurred.

## Many-side testing update - 2026-10-28

Batch T ran once on a fresh allowlisted snapshot of Many e284afd: 911 backend
passes, zero failures/errors/skips; contract hashes pass; dashboard tsc/lint
pass (one lint warning). Migration rehearsals pass. Two stale canary fixtures
and real metadata drift were corrected locally with 10 focused backend passes,
29 script passes and a clean fresh Alembic check. No full-suite result is claimed
for later application changes. See PROGRESS.md and t-closeout-evidence.

A5 resumed after Meta's official Node SDK source established a v26.0 pin and the
owner explicitly approved that target. Local upgrade and 237 related tests pass;
no live compatibility claim. R1 design is now concrete and awaits the required
owner gate before migration. Unproven provider subject namespaces remain a
blocking question, not an inferred mapping. R17/B4 re-check, remaining R19 and
D/E preparation are pending behind this ordered R1 stop. No migration added.
D5 is now CONFIRMED by owner (2026-10-28): keep `59d3442`; no code changed for this decision. Merge plan documented only; no merge executed.

## Standing rules
No push, merge, deploy, live send or paid call without separate approval. Meta tokens and webhooks stay in Many only. Tenant scope on every SaaS query, with A/B tests. Alembic migrations only. Record exact commands and outcomes in `PROGRESS.md`.

## CSV/handoff close-out update - 2026-10-29

This update supersedes historical source-head and pending-review statements above.
Reviewed Batch T/A5 changes and legacy CSV authorization fix are committed in the
Many application commit listed at the top. CSV A/B regressions first proved leaks
on all three platforms; after workspace and label scoping, 14 related tests pass.
No full-suite result is claimed. TESTING-HANDOFF.md pins the actual application
commits and verified single migration source heads: Many 0030_meta_account_erasure,
SaaS 0031_contact_erasure. R1/R17 implementation reports supersede older proposal
status. Staging, unresolved identity remediation and owner release gates remain.

## SaaS full testing close-out — 2026-10-29

This entry supersedes earlier SaaS full-suite/D1-pending statements. Worktree
batch-c, source tested by final full Playwright:
88599d7a9034f670dc0ee0fead89fa828feb69cc. Fresh allowlisted source snapshot,
new private Postgres cluster and loopback-only namespace for every run.

Full API at 86c992d: 1208 passed, 8 failed, zero errors/skips, 1330.93s.
All eight were stale fixtures (four diagnostic floors; no-model busy cap;
R19 scratch path; production-settings stub inheritance; Cairo DST arithmetic).
Test-only repairs committed in ce1532a; 78 + 16 distinct affected cases pass.
Initial full mypy's 13 pre-existing test-typing errors are separately corrected;
final app/full mypy pass (128/289 files), Ruff/format pass (304 files).
Scripts: 23 pass. Contracts: both manifests and cross-repo copies match.
Three disposable Alembic rehearsals and all drift checks pass; sole head 0031.
No production source or migration changed; no test skips/xfails added.

Frontend typecheck/lint, 24 Node unit tests and production build pass. Initial
full Playwright: 174 passed / 2 failed because widget-domain.spec.ts hard-coded
3100 instead of E2E_WEB_PORT. One-line fix 88599d7 preserves all CSP/domain
assertions; affected spec 2/2 passes. Final normal full npm test at 88599d7:
176/176 passed, no failures/errors/skips, 224.45107s JUnit (225s wall).
Normal global setup/teardown and production build, no reuse/temp config.

A16 receiver 23 cases, tenant A/B matrix, channel suite, 18 CSV export safety
cases, actual health-poll index roundtrip/clean drift and S10 absence verified.
Exact commands, all attempts, counts, logs/JUnit, provenance and teardown
warning explanation: .closeout-worktrees/batch-c/saas-full-test-evidence/README.md.

D1 is MET; R5 main merge is OPEN and unperformed. R4 deployed rebuild, hosted CI,
live Meta, real Many-to-SaaS round trip, staging canary and owner release
approvals remain UNVERIFIED. No push/merge/deploy/live send/paid or authenticated
external call. Only the canonical Many plan/progress documentation is updated
outside batch-c. The prohibited original SaaS checkouts remain untouched.
For this session batch-c/implementation/CLOSEOUT-PLAN.md is the synchronized
SaaS plan copy; it is byte-identical to this Many canonical copy.