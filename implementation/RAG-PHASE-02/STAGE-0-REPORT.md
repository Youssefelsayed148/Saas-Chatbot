# RAG Stage 0 checkpoint — 2026-10-16

Stage 0 is pending owner disposition of the partial live baseline. No Stage 1 work has started.

## Setup and owner-approved exceptions

- Started on `main`, HEAD `946f2cb16989379a4d0996db6434932e5feda18d`. `phase-1-complete` points to `fde670f83c0f5e67e0ffe597a519f0ddd8d6c62b`; ancestry check exited 0. Only documentation commit `946f2cb` was above the tag. The only initial untracked files were the supplied v2 plan/prompt.
- Created `feat/rag-phase-2`. First local commit: `0c70c5b`, containing only the two supplied documents. Corrected the prompt's reference to the actual filename, `RAG-PLAN-v2.md`.
- Both required process variables were initially **not set**, including in the elevated command environment. The owner subsequently authorized scoped `.env` loading and then updating the chain. Only the two required entries were loaded; only `CHAT_FREE_MODEL_CHAIN` was updated. No values were displayed or committed.
- The configured chain was comma-separated text with three entries. Pydantic Settings requires a JSON array; surrounding JSON whitespace is accepted, whitespace inside IDs is preserved, and bare comma/space lists are rejected. Synthetic checks verified this behavior.
- One public OpenRouter model-catalog request was made. Positions 1 and 3 had no listed, zero-priced `:free` variant. The owner explicitly authorized replacements: retained the valid entry, replaced the other two using the cached catalog, and saved a valid three-model JSON array. Each selected ID ends in `:free` and had zero prompt/completion prices in that catalog. Actual account billing is UNVERIFIED.
- The owner approved a raw-FTS baseline with LLM rewrite and translation disabled to enforce the request budget. Follow-up history remains in the cases. This measures raw FTS, not the complete existing translation/rewrite runtime.
- Conflict resolved by the latest instruction: three **affected-spec** Playwright runs here; no full Playwright/API suite before the final exit gate. The original Stage 0 wording about three suite runs was not followed as a full-suite instruction.
- The new plan calls hybrid retrieval ADR-008; the older decision register uses ADR-008 for deferred paid billing. The supplied plan takes precedence for this phase; the older register was not silently renumbered or otherwise rewritten.

## Keep-alive check

Set Uvicorn `--timeout-keep-alive 65` in the API Dockerfile, the explicit stack command, and the E2E launcher. The pinned Uvicorn default was verified as 5 seconds. Two local health requests on the same socket, separated by six seconds idle, both returned HTTP 200 without reconnecting.

Three scheduled runs of `widget.spec.ts`, `knowledge.spec.ts`, and `overview.spec.ts`, with retries disabled and a fresh disposable database per run:

| Run | Result | ECONNRESET | Failed-to-proxy / tracebacks |
|---|---|---:|---:|
| 1 | 10 passed, exit 0, 1.8m | 0 | 0 / 0 |
| 2 | 9 passed, 1 failed, exit 1, 2.2m | 0 | 0 / 0 |
| 3 | 10 passed, exit 0, 1.6m | 0 | 0 / 0 |

Run 2 failed `overview.spec.ts:127`, **workspace shell + measured overview with per-bot scoping and CSV**: expected `Messages: 2`, received `Messages: 1`. The helper accepted a restored AI bubble before the second POST completed, then navigated away. The trace shows message POST statuses 201 and -1; API logs show only the first completed POST. Added a wait for the new message POST's HTTP 201 before navigation. Run 3 passed. The failed trace and error context are preserved.

Retained the keep-alive change: the observed failure was a test synchronization race, corrected and verified in the third run. The original ECONNRESET cause remains UNVERIFIED because it was not reproduced. Docker stack startup/image rebuild and long-lived production behavior were not tested.

## Partial real-key baseline

Fixture: `stage-0-eval.jsonl`, 32 questions over the four fictional Demo Dental Clinic FAQ documents from `scripts/seed_demo.py`: 6 Arabic, 4 mixed-language, 10 unanswerable, 8 paraphrase, 4 follow-up. Arabic, mixed-language, and unanswerable cases precede the rest. Expected source keys were checked against the seed; actual document/chunk IDs are bound and stored with each attempted case.

