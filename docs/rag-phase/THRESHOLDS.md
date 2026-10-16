# Model-specific relevance thresholds

2026-10-16 owner final-fixes request. A chunk passes cosine **OR** FTS;
RRF controls ranking only.

| Embedding identity | Cosine floor | FTS floor | Status |
|---|---:|---:|---|
| `openai:text-embedding-3-large`, 1024 dimensions (default) | 0.50 | 0.01 | **UNTUNED, pending owner calibration** |
| `ollama:bge-m3`, 1024 dimensions (optional) | 0.50 | 0.01 | Untuned provisional; unavailable here |
| Any identity without a configured row | disabled | 0.01 | FTS-only gate; never inherit another model's cosine floor |

FTS acceptance also requires `RETRIEVAL_MIN_MATCHED_TERMS` content terms
(default 1). `RETRIEVAL_MIN_FTS_MATCH` defaults to 0.01 and must be positive.
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
