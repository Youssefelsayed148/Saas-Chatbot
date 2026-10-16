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
- Owner clarified the relevance gate: cosine OR FTS may pass independently.
  Approved configurable cosine 0.50 / ts_rank_cd 0.01 as explicitly untuned
  `bge-m3 (Ollama), provisional` defaults. Other models require their own
  configured/calibrated vector floor; OpenAI remains pending owner calibration.
- One implementation commit and `STAGE-N-REPORT.md` per stage. Existing plan-files
  commit is `0c70c5b`. Record implementation hashes in the final report; a report
  cannot contain the hash of the commit that first introduces that same report.
- Reuse Stage 0's three recorded affected Playwright runs. Full API (file by file)
  and Playwright suites run once at the final gate, never again for reporting.
- No push, production deployment, destructive database operations or Compose.
  Local merge/tag only under the final conditional verification rule in the request.
- After the export privacy stop, the owner explicitly approved fixing export
  redaction with a regression test, then resuming Stage 7. New per-plan/bot caps
  are configurable; **unset remains uncapped**. No numeric defaults are invented.

The RAG decision is now **ADR-019**, renumbered by explicit owner request on
2026-10-16. Deferred billing keeps ADR-008. Historical stage reports retain the
old label as evidence of the earlier collision.

## Local merge approval

2026-10-16: after receiving the final test totals and pending quality checks,
the owner explicitly instructed: "merge approved do it". This authorizes the
local merge into `main` and safe deletion of the merged feature branch despite
the remaining calibration and live-quality checks. It supersedes the earlier
conditional merge restriction only. Pending criteria remain pending; no
`phase-2-complete` tag until they pass. No push or real provider calls authorized.

## Final fixes before owner calibration (2026-10-16)

This owner request supersedes the earlier embedding-default and threshold text
above. Default identity: `openai:text-embedding-3-large`, dimensions=1024. Ollama
is optional and unavailable in this environment. Add OpenAI cosine 0.50 OR FTS
0.01, labelled **UNTUNED, pending owner calibration**. A missing identity row
uses FTS only. FTS additionally requires at least one matched content term by
default; the calibration sweeps this minimum and the FTS floor.

Client bot navigation exposes exactly `id`, `tenant_id`, `name`, `status`,
`created_at`, `updated_at`, plus redacted placeholders `config: {}` and
`widget_locator: null`. These eight fields are the serialized non-staff BotOut
response for the tenant-scoped list/detail routes, for admin/editor/viewer.
No new client fields were added by these final fixes.

Use the expanded 44-chunk demo and 76-case evaluation. No real provider calls,
merge, tag, push or deployment; run only affected tests. The previous merge
approval records a completed historical operation and does not authorize a new
merge for these fixes. Owner commands and paste-back artifact: FINAL-REPORT.md.
