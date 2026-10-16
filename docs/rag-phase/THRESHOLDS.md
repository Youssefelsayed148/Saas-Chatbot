# Model-specific relevance thresholds

Owner-approved 2026-10-16: accept a chunk when its cosine signal **OR** its
FTS `ts_rank_cd` signal meets the corresponding minimum. RRF is rank-only and
never used for relevance decisions.

| Embedding identity | Cosine floor | FTS minimum | Evidence/status |
|---|---:|---:|---|
| `ollama:bge-m3` | 0.50 | 0.01 | **bge-m3 (Ollama), provisional**, explicitly untuned; owner approved defaults; real semantic validation pending |
| `openai:text-embedding-3-large` (1024 dimensions) | — | 0.01 | **pending owner calibration**; vector signal fails closed until explicitly configured |
| Other configured identities | — | 0.01 | No inherited cosine floor; configure/calibrate each model explicitly |

Environment configuration: `RETRIEVAL_VECTOR_FLOORS` is a JSON object mapping
canonical `provider:model` identities to cosine floors. `RETRIEVAL_MIN_FTS_MATCH`
controls the keyword minimum. Unknown/invalid/nonfinite cosine floors cannot
accept vector-only evidence. Provider changes do not transfer tuned thresholds.

Rewrite switches: `CHAT_REWRITE_ENABLED` (global) and `CHAT_REWRITE_PLANS` (JSON
array of existing plan labels). All existing plan labels remain enabled by
default; context-dependent follow-ups alone invoke a rewrite. Self-contained
queries skip it. Retrieval-only evaluations disable preprocessing explicitly.

Synthetic vectors test mechanics only. They cannot validate multilingual
semantic performance or calibrate a real embedding model. Stage 6 will append
the measured comparison and owner calibration instructions.
