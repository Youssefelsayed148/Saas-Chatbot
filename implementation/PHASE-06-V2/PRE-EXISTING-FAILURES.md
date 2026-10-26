# Failures that are NOT caused by the Phase 6 channel work

Recorded 2026-10-26 on branch `claude/saas-rebuild-r00-jrd3an`. Every item below also fails on a clean `origin/main` build or test run (same tests, same counts), so none of it blocks the channel work. They are listed so the owner can schedule them as separate tickets. Root causes were NOT investigated; the "likely area" column is a pointer from the failure message only.

## A. API tests (pytest, file by file): 1003 passed, 22 failed, 0 errors

Run: `cd apps/api && TEST_DATABASE_URL=postgresql://test:test@127.0.0.1:5432/phase6 python -m pytest tests/<file>.py -q -p no:cacheprovider` for each of the 91 files.

| File | Failed | What fails (from the failure message) | Likely area / scope |
|---|---|---|---|
| test_bot_names_migration.py | 1 | `test_bot_name_backfill_keeps_existing_values`: `column "updated_at" of relation "tenants" does not exist` | Test inserts into `tenants.updated_at`, a column the schema does not have. Test-only fix likely (small). |
| test_embedding_readiness.py | 3 | `test_ingest_while_live_keeps_published_hybrid_and_reports_progress`, `test_failed_backfill_keeps_live_hybrid`, `test_backfill_skips_archived_and_rollback_embeds_on_demand`: retrieval mode is `fts_only`, test expects `hybrid` | Embedding stub / retrieval-mode setup in the test environment, or a real regression in hybrid readiness. Needs a look (medium). |
| test_hybrid_retrieval.py | 3 | Names not captured (file not re-run); same family as above | Same area as embedding readiness (medium). |
| test_knowledge_hygiene.py | 2 | `test_bot_settings_validate_always_include_ids` (settings update accepts unknown `always_include_source_ids`, returns 200); `test_new_endpoints_are_tenant_scoped_and_staff_only` (expects 403/404, gets 204) | Validation and staff-only guard on the knowledge-hygiene endpoints. Could be a real authorization gap: review first (medium, security-relevant). |
| test_rag_evaluation.py | 2 | `test_two_mode_retrieval_eval_is_entirely_offline`, `test_owner_calibration_runner_writes_one_complete_report_without_live_http`: `scripts/rag_phase2_eval.py` raises "Requested retrieval mode degraded" | Eval script depends on hybrid retrieval being available (same root as embedding readiness, probably). |
| test_rag_stage0_baseline.py | 1 | `test_real_fts_pipeline_checkpoints_and_never_replays`: `retrieve() got an unexpected keyword argument 'preview'` | `scripts/rag_stage0_baseline.py` calls `retrieve()` with an argument it no longer accepts (small). |
| test_rag_gate.py | 1 | `test_provider_has_no_retries_and_only_one_fallback` | Provider retry/fallback behaviour vs test expectation. Not investigated. |
| test_chat_streaming.py | 1 | Name not captured (file takes about 5 minutes) | Streaming chat. Not investigated. |
| test_staff_members.py | 6 | `test_create_validation_is_safe_and_atomic[payload2..payload7]` | Staff member creation validation cases. Not investigated. |
| test_tenant_route_matrix.py | 2 | `test_exact_route_contract_and_operator_knowledge`: stale route count (expects 92, app has 91); `test_every_openapi_route_role_and_cross_tenant[staff]`: staff `POST .../sources/{source_id}/replace` returns 422 where the matrix expects another status | Update the expected count and the matrix entry, or fix the route. Small, but decide which side is right. |

Lint/format on `main` (not from channel work): ruff reports 33 errors in `tests/test_knowledge_hygiene.py` (22), `tests/test_revision_embedding_migration.py` (4), `tests/test_embedding_readiness.py` (3), `tests/test_embedding_foundation.py`, `tests/conftest.py`, `app/db/models/chat.py` (E501 line 473), `app/quotas/sentiment.py`; `ruff format --check` flags 3 app files; full `mypy` (with tests) has 16 errors, 11 in untouched files and 5 in `tests/test_channels.py` (the last five are in a channel test file and are a Phase 6 follow-up). `mypy app` is clean.

## B. Playwright (existing specs)

Full run on the branch: 154 passed, 14 failed. All 14 also fail on a clean `origin/main` build (main failed 11 of the 40 tests in the second comparison, plus 6 in the first): conversations.spec:69; group-a-operator.spec:26 and :94; overview.spec:135 and :219; group-c-polish.spec:129; install.spec:26; knowledge.spec:199; widget-domain.spec:156 and :230; widget-polling.spec:155 and :171; widget-streaming.spec:369; widget.spec:285. Main additionally failed knowledge.spec:45, widget.spec:227 and conversations.spec:12, which passed on the branch. Causes not investigated: widget chat waits time out, two operator tests look for pre-redesign UI, knowledge replace/always-include matches the API hygiene failures.

## Suggested handling
1. Quick test-only fixes: bot-names migration, stage0 baseline `preview`, route-matrix count.
2. Review for security first: knowledge-hygiene staff-only 204.
3. One investigation for the retrieval family (embedding readiness, hybrid retrieval, RAG evaluation): all report degraded or `fts_only` mode.
4. Staff member validation (6) and chat streaming (1), rag gate (1): separate small tickets.
5. Playwright: widget chat waits and the two operator tests that look for pre-redesign UI.
