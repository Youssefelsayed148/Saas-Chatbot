# PHASE 2 PROMPT v2: RAG implementation (hybrid retrieval)

Read `RAG-PLAN-v2.md` first. It is the source of truth (ADR-008, runtime cycle, exit criteria). If this prompt and the plan conflict, THIS PROMPT WINS (it includes later decisions); report the conflict.

## Hard rules
- Local commits only. NEVER push. Never read or print .env or keys. Do not use `docker compose`; plain `docker` with explicit settings only.
- Start from local main (Phase 1 merged, tag `phase-1-complete`). Create branch `feat/rag-phase-2`. One commit per stage, descriptive messages.
- Do not guess. Anything not verified in code or by a test run is marked UNVERIFIED.
- Stop at every STOP gate and send a SHORT report. Do not start the next stage without my go-ahead.
- New code must be lint-clean (ruff, mypy in container, web lint/typecheck). Do not fix the 9 pre-existing repo-wide Ruff findings in this phase; list them untouched.
- Tenant isolation is application-layer (no RLS). Every new query carries tenant_id and bot_id inside the SQL.

## Product rules (decided; do not reopen)
- Clients (admin/editor/viewer) see NO bot data or settings: no knowledge, documents, chunks, document status, retrieval/model/embedding settings, traces, costs, or citations. Clients keep only insights, inbox, contacts, team, audit, exports, change requests.
- Everything in this phase is platform-staff-only (403 for all client roles, UI hidden), including new routes, trace views, cost views, backfill controls and eval tooling. Existing citation redaction for clients and visitors must keep working; citations are stored and visible to staff only.
- Every new route must be classified in the OpenAPI role matrix test. The route count comparison must stay exact.
- Operator-owned: org/bot creation, knowledge upload/publish, persona, appearance, domains, tier, limits.

## TEST RULE (to save time)
- While working, run ONLY the test files and specs the change touches.
- Run the full API suite (file by file) and full Playwright suite ONCE, at the final exit gate after Stage 7. Never rerun full suites for reporting or after docs-only commits. Playwright earlier only if a stage changes UI or widget, and then only affected specs.

## Stage 0: Baseline and keep-alive check
1. ECONNRESET (time-boxed, about one hour): hypothesis is Uvicorn keep-alive (default 5s) racing the Next proxy's reused sockets. Raise `timeout_keep_alive` (e.g. 65s) in the API run command used by the Docker stack and the E2E harness. Run the Playwright suite 3 times only if the change touches the harness; otherwise run only the specs that previously hit it (widget, knowledge, overview). Report result; keep the change only if it does no harm.
2. Real-key FTS baseline: stub unset; CHAT_OPENROUTER_API_KEY and non-empty CHAT_FREE_MODEL_CHAIN come from the environment (never print them). If the key is absent, STOP and tell me.
3. Build a baseline eval set of at least 30 questions over the Demo Dental Clinic knowledge: paraphrases, follow-ups, Arabic, mixed-language, and 8+ unanswerable questions. Run it on current FTS-only retrieval. Record hit@k, refusal behaviour, answer quality notes, and any internals leaking in widget/API error text.
STOP 0: baseline numbers, failures, keep-alive result.

## Stage 1: Embedding foundation
1. Check whether OpenRouter serves embeddings (UNVERIFIED); default to OpenAI embeddings for all tiers if not. Pick ONE multilingual model, ONE dimension per deployment, set by env. Report the choice and cost per 1M tokens.
2. Alembic migration: pgvector `embedding vector(N)`, `embedding_model`, `embedding_dim` on chunks; per-bot `active_embedding_model`, `retrieval_mode` (hybrid default | fts_only kill switch), `generation_provider/model`; tier presets (Standard = paid low-cost OpenRouter model, not :free; Premium = OpenAI) with per-bot override.
3. HNSW index. Handle filtered-ANN truncation (iterative scan or equivalent) so tenant/bot-filtered queries return full k.
4. Embedding in the existing Postgres job queue. `reembed_backfill` job per bot: resumable, idempotent, progress state (total, done, failed, status), atomic flip of `active_embedding_model`; bot serves FTS-only until the flip. Backfill existing demo knowledge.
STOP 1: migration, kill-and-resume test of the backfill, embedding provider decision.

