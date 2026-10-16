# Owner calibration and generation checks

Run from the repository root. Start the existing disposable loopback pgvector
PostgreSQL on port 55462 first. The scripts create/migrate only an explicitly
local database ending `_test`; they never start Docker or deploy anything.
Use process environment credentials only; dotenv is ignored and keys are never
printed. Set `CHAT_OPENAI_API_KEY` for calibration. Generation uses
`CHAT_OPENROUTER_API_KEY` and `CHAT_FREE_MODEL_CHAIN` (JSON array of `:free` IDs).

```powershell
.venv/Scripts/python.exe scripts/rag_calibrate.py --database-url postgresql://postgres@127.0.0.1:55462/rag_owner_calibration_v2_test --output .test-storage/rag-owner-calibration-v2
```

This prints the conservative UTF-8-byte token/cost estimate first, then aborts
above 2M tokens or an unsafe per-input bound before filesystem writes, database
connections or provider calls. The estimate uses the existing configured
USD 0.13/million accounting assumption, not a measured bill or price guarantee.
The exact planned 44-chunk corpus and all 76 raw questions are included. The
script validates every source label and rejects a stale/different database
corpus before spending. It embeds OpenAI `text-embedding-3-large` at 1024
dimensions, caches vectors and usage, backfills the scoped index, then runs
FTS-only and hybrid retrieval using cached queries without generation calls.

Paste back **`.test-storage/rag-owner-calibration-v2/calibration-results.json`**.
This single file contains the estimate, model, measured embedding usage,
FTS configs, raw rankings, hit@3, MRR, current gate metrics, all threshold
settings with leaks/refusals/wrong-evidence accepts, and recommended thresholds.
The helper cache/journals stay local. No recommendation is applied to the app.
Review the result before the second command; it explicitly uses the proposed
thresholds for this generation check only.

```powershell
.venv/Scripts/python.exe scripts/rag_generation_check.py --database-url postgresql://postgres@127.0.0.1:55462/rag_owner_calibration_v2_test --mode hybrid --embedding-cache .test-storage/rag-owner-calibration-v2/embedding-cache.jsonl --calibration-results .test-storage/rag-owner-calibration-v2/calibration-results.json --baseline-results .test-storage/rag-stage-0/baseline/results.jsonl --output .test-storage/rag-owner-generation-v2
```

Generation uses cached embeddings only and the expanded eval set. It skips the
9 completed historical baseline IDs, prioritizes Arabic/mixed/unanswerable,
preserves follow-up history, disables rewrite/translation, and reserves at most
40 requests including fallback attempts in a durable journal. It stops at the
first quota/auth error and preserves every raw result. The expanded corpus
means historical answers are skip evidence, not a comparable current-corpus
benchmark. Inspect answer language/groundedness manually.

Cache-start markers prevent automatic replay after a crash. `--resume` on the
generation command skips all started questions, including interrupted ones;
it never overrides a quota/auth stop. Do not use a fresh output to evade a cap.
The v2 outputs above are a distinct expanded-corpus evaluation, not a quota reset.
These commands have not been run against real providers by Codex.
