# Stage 0 checkpoint

2026-10-16. Base/plan commit `0c70c5b`; implementation commit `ba7ffa0`.
Earlier live results and browser evidence are preserved in
`implementation/RAG-PHASE-02/STAGE-0-REPORT.md` and `PROGRESS.md`.

## Measurements

**FTS-only, translation off.** Current production code already has translation;
this budget-limited baseline disables it and rewrite. Generation history is now
explicitly retained by the operator runner, while retrieval uses the raw question.

All 32 questions measured at zero chat/embedding cost. Expected-source hit@8:

| Type | Questions | Expected-source hits | Empty evidence |
|---|---:|---:|---:|
| Arabic | 6 | 0 | 6 |
| Mixed-language | 4 | 4 | 0 |
| Unanswerable | 10 | N/A | 6 |
| Paraphrase | 8 | 3 | 4 |
| Follow-up | 4 | 2 | 2 |

Answerable hit@8: **9/22 (40.9%)**. Four unanswerable questions returned evidence;
no-generation measurements do not establish their final refusal correctness.

Historical live run: nine questions completed, three valid returned citations,
six Arabic wrong refusals, first HTTP 429 on question ten. **Five completion
requests and one catalog request** previously used. **Zero additional requests**
in this continuation. Remaining generation measurements are PENDING, not passed.
The saved live rows/journal were not overwritten or replayed.

## Keep-alive and checks

- Retained 65-second Uvicorn keep-alive in Dockerfile, stack command and E2E
  launcher. Same socket survives six seconds idle. Cause of the original reset
  is UNVERIFIED because the reset was not reproduced.
- Three earlier affected Playwright runs: 10 passed; 9 passed/1 failed; 10 passed.
  Zero ECONNRESET in every run. Fixed the overview helper's restored-message
  synchronization race before run 3. No redundant browser reruns here.
- `tests/test_rag_stage0_baseline.py`: **14 passed**, 1 existing warning, exit 0
  (3.72s). Mock HTTP covers budgets, quota stop, history, checkpoint/replay, DB
  guards and real FTS retrieval. Container Ruff/format passed; mypy **156 files**.
- The nine known unrelated Ruff findings remain untouched (historical report list).

## Files and limits

Changed API Dockerfile, stack YAML, E2E launcher and overview helper; added the
Stage 0 runner/test, 32-case fixture, reports, overrides and PROGRESS evidence.
Removed the runner's dotenv-loading option under the latest hard rule.
Process key and chain remain not set (chain length 0); no dotenv reads here.

Raw outputs: `.test-storage/rag-stage-0/baseline/results.jsonl` (historical live),
`journal.jsonl`, and `retrieval-results.jsonl` (all 32). Credential/model values
are never displayed. No full suites, OpenAI calls, new routes, client features,
push, merge, tag, deployment or destructive cleanup at this stage.
