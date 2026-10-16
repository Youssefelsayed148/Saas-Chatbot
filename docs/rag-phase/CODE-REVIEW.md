# RAG Phase 2 code review

Reviewer scope: `git diff phase-1-complete..<tip>` against `RAG-PLAN-v2.md` (ADR-008, renamed ADR-019 in the repo) and `RAG-PHASE-PROMPT-v2.md`.

**Tip reviewed: `main` @ `fc3fdcd`.** `fix/rag-phase-2-final` does not exist. Review branch `review/rag-phase-2` was created from `fc3fdcd` (it already existed in a linked worktree at that commit; it was reused, not recreated).

Static review only until the final section. The checkout at the repo root has 25 uncommitted modified files plus one untracked file (`git status` at session start: retrieval, config, tests, docs, scripts). Those were **not reviewed**; this review covers committed content only (UNVERIFIED for the dirty tree).

Real embeddings and real generation were not run. Criteria needing them are PENDING.

## Findings

Severity: blocker = must be fixed before `phase-2-complete` / dogfood; high = wrong behaviour or unmet requirement in a normal path; medium = defect with a workaround or limited blast radius; low = hygiene.

| ID | Sev | Category | File:line | Problem | Suggested fix |
|---|---|---|---|---|---|
| F-01 | blocker | product bug | `quotas/rag.py:248-256`, `quotas/ai.py:86-88,101-110,140-148`, `chat/conversations.py:308-312,355-357` | Reservations are never released. A provider call that fails (outage, 4xx/5xx, quota stop) settles with `tokens=None`, which sets `status=usage_unreported` and `accounted_tokens=reserved_tokens` (the full conservative byte bound). Every failed query-embedding, rewrite, translation or generation call therefore consumes budget. Separately, the `message` reservation (`conversations.py:308`) is settled only on success (`:355`). If `chat_answer` raises (a 429 from the token reserve, any uncaught `ApiError`), the reservation stays `reserved` and counts toward `monthly_messages` (`rag.py:71-83`). Under a provider outage or an exhausted token cap, a capped bot burns its message/embedding/token cap and returns 429 "contact us" for the rest of the month. Violates "reservations released on failure". `test_rag_limits.py:104` asserts the keep-budget behaviour for unknown usage but nothing covers definite failure. | Add a `released` status (accounted 0) for failures where no provider response was produced (connect error, non-2xx before output, `EmbeddingError`). Keep the conservative hold only for ambiguous outcomes (timeout after send, missing usage on a 200). Wrap the message reservation in try/finally. Add tests for outage, aborted turn and cap-exhaustion loops. |
| F-02 | blocker | spec error / product bug | `core/config.py:88`, `embeddings/providers.py:51-56`, `core/config.py:121-134` | Default embedding identity is `ollama:bge-m3`, with base URL `host.docker.internal:11434` (`config.py:91`). The review brief and plan require `openai:text-embedding-3-large` at 1024 as the default. The owner override (`EXECUTION-OVERRIDES.md`) chose Ollama as the *development* default, but nothing restricts it to development: `validate_startup_settings` only blocks the test stub. A production deploy that omits `EMBEDDING_PROVIDER` silently selects Ollama, every query embedding fails, every request degrades to FTS-only (INFO log only, `hybrid.py:222-227`), and the backfill never completes (`backfill.py:155-158`). Nothing alerts staff. Ollama is therefore not "optional only". | Require `EMBEDDING_PROVIDER` explicitly outside `environment in {development,test}` (startup error otherwise), or default to `openai`. Resolve the brief-vs-override conflict in DECISIONS.md. Surface backfill failure to staff (see F-13). |
| F-03 | high | product bug | `retrieval/hybrid.py:250-253` | Hybrid mode discards the keyword pass's evidence assembly. `fuse()` is fed `result.candidates` (one best chunk per document), and `result.evidence` is overwritten with `ranked[:final_k]`. The `always_include_document_ids` reserved slots, the best-document-whole rule and the small-document-whole rule (`service.py:275-327`) are lost in hybrid mode, which is the default. Bots configured with always-include documents (e.g. opening hours, policies) silently stop receiving them. No test covers hybrid plus always-include. | Merge the keyword evidence list and the vector hits before the gate (reserved docs first), or apply the same expansion rules to the fused ranking. Add a hybrid always-include test. |
| F-04 | high | product bug / spec | `retrieval/gate.py:32-35`, `core/config.py:102`, `retrieval/query.py:196-215` | Keyword leg of the OR gate is `ts_rank_cd >= 0.01` over a tsquery whose content terms are OR-joined. An unnormalised `ts_rank_cd` for one matching lexeme is well above 0.01 (UNVERIFIED numerically here; no DB run), so the leg reduces to "any content word matched". The project's own measurement agrees: 4 of 10 unanswerable cases pass the gate (`THRESHOLDS.md`, `FINAL-REPORT.md` exit table). The OR "guards" cover only non-finite/out-of-range floors, not weak keyword evidence. The vector leg for `openai:text-embedding-3-large` is unconfigured, so with the plan's default model the gate is keyword-only. | Require a calibrated FTS floor (or ≥2 distinct matched terms / coverage ratio) and set it from the real-embedding eval. Until calibrated, document that refusal depends on the generation `can_answer=false` path. |
| F-05 | medium | product bug | `retrieval/service.py:328-330` | Every chunk of the expanded evidence inherits its document's best-chunk `ts_rank_cd`. In FTS-only mode (kill switch, backfill, embedding failure) a chunk that does not match the query passes the gate because a sibling chunk matched, and traces show an `fts_match` the chunk never earned. | Score per chunk (store each chunk's own rank) and gate on that; keep the document score separately. |
| F-06 | medium | product bug | `retrieval/hybrid.py:219-228`, `chat/service.py:130,158` | Degradation is incomplete. The vector worker catches only `EmbeddingError`/`SQLAlchemyError`. A `QUOTA_EXCEEDED` `ApiError` from `metered_embed` (embedding-token cap) propagates out of `future.result()` and fails the whole turn with 429, rather than the plan's "FTS-only for that request, logged" (ADR #9). Likewise `condense`/`translate_query` catch only `ProviderError`, so a token-cap 429 during rewrite aborts the turn. | Decide per cap: embedding-budget exhaustion degrades to FTS-only with a logged reason; rewrite/translation budget exhaustion skips the optional step. Add tests. |
| F-07 | medium | spec error | `embeddings/router.py:117-122`, `chat/models.py:24-32`, `quotas/ai.py:21` | ADR #3 and Stage 1.2 define Standard as a *paid low-cost OpenRouter* model, "not :free". `PATCH .../rag` rejects any non-`:free` OpenRouter model with 422, and the OpenRouter branch hard-codes `free_only=True`. The owner override limits *live work* to free models; it does not forbid configuring a paid model. Cost labelling also assumes `free_only` means OpenRouter (`ai.py:21`) and `:free` means zero cost (`ai.py:90-93`). | Allow paid OpenRouter ids (flag the free restriction as an eval-script concern only), derive the label from the configured provider, and treat only explicitly priced/free models as zero cost. |
| F-08 | medium | product bug | `chat/prompts.py:58-61` (vs `:43-46`) | The refusal copy was changed to offer inbox handoff in English only. The Arabic `cannot_confirm` text still says it cannot confirm and points to support, with no handoff offer. Refusal requirement ("I don't have that information", offer handoff) is met for one of two supported languages. | Update the Arabic string and add a test per language. |
| F-09 | medium | product bug | `retrieval/hybrid.py:202` | `embed_query` events are always logged with `channel="website"`, including playground traffic and any future channel. Per-channel cost analytics (Stage 7.3) are wrong for query embeddings. | Pass the real conversation channel into `retrieve_hybrid`. |
| F-10 | medium | product bug | `quotas/rag.py:279-306`, `embeddings/providers.py:112-113`, `retrieval/hybrid.py:255`, `chat/service.py:293` | Unknown stays null in the ledger but is flattened to zero elsewhere. `cost_summary` returns `cost_usd:"0"` and `measured_tokens:0` for groups whose events are all unreported (the count is exposed only as `unmeasured_events`); API consumers can misread it as zero cost. `EmbeddingBatch.tokens` is `0` when the provider reports none, and that `0` is written to the trace as `embedding_tokens` (`hybrid.py:255`). The summary also loads every month row into Python with no limit. | Return `null` for a group total when every event is unreported; carry `tokens: int | None`; aggregate in SQL. |
| F-11 | medium | product bug | `embeddings/backfill.py:117-147,186` | Backfill is O(n²) and unbatched. Each loop iteration runs two `COUNT(*)` scans over all of the bot's chunks, makes one provider request for one chunk (`texts=[text]`), and issues three commits. A bot with thousands of chunks needs thousands of requests and quadratic DB work. The scope is also every revision of the bot (`base` has no revision filter), so superseded revisions are embedded and paid for. | Batch (e.g. 16-64 chunks), keep a running remaining count, restrict to published + draft revisions that can be served. |
| F-12 | medium | product bug | `knowledge/ingest.py:797-802`, `embeddings/backfill.py:104-135`, `retrieval/hybrid.py:176-184` | Any successful ingest, including into an unpublished draft, calls `queue_backfill`, which sets `embedding_ready=False`. The live published bot drops to FTS-only until the backfill finishes. If the job exhausts its attempts, `embedding_ready` stays false permanently; the only signal is an INFO log. There is no staff UI for backfill progress, `retrieval_mode`, tier or generation model (only limits/costs/traces were built, `rag-operator-panel.tsx`), contrary to "Operator controls" in the plan. | Only flip readiness when the *published* revision changes; keep serving the old index for the live revision; add a staff alert/field and UI for backfill status and retrieval mode. |
| F-13 | medium | product bug | `chat/service.py:341-360`, `chat/prompts.py:11-34` | Prompt-injection hardening is a prose instruction only. Chunk text is interpolated raw into the *system* message with no delimiters or escaping, so document text can include fake `[uuid]` evidence headers or instruction-like text at system-prompt authority. Citation validation (`service.py:183-193`) limits fabricated sources, but not instructed behaviour. The only injection tests are the legacy offline `tests/eval` cases, which do not exercise the hybrid path or a real model. | Wrap each chunk in unambiguous delimiters with the delimiter stripped from chunk text, move evidence to a non-system role, and add a hybrid-path injection test. Real-model resistance is PENDING. |
| F-14 | medium | product bug | `quotas/rag.py:107-113`, `core/errors.py:44-45`, `widget/service.py:259-271` | The RAG `QUOTA_EXCEEDED` body carries `details: {"counter": "monthly_embedding_tokens"}`. The widget serves visitors through the same global handler, so visitors can read internal cap names. Plan: "Widget errors show a safe message only, no internals." | Drop `details` for non-staff/visitor callers. |
| F-15 | low | product bug | `quotas/ai.py:101-110` | `settle()` runs in `finally`; if it raises (e.g. tenant suspended mid-call, `scope()` 404) it masks the provider result/exception and aborts the turn. | Catch/log settle failures; keep the reservation. |
| F-16 | low | test gap / environment | `knowledge/ingest.py:121-141`, `tests/test_knowledge_parsers.py` (new test `skipif(os.name != "posix")`) | Process-tree kill is tested on POSIX only. The dev host is Windows; `taskkill /T` path and the lack of `setsid` on Windows are untested (the final report lists it UNVERIFIED). | Add a Windows-gated test, or document POSIX-only support. |
| F-17 | low | spec error | `knowledge/schemas.py:78`, `knowledge/router.py:168` | Per-document status is a constant `"parsed"`; the only warning is "no chunks". Plan asks for parsed / chunk count / warnings (e.g. truncated by page cap, skipped content). Source-level failure state exists separately (`Source.status/error`). | Persist parse warnings per document. |
| F-18 | low | environment | `infra/compose.yaml:4`, `retrieval/hybrid.py:69-73`, `alembic/versions/0014_rag_embeddings.py:19` | `pgvector/pgvector:pg17` is an unpinned tag. `hnsw.iterative_scan`/`hnsw.max_scan_tuples` need pgvector ≥ 0.8; `set_config` of an unknown dotted GUC succeeds silently, so an older image runs without iterative scan (the exact repair path then masks it, at higher cost). `CREATE EXTENSION` needs a privileged role in managed Postgres (UNVERIFIED). | Pin the image/version, assert version at startup, document privilege. |
| F-19 | low | hygiene | `retrieval/evaluation.py:13` | Production package `app.retrieval` imports `scripts.rag_stage0_baseline` (pulls psycopg/alembic). Layering inversion; harmless only while nothing in `main` imports `evaluation`. | Move shared helpers into `app/`. |
| F-20 | low | hygiene | `.env.example` (HEAD) | No `EMBEDDING_*`, `RETRIEVAL_*`, `RAG_PLAN_LIMITS`, `CHAT_REWRITE_*` entries; configuration is documented only in `docs/rag-phase`. (The dirty root checkout modifies this file; UNVERIFIED.) | Add the variables with safe placeholders. |
| F-21 | low | hygiene | `embeddings/router.py:111-122` | `PATCH .../rag` can switch `generation_provider` and leave a stale `generation_model` from the other provider; `exclude_none` makes it impossible to clear a model except by changing tier. | Validate the pair; accept explicit null. |
| F-22 | low | hygiene | `quotas/ai.py:51-55`, `chat/tracing.py:18-22` | Event kind (rewrite/translation) is derived by substring-matching the system prompt (`"condense a visitor"`), duplicated in two classes together with duplicated cost fallback logic. A prompt edit silently reclassifies cost events. | Pass the kind explicitly from the call site. |
| F-23 | low | hygiene | `knowledge/service.py:9-35`, `db/models/knowledge.py:409-411`, `quotas/rag.py` | Style drift in new code: `knowledge/service.py` import order (`quotas.service` before `quotas.rag`, I001), multi-line `check_resources(...)` call and the HNSW `Index(...)` block not in ruff-format style. The final report lists `knowledge/service.py:9 I001` as pre-existing, but the line that added `app.quotas.rag` is new. UNVERIFIED (ruff not run). | Run `ruff check --fix` / `ruff format` on touched files. |

