# P2-03 REPORT — Indexing pipeline, dedupe, draft → publish → rollback

Date: 2026-10-12. Status: DONE, locally verified.

## Pipeline (`app/knowledge/ingest.py`)

`ingest_batch` job handler (claimed by `app/jobs/runner.py`):

1. **Re-validation before acting**: tenant must exist and be `active`; bot must exist, belong to `job.tenant_id` and not be archived — otherwise `JobFatal` → permanent failure with an actionable message (never a write).
2. **Draft revision**: `get_or_create_draft_revision` — one draft per bot (partial unique index guarantees this at the DB level, with a concurrent-ingest recovery path). A **fresh draft is a full snapshot copy** of the current published revision (documents + chunks with re-anchored ids), so publish stays a pure pointer swap and rollback is trivial.
3. Per source: storage read → parse (with timeout, P2-02) → plan documents + chunks (§4 chunking, per-chunk language detection, Arabic normalisation, front-matter overrides, CSV rows unsplit) → **dedupe by `content_hash`** (identical normalised chunk text stored once per `(revision, source)` — enforced also by the unique index).
4. **No-op detection**: the planned documents + chunks are compared to the existing rows for that source in the draft; identical → nothing is written, the source just flips to `ingested` (unchanged re-ingest is a no-op). Otherwise the source's rows inside the draft are replaced atomically (delete + insert in one transaction; `source_pages` re-created per parse).
5. Failures are per-source (`status=failed` with an actionable `error`); the job continues with the remaining sources and only fails wholly if all of them failed.

## Publish / rollback (`app/knowledge/service.publish_revision`)

- Admin+ only (docs/06); archived bot → 409; empty revision (0 chunks) → 409 `KNOWLEDGE_EMPTY`; unknown/foreign revision → 404 (indistinguishable from a wrong id).
- **Atomic pointer swap** implemented as ordered Core-SQL updates in one transaction: demote the current published revision (`status=archived`, `published_at=NULL`) → archive stale drafts → promote the target (`published`, `published_at=now`) → update `bots.published_revision_id`. Both the ORM-object path and partial unique indexes were validated against a real bug the pipeline test caught (promote-before-demote violated `uq_knowledge_revisions_published`); the final implementation passes.
- Publishing an **archived** revision = rollback (audited `knowledge.rolled_back`); publishing again the current revision is an idempotent no-change response. Publishes of drafts run the same swap and free the "only one draft per bot" slot.
- Audited: `knowledge.published`, `knowledge.rolled_back`, plus `knowledge.sources_uploaded`, `knowledge.ingestion_started`, `knowledge.job_cancelled`, `knowledge.job_retried`.

## Endpoints added (all tenant-scoped, stable error format)

| Route | Role | Notes |
|---|---|---|
| GET/PATCH-free `GET /bots/{id}/sources`, `GET /bots/{id}/sources/{sid}` | member | Q&A row report included |
| `POST /bots/{id}/sources/files` | editor+ | P2-02 |
| `GET /bots/{id}/sources/qa-template` | editor+ | CSV template download |
| `POST /bots/{id}/ingestion` | editor+ | 202 + one job |
| `GET /bots/{id}/jobs`, `GET /bots/{id}/jobs/{jid}` | member | statuses + errors |
| `POST /bots/{id}/jobs/{jid}/cancel`, `/retry` | editor+ | retry re-queues a fresh cycle |
| `GET /bots/{id}/documents?source_id&revision=published|draft` | member | with chunk counts |
| `GET /bots/{id}/documents/{id}/chunks` | member | chunk preview |
| `GET /bots/{id}/revisions` | member | counts + `is_current` |
| `POST /bots/{id}/revisions/{rid}/publish` | admin+ | publish **or** rollback |

## Tests (`tests/test_knowledge_pipeline.py` — 9 tests; isolation tests in `test_knowledge_uploads.py`; all green on Linux + Windows)

- `test_upload_parse_chunk_into_draft_revision` — upload EN+AR markdown → job → sources `ingested`, draft chunk rows with per-chunk language, stripped diacritics in `text_norm`, front-matter `source_url` on the documents; nothing published yet.
- `test_pdf_pages_become_documents` — real PDF bytes → per-page documents `<file> — Page N`, `page_ref` "Page 1/2".
- `test_docx_sections_tables_and_headings` — heading + table-as-text verification.
- `test_qa_csv_one_chunk_per_row` — 2 valid rows → exactly 2 chunks starting `Q:` with one `A:` each; `page_ref` = "Row N".
- `test_skill_output_folder_uploads_end_to_end` — skill folder (2 md pages + coverage + qa.csv) end to end, citations carry both `source_url`s.
- `test_reingest_unchanged_source_is_noop` — re-running the succeeded job leaves documents/chunk rows byte-identical (row counts + full row tuples unchanged); re-queuing an ingested source is 404/409-guarded.
- `test_publish_rollback_and_failed_job_isolation` — publish; ingest a corrupt PDF → job `failed` with "corrupt" (visible in jobs after retry/exhaustion) while the published pointer and published chunk rows are untouched; second good ingest builds a fresh draft; rollback to revision 1 works (pointer swap, 200).
- `test_two_tenants_identical_content_share_no_rows` — same file ingested by two tenants → identical chunk counts, **disjoint id sets**, and a cross-tenant referential check (`chunks.tenant_id != documents.tenant_id` count = 0).
- Endpoint isolation + role tests: tenant B guessed-UUID → 404 on sources/jobs/documents/revisions; viewer 403 on uploads/ingestion/cancel/retry/publish; editor 403 on publish; archived bot 409.

## Exact commands

Linux checks image on `chatbot_dev_test`: `ruff check . && ruff format --check . && mypy && python -m pytest -q` → green, 123 passed. Windows host: identical, green, 123 passed.
