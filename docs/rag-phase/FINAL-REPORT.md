# Phase 2 final exit report

2026-10-16. Branch `feat/rag-phase-2`. Implementation through Stage 7 is
committed. Both final suites completed once; evidence below was copied from
the saved checkpoints without rerunning tests.

Stages 0–7 implement hybrid retrieval, resumable embedding backfill, relevance
gating, follow-up rewrite, grounded generation, private traces, bounded parsing,
offline evaluation and staff-only metering/configurable limits. Unknown usage
and cost remain explicitly unknown; configured token caps reserve conservatively
before provider calls. Unset caps remain uncapped, as approved.

## Instruction conflicts and setup

- The whole-phase attachment supersedes approval pauses: STOP gates became
  checkpoints. The actual plan filename is `RAG-PLAN-v2.md`; the prompt reference
  was corrected. The RAG ADR-008 identifier collides with the older deferred
  billing ADR-008; no unrelated billing decision was changed.
- The latest request overrides paid Standard/OpenAI-default language: live chat
  uses only the free OpenRouter chain; development embeddings default to local
  Ollama bge-m3, 1024 dimensions. OpenAI and OpenRouter embedding backends are
  implemented and mock-tested. No real OpenAI calls were made.
- The owner approved minimal client bot navigation fields, cosine **OR** FTS
  acceptance, provisional thresholds, the export privacy correction, and optional
  caps whose unset values remain uncapped. See `EXECUTION-OVERRIDES.md`.
- Original main was `946f2cb`; `phase-1-complete` is an ancestor, with only docs
  above the tag at setup. The plan files were the first feature-branch commit.
- At continuation setup, process key: **not set**; chain: **not set**, length
  **0**. No dotenv/key reads in this continuation. Historical explicitly approved
  scoped dotenv loading/chain repair belongs to the earlier baseline run.
- `CHAT_FREE_MODEL_CHAIN` is a typed `list[str]` decoded as a **JSON array** by
  Pydantic Settings, not split on commas. JSON whitespace is accepted; model
  strings are not automatically trimmed. Free-only validation requires `:free`.

The embedding column is fixed at 1024 dimensions. Default identity is
`ollama:bge-m3`; local execution has no provider token charge (host compute is
not measured). The OpenAI large adapter's configured accounting rate is
USD 0.13 per million measured input tokens; this is the implementation rate,
not a measured bill. OpenRouter embedding cost remains unknown in this adapter.
All production-model behavior remains UNVERIFIED here.

## Commits and requests

| Work | Local commit | Real completion requests |
|---|---|---:|
| Plan files first | `0c70c5b` | 0 |
| Stage 0 | `ba7ffa0` | 5 historical; 0 additional |
| Stage 1 | `39e3888` | 0 |
| Stage 2 | `8f163e9` | 0 |
| Stage 3 | `555ffc7` | 0 |
| Stage 4 | `85dbe92` | 0 |
| Stage 5 | `75ee690` | 0 |
| Stage 6 | `fa1baff` | 0 |
| Stage 7 | `e1d1c23` | 0 |

Historical usage also includes **one catalog lookup**. Of five completion
requests, four returned HTTP 200 and the fifth returned the first HTTP 429.
Nine of 32 baseline questions completed (some required no generation). The
partial journal was preserved; no completed question was replayed. The other
23 generation-dependent cases remain PENDING. No live embedding requests were
made. Both owner scripts were built but never executed, including `--help`.

At final review, missing embedding usage was found to produce an invented zero
OpenAI cost. The final correction preserves null cost for missing/invalid usage
and adds five mocked cases in `test_embedding_foundation.py`. It was applied
before that file's first execution in the final gate. No full-suite restart.

## Exit evidence