### Risks (not defects)

| ID | Sev | Risk |
|---|---|---|
| R-01 | medium | **Arabic FTS uses the `simple` config** (`retrieval/service.py:83-90`, `query.py` `_arabic_variants`). No stemming, no stop-word removal in the index, and only the leading `ال` is handled; `:*` prefix matching helps with suffixes but not with attached clitic prefixes (و، ب، ل، ف، ك، س) or broken plurals. Recall for Arabic keyword search is structurally limited, so Arabic quality depends on the vector leg and its floor. That floor is the untuned `0.50` for `ollama:bge-m3` and unconfigured for OpenAI. The synthetic eval shows Arabic accepted evidence 0/6 in both modes (`THRESHOLDS.md`). Real Arabic recall is UNVERIFIED. |
| R-02 | low | The exact-repair query runs whenever the ANN returns fewer than `k` rows (`hybrid.py:75-79`), including every query on bots with fewer than `k` embedded chunks. Correct, but doubles vector work for small bots. |
| R-03 | low | `metered_embed`/`MeteredChatModel` hold a reservation per call and commit three times per backfill chunk; at high concurrency the bot-row lock in `scope(lock=True)` serialises all AI calls for one bot. Load behaviour UNVERIFIED. |

## Review checklist results

1. **Isolation: no isolation defect found.** `hybrid.py:30-47` carries `tenant_id`, `bot_id`, `revision_id`, `embedding_model` and `embedding_dim` inside the same statement for both the ANN and the exact-repair SQL; `d.tenant_id/bot_id` are also joined. Parameters are bound; the f-strings interpolate module constants only. Backfill queries filter tenant and bot (`backfill.py:113`). Traces, costs and quotas filter tenant and bot (`embeddings/router.py:44-54`, `quotas/rag.py:41-47`). Minor: the FTS query joins `documents` on `d.id` only (`service.py:126`), safe because chunk filters and the composite FK already scope it. Iterative scan is `strict_order` with a tuple cap, and underfill is repaired exactly (`hybrid.py:69-79`); `test_hybrid_retrieval.py:59` covers cross-tenant and cross-bot decoys, a tiny target and `EXPLAIN`. Not executed in this review until the final section.
2. **Staff-only: verified for the new surface.** The 5 new routes are `platform_staff_only` in `core/permissions.py:4-8` and call `require_operator()` (`embeddings/router.py:42,69,104,138,154`); the mutating ones require CSRF. Client bot payloads expose only `id, tenant_id, name, status, created_at, updated_at` (`bots/router.py:17-23`, `bots/schemas.py:103-113`); `config` is `{}` and `widget_locator` null. Tenant export applies column allowlists, drops `ai_usage` rows and empties other usage payloads (`tenants/data.py:352-358`); new bot/chunk columns are not in the allowlists. Playground trace panel and cost/limits panel render only for `is_platform_staff` (`playground/page.tsx:56`, `analytics/page.tsx:49`); this is UI-only gating on top of server enforcement. Residual: F-14 (counter name to visitors). Inbox/conversation payloads still blank `citations` for non-staff (`inbox/router.py:98`, `conversations/router.py:154`). Browser-level behaviour UNVERIFIED until the final run.
3. **Gate and refusal.** Gate uses `vector_similarity` and `fts_match`, never `rrf_score` (`gate.py:19-39`); an identity without a floor falls back to FTS-only acceptance (`gate.py:19`); malformed floors fail closed. Refusal makes no generation call and returns `needs_human=True`, `can_answer=False`, which feeds the unanswered report (`chat/service.py:326-338`, `analytics/service.py:218-244`). Issues: F-04, F-05, F-08.
4. **Embeddings and backfill.** Model, dim and revision are stored per chunk (`db/models/knowledge.py:333-335`, CHECK `ck_chunks_embedding`); the pointer and `embedding_ready` flip in one transaction (`backfill.py:129-135`); backfill is resumable and lease-fenced (`test_embedding_foundation.py:112,211`); serving falls back to FTS during backfill (`hybrid.py:178-184`) and re-checks after the vector query (`:229-249`); no model mixing (the model filter is in SQL). Issues: F-02, F-11, F-12. OpenAI large is the only adapter with a priced cost; OpenRouter cost stays null (correct).
5. **Generation.** Citations are validated against the retrieved set and dropped or the answer falls back (`chat/service.py:183-193`); invalid-citation filtering is tested (`test_chat.py:228`); replies use the detected language; provider failures return a canned message (`service.py:395-405`). Issues: F-13, F-08.
6. **Cost and limits.** Per-event-type ledger with bot, model, channel (`quotas/rag.py:202-218`); unknown usage stays null in the ledger (`rag.py:251-263`) but see F-10; 429 `QUOTA_EXCEEDED` paths exist for documents, chunks, storage, messages, tokens, embeddings (`rag.py:107-146,189-201`); unset caps are uncapped and documented (`LIMITS-AND-METERING.md`, `rag_contracts.py`). Issues: F-01, F-06, F-09, F-10, F-14.
7. **Parsing.** Wall-clock timeout, byte cap before spawn, process-group kill (POSIX) and `taskkill /T` (Windows) in `ingest.py:100-165`; DOCX table rows repeat headers (`parsers.py:139-155`); CSV/QA is per record (existing). Page caps are the existing `ParseLimits`. Document status is staff-only but thin (F-17). Windows tree kill is untested (F-16). Arabic `simple` config: R-01.
8. **Calibration scripts: caps hold.** `rag_calibrate.py` and `rag_generation_check.py` force `ENVIRONMENT=test`, ignore dotenv (`_env_file=None`, `load_credentials` reads the process environment only), print a conservative cost bound before any embedding call (`rag_phase2_eval.py:255-256`) and abort above 2M tokens (`evaluation.py:15,33-37`). The chat cap is 40 requests, journaled *before* the request and surviving restarts (`evaluation.py:119-136`); the key is redacted from artifacts (`append_record(..., secret=key)`); non-`:free` ids are rejected (`rag_stage0_baseline.py:151-159`). `prepare_database` accepts only a local PostgreSQL database named `*_test`, rejects `prod|live|staging`, URL query strings and non-loopback hosts (`rag_stage0_baseline.py:163-173`). That makes "disposable" a naming convention: any local `*_test` database, including a developer's real one, will be migrated and seeded. No confirmation pause follows the printed estimate (low). I did not execute either script.
9. **Security and hygiene.** No credentials found in the diff (the only key-like strings are `synthetic-key` test literals); `.test-storage` is untracked. No SQL is built from user input (f-strings use constants/a fixed column helper). The synthetic-vector guard exists in `from_settings` (`providers.py:146-148`) and at startup (`config.py:126-127`); both key off `environment == "test"`, so a production process started with `ENVIRONMENT=test` would pass (low; same trust model as the existing stub guard). Migrations 0014/0015 are additive, take no data rewrite, and refuse a downgrade that would discard data; the `ADD CONSTRAINT` checks scan the table once. Dead/duplicate code: F-19, F-22. Staff trace route returns the last 50 with no pagination (`embeddings/router.py:52`).
10. **Plan conformance:** table below.

