# Failures that are NOT caused by the Phase 6 channel work

Rewritten 2026-10-27 (close-out session C-05) on `claude/phase-6-channels-closeout-nznxfu` (= feature/phase-6-channels 22acf2d + C-01..C-04) merged with `origin/main` (d189893). Environment: Ubuntu 24.04 cloud VM, PostgreSQL 16.15, **pgvector 0.6.0** (the earlier run used 0.8.0), Python 3.12, disposable DBs only.

> Historical section below (pgvector 0.6.0 run). The current record is the "Final record" section at the end of this file.

## API tests (pytest, file by file, 97 files): 1112 passed, 9 failed

Command per file: `cd apps/api && PYTHONUTF8=1 TEST_DATABASE_URL=postgresql://test:test@127.0.0.1:5432/phase6_test python -m pytest tests/<file>.py -q -p no:cacheprovider`.

| Test file | Failures on this branch | Same file on clean `origin/main` (worktree d189893, DB `mainchk_test`) |
|---|---|---|
| `test_embedding_readiness.py` | 3 failed, 3 passed (`test_ingest_while_live_keeps_published_hybrid_and_reports_progress`, `test_failed_backfill_keeps_live_hybrid`, `test_backfill_skips_archived_and_rollback_embeds_on_demand`) | 3 failed, 3 passed (identical) |
| `test_hybrid_retrieval.py` | 3 failed, 8 passed (`test_filtered_vector_isolation_full_k_and_explain`, `test_hybrid_keeps_always_include_and_whole_document_rules`, `test_active_backfill_and_unready_draft_do_not_degrade_live_hybrid`); mode is `fts_only` where `hybrid` is expected | 3 failed, 8 passed (identical) |
| `test_rag_evaluation.py` | 2 failed, 10 passed (`test_two_mode_retrieval_eval_is_entirely_offline`, `test_owner_calibration_runner_writes_one_complete_report_without_live_http`) | 2 failed, 10 passed (identical) |
| `test_tone_prompt.py` | 1 failed (`test_empty_tone_leaves_prompt_body_byte_identical`) | 1 failed (identical; known) |
| `test_trace_context.py` | **passes** (5 passed) | passes (5 passed) |

All nine fail identically on clean main, so none is caused by Phase 6. The embedding/hybrid/RAG failures are new compared with the previous record and very likely come from this VM's pgvector 0.6.0 (hybrid falls back to `fts_only`); they were not investigated further and need a re-run on pgvector 0.8.0. `test_trace_context` (zero-evidence) failed in the previous record but passes in this environment on both trees, so it is environment- or order-dependent, not fixed by this branch.

## Lint, types, migrations

`ruff check .`, `ruff format --check .` (299 files) and `mypy app` (127 files) clean, re-run after the last code change. Alembic on a fresh DB: `upgrade head`, `downgrade 0022_knowledge_hygiene`, `downgrade base`, `upgrade head` all exit 0; one head, `0030_channel_health_poll_index`. `alembic check` reports only main-owned drift: `bots.uq_bots_widget_locator` (index vs unique constraint) and `provisioning_requests` (`ix_provisioning_requests_created`, `uq_provisioning_scope_key`). The 0030 index is declared in the `Job` model, so it adds no drift.

## Web

`npm run typecheck` exit 0; `npm run lint` (eslint --max-warnings 0) exit 0; `node --test tests/*.unit.mjs`: 24 pass, 0 fail.

## Playwright

Only the three channel specs (channels, channel-insights, channel-delivery): **5 passed** (55 s), using a temporary config with `executablePath` of the installed Chromium 1243 (the config was deleted afterwards). Every other spec is NOT VERIFIED here.

## Final record 2026-10-27 (close-out session 2, batch 5; supersedes the pgvector 0.6.0 numbers above and the batch-1 note)

Environment: Ubuntu 24.04 cloud VM, PostgreSQL 16.15, **pgvector 0.8.0** (built from the upstream 0.8.0 tarball), Redis 7.0.15, Python 3.12.3, disposable DBs only. Branch tree = 8cc6a16-era code (8987b24 plus batch 2 fixes); clean main = `origin/main` d189893 in a detached worktree.

### API (pytest, file by file, 97 files, once): 1123 passed, 2 failed

Command per file: `cd apps/api && PYTHONUTF8=1 TEST_DATABASE_URL=postgresql://test:test@127.0.0.1:5432/phase6_test python -m pytest tests/<file>.py -q -p no:cacheprovider`.

| Failing test | Branch | Clean `origin/main` d189893 | Cause |
|---|---|---|---|
| `test_tone_prompt.py::test_empty_tone_leaves_prompt_body_byte_identical` | fails | fails (identical) | Stale pinned SHA-256 (`2cd35a17...` expected, `33c62542...` actual); DB-free; not pgvector |
| `test_trace_context.py::test_zero_evidence_lists_the_top_rejected_candidates` | fails (`'answer' == 'cannot_confirm'`) | fails (identical, re-run on both) | Depends on the pgvector version: it passed on 0.6.0 and fails on 0.8.0, because 0.8.0 retrieval now finds evidence for the "zero evidence" question |

The nine earlier failures (embedding_readiness 3, hybrid_retrieval 3, rag_evaluation 2, tone_prompt 1) are down to one: the eight retrieval/embedding/RAG-eval ones were pgvector 0.6.0; `test_trace_context` is the mirror image (new on 0.8.0, same on main). Neither remaining failure is Phase 6.

### Lint, types, migrations

`ruff check .` All checks passed; `ruff format --check .` 299 files already formatted; `mypy app` Success, 127 source files. Alembic on fresh DB `phase6_alembic_test`: `upgrade head`, `downgrade 0022_knowledge_hygiene`, `downgrade base`, `upgrade head` all exit 0; `alembic heads` single `0030_channel_health_poll_index`. `alembic check` drift is main-owned and identical on clean main (ticket: `implementation/PHASE-06/TICKET-alembic-drift.md`).

### Web and tooling

`npm run typecheck` exit 0; `npm run lint` exit 0; `node --test tests/*.unit.mjs`: 24 pass, 0 fail; `make check-contract` OK; `scripts` unittest 9 OK.

### Playwright (full suite, once): 162 passed, 12 failed (NOT green)

Temporary config with `executablePath` of the installed Chromium 1243 (not committed). The same 12 tests fail on clean main (re-run of the four failing spec files there: 18 passed, 12 failed): `group-c-polish.spec.ts:129`, `knowledge.spec.ts:204`, `overview.spec.ts:136` and `:220` (240 s timeouts), and eight in `widget-streaming.spec.ts` (242, 260, 278, 291, 316 x2, 331, 343). All three channel specs pass. Details in `implementation/PHASE-06/PROGRESS.md` batch 4b.
