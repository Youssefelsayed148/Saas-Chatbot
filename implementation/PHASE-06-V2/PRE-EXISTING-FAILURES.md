# Failures that are NOT caused by the Phase 6 channel work

Rewritten 2026-10-27 (close-out session C-05) on `claude/phase-6-channels-closeout-nznxfu` (= feature/phase-6-channels 22acf2d + C-01..C-04) merged with `origin/main` (d189893). Environment: Ubuntu 24.04 cloud VM, PostgreSQL 16.15, **pgvector 0.6.0** (the earlier run used 0.8.0), Python 3.12, disposable DBs only.

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