## Conformance

Status: implemented / partial / missing / deviates / PENDING.

| Requirement | Status | Evidence |
|---|---|---|
| ADR #1 hybrid FTS+vector, RRF, every bot | partial | RRF `hybrid.py:100-112`; default `retrieval_mode=hybrid` (`models/core.py:148`), but a bot is FTS-only until a backfill completes (`hybrid.py:176-184`); evidence assembly regression F-03 |
| ADR #2 three settings | implemented | `models/core.py:148-157`; deployment-wide dim 1024 (`config.py:89`) |
| ADR #3 tiers are presets; Standard = paid low-cost OpenRouter | deviates | free-only enforced, `embeddings/router.py:117-122` (F-07) |
| ADR #4 multilingual embeddings; OpenRouter embeddings unverified | partial / PENDING | bge-m3 and text-embedding-3-large adapters (`providers.py`); mocked HTTP only; no real call |
| ADR #5 model+dim per chunk; query matches active model only | implemented | `hybrid.py:35`, CHECK `ck_chunks_embedding` |
| ADR #6 resumable idempotent `reembed_backfill`, atomic pointer | implemented | `backfill.py:104-135`; `test_embedding_foundation.py:112,211`; efficiency F-11, trigger F-12 |
| ADR #7 filters in the vector SQL; iterative scan/repair | implemented | `hybrid.py:25-79`; pgvector version UNVERIFIED (F-18) |
| ADR #8 gate on cosine floor + FTS match, not RRF | implemented / weak | `gate.py`; strength F-04; OpenAI floor unset (fails closed on vector) |
| ADR #9 degradation to FTS-only, logged | partial | embedding failure and backfill handled (`hybrid.py:176-228`); quota path not (F-06) |
| ADR #10 limits per bot/plan through 429 | partial | `quotas/rag.py`; reservation release F-01 |
| ADR #11 visibility: staff-only, citations redacted | implemented | checklist 2; browser run UNVERIFIED until final section |
| Cycle 1 follow-up rewrite, per-plan switch, skipped for self-contained | implemented | `chat/service.py:40-48,251-261`; regex heuristic is narrow (recall of rewrite triggers UNVERIFIED) |
| Cycle 2 parallel FTS+vector, RRF, SQL filter | implemented | `hybrid.py:216-257`, `test_hybrid_retrieval.py:187` |
| Cycle 4 refusal: no generation call, handoff offer, gap logged | partial | EN only offers handoff (F-08); no generation call `service.py:326-338` |
| Cycle 5 grounded generation, validated citations, not shown to clients | implemented | `service.py:166-193`, redaction checklist 2; prompt hardening F-13 |
| Cycle 6 post-check hook | implemented (hook only) | `post_check` parameter, `service.py:388-392` |
| Cycle 7 trace per answer | implemented | `service.py:289-315`, `tracing.py`, `conversations.py:330,348-352`; unknown-token flattening F-10 |
| Operator controls: tier/limits, retrieval_mode, backfill + progress, trace view, per-channel cost | partial | API complete (`embeddings/router.py`); UI only for limits, costs, traces; channel attribution F-09; no UI for mode/backfill (F-12) |
| Ingestion: timeouts, size/page caps, tree kill | implemented (POSIX) / UNVERIFIED (Windows) | `ingest.py`; F-16 |
| Tables flattened row-wise with repeated headers; CSV per record | partial | DOCX `parsers.py:139-155`; PDF table fidelity unverified (final report) |
| OCR async/page-capped/metered | deferred (permitted by plan) | no OCR path; caps exist only as config |
| Cost tracking per event type with bot/model/channel | partial | embed ingest/query, rewrite, translation, generation recorded; F-09, F-10 |
| Stage 0 keep-alive | implemented | `infra/compose.yaml:37` `--timeout-keep-alive 65`; E2E harness change not reviewed |
| Exit 1: hybrid beats fts_only on paraphrase and Arabic | **PENDING** | only synthetic hash vectors (9/22 vs 22/22 is coverage; whole corpus fits in k=8). No real-embedding run |
| Exit 2: unanswerable refuse; citations valid; no internals | **PARTIAL / PENDING** | 6/10 refused at the gate; 4 pass on keyword (F-04); citation validity mocked only; live generation sample 9 rows |
| Exit 3: isolation passes on the vector query | implemented (re-run in final section) | `test_hybrid_retrieval.py:59` |
| Exit 4: thresholds documented per embedding model; re-tune on change | partial | `THRESHOLDS.md` documents bge-m3 as provisional/untuned; OpenAI pending owner calibration |
| Exit 5: new routes staff-only in the matrix; clients see nothing new | implemented | `permissions.py:4-8`; matrix test count per final report 82=82 (re-run in final section) |

