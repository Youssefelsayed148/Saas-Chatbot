# RAG final fixes before owner calibration

2026-10-16. Implemented the owner's final fixes. Real provider calibration and
language/groundedness validation remain **PENDING**. No real provider calls,
merge, tag, push or deployment were performed for these fixes.

## Defaults and safe gating

Default embedding identity is **`openai:text-embedding-3-large`**, dimensions
**1024**. Ollama remains an optional backend; it is unavailable here.
The OpenAI threshold row is cosine **0.50 OR FTS 0.01**, labelled
**UNTUNED, pending owner calibration**. Each identity requires its own row.
A missing/invalid vector floor disables cosine acceptance; the gate then uses
FTS only. FTS must have a positive finite score meeting the floor and at least
`RETRIEVAL_MIN_MATCHED_TERMS` distinct content terms (default 1). RRF never
passes the relevance gate. See THRESHOLDS.md and `.env.example`.

Scores and term counts now come from each selected chunk's own stored index,
including expanded documents and hybrid candidates. The SQL retains tenant,
bot and revision scope; a different chunk's document score is not copied.

## Corpus and calibration

The shared demo now seeds **44 chunks** across 44 documents: **36 English and
8 Arabic**. Eight English shop/workshop distractors and two Arabic shop chunks
share close hours/pricing/booking/address wording with the clinic facts.
The **76 cases** comprise 62 answerable and 14 unanswerable questions, label
every source, retain paraphrases/mixed/follow-ups, and add near-topic gaps.
The seeder remains idempotent and preserves an existing demo. Calibration
rejects a stale four-chunk database before provider requests; use the fresh v2
disposable database in the commands below.

Arabic FTS uses PostgreSQL **`simple`** on normalized **`fts_simple`**;
English uses **`english`** on **`fts_en`**. Arabic article/prefix variants for
one query term count as one content-term group. No Arabic stemming dictionary
is configured. Mixed queries follow the existing language/fallback routing;
raw evaluation disables translation and rewrite.

`scripts/rag_calibrate.py` delegates to the tested owner runner, which plans
the exact expanded seed before I/O, prints its estimated cost first, aborts
above **2,000,000 tokens**, and embeds/caches OpenAI 1024-dimensional vectors.
It reports raw answerable **hit@3** and **MRR over top-8 candidates** for
`fts_only` and `hybrid`, alongside gate refusal metrics. It sweeps FTS floors
0.005/0.01/0.05/0.10/0.20 and minimum matched terms 1/2/3; hybrid also sweeps
cosine disabled/0.40/0.50/0.60/0.70. The **90 settings** each show unanswerable
gate leaks, wrong refusals and wrong-evidence accepts. The recommendation
minimizes leaks, then refusals, then wrong-evidence accepts. These are sample
recommendations for owner review, never automatic runtime changes.

One paste-back file, **`calibration-results.json`**, includes raw rankings,
mode metrics, estimates, measured embedding usage, configs, every sweep setting
and the recommended threshold set. Cache and crash journals remain local.
Real scores, actual cost and semantic improvement are unmeasured until the
owner runs calibration. Synthetic test results cannot establish model quality.

## ADR and exact client navigation override

The RAG decision is now **ADR-019**, previously unused. References in the plan,
prompt and decision register agree. Billing retains ADR-008 unchanged;
historical stage reports retain their original collision note.

Non-staff admin/editor/viewer bot list/detail responses expose exactly these
eight serialized fields:

| Field | Client value |
|---|---|
| `id` | Bot UUID |
| `tenant_id` | Authorized tenant UUID |
| `name` | Bot display name |
| `status` | Bot lifecycle status |
| `created_at` | Creation timestamp |
| `updated_at` | Last update timestamp |
| `config` | Always `{}` |
| `widget_locator` | Always `null` |

The six navigation values and two redacted placeholders are the complete
exception. No retrieval, model, knowledge, traces, costs or citation fields
are exposed by this override. Implementation: `app/bots/router.py` and
`app/bots/schemas.py`; this fix does not change the response contract.

## Exact two owner commands

From the repository root, with disposable pgvector PostgreSQL listening at
127.0.0.1:55462. Process environment only: `CHAT_OPENAI_API_KEY` for the first
command; `CHAT_OPENROUTER_API_KEY` and JSON `CHAT_FREE_MODEL_CHAIN` of `:free`
models for the second. Credentials are never printed. The estimate assumes
the adapter's existing USD 0.13/million input-token accounting rate.

```powershell
.venv/Scripts/python.exe scripts/rag_calibrate.py --database-url postgresql://postgres@127.0.0.1:55462/rag_owner_calibration_v2_test --output .test-storage/rag-owner-calibration-v2
```

Paste back `.test-storage/rag-owner-calibration-v2/calibration-results.json`.
Inspect the recommendation before the second command, which explicitly loads
it for that check. This does not save settings to the app.

```powershell
.venv/Scripts/python.exe scripts/rag_generation_check.py --database-url postgresql://postgres@127.0.0.1:55462/rag_owner_calibration_v2_test --mode hybrid --embedding-cache .test-storage/rag-owner-calibration-v2/embedding-cache.jsonl --calibration-results .test-storage/rag-owner-calibration-v2/calibration-results.json --baseline-results .test-storage/rag-stage-0/baseline/results.jsonl --output .test-storage/rag-owner-generation-v2
```

The second command uses cached embeddings, skips completed historical baseline
IDs and has a durable 40-request cap including fallbacks; it stops at the first
quota/auth error. Do not restart with new output paths to evade the cap.
See OWNER-CHECKS.md for crash/resume details and prerequisites.

## Verification and limitations

**120 distinct affected tests passed across scoped runs.** The first run had
99 passes and one stale English-only-demo Arabic-refusal assertion; it was
updated for the new Arabic source. A follow-up caught ASCII pipeline corruption
in a new Arabic test input and two fixture questions; those were corrected and
an Arabic-content regression assertion added. Final follow-up: **44 passed,
exit 0, 260.74s**, covering all changed/new tests plus affected chat behavior.
The 99 and 44 totals overlap by 23 cases. No remaining affected failure or skip;
one existing Starlette/httpx deprecation warning. No real HTTP providers.

Scoped Ruff passed; format check passed **17 files**. Scoped mypy passed
**14 files**, then **3 files** for the last runner/test updates. An initial mypy
internal cache error and three typing errors were corrected as recorded in
PROGRESS.md. `git diff --check` passed. Exact commands, intermediate failures
and outcomes: PROGRESS.md; final follow-up log:
`.test-storage/rag-owner-fixes/affected-followup-corrected.log`.
No full-suite or browser rerun for these changes.

Historical pre-fix verification remains **353 API tests / 40 Playwright tests**
from the previous final gate, with exact evidence in FINAL-TEST-RESULTS.json.
Those totals do not validate these newer edits. Earlier four-chunk hit@8 numbers
are obsolete for this corpus and never established semantic improvement.
The existing nine unrelated broad Ruff findings remain outside this scope.

Changed files: `.env.example`; API config and retrieval gate/query/service/hybrid/
evaluation modules; `scripts/demo_knowledge.py`, `scripts/seed_demo.py`,
`scripts/rag_phase2_eval.py`; affected RAG/embedding/seed/retrieval tests and
`rag-phase2-eval.jsonl`; root calibration entrypoint; DECISIONS.md, RAG plan/prompt,
and this phase's thresholds/owner-checks/overrides/report plus PROGRESS.md.
No migration or production database change is needed. Existing active embedding
indexes require the already implemented scoped backfill to change identity;
changing the deployment default does not rewrite an active pointer.