## Stage 2: Hybrid retrieval and isolation
1. FTS and vector in parallel, RRF merge, top-k chunks with doc id, title, locator, vector similarity, FTS match.
2. Tenant and bot filter inside the same SQL as the vector search; never post-filter.
3. Degradation: embedding call fails or backfill active -> FTS-only for that request, logged. `fts_only` forces FTS-only.
4. Isolation test: two tenants with near-identical content, one tiny; zero cross-tenant and cross-bot hits, including highly selective filters.
STOP 2: isolation results and EXPLAIN plans for the filtered vector query.

## Stage 3: Follow-up rewrite, relevance gate, refusal
1. Follow-up rewrite: standalone query from conversation history via a small LLM call; skipped for self-contained queries; switchable per plan.
2. Relevance gate on vector cosine similarity floor plus minimum FTS match. Never gate on RRF score. Thresholds in config.
3. Refusal path when nothing passes: no generation call, answer "I don't have that information", offer inbox handoff, log as an unanswered gap (feeds the existing unanswered report).
4. Safe error messages only; verify no internals leak.
STOP 3: gate behaviour on the Stage 0 set.

## Stage 4: Grounded generation, citations, traces
1. Prompt: answer only from supplied chunks, say so when they do not cover the question, reply in the user's language, cite chunk ids; small chunk count (config).
2. Validate every citation maps to a retrieved chunk; flag or drop answers without a valid citation. Leave a hook for an LLM-as-judge check (not built now).
3. Per-answer trace: chunk ids, scores, gate decision, retrieval mode, rewrite used, model, tokens, cost, channel. Staff-only trace view.
STOP 4: sample traces (answerable, unanswerable, follow-up).

## Stage 5: Parsing limits and ingestion
1. Text PDFs/docs parse directly. Scanned PDFs: OCR async, page-capped, metered per plan, only if an OCR path exists; otherwise report UNVERIFIED and defer.
2. Tables flattened row-wise with repeated headers; CSV/FAQ chunked per record.
3. Parse timeouts, page and size caps for all tiers, with process-tree kill on timeout (open item).
4. Per-document status (parsed, chunk count, warnings) visible to STAFF ONLY.
STOP 5: limits and kill-on-timeout test.

## Stage 6: Eval harness and threshold tuning
1. Eval format: question, expected doc/chunk ids or "unanswerable", language, type (paraphrase|follow-up|arabic|mixed|unanswerable).
2. Script runs the set across `fts_only` and `hybrid`; report hit@k, citation validity, refusal correctness, wrong-refusal rate.
3. Tune gate thresholds; record values with the embedding model they belong to.
STOP 6: comparison table and chosen thresholds.

## Stage 7: Cost tracking and limits
1. Log tokens and cost per event type (embed at ingest, embed at query, rewrite, generation) with bot id, model, channel.
2. Per-bot and per-plan limits (documents, chunks, storage, monthly messages, token budget, embedding/OCR budget) enforced through the existing 429 QUOTA_EXCEEDED ("contact us").
3. Per-bot, per-channel AI cost in the staff analytics view only.
STOP 7: report.

## FINAL EXIT GATE (once)
Run the full API suite file by file (list every file with its pass count) and one full unscoped Playwright run. Report totals and any ECONNRESET with spec name. Then show evidence for each exit criterion:
- Hybrid beats fts_only on the paraphrase and Arabic sets.
- Unanswerable questions refuse; citations valid; no internals in errors.
- Isolation test passes on the vector query.
- Thresholds documented per embedding model.
- All new routes classified staff-only in the matrix test; clients see nothing new.
Merge to local main only if all pass; tag `phase-2-complete`; safe cleanup (`git branch -d` only, never clean -fdx or reset --hard or push).

## Every report (keep it short)
Files changed, commit ids, affected-test results, what is UNVERIFIED, what you did not do.
