# Stage 1 — embedding foundation

2026-10-16. Parent/checkpoint `ba7ffa0`; this stage's implementation hash is
recorded in the final report. No chat requests or real OpenAI calls used.

## Changes

- Additive Alembic migration `0014_rag_embeddings`: nullable `vector(1024)`, model
  identity and dimension on chunks; HNSW cosine index; separate per-bot retrieval
  mode, active model pointer/readiness, tier and generation provider/model.
  No existing rows are updated or deleted by upgrade. Downgrade refuses to discard
  populated RAG settings/vectors/jobs. Only disposable databases were migrated.
- Pluggable Ollama, OpenAI and OpenRouter HTTP embedding adapters: fixed dimension,
  finite/nonzero vector validation, batch/index validation, timeouts, safe errors,
  no retries or implicit provider/model fallback. Runtime HTTPX dependency now
  ships the same pinned version already used by tests.
- Default identity `ollama:bge-m3`, 1024 dimensions. Ollama was unavailable from
  the API container; no install/model pull. Tests/E2E use an explicitly guarded
  deterministic, non-semantic embedder. No fake production fallback is enabled.
- Existing Postgres queue now handles `reembed_backfill`. Per-chunk commits,
  durable total/done/failed counters, lease renewal/fencing, consistent Bot→Job
  lock order, cancellation checks, atomic active-model/readiness flip. Partial or
  failed work retains FTS fallback readiness. Ingestion schedules embedding work;
  unchanged cloned chunks retain their tagged vectors.
- Three new staff-only routes: GET/PATCH `.../bots/{bot_id}/rag`, POST
  `.../bots/{bot_id}/rag/backfill`. Client roles get 403; foreign bot IDs get 404.
  Mutations are audited without configuration values. Minimal client navigation
  contracts remain unchanged and expose no new RAG fields.
- Standard preset selects OpenRouter free generation; Premium selects configurable
  OpenAI generation. Fields are persisted here; per-bot runtime selection follows
  in the generation stage. The latest free-tier instruction supersedes the plan's
  paid Standard preset for current execution.

OpenRouter embedding support is documented, not guessed:
[embedding endpoint](https://openrouter.ai/docs/api/api-reference/embeddings/create-embeddings).
OpenAI default: `text-embedding-3-large`, `dimensions=1024`, listed input price
**$0.13 / 1M tokens** at verification time
([API contract](https://platform.openai.com/docs/api-reference/embeddings/create),
[model/pricing](https://developers.openai.com/api/docs/models/text-embedding-3-large)).
No real-key embedding request was made to either service. OpenRouter embedding
model selection is explicit deployment configuration; its cost is not assumed.

## Verification

| Affected API file | Final pass count |
|---|---:|
| test_embedding_foundation.py | 11 |
| test_knowledge_pipeline.py | 9 |
| test_tenant_route_matrix.py | 6 |
| test_jobs.py | 8 |
| test_migrations.py | 1 |
| test_startup_guard.py | 5 |
| Total | 40 |

All exit 0, with the existing Starlette deprecation warning. The backfill test
kills an actual child worker after a committed partial checkpoint, checks that
the old pointer remains, expires/reclaims its lease, and completes all four Demo
Dental FAQ chunks. A separate test proves a stale worker cannot release a stolen
lease. Provider contract tests use mocked HTTP for all three adapters.

Initial foundation failure was an unflushed test setup change overwritten by a
fresh database read; flushed the setup and rechecked successfully. Initial
ingestion failures assumed a single job type; assertions now distinguish and
validate both ingestion and backfill jobs. No isolation test returned foreign hits.

- Exact route matrix: **80 declared = 80 actual**, all three additions staff-only.
- Affected Playwright widget/knowledge/overview: **10 passed**, exit 0, 1.7m;
  ECONNRESET **0**. Test worker and API explicitly enable test-only embedding stubs.
- Container Ruff on affected clean files and format check passed; mypy **161
  source files**, exit 0. Web lint/typecheck and changed-file Prettier passed.
- Broad Ruff inventory still has exactly the same **9** findings, not fixed.
  The existing knowledge-model long string remains long while its job-type check
  is extended; no unrelated lint cleanup occurred.

## Files / pending

Added migration, `app/embeddings/{providers,backfill,router}.py`, package init and
`test_embedding_foundation.py`. Updated core settings/permissions, bot/chunk/type
models, job dispatch, ingestion, app router registration, pinned runtime HTTPX,
affected tests/E2E setup, this report and PROGRESS.

UNVERIFIED: live embeddings on all backends, semantic quality, real development
demo backfill, deployment/extension privileges and production load. Filtered ANN
query behavior and EXPLAIN evidence belong to Stage 2, when the vector query is
introduced. No full suites, paid calls, dotenv reads, push, merge or deployment.