The **single live run stopped at the first HTTP 429**, exit 2. No retry, rotation, wait, or additional provider request followed it. Nine questions completed; the tenth was checkpointed as quota-stopped; 22 were not attempted. Usage: **5 completion requests + 1 catalog request = 6 external requests**. Three generation calls produced usable answers; the quota-stopped question received HTTP 200 without a usable completion and its one allowed fallback received HTTP 429.

| Completed group | Completed | Hit@8 | Wrong refusals |
|---|---:|---:|---:|
| Arabic | 6 / 6 | 0 / 6 | 6 / 6 |
| Mixed-language | 3 / 4 | 3 / 3 | 0 / 3 |
| All completed answerable cases | 9 | 3 / 9 (33.3%) | 6 / 9 (66.7%) |

- Three returned citations were valid against retrieved evidence: **3/3**. Zero internal-error markers were found in the nine completed reply texts. These observations do not prove all widget/API error paths are safe.
- The three completed mixed-language answers correctly reported checkup price 50 demo credits, cleaning price 80 demo credits, and weekday hours 09:00–17:00. They were in English. Mixed-language response suitability needs further review.
- All six Arabic answerable questions wrongly refused because raw FTS could not match Arabic questions to the English-only seed. The Arabic canned refusal also includes the English phrase `our support team`.
- Unanswerable refusal correctness, paraphrase results, follow-up results, and full-set answer quality are **UNVERIFIED**: those cases were not reached. Do not extrapolate these partial rates to the whole set or compare them with a later full-runtime eval without accounting for disabled preprocessing.
- Current retrieval leaves `RetrievalResult.candidates` empty. The eval observes the existing ranked SQL function instead, without issuing extra retrieval queries or changing production retrieval behavior. The integration test checks a real FTS hit against the seeded expected chunk.

Raw results (answer, citations, requested model, latency, HTTP statuses, request count, expected IDs, retrieval evidence) are flushed and fsynced after every attempted question to `.test-storage/rag-stage-0/baseline/results.jsonl`. The start journal prevents replay after interruption. A future explicitly approved `--resume` skips every started question, including the quota-stopped one; it does not automatically retry that question.

## Checks, files, and limits

- Affected API file: `tests/test_rag_stage0_baseline.py` — final **13 passed**, 1 existing Starlette warning, exit 0. Mock HTTP verifies one generation request, one fallback maximum, immediate 402/429 stop, authorization stop, disabled preprocessing, durable/redacted checkpoints, disposable-target rejection, real FTS measurement, and no replay. No owner-key requests are made by these tests.
- New-file container Ruff and format checks passed. Container mypy passed for **156 source files** including the operator script. Web lint, typecheck, and changed-file Prettier checks passed. Exact commands and initial failures are recorded in `PROGRESS.md`.
- Nine existing Ruff findings remain untouched: E501 at `app/db/models/chat.py:428`, `app/db/models/knowledge.py:84`, `app/platform/router.py:259`, `app/platform/router.py:328`, `app/quotas/sentiment.py:121`, `app/quotas/service.py:194`; I001 at `app/knowledge/service.py:9`, `app/platform/router.py:10`, `tests/conftest.py:9`.
- Implementation files: `apps/api/Dockerfile`, `infra/compose.yaml`, `apps/web/tests/e2e-api-setup.ts`, `apps/web/tests/overview.spec.ts`, `apps/api/scripts/rag_stage0_baseline.py`, `apps/api/tests/test_rag_stage0_baseline.py`; evidence files: this report, `stage-0-eval.jsonl`, `PROGRESS.md`. The authorized local `.env` chain change is ignored by Git.
- Only the first plan-files commit exists so far. The single Stage 0 implementation commit is deferred while the owner decides whether to accept the partial baseline or keep Stage 0 pending.
- Stopped only `rag-stage0-checks` and `rag-stage0-postgres` after verification, preserving their data and the checkpoint artifacts. `git diff --check` passed after the report/progress updates.
- No new routes or client UI; no embedding/hybrid/gate implementation, full suites, push, merge, tag, deployment, Compose invocation, destructive database operation, or additional live eval run. Tests and eval use only disposable local databases. Artifacts remain ignored locally; no credentials are added to Git.
