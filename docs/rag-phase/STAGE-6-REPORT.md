# Stage 6 — eval harness and model-specific calibration

2026-10-16. Parent `75ee690`; implementation hash follows next checkpoint.
Chat requests **0**; real embedding/OpenAI requests **0**.

- Added a two-mode retrieval-only eval with bound expected document/chunk IDs,
  explicit unanswerable/language/type labels, per-case checkpointed scores, hit@k,
  gate refusal/wrong-refusal metrics and clearly separate PENDING generation metrics.
- Built both requested owner scripts. Calibration estimates tokens/cost before
  spending, aborts above 2M tokens, uses OpenAI large/1024 and cached embeddings,
  and runs a scoped resumable backfill. Generation uses cached vectors, skips
  completed baseline cases, caps all requests/fallbacks at 40, stops on quota,
  and saves partial raw results. Neither script was executed. Commands and
  prerequisites: `OWNER-CHECKS.md`.
- Threshold proposals expose overlap rather than inventing a refusal/recall
  tradeoff. Approved 0.50 / 0.01 bge-m3 provisional values remain **untuned**;
  OpenAI calibration remains pending. No synthetic semantic-quality claims.

## Offline comparison (synthetic lexical vectors)

| Metric | FTS-only | Hybrid |
|---|---:|---:|
| Cases | 32 | 32 |
| Answerable candidate hit@8 | 9/22 | 22/22 |
| Paraphrase candidate hits | 3/8 | 8/8 |
| Arabic candidate hits | 0/6 | 6/6 |
| Arabic gate passes | 0/6 | 0/6 |
| Unanswerable gate refusals | 6/10 | 6/10 |
| Answerable wrong gate refusals | 12/22 | 12/22 |

All four demo chunks fit within k=8, so hybrid candidate coverage is not evidence
of better semantic retrieval. Actual multilingual quality and generation refusal
correctness remain PENDING. No real generation samples added (historical baseline
still 9 completed, 3 returned valid citations). Raw comparison/case evidence:
`STAGE-6-COMPARISON.json`, `STAGE-6-RETRIEVAL-RESULTS.jsonl`.

Verification: **21 unique affected tests passed** (7 eval/budget/cache, 14 baseline).
The 64-row comparison ran once; final budget checks explicitly excluded it.
HTTP contracts/cap/restart/quota behavior mocked. Mypy **171 source files** passed,
affected Ruff/format passed. Owner wrappers AST parsed, never executed. No web
changes, full suites, real calls, dotenv reads, merge, push, deploy or Compose.

Files: retrieval eval primitives, API eval runner, two root owner entrypoints,
eval tests, baseline integer-usage compatibility fix, report/score/threshold docs
and PROGRESS. Live semantic calibration, rewrite effect and generation quality
remain UNVERIFIED/PENDING; LLM judge deferred.
