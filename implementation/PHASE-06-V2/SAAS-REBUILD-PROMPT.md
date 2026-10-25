# Agent prompt: rebuild Phase 6 (ManyOsirisChat channel) on the current SaaS

Paste everything below the line into the coding agent in this repo. Attach: implementation/PHASE-06-V2/REVIEW-REPORT.md and CONTRACT-V1.1-DELTA.md (same folder).

---

You are a senior engineer in this repo on branch `feature/phase-6-channels` (AGENTS.md rules apply and win over anything below: tenant scope everywhere, hidden = 404, typed contracts, Alembic only, tests with every ticket, disposable test DB only, no push/merge/deploy/paid API calls, no Meta tokens or webhooks here, never fabricate results, record exact commands and outcomes in PROGRESS.md, stop on ambiguity or an OPEN decision).

GOAL
Close out the SaaS side of the ManyOsirisChat channel (docs/17 v1 + the v1.1 delta) ON THE EXISTING BRANCH `feature/phase-6-channels` (worktree `..\SAAS-chats-ai-phase6`), by first bringing it up to date with the current code (`feat/ui-polish`, which contains main), then fixing the defects and gaps in REVIEW-REPORT.md. The branch is 164 commits behind and has real conflicts, so the update is a ticket of its own (R-01) with the baseline restored before any new work. Read REVIEW-REPORT.md first. The owner approves contract v1.1 by issuing this prompt.

SOURCES OF TRUTH (in order): latest owner instruction, docs/ (17 + the v1.1 delta, 18, 19, 06, 04, 05), DECISIONS.md, the code and tests on the new branch. The old branch's PROGRESS.md/PHASE-REPORT.md are history, not proof.

HOW TO UPDATE THE BRANCH (no rebase, no force, no push)
1. Work in the phase-6 worktree on `feature/phase-6-channels`. Its own venv; check `python -c "import app; print(app.__file__)"` is inside the worktree before any test. Commit nothing on `main` or `feat/ui-polish`.
2. Update with `git merge feat/ui-polish` (a merge commit, history kept). Resolve conflicts by taking CURRENT code for everything unrelated to channels and re-applying only the channel touch points. Merge order later: `feat/ui-polish` must be merged to main before this branch.
3. Migrations: this branch's 0017..0020 collide with main's 0017..0022. They are unmerged, so renumber them on the branch to follow the real head (0023..), fix `down_revision` chains and any tests that name them; `alembic heads` must show exactly one head. Test up and down on the disposable DB; website data unchanged; test `conversations.connection_id` Text -> UUID with a non-empty table.
4. Web files: where the redesign (ui-polish B2 to B6) and the branch's UI changes both touched a file, keep the redesigned file and rebuild the channel parts on it in R-06; do not hand-merge old-style markup.
5. After the merge compiles, restore a green baseline (website suites and the branch's channel suites) BEFORE touching behaviour. Record exact commands and counts.

NON-NEGOTIABLE DESIGN POINTS (from the review)
- One reply brain: refactor so website and channel turns share ONE core (extract from `visitor_chat_turn`, keep `visitor_chat_turn` behaviour byte-equivalent for existing tests). Channel-specific parts are only: persistence of the visitor message, mode/status gating, no-deadline async delivery, output sanitizing, outbound enqueue. If any existing website test must change: STOP and report.
- Channel output: plain text for DMs (strip markdown/bullets markers appropriately, no citation markers or source links), per-channel style hint (short DM replies) as a bot/connection setting with a sane default; keep the answer contract extensible for later tool calls.
- Everything in REVIEW-REPORT sections 3 (D1 to D13) and 4/5 that concerns this repo is in scope. In particular: channel must equal connection channel (422); per-conversation row lock for the whole turn; bytes-safe signature compare (401, never 500); localized unsupported/busy texts; human mode beats AI-off/paused status flips; `received_at` clamp; `unconfirmed` sweep; Instagram byte-limit splitting; per-contact flood throttle and busy-reply cap; unique (channel, many_channel_ref) among non-revoked connections; "resend" option for messages that failed with `connection_paused`.
- Keep and re-verify: signing/rotation, generic 401, 64 KB cap, dedupe, tenant derived from the connection only, DNS-pinned outbound, encrypted secrets with the production startup guard, no secrets in repr/logs/exports, audit rows, route-matrix classification, retention/export/delete coverage.
- Contract v1.1 delta A1 to A13 is the spec. The fake Many must implement it so the contract suite pins it (including A2 unconfirmed, A8 throttle, A9 pull freshness, A10 clamp).

TICKETS (one per turn; after each, report in five lines and wait for "continue"; stop at the gate)
R-00 Preflight, no code: confirm the branch head and what `git merge feat/ui-polish` would conflict on (dry run with `git merge --no-commit --no-ff` then abort), current alembic head, run the baseline tests of the areas you will touch (file by file on the disposable DB 127.0.0.1:55462 set as TEST_DATABASE_URL per process, database name not used by other runs), list exact files to change, write ADR-021 (v1.1 adopted) and update docs/17 with the delta (docs only), note ADR-020 is still awaiting sign-off.
R-01 Update the branch: merge `feat/ui-polish`, resolve conflicts, renumber migrations, make everything start and pass again as described in HOW TO UPDATE. No behaviour change yet except what the merge forces. Report the conflict list and every decision. Gate: green baseline.
R-02 Shared turn core + channel turn: the refactor described above plus gating, throttle, sanitizer, localization, locking. Tests: website regression files unchanged and green; new channel turn tests (human mode, AI off, paused, resolved reopen, unsupported, long text, quota, provider failure, rerun idempotency, concurrent messages in one conversation).
R-03 Inbound events: endpoint hardening (D1, D3, D7), channel_inbound job, contact identity refresh, origin storage and A11, ordering (A7). Auth matrix and replay tests.
R-04 Outbound + delivery: outbox with byte-aware splitting (A4), error enum and unconfirmed sweep (A2, A3), busy-reply cap (A8), resend of `connection_paused` failures. Tests with the fake Many: success, 500 then success, timeout, 429 Retry-After, permanent 4xx, duplicate send idempotency, window_closed callback, out-of-order statuses, paused.
R-05 Health and operations: A9, poll job scheduling with multiple workers, ADR-020 text ready for sign-off, runbook in docs/16, canary plan, rollback = pause.
R-06 UI on the redesigned app (use the B2 foundation components, no old styles): staff Channels inside the organization workspace (create wizard with copy-once secret, pause/resume/revoke, rotate, AI toggle, check now, health, last event; plus a staff overview list), client read-only Overview card on the new dashboard, plan-usage meter for channel connections, Conversations module (Inbox + History tabs) with channel badge/filter, connection name, "From campaign", per-message delivery state incl. unconfirmed, paused composer, resend; Insights by channel reusing the B3 backend and B4 charts (no duplicate analytics code); Contacts channel column/filter. Arabic/RTL and 360 px. Playwright for each.
R-07 Verification gate: full API suite file by file, channel + contract suites, ruff/mypy on touched files, lint/typecheck, full Playwright once. Record exact commands and counts. Update docs/04, 05, 06, 16, 17, 18, ROLE-MATRIX, PHASE-CHECKLISTS, PHASE-06 PROGRESS/PHASE-REPORT. Report remaining gaps honestly. STOP: owner sign-off. No merge, no push.
R-08 (only on explicit approval after R-07) Quality tuning for DM answers using the existing eval harness: stub model by default; any real-provider run needs owner approval and a stated cost.

FIRST ACTION: R-00 only, then report.
