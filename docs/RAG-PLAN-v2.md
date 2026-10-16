# RAG Plan v2 and ADR-008: Hybrid Retrieval (Phase 2)

Status: approved. Supersedes RAG-PLAN.md. Repo is local-only commits, never push. Never read or print .env or keys.
Items marked UNVERIFIED must be checked before implementation.
Baseline: Phase 1 merged on local main (tag `phase-1-complete`). Client roles are admin/editor/viewer; platform staff (the operator) alone controls bots and everything below.

## ADR-008: Decisions

1. Every bot runs hybrid retrieval by default: Postgres FTS plus pgvector, merged with rank fusion (RRF). Every bot handles all supported data types.
2. Three separate per-bot settings: `retrieval_mode` (`hybrid` default, `fts_only` operator kill switch), `generation_provider/model`, and one deployment-wide embedding model and dimension.
3. Tiers are presets, not capabilities. Standard = hybrid + paid low-cost OpenRouter model (not :free). Premium = hybrid + OpenAI generation. Differences are model quality, limits and optional extras (rewrite, post-check).
4. Embedding model must be multilingual (Arabic + English). UNVERIFIED: whether OpenRouter serves embeddings; otherwise OpenAI embeddings for all tiers.
5. Each chunk stores `embedding_model` and `embedding_dim`. Queries only match chunks of the bot's active embedding model.
6. Changing embedding model is a `reembed_backfill` job (resumable, idempotent, progress state). The bot serves FTS-only or the old index until an atomic `active_embedding_model` pointer flips.
7. Tenant and bot filter live inside the same SQL statement as the vector search, never post-filtered. With ANN indexes use iterative scan or partitioning so filtered results are not silently truncated.
8. The relevance gate uses vector cosine similarity floor plus a minimum FTS match, never the RRF score (rank-only). Threshold is tuned per embedding model with the eval set.
9. Degradation paths: embedding call fails -> FTS-only for that request, logged. Backfill running -> FTS-only. Operator can force `fts_only`.
10. Limits are metered per bot and per plan, enforced through the existing 429 QUOTA_EXCEEDED ("contact us").
11. Visibility: clients see no bot data or settings. Knowledge, documents, chunks, document status, retrieval/model/embedding settings, traces, costs and citations are staff-only. Client and visitor responses stay citation-redacted. Every new route is classified staff-only in the OpenAPI role matrix test.

## Who does what

- Operator (platform staff): creates org and bot; sets tier and limits; uploads, ingests and publishes knowledge; sets persona, tone, language, handoff rules, appearance and domains; installs or sends the widget snippet; tests in the playground; enables the bot; deletes orgs (soft delete, 30-day grace, typed org name).
- Client admin: team and roles, audit, exports, contacts administration, inbox and messaging, insights, "request a change".
- Client editor: inbox and messaging, follow-ups, contact create/edit, insights.
- Client viewer: read-only insights, inbox and contacts.

## Bot lifecycle

1. Create (operator): org and bot with hybrid retrieval, tier preset and plan limits.
2. Configure (operator): persona, tone, language, handoff rules, appearance, allowed domains. Appearance saves as draft, then publish.
3. Ingest (operator): files parsed, chunked and embedded as background jobs. Per-document status (parsed, chunk count, warnings) is visible to the operator only. OCR is async, page-capped, metered.
4. Test (operator): playground with trace view (chunks, scores, gate decision). Operator installs the snippet on the client site and verifies on the real domain before enabling.
5. Go live: widget on the client site. Later channels (app, Meta) attach to the same bot and knowledge.

## Runtime answer cycle

1. Rewrite follow-ups into standalone queries using conversation history (small LLM call, per-plan option, skipped for self-contained queries).
2. Hybrid retrieval: FTS and vector in parallel, RRF merge, tenant/bot filter in SQL.
3. Relevance gate (decision 8).
4. Refusal path if nothing passes: "I don't have that information", offer inbox handoff, log the question as an unanswered gap. No generation call.
5. Grounded generation from a small chunk set, citing chunk ids; citations validated against retrieved chunks. Citations are stored for staff and not shown to clients or visitors.
6. Post-check (later, hook only): LLM-as-judge groundedness check, Premium or sampled.
7. Store a trace per answer: chunk ids, scores, gate decision, mode, rewrite used, model, tokens, cost, channel.

## Expected behaviour

- Answers only from the client's knowledge, in the user's language.
- Refuses cleanly instead of guessing; hands off to a human on request or gate failure.
- Widget errors show a safe message only, no internals.
- Over plan limit: 429 with "contact us".
- Embedding failure or backfill: degrades to FTS-only per request, logged.

## Client improvement loop

Clients see unanswered questions and top questions in insights. To improve the bot they send a "request a change" (type: knowledge, with documents attached). The operator ingests and publishes. Clients never touch knowledge directly.

## Operator controls

- Tier preset and per-bot limits: documents, storage, monthly messages, token budget, embedding/OCR budget.
- `retrieval_mode` override, re-embed backfill with progress, trace view, per-bot per-channel AI cost analytics. All staff-only.

## Ingestion and parsing

- Text PDFs and docs: parse directly. Scanned PDFs: OCR, async, page-capped, metered (only if an OCR path exists; otherwise defer).
- Tables: flatten row-wise with headers repeated per row. CSV/FAQ: chunk per record.
- All tiers: parse timeouts, page and size caps, process-tree kill on timeout.

## Cost tracking

Log tokens and cost per event type (embed at ingest, embed at query, rewrite, generation) with bot id, model, channel. Feeds staff AI cost analytics and Standard/Premium pricing.

## Test cadence

During a stage run only the files and specs the change touches. Run the full API suite (file by file) and the full Playwright suite once, at the final exit gate. No full reruns for reporting or after docs-only commits.

## Rollout order

0. Keep-alive (ECONNRESET) time-boxed check and real-key FTS baseline with eval set.
1. Embedding schema, backfill job, ingestion.
2. Hybrid retrieval plus cross-tenant isolation test (two tenants with near-identical content, one tiny; zero cross-tenant hits).
3. Follow-up rewrite, relevance gate, refusal path.
4. Grounded generation, citation validation, traces.
5. Parsing limits and staff-only ingestion status.
6. Eval harness: paraphrase, Arabic, mixed-language, follow-up and unanswerable questions across fts_only vs hybrid; hit@k, citation validity, refusal correctness, wrong-refusal rate; tune thresholds.
7. Cost tracking and limits.

## Exit criteria

- Hybrid beats fts_only on the paraphrase and Arabic sets.
- Unanswerable questions refuse; citations valid; no internals in errors.
- Isolation test passes on the vector query.
- Thresholds documented per embedding model; re-tune on model change.
- All new routes classified staff-only in the matrix test; clients see nothing new.

## Deferred and open

- Deferred: channel connections and per-channel analytics filter (Phase 3); LLM-as-judge post-check (hook only); staff cannot reply or take over inbox conversations without membership; Postgres RLS as a second isolation layer (security review).
- Open before dogfood: ADR-007 hosting, restore drill, independent security review, AI cost analytics, backfill NULL widget_locator rows.
