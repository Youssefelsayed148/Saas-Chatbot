# RAG hardening batches (H1–H5)

Source: the bot/retrieval review of 2026-10-25 (branch fix/r3c-provider-widget at review time).
Run one batch per session, in order, each on its own branch from main (after R3c is merged):
`fix/h1-embedding-readiness`, `fix/h2-knowledge-hygiene`, and so on. Each batch ends at a gate:
stop, report, wait for owner sign-off before the next one. Local commits only.

Shared rules for every prompt below (they restate AGENTS.md):
- Tenant scope on every query; hidden resources 404; add tenant A/B tests for anything new.
- Alembic migrations, never create_all. Disposable test DB only (127.0.0.1:55462, set TEST_DATABASE_URL per process, PYTHONUTF8=1, ENVIRONMENT=test).
- No push, merge, deploy, paid or live provider calls. If a spec parameter is TBD or a DECISIONS.md item is OPEN, stop and ask.
- Tests with every change. Record exact commands and real outcomes in PROGRESS.md; never fabricate results. If something could not be run, say so.
- If a change alters documented behaviour, add a dated note to docs/14 (or the relevant doc) and a DECISIONS.md entry only where the owner approves.
- Subagents (only when the owner has allowed them in the session; each starts cold, so give it the
  exact question, file list and the AGENTS.md constraints, and expect a short report back):
  - Allowed: READ-ONLY impact sweeps before editing (Explore agent) and one independent REVIEW after the
    batch is committed and its tests are green (general-purpose agent, told to review the diff against
    this batch's prompt and AGENTS.md, and to report findings only, not edit).
  - Not allowed: parallel agents editing code, running tests against the DB, touching git state, any
    live or paid provider call, or reading/printing credentials. One writer at a time: the main session.
  - Treat subagent output as leads to verify in the code, never as test results; only commands you ran
    yourself go into PROGRESS.md.

---

## H1 — Embedding readiness and backfill (review gaps 1, 10)

Problem: every ingest sets `bots.embedding_ready = False` (embeddings/backfill.py `queue_backfill`), and `retrieve_hybrid` then serves the LIVE bot keyword-only until the backfill finishes, although the published revision is fully embedded. The backfill embeds one chunk per HTTP call, covers all revisions (including archived), and a provider failure leaves the live bot degraded. `run_ingest_batch` also reports the job as failed if `queue_backfill` raises after a successful ingest.

Prompt:
```
Read AGENTS.md, docs/14 §1/§5, DECISIONS.md ADR-019, and apps/api/app/embeddings/backfill.py,
retrieval/hybrid.py, knowledge/ingest.py, knowledge/service.py (publish_revision).
Goal: ingesting new content must never degrade the live published bot's retrieval.
Tasks:
1. Readiness per revision: record embedding completeness for the PUBLISHED revision separately from
   the draft (design the smallest schema change, with an Alembic migration and up/down/up test).
   retrieve_hybrid uses hybrid whenever the published revision's chunks all carry the active model's
   embedding; draft backfill progress must not affect it.
2. Backfill scope: embed only draft and published revisions' chunks (skip archived; embed an archived
   revision on demand when it is rolled back to, and keep FTS serving meanwhile).
3. Batch the provider call (configurable batch size, default 32, respecting provider input limits),
   keeping the per-batch checkpoint, lease fencing, metering reserve/settle and cancel behaviour.
4. Publish: if the draft being published is not fully embedded, publish still works (FTS covers it)
   but the bot reports a clear "keyword-only until embeddings finish" state; the knowledge page must
   show embedding progress and the current retrieval mode for published and draft.
5. Failure isolation: a backfill failure leaves the published revision's hybrid mode intact. Make
   queue_backfill errors after a successful ingest non-fatal to the ingest job (record a warning on
   the job instead).
6. Tests: ingest while live keeps hybrid mode; failed backfill keeps live hybrid; rollback to an
   archived revision; batch size and checkpoint resume; tenant A/B; metering counts match.
Subagent help (if allowed): BEFORE editing, one Explore agent (very thorough, read-only) lists every
reader/writer of bots.embedding_ready, active_embedding_model, Chunk.embedding* and reembed_backfill
jobs across app/, scripts/, tests/ and apps/web, and every place that assumes one readiness flag per bot.
AFTER green tests, one review agent checks the diff for: live-bot degradation paths still left, lease/
metering regressions, tenant scoping on new queries, migration up/down safety.
Verify with the named test files plus tests/test_hybrid_retrieval.py, test_rag_*.py, test_jobs.py,
test_migrations.py. Update PROGRESS.md. Stop at the gate.
```

---

## H2 — Knowledge hygiene (review gaps 4, 7)

Problem: uploading the same file twice duplicates documents (no `sha256` comparison; dedupe is per source only) and burns evidence slots. There is no way to delete or replace a source, so stale content stays and can contradict new content. `always_include_document_ids` is read by chat but cannot be set (not in `BotConfig`, extra=forbid) and document ids change on every draft copy.

Prompt:
```
Read AGENTS.md, docs/14 §3/§5, docs/18 (P2 section), apps/api/app/knowledge/{service,ingest,router}.py,
apps/api/app/bots/schemas.py, apps/api/app/chat/service.py (always_include) and the knowledge web page.
Goal: knowledge content stays clean: no duplicates, stale content removable, "always include" usable.
Tasks:
1. Upload dedupe: same sha256 for the same bot returns/links the existing source (clear message in
   the response, no new Source, no new ingest). Different bots/tenants stay independent.
2. Replace: upload a new version of an existing source (keeps the source identity); ingest replaces
   its documents/chunks in the draft; the old version is not retrievable once published.
3. Delete source: staff-only DELETE endpoint (CSRF, audit row, tenant scoped, 404 for hidden) that
   removes the source's documents/chunks from the DRAFT revision and marks the source removed; stored
   file cleanup via the existing storage interface; published knowledge is unchanged until publish.
4. Cross-source duplicate chunks: when two different sources produce identical normalised chunk
   hashes within a draft, keep one (prefer the newer source) and surface a warning in the document list.
5. Always-include: make it addressable by a stable key that survives draft copies (for example a
   per-source or per-document flag carried through _copy_revision_snapshot), expose it in the
   knowledge UI and the bot settings API with validation, and keep the reserved evidence slots rule.
6. Knowledge UI: delete, replace and always-include controls with confirm dialogs; show duplicates
   skipped.
7. Tests: duplicate upload, replace, delete + publish + retrieval no longer finds removed content,
   rollback restores it, always-include survives a re-ingest, tenant A/B on every new endpoint,
   Playwright spec written (run only if the owner has servers up; otherwise say not run).
Subagent help (if allowed): BEFORE editing, one Explore agent maps every use of Source, Document.source_id,
Chunk.source_id, the storage interface, tenant deletion/data export (tenants/data.py, deletion.py) and
the web knowledge page so delete/replace cannot orphan rows or break purge/export. AFTER green tests,
one review agent hunts for cross-tenant paths in the new endpoints, published-revision leaks before
publish, and stale always-include references.
Update docs/05 (API contracts), docs/18 and PROGRESS.md. Stop at the gate.
```

---

## H3 — Conversation intelligence (review gaps 2, 3)

Problem: "who are you / what can you do / how are you / help / what's your name" (EN and AR) reach retrieval and end in the canned refusal with `needs_human=true`. "thanks" returns the welcome message again. A refusal is a dead end. Follow-up detection is a regex that misses common follow-ups, so history exists but the raw message is searched.

Prompt:
```
Read AGENTS.md, docs/14 §6/§15, apps/api/app/chat/{routing,service,prompts,history,streaming}.py,
inbox/handoff.py and tests/test_routing.py, test_chat.py, test_playground_parity.py.
Goal: grounded answers stay grounded, but the bot handles meta questions, thanks and follow-ups well.
Constraints: no answers from general knowledge; business facts still only from evidence; routing stays
rule-based and deterministic (no extra LLM call for intent); buffered and streamed paths must behave
identically (parity tests).
Tasks:
1. Meta-intent routing (pre-retrieval, EN + AR, whole-token matching like the existing router):
   identity ("who are you", "what's your name"), capability ("what can you do", "help"), how-are-you,
   thanks, farewell. Replies are composed from bot config only (assistant_name, business_name,
   business_description, opening_questions) in the visitor's language, with distinct thanks/farewell
   texts instead of the welcome message. They are can_answer=true, needs_human=false and never count
   toward the unanswered-twice handoff. A message that also contains an informational question
   ("hello, what are your hours?") still goes to retrieval.
2. Refusal with direction: when the gate refuses but near-miss candidates exist, the canned reply
   adds up to 3 suggested topics taken from candidate document headings/titles (never from model
   text), localized, plus the support contact. Keep needs_human behaviour unchanged. Trace the
   suggestions.
3. Follow-up resolution: replace the regex-only trigger. Condense when history exists and the message
   is short or lacks content terms after stop-word removal, and ALSO retry retrieval once with the
   condensed query when the first pass is refused and history exists (respect the turn budget and the
   plan list; unknown plan labels must not silently disable rewrite: document or fix that).
   Cover the failing probes: "how much is the large one?", "tell me more", "the same for kids?",
   "كم سعره", "ماذا عن الأحد".
4. Prompt: pass the language NAME (English/Arabic) not the code; keep prompt versioning
   (bump PROMPT_TEMPLATE_VERSION) and the streaming evidence-marker contract intact.
5. Tests per probe set above, parity (buffered vs stream), handoff counters, history skipping rules,
   Arabic cases. Record before/after on tests/eval (stub) in PROGRESS.md; do not claim real-model results.
Subagent help (if allowed): BEFORE editing, one Explore agent lists every consumer of ChatReply.kind,
the routing helpers, history_for_turn and the streaming parity tests, plus the existing AR/EN canned
texts, so new kinds do not break analytics, inbox decisions or the widget. AFTER green tests, one
review agent writes 20 adversarial EN/AR messages (meta questions mixed with info questions, injection
inside "who are you") and traces by reading code which path each takes; report mismatches only.
Update docs/14 §6 with a dated note. Stop at the gate.
```

---

## H4 — Retrieval quality and calibration (review gaps 5, 6)

Problem: matched-term counting includes filler words and dialect Arabic fillers; gate thresholds are untuned; Arabic recall is unverified; no real-model eval has completed. Part A is offline; Part B spends money and needs explicit owner approval.

Prompt (Part A, run now):
```
Read AGENTS.md, docs/14 §1/§2/§5, DECISIONS.md ADR-019, apps/api/app/retrieval/{query,gate,service,
evaluation}.py, tests/eval/*, implementation/RAG-PHASE-02/STAGE-0-REPORT.md.
Goal: improve term quality and measurement, offline only.
Tasks:
1. Filler terms: add an English and Arabic (MSA + Gulf/Egyptian/Levantine fillers such as ايه، كم،
   ازاي، فين، عايز، بدي، ممكن) low-information list used only for the matched-term COUNT, not the ranking
   query; keep `retrieval_gate_ignore_terms` working on top. Test against the DB english stop list
   consistency test.
2. Arabic recall: add EN/AR/dialect paraphrase and typo cases to the offline eval corpora, with
   expected sources; measure hit@k and wrong-refusal per mode with the existing stub/test embedder and
   report honestly that the test embedder is non-semantic.
3. Gate diagnostics: extend the staff trace/report so each refusal says which rule failed and what
   the nearest candidate scored; add a script that prints a threshold sweep (cosine floor, FTS floor,
   min terms) over the eval set without applying anything.
4. Do not change default thresholds in this part. Output a recommendation table only.
Subagent help (if allowed): an Explore agent may draft candidate dialect fillers and paraphrase/typo
questions from the existing corpora for you to review (it must not call any provider). A review agent
may check the eval cases for leakage (expected answers that appear verbatim in the question) and for
unfair expected sources. You decide what enters the corpus.
Update PROGRESS.md with commands and numbers. Stop at the gate.
```

Prompt (Part B, only after the owner approves a spend limit in writing):
```
Owner has approved up to <N> live requests and <budget> for calibration. Use only the eval fixtures,
a disposable DB, and checkpointed runs (resume, no replay, stop on first 402/429 as in Stage 0).
Run the full bilingual set (grounded, paraphrase, typo, dialect Arabic, cross-language, unanswerable,
injection, follow-up) in full-runtime mode for BOTH tiers (standard chain, premium gpt-5.4-nano).
Report hit@8, wrong refusals, false answers on unanswerable, citation validity, latency and cost per
tier. Propose threshold changes; apply none without owner sign-off (dated note in docs/14 + DECISIONS.md).
```

---

## H5 — Staff tooling, quotas and resilience (review gaps 8, 9, 11, low items)

Problem: playground can only test the published revision; staff playground turns count against the client's monthly/daily message quota; Premium has a single model with no fallback; widgets poll every 2 s forever; PDF pages lose cross-page context.

Prompt:
```
Read AGENTS.md, docs/09, docs/13, apps/api/app/{quotas/*,chat/models.py,chat/providers.py,
widget/service.py,chat/conversations.py}, apps/web/app/widget/frame/page.tsx and the playground page.
Tasks:
1. Draft preview: playground (staff only) can choose "Published" or "Draft" knowledge; retrieval
   takes an explicit revision id for the draft case; the widget path can never use a draft. Show which
   revision answered in the trace. Tests: widget ignores draft, playground uses it, tenant A/B.
2. Quota hygiene: usage events from playground conversations do not count toward the tenant monthly
   message quota or the per-bot daily cap (keep them visible in staff usage with a source label);
   migration only if a schema change is needed. Regression tests for both counters.
3. Premium resilience: optional ordered fallback list for the OpenAI tier (config, validated,
   same one-attempt-per-model rule, same trace/attempt log); free_only guard unchanged for Standard.
   A provider failure should not hand off when a fallback succeeded. Tests with mocked HTTP only.
4. Widget polling: poll only when the conversation is waiting_human/human or a follow-up is pending,
   otherwise stop; resume on handoff; exponential backoff on errors; keep `?debugWidget=1` behaviour.
   Tests for the polling rules (unit) and widget-layout/handoff Playwright specs written (run only if
   servers are up).
5. PDF context (small): carry the previous page's last sentence as overlap into the next page's first
   chunk only when the page break splits a sentence; keep page citations correct; add tests.
Subagent help (if allowed): BEFORE editing, one Explore agent lists every counter of `message` usage
events (quotas/service.py, quotas/rag.py, widget daily cap, analytics, platform views) and every
reader of `Conversation.source`, so the playground exclusion is complete and analytics stay correct.
AFTER green tests, one review agent checks that the widget can never reach a draft revision, that
fallback never fires on a 401/402 block, and that polling stops/resumes correctly across handoff.
Update PROGRESS.md and docs. Stop at the gate.
```

---

## Final gate — full verification (after H1–H5)

Run the full API suite, evals (stub), web typecheck/lint, and the full Playwright suite on disposable
databases; record exact commands and outcomes in PROGRESS.md; then ask the owner for the H4 Part B
calibration decision and the merge decision. Nothing is merged or pushed by the agent.
