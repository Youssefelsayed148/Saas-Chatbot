# Owner-only calibration and generation checks

Codex built and syntax-checked these entrypoints but **did not execute either**.
Provider/cache/budget helpers were tested with mocked HTTP only. Both scripts
ignore dotenv, accept only explicit loopback PostgreSQL databases ending `_test`,
and use the fictional demo corpus. Start a disposable pgvector database yourself;
these scripts never invoke Docker/Compose or deploy anything.

Run from the repository root using its installed virtual environment. Set
`CHAT_OPENAI_API_KEY` in the process environment for calibration, without putting
the key in commands or output. OpenRouter generation requires process variables
`CHAT_OPENROUTER_API_KEY` and `CHAT_FREE_MODEL_CHAIN` (JSON array of `:free` IDs).

```powershell
.venv/Scripts/python.exe scripts/rag_calibrate.py --database-url postgresql://postgres@127.0.0.1:55462/rag_owner_calibration_test --output .test-storage/rag-owner-calibration
```

This estimates conservative UTF-8-byte token/cost upper bounds before spending,
aborts above **2M tokens** or unsafe per-input lengths, then uses
`text-embedding-3-large`, `dimensions=1024`. It caches measured vectors/usage,
backfills via a scoped resumable job with atomic active-model flip, binds expected
document/chunk IDs and compares FTS/hybrid retrieval without chat calls. Cache
markers prevent automatic reruns after a crash. Threshold proposals are never
automatically applied. Inspect raw scores and choose/configure an OpenAI floor in
`RETRIEVAL_VECTOR_FLOORS` before assessing OpenAI gate refusal behavior.

Then, within your available OpenRouter quota:

```powershell
.venv/Scripts/python.exe scripts/rag_generation_check.py --database-url postgresql://postgres@127.0.0.1:55462/rag_owner_calibration_test --mode hybrid --embedding-cache .test-storage/rag-owner-calibration/embedding-cache.jsonl --baseline-results .test-storage/rag-stage-0/baseline/results.jsonl --output .test-storage/rag-owner-generation
```

The generation check skips the **9 completed historical baseline questions**.
It runs Arabic/mixed/unanswerable first, preserves follow-up history, disables
rewrite/translation, uses cached embeddings only and permits at most one
generation plus one non-quota fallback per question. The durable **40-request**
cap includes fallback attempts and survives process restarts. First quota/auth
failure stops immediately, saves partial raw answer/citations/model/latency/status,
and prevents automatic retry. No catalog lookup or model smoke tests.

`--resume` skips every previously started question, including interrupted ones;
it does not override a quota/auth stop. Do not choose a new output to evade quota.
For FTS-only checking use `--mode fts_only` and omit `--embedding-cache`.

Cached-query retrieval timings are not production embedding latency. Review answer
quality/language manually; citation mapping and refusal flags alone do not prove
groundedness. An LLM judge remains deferred.
