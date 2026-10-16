# Stage 2 — hybrid retrieval and isolation

2026-10-16. Implementation `8f163e9`, parent `39e3888`.
Chat requests: **0**; real embedding/OpenAI requests: **0**.

- Added parallel FTS/vector retrieval with separate SQLAlchemy sessions, RRF
  (rank constant 60), chunk provenance and independent cosine/FTS scores.
  Every vector query filters tenant, bot, published revision and active model
  inside SQL. Whole-document FTS expansion now explicitly carries bot scope too.
- HNSW iterative scans have a configurable bound (20,000 tuples by default).
  Underfill triggers an exact materialized, identically scoped SQL search;
  no Python filtering. An active backfill, missing index, provider/SQL failure,
  concurrent pointer change or operator kill switch degrades to logged FTS.
- This commit introduces the retrieval library. Production chat wiring waits for
  Stage 3's relevance gate, so ungated vector matches cannot generate answers.

## Evidence

**29 affected tests passed**: `test_hybrid_retrieval.py` 6;
`test_retrieval.py` 9; `test_rag_stage0_baseline.py` 14. Existing Starlette
deprecation warning only. Container mypy passed for **163 source files**;
affected Ruff and formatting checks passed (6 files).

The actual pgvector isolation test seeds identical vectors/near-identical text
across two tenants and a same-tenant decoy bot, plus unpublished revisions.
The target has **3** published chunks versus **300+** foreign decoys. With scan
budget **1**, all **3/3** eligible chunks return; **0** cross-tenant/bot/revision
hits. A different active model returns no hits. Parallelism and safe logged
degradation are tested independently.

Raw `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` evidence:
`STAGE-2-EXPLAIN.json`. ANN uses `ix_chunks_embedding_hnsw`; both plans contain
tenant/bot/revision/model filters and return 3 rows. ANN execution 0.216 ms;
exact repair 116.686 ms under deliberately forced planner settings. These are
tiny-fixture diagnostic timings, not representative performance measurements;
forced sort cost/JIT affects the exact path. Production planner settings are
unchanged.

Initial checks found test-only nullable UUID/implicit-export typing errors, an
Alembic-disabled logger, and an overly optimistic index-plan assertion on a tiny
fixture. Corrected annotations/log setup and forced the ANN path explicitly in
the test; all final checks passed. No isolation check returned foreign hits.

Files: `app/retrieval/hybrid.py`, `app/retrieval/service.py`, core config,
`tests/test_hybrid_retrieval.py`, these report/plan artifacts, Stage 1 hash and
`PROGRESS.md`.

UNVERIFIED: real embedding quality, real provider behavior, deployment-scale
plans/latency. Synthetic vectors prove mechanics/isolation only. No browser/UI
changes, full suites, dotenv reads, real calls, merge, push or deployment.

Stage 3's gate combination and uncalibrated provisional thresholds need the
owner's decision under the explicit ambiguity-stop rule. No Stage 3 code started.

Subsequent owner reply approved OR and provisional 0.50 / 0.01; Stage 3 resumed.
