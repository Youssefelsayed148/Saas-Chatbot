# PHASE-03 REPORT — Chat (P3-01 → P3-05)

Date: 2026-10-13. Status: ALL P3 TICKETS IMPLEMENTED AND LOCALLY VERIFIED. **STOPPED FOR OWNER SIGN-OFF.**

Branch: `feat/p1-01-foundation` (extended; 4 P3 commits + 1 eval commit, no push/merge/deploy, no paid APIs — the whole phase runs on local Postgres and the deterministic offline stub model).

## What works end to end now (owner-readable summary)

1. Open a bot → **Playground**. Ask "What are your opening hours?" → the answer comes ONLY from the bot's published knowledge, shows the citation (page title + original URL), the response time, and 👍/👎 (one rating per person per answer; repeats don't double-count).
2. Ask something the knowledge does not cover ("Are you open on Sundays?" against Mon–Sat hours; "How long is the warranty?" with no warranty page) → "I cannot confirm that… please contact <support contact>" — never an invented fact, never a stack trace.
3. Arabic works symmetrically: «ما ساعات العمل لديكم؟» answers from the Arabic page (diacritics, «ال»-variants and prefixes all match); Arabic answers render RTL. TypeScript input `dir="auto"`.
4. "Where is my order?" type questions hand off to a human contact line without calling the model at all (toggle per bot); smalltalk gets a localized welcome.
5. Conversation storage is channel-agnostic from day one (website channel now; WhatsApp/Messenger/Instagram come through the Many contract in P6): contacts, identities, conversations (mode/status), messages with citations/needs_human/response time, idempotent usage counters, retention purge job (daily, worker-scheduled or queue-run).
6. Evaluation: fixtures (EN+AR) + 17 eval.jsonl cases run through the REAL pipeline on every suite run; deterministic numbers vs docs/14 §10 — grounded 8/8 (100%, target ≥90%), unanswerable-abstained 5/5 (100%, target ≥95%), injection-resisted 2/2 (100%, target 100%), cross-tenant leakage 0/0. Cross-SCRIPT language translation measured 0/2 with the deterministic stub — no target defined in docs/14 §10; the retrieval fallback + model-translation assembly is a real-model P3 gate item (see "model note" below).

## Model note (P3 gate input — please read with the eval report)

This phase includes `ExtractiveStubModel` — a deterministic, offline, extractive "model" (answers are spans of the actual evidence; abstinence calibrated by coverage + weekday-vocabulary detection) used in tests, the eval run and the E2E harness via the explicit dev-only `CHAT_STUB_MODEL` flag — never in production config. It lets the whole pipeline run WITHOUT provider keys and measures the retrieval/routing/contract stack. The provider layer (`OpenAICompatibleModel`, OpenRouter `:free` chain with fallback, OpenAI for paid plans per ADR-013, 25 s timeout, 2 retries) is implemented and unit-tested but deliberately holds NO keys in this environment: wiring the real key/model is a config change (`chat_openrouter_api_key`, chat_free_model_chain) plus the plan assignment (P7 free/paid plans). The P3 gate (docs/14 §10): with a real model the eval reruns as-is — paraphrase/typo recall and Arabic→English answer translation are the model-side capabilities this run cannot demonstrate.

## Verification evidence (final state)

| Check | Linux (checks image, disposable chatbot_dev_test) | Windows host (repo venv) |
|---|---|---|
| `ruff check` / `ruff format --check` (apps/api) | All green (146 files) | All green (95 files) |
| `mypy` strict | 91 source files, no issues | same |
| `python -m pytest -q` | **162 passed**, 1 warning | **162 passed** |
| eval suite | 2 passed; EVAL-REPORT.md written to implementation/PHASE-03 | same |
| `npm run format:check` / `lint` / `typecheck` | — | all green |
| `npm test` (Playwright; real API + real worker + stub model, disposable chatbot_dev_e2e_test) | — | **12 passed** |
| Compose stack | rebuilt during the phase: db/api/web/worker all healthy | — |

Ticket reports: `P3-01-REPORT.md` (retrieval), `P3-02-REPORT.md` (chat service/providers/contract), `P3-03-REPORT.md` (conversation core), `P3-04-REPORT.md` (playground+UI), `P3-05-REPORT.md` (eval suite + report), plus `EVAL-REPORT.md` (the raw numbers).

## Checklist status (implementation/PHASE-CHECKLISTS.md)

All P3 items ticked with evidence pointers; remaining open item: **owner review and sign-off**.

## docs/18 behaviours after P3

- Playground answer + citations + "not ready" state when nothing is published ✅ (503 handled with a controlled notice; a bot with no published revision answers cannot-confirm).
- "Search is keyword-based: exact wording matters" — the eval + retrieval tests document that behavior and its Arabic normalisation/prefix range ✅.
- "A 'page text' that says 'ignore your instructions' does not change behaviour" ✅ (injection cases + prompt data-only rule).
- "Conversations and usage events are stored; bot with nothing published says it is not ready" ✅.
- Thumbs feedback + unanswered questions list arrives as analytics in P4-05 (feedback storage exists here).

## Limitations and open risks

1. **Real-model path not exercised live** (no provider keys in this environment — no paid calls authorized): provider layer is unit-tested; live OpenRouter/OpenAI verification is pending the owner-provided keys, then the eval re-runs as the §10 gate.
2. **Cross-script translation** (Arabic question about English-only content) needs a real model; the deterministic stub records 0/2 with documentation, and docs/14 §10 defines no numeric cross-language target. The retrieval fallback path itself is proven (bilingual-typed case).
3. **Hosted CI has never run** (carried limitation; workflow updated, no remote authorized).
4. Login rate limiter still in-process (carried; Postgres-backed counters planned for the widget phase per docs/14 §7).
5. ExtractiveStubModel is dev/test/eval-only (`chat_stub_model`), never in production config; the E2E harness relies on it for offline runs.
6. Playwright stub: the "not configured 503" UI notice is exercised in the API test only (the E2E deploy runs with the stub model).
7. `sentiment` column exists but is always null until the P5-05 job (per docs/14 §14) — spot-checked in tests.
8. The eval AR "warranty" case pivots on a single Arab token («الضمان») covered nowhere in the corpus; if the corpus later gains warranty content the case must move with it (documented in the eval fixtures).
9. Widget-side (public API) chat is P4-01 — the pipeline already runs conversation-agnostically, but there is no visitor-facing endpoint in this phase (playground is dashboard-only).
10. Databases used: chatbot_dev_test / chatbot_dev_migration_test / chatbot_dev_e2e_test (disposable). chatbot_dev (the review database) was migrated to `0003_conversation_core` and stray rows from an earlier harness mishap were truncated afterwards; the compose stack is left running for review (loopback 3000/8000/55432).

## Second-approval notes for the owner

- Scope: no embeddings/pgvector (ADR-005), no response cache, no live product lookups, no Meta endpoints (P6 only through the contract), i18n per docs/14 §2, no prompt-topic knowledge in the system prompt.
- The P3-06 semantic/hybrid upgrade is NOT started (per the phase rules) — the eval report is the input for that gate decision.
- Next phase after sign-off: P4 Widget (P4-01 → P4-06).