## Verdict

**Not ready for `phase-2-complete` or dogfood.** The merge to local `main` stands, but the isolation and staff-only work contains no defect I could find. Two blockers must be fixed first: F-01 (failed calls and aborted turns consume caps) and F-02 (Ollama can silently be the production default). Fix the highs F-03 and F-04 as well. Without them, hybrid mode, the default, drops always-include evidence, and the gate passes any single-word keyword match. Exit criteria 1 and 2 stay PENDING until the owner runs the calibration and generation checks with real providers; none of this review's code reading substitutes for that.

Missing tests worth adding: hybrid + always-include (F-03); definite-failure reservation release and aborted-turn message reservation (F-01); embedding-cap 429 degradation (F-06); Arabic refusal copy (F-08); `embed_query` channel attribution (F-09); production startup with default embedding provider (F-02); permanently failed backfill state (F-12); prompt injection on the hybrid path (F-13); Windows tree kill (F-16).

UNVERIFIED: pgvector version in the target database, numeric `ts_rank_cd` values, load behaviour, ruff/mypy status of the touched files, the uncommitted changes in the root checkout, the Playwright harness changes, real provider behaviour.

## Test results (run once, at the end)

Tip under test: worktree of `fc3fdcd` plus this review file (documentation only). API tests ran in the `saas-chats-ai-p5-close-checks` image with the worktree's `apps/api` bind-mounted read-only, against disposable pgvector databases (`rag_review_*_test`). No real provider calls.

