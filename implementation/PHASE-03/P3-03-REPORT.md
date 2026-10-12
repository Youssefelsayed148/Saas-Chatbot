# P3-03 REPORT — conversation core + playground pipeline + retention

Date: 2026-10-13. Status: DONE, locally verified (Linux container + Windows host).

## Migration 0003_conversation_core (Alembic; up/down cycle verified)

- **contacts** — one person per tenant: display_name, citext email (unique per tenant when present), phone, stage (`new` default — editable names in P5-04), tags/custom_fields/consent JSONB, source_channel; `ck_contacts_reachable` (email or phone), anchors `(tenant_id, id)` + partial-unique tenant email.
- **contact_identities** — unique per `(tenant, channel, external_id)`; composite FK `(tenant_id, contact_id) → contacts`.
- **conversations** — channel (`website|whatsapp|messenger|instagram`; Meta VALUES per docs/14 §14 ManyOsirisChat mapping in P6), `connection_id` (null for website), `mode ai|human`, `status open|waiting_human|resolved`, `assigned_user_id` anchored to memberships composite FK (an assignee must be a member of THAT tenant), `handoff_reason`, `last_message_at`, `sentiment` (always null until the P5-05 job), `source` (playground vs website channel), composite FK `(tenant_id, bot_id) → bots`.
- **messages** — `sender_type visitor|ai|agent|system`, `sender_user_id` (agents only, anchored to memberships), text, citations JSONB (AI turns: the validated contract objects), `can_answer`, `needs_human`, `response_ms`, `channel_message_id`, `delivery_status` lifecycle + `error_code` (P6 delivery), composite FK `(tenant_id, bot_id, conversation_id) → conversations`.
- **usage_events** — `kind` (`message|widget_open|lead|feedback_up|feedback_down|handoff`), idempotency via UNIQUE `(tenant, bot, external_key)`; `jobs.type` check widens to `retention_purge`.

## Pipeline + storage (`app/chat/conversations.py`)

- `visitor_chat_turn`: stores the visitor turn, runs the chat pipeline **only when `mode == 'ai'`** (a human takeover makes the AI silent → 409 `CONVERSATION_IN_HUMAN_MODE`), measures `response_ms`, stores the AI turn with validated citations / `can_answer` / `needs_human`, writes the idempotent usage event `message:{ai_message_id}`, 1000-char message cap (422).
- Playground conversations are per user+bot (`source='playground'`, anonymous — no CRM contact yet); threaded GET returns the retention-filtered thread (expired messages drop out immediately, docs/14 §7 — proven by a time-travel test).
- **Thumbs feedback** endpoint (editor+): `POST /bots/{bot}/messages/{message_id}/feedback` `{rating: up|down}` → idempotent per rater+rating via `feedback:{rating}:{message}:{user}` external key (duplicate posts cannot double-count; verified).
- **Retention purge**: `run_retention_purge` deletes messages older than `Settings.retention_days` (default 30 per docs/14 §7); the job runs through the queue (`retention_purge` job type claims + executes; proven) AND the worker self-schedules it every `retention_purge_interval_seconds`; both tests verified.

## Endpoints (roles: send = editor+, read = member, feedback = editor+)

- `POST /api/v1/tenants/{t}/bots/{b}/playground/messages` — one turn; 503 `MODEL_NOT_CONFIGURED` with a controlled message until a provider key (or the deterministic dev stub) is configured.
- `GET /api/v1/tenants/{t}/bots/{b}/playground/conversation` — thread + counts.
- `POST /api/v1/tenants/{t}/bots/{b}/messages/{id}/feedback`.
All tenant-scoped; other tenants' bots/messages look like 404; viewer writes 403 (tests).

## Deterministic dev stub model (`ExtractiveStubModel` + `Settings.chat_stub_model`)

- DEV/TEST/EVAL ONLY (documented "never configured for production"): answers extractively **from the actual evidence in the prompt** — no network, no invented text; coverage gate abstains when the knowledge does not even mention the asked content (weekday-calendar gaps force abstention — "Are you open on Sundays?" over Mon-Sat knowledge abstains); coverage source = title+heading+body per docs/14 §4; cross-script tokens ignored by coverage (a stub cannot translate).
- This lets the pipeline, conversation storage, feedback and the E2E run end to end before provider keys exist. The `chat_stub_model` flag is the ONLY path to it and it is not set in production config.

## Tests (13, all passing Linux + Windows)

Pipeline + storage: turns + citations + usage event idempotency; second turn reuses the conversation; per-bot scope of playground threads; mode guard; retention-filtered thread; feedback idempotency + wrong-id 404 + tenant scope; retention purge direct and via the queue; roles (viewer 403 on send/feedback, member read allowed); tenant B guessed ids 404; 503 without a model; schema-level cross-tenant conversation write rejected (composite FK). 

## Exact commands

`ruff check .` / `ruff format --check .` / `mypy` / `python -m pytest -q` → green (160→162 final counts), Linux + Windows. Compose `docker compose --env-file .env -f infra/compose.yaml up --build -d --wait` — all four services (db/api/web/worker) healthy.
