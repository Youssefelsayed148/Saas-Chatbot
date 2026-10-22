# Model-specific relevance thresholds

2026-10-16 owner final-fixes request. A chunk passes cosine **OR** FTS;
RRF controls ranking only.

| Embedding identity | Cosine floor | FTS floor | Status |
|---|---:|---:|---|
| `openai:text-embedding-3-large`, 1024 dimensions (default) | 0.50 | 0.01 | **UNTUNED, pending owner calibration** |
| `ollama:bge-m3`, 1024 dimensions (optional) | 0.50 | 0.01 | Untuned provisional; unavailable here |
| Any identity without a configured row | disabled | 0.01 | FTS-only gate; never inherit another model's cosine floor |

FTS acceptance also requires `RETRIEVAL_MIN_MATCHED_TERMS` content terms
(code default **2**; an earlier revision of this file said 1, which no longer matched
the code — corrected 2026-10-22, value unchanged and still untuned). `RETRIEVAL_MIN_FTS_MATCH` defaults to 0.01 and must be positive.
Unknown/invalid/nonfinite cosine floors disable vector acceptance. Zero/NaN FTS
scores and missing term matches cannot pass. `RETRIEVAL_VECTOR_FLOORS` is a JSON
object of canonical `provider:model` identities; supplying it replaces the map.

The matched-term rule counts distinct PostgreSQL term queries against the
chunk's stored index. English stemming uses `english` / `fts_en`; Arabic uses
`simple` / normalized `fts_simple`, including the existing article/prefix
variants. Arabic variants for one query term count as one group. Stop words
are removed by the existing query builder. Each chunk receives its own score;
document expansion does not copy a different chunk's score.

Owner calibration evaluates the expanded 44-chunk corpus and 76 cases. It
reports answerable-only raw hit@3 and MRR (over all top-8 candidates), alongside
current-gate metrics. Threshold sweeps operate on the actual evidence list:
cosine disabled/0.40/0.50/0.60/0.70 for hybrid, FTS
0.005/0.01/0.05/0.10/0.20, minimum matched terms 1/2/3 in both modes.
Each setting reports unanswerable gate leaks, wrong refusals and wrong-evidence
accepts. Recommendations minimize leaks, then wrong refusals, then wrong-evidence
accepts, with deterministic ties. They require owner review and are never applied
to runtime configuration automatically.

Synthetic vectors verify mechanics only. Historical four-chunk hit@8 results
cannot establish semantic improvement. Real-model multilingual performance and
calibrated thresholds remain pending. See OWNER-CHECKS.md.

## Calibration tooling (Batch B, 2026-10-22) — no values chosen

These knobs and tools exist so the owner can pick values from evidence. All
defaults reproduce the previous behaviour (proved by a grid test against the old
gate in `apps/api/tests/eval/offline/test_gate_trace.py`).

| Setting (environment variable) | Default | Effect |
|---|---|---|
| `RETRIEVAL_VECTOR_FLOORS` | 0.50 per model | cosine floor (existing) |
| `RETRIEVAL_MIN_MATCHED_TERMS` | 2 | distinct content terms a chunk must match (existing) |
| `RETRIEVAL_MIN_FTS_MATCH` | 0.01 | minimum `ts_rank_cd` (existing) |
| `RETRIEVAL_GATE_IGNORE_TERMS` (JSON list) | `[]` | store-name and filler words left out of the matched/query term counts; the ranking query is unchanged |
| `RETRIEVAL_TOP_RESULT_COSINE_FLOOR` | unset (rule off) | the best-cosine chunk passes at this lower floor... |
| `RETRIEVAL_TOP_RESULT_MARGIN` | 0.0 | ...when it also leads the runner-up by at least this margin |

- Frozen corpus: `apps/api/tests/eval/corpus/` (10 PDFs, SHA-256 list). Cases:
  `apps/api/tests/eval/nile_eval.jsonl` (41, expected file and page per case).
- Trace: each candidate chunk in the staff trace lists query terms, matched terms,
  cosine, FTS score and the gate verdict with the rule that decided it.
- Eval runner (`tests/eval/test_nile_eval.py`): fts_only and hybrid, dated files in
  `tests/eval/results/`. Hybrid on the test embedder proves mechanics only; the
  real-embedding comparison runs on the owner's stack.
- Gate comparison (`tests/eval/test_gate_compare.py`): retrieval only, per case and
  per candidate setting, whether the expected page passed the gate or an abstain
  case leaked. Candidate file format is in `tests/eval/gate_compare.py`.
- Final values, the wrong-refusal ceiling and the ADR note stay pending owner review.
