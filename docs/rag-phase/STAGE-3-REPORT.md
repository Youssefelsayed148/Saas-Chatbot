# Stage 3 — rewrite, relevance gate and safe refusal

2026-10-16. Parent `8f163e9`; this stage's hash follows in the next checkpoint.
Provider requests: **0**. Owner approved **cosine OR FTS**, with explicitly
untuned `bge-m3 (Ollama), provisional` defaults 0.50 / 0.01.

- Wired hybrid retrieval into chat. Independent, finite cosine/FTS signals gate
  evidence before generation; RRF is never a relevance threshold. Unknown model
  identities have no inherited vector floor. Settings and calibration status:
  `THRESHOLDS.md`.
- Context-dependent follow-ups use the existing small rewrite call; self-contained
  queries skip it. Global and per-plan switches are configurable. Generation
  retains visitor history even when rewriting is skipped/disabled.
- Empty/rejected evidence returns “I don't have that information,” offers inbox
  handoff, and makes no generation call. Existing message persistence marks it
  `can_answer=false`, feeding unanswered analytics and the handoff state machine.
- Provider client now makes no retries, at most one immediate-model fallback;
  auth/quota errors block subsequent preprocessing/generation calls that turn.
  HTTP clients close properly, errors contain no provider bodies or credentials.
  Existing cross-script translation remains available in normal runtime;
  budget-limited raw-FTS evaluations keep it disabled.

## Measurements

All **32** baseline questions measured on raw FTS, translation/rewrite off,
zero requests. Expected-source accepted hit@8: **9/22 (40.9%)** answerable cases.
Arabic 0/6; mixed 4/4; paraphrase 3/8; follow-up 2/4. Gate rejected **6/10**
unanswerable cases; four still pass keyword overlap. These numbers do not measure
generation refusal correctness or multilingual semantic quality. Raw scores and
case outcomes: `STAGE-3-GATE-RESULTS.json`.

Affected tests and exact commands/outcomes are recorded in `PROGRESS.md`.
New gate/provider/all-case checks **13 passed**; budget compatibility **14 passed**;
chat **16** + cross-script **3** = **19 passed**. Persistence **13**, handoff **5**, unanswered analytics **6** passed.
A targeted history-window test also passed: **71 unique affected API tests** total.
Review found and fixed inclusion of the current question and selection of oldest
history; recent prior turns are now scoped by tenant/bot and configured window.

Mypy **165 source files**, affected Ruff and 9-file format checks passed.
Affected Playwright widget/playground: **7 passed (1.3m)**, ECONNRESET **0**.
No full suites. The nine pre-existing Ruff findings remain untouched.

Files: core settings; retrieval gate; chat service, prompts, provider/factory;
affected/new tests and portable 32-case fixture; threshold/result/report docs;
execution overrides and PROGRESS.

UNVERIFIED/PENDING: real bge-m3 scores, semantic improvement, live rewrite and
remaining generation/refusal samples; OpenAI real calls and calibration.
No real calls, dotenv reads, merge, push, deploy, Compose or Stage 4 changes.
