# Staff RAG limits and metering

Owner approved configurable limits with **unset values uncapped**. No new numeric
plan promises are introduced. Existing tenant message/upload/page limits still
apply. Standard/Premium generation presets do not change knowledge capabilities.

Deployment plan defaults: process `RAG_PLAN_LIMITS`, a JSON object keyed by the
existing `free`, `starter`, `pro`, `business` labels. Values accept these optional
nonnegative integer caps (zero blocks new work):

| Field | Unit / scope |
|---|---|
| documents | Documents per knowledge revision, per bot |
| chunks | Chunks per knowledge revision, per bot |
| storage_bytes | Stored uploaded file bytes, per bot |
| monthly_messages | AI replies including playground, per bot |
| monthly_tokens | Embedding + rewrite + translation + generation tokens, per bot |
| monthly_embedding_tokens | Ingest and query embedding tokens, per bot |
| monthly_ocr_pages | OCR pages, per bot; no OCR execution path currently exists |

Calendar months are UTC. GET/PATCH `.../bots/{bot_id}/rag` exposes staff-only
limits/effective limits/usage. A PATCH `limits` object replaces bot overrides;
omitted keys inherit plan defaults, explicit null is uncapped, and `limits:null`
resets overrides to plan defaults. The staff analytics page edits bot overrides
and displays measured cost by bot, channel, model and event type. Plan defaults
are deployment configuration, never editable by clients. All new limits default
to null; configuration alone does not enforce an invented spend ceiling.

Uploads check storage before saving files. Ingestion checks parsed document/chunk
counts before replacing draft rows; unchanged re-ingestion remains a no-op.
Async ingest failures report `QUOTA_EXCEEDED` in the staff job/source error;
synchronous requests use HTTP 429 `QUOTA_EXCEEDED` with “Contact us.” Lowering
caps never deletes/hides existing data. Staff limit mutations are audited by field
name, without private values in client audit/export surfaces.

Before provider I/O, a bot-row lock serializes a durable usage reservation. Locks
are released before network calls. Chat bounds use UTF-8 input bytes plus protocol
allowance and max output, covering the one allowed fallback; embeddings use input
bytes plus allowance. Measured usage settles the reservation. Missing usage,
uncertain failed/fallback usage or a killed worker retains conservative accounting
instead of crediting unknown work as zero. These bounds can reject early; staff
can review records and adjust caps. Reservations do not auto-expire to evade a
budget after a crash. This is token/unit enforcement, not a currency spend cap.

`ai_usage` records event type, bot, model, channel, reservation/measurement state,
reported tokens and measured USD cost. Supported events: ingest/query embeddings,
rewrite, translation, generation and internal message reservation. Unknown pricing
stays null; known free/local work has zero cost, but explicit provider-reported
cost takes precedence. Staff cost totals are measured subtotals with unreported
event counts, not an asserted total for unknown providers. No OpenAI generation
price is invented. OCR is deferred; its configured page cap is ready for a future
metered OCR path and grants no OCR capability today.

Client exports remove every `ai_usage` row and empty other usage payloads, closing
the Stage 4 trace leak. Staff exports retain instrumentation. Traces and costs
remain absent from client/visitor replies and hidden from client UI. The exact
tenant route matrix has 82 entries; `/rag/costs` is platform-staff-only.

Migration `0015_rag_metering` adds a nullable bot override column and extends an
event-kind check. Upgrade does not modify existing rows. Downgrade refuses when
limits or metering events would be lost. Only disposable databases were migrated.
