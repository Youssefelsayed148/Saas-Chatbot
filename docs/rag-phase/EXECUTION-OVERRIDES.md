# Owner-approved Phase 2 execution overrides

2026-10-16. The attached whole-phase request supersedes conflicting wording in
`RAG-PHASE-PROMPT-v2.md` and `RAG-PLAN-v2.md`.

- Execute stages 0–7 in order; numbered STOP gates are reports/checkpoints, not
  approval pauses. Stop immediately on the owner's five explicit failure conditions.
- Preserve the existing client navigation fields (bot IDs, names, status,
  timestamps). All operator data, knowledge, settings, traces, costs and citations
  remain staff-only. This exception was explicitly confirmed after a conflict check.
- Never read `.env` in this continuation; process credentials only. Historical
  scoped dotenv authorization and changes are documented as past actions.
- Reuse the partial live baseline; do not replay completed questions. Label the
  baseline **FTS-only, translation off**: translation already exists in the runtime.
  Raw retrieval sees raw text; any future follow-up generation receives history.
  Run retrieval-only measurements for all questions with no provider cost.
- A persistent 429 blocks further chat calls, not offline implementation or tests.
  Preserve partial results and mark chat-dependent measurements PENDING.
- OpenRouter free generation only for live work; no real OpenAI calls, embedding
  or chat. Implement provider backends and exercise paid backends with mocked HTTP.
- Deployment embedding dimension is 1024. Providers: Ollama bge-m3 (development
  default if verified from the API container), OpenAI text-embedding-3-large with
  dimensions=1024, and configurable OpenRouter. If Ollama is unavailable, use
  deterministic fake vectors in tests, explicitly labelled; never as a production
  provider. Model changes require resumable backfill and an atomic active pointer.
- Thresholds are model-specific. Ollama bge-m3 development values are provisional;
  OpenAI calibration is pending owner execution. Build, but do not run, the capped
  calibration and generation-check scripts requested by the owner.
- One implementation commit and `STAGE-N-REPORT.md` per stage. Existing plan-files
  commit is `0c70c5b`. Record implementation hashes in the final report; a report
  cannot contain the hash of the commit that first introduces that same report.
- Reuse Stage 0's three recorded affected Playwright runs. Full API (file by file)
  and Playwright suites run once at the final gate, never again for reporting.
- No push, production deployment, destructive database operations or Compose.
  Local merge/tag only under the final conditional verification rule in the request.

The plan's RAG ADR-008 identifier collides with the older register's deferred
billing ADR-008. This document does not renumber or resolve that unrelated billing
decision; the approved RAG plan controls this work.