| Criterion | Status | Evidence and limitation |
|---|---|---|
| Hybrid beats FTS on paraphrase and Arabic | **PENDING; not established** | Raw expected-source hit@8: FTS 9/22, synthetic hybrid 22/22. All four demo chunks fit k=8, so this is coverage, not semantic improvement. Paraphrase candidate hits 3/8 vs 8/8; Arabic 0/6 vs 6/6, but accepted Arabic evidence remains 0/6 in both modes. Real multilingual validation is pending. |
| Unanswerable refusal, valid citations, safe errors | **PARTIAL** | Both raw gates refuse 6/10 unanswerable cases; four keyword matches pass the gate. Both wrongly refuse 12/22 answerable cases. Historical live sample: six Arabic wrong refusals, three mixed answers with valid citations, no internals observed in nine completed rows. Mocked citation/error contracts pass; full live groundedness/language/refusal quality is pending. |
| Vector isolation | **PASS** | Same-SQL tenant/bot/revision/model filters, tiny tenant with 300+ foreign decoys, full eligible k and zero foreign hits. Iterative HNSW plus exact scoped repair; EXPLAIN in `STAGE-2-EXPLAIN.json`. |
| Model-specific thresholds | **PASS documentation/configuration; calibration PENDING** | `bge-m3 (Ollama), provisional`: cosine 0.50 OR FTS 0.01, explicitly untuned. OpenAI vector floor absent pending owner calibration; no automatic transfer across models. See `THRESHOLDS.md`. |
| New routes staff-only; clients see no new operator data | **PASS** | Exact matrix 82=82, client roles denied, visitors citation-redacted, staff panels hidden from clients. Stage 7 fixes the export trace leak after an owner-authorized stop; regression covers client redaction and staff retention. Full browser gate passed. |

No meaningful semantic improvement has been demonstrated, so the completion
gate remains open. After reviewing this limitation, the owner explicitly
approved the local merge on 2026-10-16 ("merge approved do it"), overriding the
earlier instruction to leave the branch unmerged. Calibration and real-call
criteria remain PENDING. Do not create `phase-2-complete` until they pass.

## Full verification, run once

API: **353 passed across all 44 files**, no failures, errors, skips or deselections. Every file exited 0. The single file-by-file run used separate disposable pgvector databases and no live providers. Exact commands, exit codes, counts and timings: `FINAL-TEST-RESULTS.json`. Raw logs remain in `.test-storage/rag-phase2-final/`.

| API test file | Passed |
|---|---:|
| `tests/eval/test_eval.py` | 2 |
| `tests/test_analytics.py` | 6 |
| `tests/test_auth.py` | 15 |
| `tests/test_bot_status.py` | 5 |
| `tests/test_bots.py` | 4 |
| `tests/test_change_requests.py` | 1 |
| `tests/test_chat.py` | 16 |
| `tests/test_contacts.py` | 1 |
| `tests/test_conversations.py` | 13 |
| `tests/test_conversations_view.py` | 5 |
| `tests/test_cross_script.py` | 3 |
| `tests/test_database_guard.py` | 5 |
| `tests/test_embedding_foundation.py` | 16 |
| `tests/test_followups_analytics.py` | 2 |
| `tests/test_handoff.py` | 5 |
| `tests/test_health.py` | 6 |
| `tests/test_hybrid_retrieval.py` | 6 |
| `tests/test_inbox_list.py` | 5 |
| `tests/test_invitations.py` | 6 |
| `tests/test_jobs.py` | 8 |
| `tests/test_knowledge_parsers.py` | 29 |
| `tests/test_knowledge_pipeline.py` | 9 |
| `tests/test_knowledge_uploads.py` | 19 |
| `tests/test_members.py` | 8 |
| `tests/test_migrations.py` | 1 |
| `tests/test_models_constraints.py` | 13 |
| `tests/test_platform.py` | 9 |
| `tests/test_platform_ops.py` | 4 |
| `tests/test_quotas.py` | 10 |
| `tests/test_rag_evaluation.py` | 7 |
| `tests/test_rag_gate.py` | 14 |
| `tests/test_rag_limits.py` | 8 |
| `tests/test_rag_stage0_baseline.py` | 14 |
| `tests/test_rag_traces.py` | 3 |
| `tests/test_retrieval.py` | 9 |
| `tests/test_seed_demo.py` | 21 |
| `tests/test_self_service_signup.py` | 4 |
| `tests/test_startup_guard.py` | 5 |
| `tests/test_tenant_data.py` | 2 |
| `tests/test_tenant_route_matrix.py` | 6 |
| `tests/test_tenants.py` | 6 |
| `tests/test_widget_appearance.py` | 3 |
| `tests/test_widget_leads.py` | 5 |
| `tests/test_widget_public.py` | 14 |

