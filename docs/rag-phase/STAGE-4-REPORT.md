# Stage 4 — grounded generation, citations and private traces

2026-10-16. Implementation `85dbe92`, parent `555ffc7`.
Chat/real embedding/OpenAI requests: **0**.

- Per-bot Standard/OpenRouter-free and Premium/OpenAI provider/model selection
  now applies to playground, widget and conversation runtime. OpenAI HTTP is
  mock-tested only; missing configuration does not silently switch paid providers.
- Kept the grounded prompt, small configurable evidence set and strict citation
  validation: unknown IDs are dropped and answers with no valid citation fail
  safely. Optional post-check callback is wired/tested; no LLM judge is built.
- Store per-answer chunk/document IDs, locators, cosine/FTS/RRF scores, gate and
  rewrite decisions, model, measured tokens/cost, latency and channel in existing
  private usage-event JSON. No schema migration/data rewrite needed. Missing
  provider usage/pricing remains null, never an invented zero.
- GET `.../rag/traces` returns the latest 50 scoped traces to platform staff only.
  Staff playground renders traces; clients/visitors receive no new fields.
  Exact role matrix: **81 declared = 81 actual**, including this staff-only route.

Mock answerable/refusal/follow-up examples: `STAGE-4-SAMPLE-TRACES.json`.
They demonstrate trace shape and control flow, not live answer quality.

Verification: trace/gate files **17 passed** (3 + 14); exact role matrix **6**;
selected citation/error cases **4 passed**, 12 deselected. Visitor checks **14 passed**: **41 affected API tests** total. Mypy **167 source files** passed; affected Ruff and 14-file format check
passed; web lint/typecheck passed. Initial mypy found two new test-only setup/
narrowing errors, corrected before tests. No isolation or privacy failures.

Affected playground browser spec: **3 passed (1.1m)**, ECONNRESET **0**; includes
staff trace display and viewer denial. Exact commands in `PROGRESS.md`.

Files: chat tracing/service/provider/factory/persistence/router; widget factory
wiring; RAG router and role metadata/matrix; new trace tests; typed API client,
playground page/spec; sample/report docs and PROGRESS.

UNVERIFIED: real provider behavior, live groundedness/rewrite/language quality,
unreported provider token/cost usage. No LLM judge, full suites, dotenv reads,
real calls, merge, push, deploy or Compose.

Later regression review found that existing client exports still serialized
private usage payloads containing these traces. The Stage 4 route/UI checks
above did not cover that export path. Work stopped; the owner approved the
redaction fix and regression test, committed in Stage 7 (`e1d1c23`). Client
exports now omit AI ledger rows and strip operational usage payloads.
