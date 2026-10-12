# P2-01 REPORT — Knowledge schema + DB job queue + worker

Date: 2026-10-12. Status: DONE, locally verified.

## Migration 0002_knowledge (Alembic; no create_all anywhere)

`apps/api/alembic/versions/0002_knowledge.py` creates, in dependency order:

- `jobs` — durable queue: type (`ingest_batch`), status `pending/running/succeeded/failed/cancelled`, JSONB `payload` (ids only, no secrets), `attempts/max_attempts`, `run_at` (backoff), `lease_expires_at/leased_by/started_at/finished_at`, `error`, `cancel_requested`, `created_by`; composite FK `(tenant_id, bot_id)` → `bots (tenant_id, id)` (ADR-010); claim index `(status, run_at)`.
- `sources` — kind `pdf/docx/txt/md/qa_csv`, `original_name` (display only), `storage_key` (generated, unique), `size_bytes`, `sha256`, status `stored/queued/ingested/failed`, error, Q&A `row_errors/valid_rows/total_rows`; composite FK to bots; unique anchors `(tenant_id, id)` and `(tenant_id, bot_id, id)`.
- `source_pages` — parsed page view per source (PDF page N etc.), title/source_url/page_type/language/raw text; 3-column composite FK to sources.
- `knowledge_revisions` — status `draft/published/archived`, `published_at/created_by`; composite FK to bots; **partial unique indexes**: at most one draft and one published revision per bot; composite FK anchors for chunks.
- `documents` — revision-scoped sections (so an ingest can never mutate rows a published snapshot points at): title/heading/source_url/page_ref/ordinal/language/priority/text/total_chars; FKs to revision + source via composite keys.
- `chunks` — tenant/bot/revision/source/document ids, `title/heading/text/text_norm/language/priority/content_hash/ordinal`; **generated tsvector columns** `fts_en` (`english` config over title+heading+text) and `fts_simple` (`simple` over `text_norm`) with **GIN indexes**; unique dedupe per `(revision_id, source_id, content_hash)`; composite FKs to bots and to revision/source/document. **No vector column, no pgvector extension (ADR-005).**
- `bots.published_revision_id` — nullable FK to `knowledge_revisions.id` (`SET NULL`).

Verification: `alembic upgrade head` → `downgrade 0001_initial` → `upgrade head` succeed on `chatbot_dev_test` (commands: `python -m alembic upgrade head`, `python -m alembic downgrade 0001_initial`, re-upgrade, `python -m alembic current` → `0002_knowledge (head)`). The dev DB `chatbot_dev` was restored to `0001_initial` after an exploratory migration during development and then migrated to `0002_knowledge` after the final migration was verified (dev-DB application evidence: `alembic upgrade head` against chatbot_dev at the Compose bring-up).

## ORM models

`app/db/models/knowledge.py` (+ `TSVECTOR` UD type in `models/types.py`), registered in `models/__init__.py`. `mypy --strict` clean.

## Job queue (`app/jobs/queue.py`, `app/jobs/runner.py`)

- `enqueue_job` → pending with `run_at=now`; payload `{source_ids: [...]}` (ids only).
- `claim_job`: `SELECT … FOR UPDATE SKIP LOCKED` over pending-but-due **or** running-with-expired-lease jobs; claims increment `attempts`, set the lease and `leased_by`; a pending job with `cancel_requested` flips to `cancelled` at claim instead of running.
- `release_job`: success → `succeeded`; failure → exponential backoff (`30s × 2^(attempt−1)`) until `max_attempts`, then `failed`; `cancel_requested` wins either way.
- `requeue_for_retry` (explicit user retry resets attempts to a fresh cycle) and `request_cancel` (pending → immediate cancel; running → flag-checked between units of work).
- `execute_claimed_job` dispatches `ingest_batch`; `JobFatal` (tenant/bot re-validation) fails permanently on the first attempt.

## Worker (`python -m app.worker`, same codebase)

- `app/worker/__main__.py` loop: claim → execute → release; poll interval 1 s; heartbeat file touched every loop; SIGTERM/SIGINT stop after the current job; refuses to start without `DATABASE_URL`.
- **Test-DB guard**: `WORKER_ALLOW_ONLY_TEST_DB=1` makes the worker refuse any database not ending in `_test` (used by tests/E2E). Verified live: worker boots against `chatbot_dev_test` and heartbeats; refuses `chatbot_dev` with the flag (exit 1).

## Compose worker service (`infra/compose.yaml`)

- New `worker` service — same `apps/api` image, `python -m app.worker`, shares the `app_data` volume with the API (`STORAGE_ROOT=/data/storage`), `depends_on: db healthy`, healthcheck = heartbeat file younger than 30 s. All four services healthy via `docker compose --env-file .env -f infra/compose.yaml up --build -d --wait` (ps output in PHASE-REPORT evidence).
- The API image creates and owns `/data/storage` (non-root `api` user); volume `app_data` recreated after the permission fix.

## Playwright harness

`apps/web/tests/e2e-api-setup.ts` spawns `python -m app.worker` with `WORKER_ALLOW_ONLY_TEST_DB=1` and the E2E disposable database URL (teardown kills it; `[e2e] Stopped the E2E worker.` in the run log). The knowledge E2E therefore exercises the REAL queue end to end.

## Tests (tests/test_jobs.py — 8 tests, all passing on Linux + Windows)

- `test_job_foreign_bot_rejected_by_composite_fk` — a `(tenant A, bot B)` job row cannot exist (`fk_jobs_tenant_bot` IntegrityError).
- `test_two_workers_never_claim_one_job` — two threads claim concurrently on separate sessions; exactly one winner gets the job, `leased_by` set, `attempts == 1`.
- `test_crashed_job_lease_expiry_is_reclaimed_then_retries` — claimed job with an expired lease is reclaimed by worker B (attempt 2); failing runs back off (`run_at` moves forward) until `max_attempts` → `failed` with `finished_at`.
- `test_pending_job_run_at_gates_the_claim` — future `run_at` invisible; claimable once due.
- `test_cancel_pending_immediately_and_running_via_flag` — pending cancels at claim; running cancels via the flag at release.
- `test_retry_resets_attempts` — explicit retry gives a fresh cycle.
- `test_ingest_job_revalidates_tenant_and_bot` — archived bot and archived tenant Tenants fail the job permanently (`attempts == max_attempts`) with actionable errors; no writes.
- `test_jobs_are_listed_per_bot` — listing is tenant-scoped.

## Exact commands

Linux (checks image `saas-chats-ai-api-checks:p2`, disposable `chatbot_dev_test`): ruff check / format --check / mypy → green; `python -m pytest -q` → 123 passed. Windows host: identical → green. Migration cycle commands against `chatbot_dev_test` and `chatbot_dev_migration_test` as shown above.