Playwright: **40 passed (3.5m), exit 0**, one full unscoped run. Log scan:
**0 ECONNRESET, 0 Failed to proxy, 0 Python tracebacks**; affected spec: none.
The 65-second keep-alive is retained. The original socket reset's root cause
remains UNVERIFIED. Stage 0's three historical affected runs were 10 passed;
9 passed/1 synchronization failure, corrected; 10 passed, all with zero resets.

Full browser command, from `apps/web`:

```powershell
$env:ENVIRONMENT='test'
$env:DATABASE_URL='postgresql://postgres@127.0.0.1:55462/rag_final_browser_test'
$env:E2E_API_PORT='18162'
$env:API_PROXY_TARGET='http://127.0.0.1:18162'
$env:STORAGE_ROOT='D:/Projects/Work Projects/The Osiris Labs/SAAS-chats-ai/.test-storage/rag-phase2-final/browser-storage'
npm.cmd test -- --reporter=line 2>&1 | Tee-Object -FilePath '../../.test-storage/rag-phase2-final/playwright-full.log'
```

Final corrected mypy passed **176 source files**. Web lint and typecheck passed
at Stage 7; final correction touches only Python. Affected Python Ruff/format
checks passed. Broad Ruff still reports exactly the nine pre-existing findings,
left untouched: `chat.py:428 E501`; `knowledge.py:87 E501`;
`knowledge/service.py:9 I001`; `platform/router.py:10 I001, :259/:328 E501`;
`quotas/sentiment.py:121 E501`; `quotas/service.py:194 E501`;
`tests/conftest.py:9 I001`. Broad Ruff is not claimed clean.

Stage-specific affected tests, initial failures and corrections, exact commands,
changed-file groups and checkpoints are recorded in `STAGE-0-REPORT.md` through
`STAGE-7-REPORT.md` and `PROGRESS.md`.

## Owner checks, not executed by Codex

Use process environment keys only; do not print values. Start the disposable
loopback pgvector database first. From the repository root:

```powershell
.venv/Scripts/python.exe scripts/rag_calibrate.py --database-url postgresql://postgres@127.0.0.1:55462/rag_owner_calibration_test --output .test-storage/rag-owner-calibration
```

This uses OpenAI `text-embedding-3-large`, dimensions=1024, prints a conservative
token/cost bound before I/O, aborts above 2M tokens and caches vectors. Review
proposed thresholds and explicitly configure the OpenAI model floor first.
Then, within available free OpenRouter quota:

```powershell
.venv/Scripts/python.exe scripts/rag_generation_check.py --database-url postgresql://postgres@127.0.0.1:55462/rag_owner_calibration_test --mode hybrid --embedding-cache .test-storage/rag-owner-calibration/embedding-cache.jsonl --baseline-results .test-storage/rag-stage-0/baseline/results.jsonl --output .test-storage/rag-owner-generation
```

Durable cap: 40 requests including fallback attempts. It skips historical
completed questions, prioritizes Arabic/mixed/unanswerable, writes each raw result,
and stops at the first quota/auth error. Do not create new outputs to evade quota.
See `OWNER-CHECKS.md` for prerequisites and crash/resume behavior.

## Remaining limitations and scope

UNVERIFIED: actual Ollama connectivity/semantics (unavailable from API container),
real OpenAI/OpenRouter embedding behavior, real rewrite/generation language and
groundedness, provider usage accuracy, real-score threshold calibration,
production vector/ledger load, production extension privileges, Windows parser
descendant termination, and PDF visual-table fidelity. POSIX descendant kill,
worker kill/resume, stale-owner fencing and additive migrations were tested.
Synthetic vectors are test-only, guarded against production startup.

OCR is deferred because no OCR path exists; scanned PDFs fail safely. OCR caps
are ready for a future implementation. LLM judge, channel integrations, RLS,
restore drill and independent security review remain deferred/outside this work.
Per-channel AI accounting was implemented as requested; channel connections were
not implemented. Unknown usage retains conservative reservations and can reject
early; no currency-spend ceiling was invented.

No push, deployment, Compose execution, production database mutation, destructive
cleanup or completion tag. The owner subsequently authorized local merge and
safe deletion of the merged feature branch. All database work used local
disposable tests.

Changed-file inventory and all exact final API commands are in `FINAL-TEST-RESULTS.json`. No further implementation changes followed the covered accounting correction. Final report/evidence changes did not trigger suite reruns.