**API, file by file: 353 passed across 44 files, every file exit 0.**

Harness note: in the first pass 17 files errored in fixtures because Git Bash rewrote `--basetemp=/tmp/...` into a Windows path (`FileNotFoundError: /app/C:/Users/...`). That was my invocation error, not a code failure. Those 17 files were re-run once with the path fixed and all passed; their counts below are from the re-run.

| File | Passed |
|---|---:|
| tests/eval/test_eval.py | 2 |
| tests/test_analytics.py | 6 |
| tests/test_auth.py | 15 |
| tests/test_bot_status.py | 5 |
| tests/test_bots.py | 4 |
| tests/test_change_requests.py | 1 |
| tests/test_chat.py | 16 |
| tests/test_contacts.py | 1 |
| tests/test_conversations.py | 13 |
| tests/test_conversations_view.py | 5 |
| tests/test_cross_script.py | 3 |
| tests/test_database_guard.py | 5 |
| tests/test_embedding_foundation.py | 16 |
| tests/test_followups_analytics.py | 2 |
| tests/test_handoff.py | 5 |
| tests/test_health.py | 6 |
| tests/test_hybrid_retrieval.py | 6 |
| tests/test_inbox_list.py | 5 |
| tests/test_invitations.py | 6 |
| tests/test_jobs.py | 8 |
| tests/test_knowledge_parsers.py | 29 |
| tests/test_knowledge_pipeline.py | 9 |
| tests/test_knowledge_uploads.py | 19 |
| tests/test_members.py | 8 |
| tests/test_migrations.py | 1 |
| tests/test_models_constraints.py | 13 |
| tests/test_platform.py | 9 |
| tests/test_platform_ops.py | 4 |
| tests/test_quotas.py | 10 |
| tests/test_rag_evaluation.py | 7 |
| tests/test_rag_gate.py | 14 |
| tests/test_rag_limits.py | 8 |
| tests/test_rag_stage0_baseline.py | 14 |
| tests/test_rag_traces.py | 3 |
| tests/test_retrieval.py | 9 |
| tests/test_seed_demo.py | 21 |
| tests/test_self_service_signup.py | 4 |
| tests/test_startup_guard.py | 5 |
| tests/test_tenant_data.py | 2 |
| tests/test_tenant_route_matrix.py | 6 |
| tests/test_tenants.py | 6 |
| tests/test_widget_appearance.py | 3 |
| tests/test_widget_leads.py | 5 |
| tests/test_widget_public.py | 14 |

The passing suite confirms the existing tests, including the vector isolation test and the route matrix, pass. It does not contradict any finding above: F-01 to F-14 describe behaviour the current tests do not cover.

**Playwright, one full unscoped run: 40 passed (3.8m), exit 0. ECONNRESET: 0** (no spec affected; no "Failed to proxy" or Python traceback lines in the log).

Harness note: the first Playwright attempt failed before any spec ran, because Next.js could not resolve `node_modules` junctions I had created in the worktree. I replaced them with real copies and ran once more; the result above is that run. The widget package under `node_modules` is a copy from the root checkout, which has no uncommitted changes under `packages/`.
