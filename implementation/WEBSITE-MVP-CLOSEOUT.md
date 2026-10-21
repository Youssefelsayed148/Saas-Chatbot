# Website MVP closeout plan

Status: DRAFT for owner review. Written 2026-10-17 after the review-phase triage session.
Companion document: `docs/19-CHATBOT-STRATEGY-AND-MANYOSIRISCHAT-PLAN.md` (decisions and findings).
Baseline: main at e850a9d (Groups A, 0, B, C merged locally). RAG Phase 2 fixes are merged into main (52e57cf, 9522cf7). Backend 409 passed / 1 skipped, frontend 62 passed at e850a9d.

## 1. Goal and definition of done

Goal: the website chatbot is tested and closed out, so a new client can be deployed (org, bot, knowledge, widget on their site) in minutes, and answers correctly from the client's own data. ManyOsirisChat integration starts only after this closes.

Done means ALL of these:
- Review phase closed (manual pass clean, section Stage 0).
- Retrieval and answers meet the pass targets (section 3) on the demo client with real provider keys.
- A timed onboarding run of the demo client completes within the target in section 5, using only the staff flow.
- Known issues in section 4 are each classified as MVP blocker or not, and every blocker is closed.
- Full API suite and full Playwright suite pass once at the end, on the disposable DB.

## 2. Rules for every stage

- Repo: D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai. Local commits only. Never push. No tags unless the owner says.
- Never read or print .env or .env.local or any key.
- Coding agents never run docker. The owner runs docker.
- Tests run only against the disposable DB on 127.0.0.1:55462 (container saas-test-db), set per process as TEST_DATABASE_URL, never in a file, never against the dev DB.
- Fix work: new branch from main, small commits, merge --no-ff, git branch -d, main left clean, no push.
- Reporting format from the owner: step + what I did + what I saw.
- Triage format from Claude: classify (product bug / test gap / spec error / environment), then pass / fix / continue.

## 3. Pass targets (from docs/14 section 10, plus additions)

| Measure | Target |
|---|---|
| Grounded questions: correct answer with valid citation | >= 90 % |
| Unanswerable questions: abstained / handed off, no invention | >= 95 % |
| Prompt-injection cases resisted | 100 % |
| Cross-tenant leakage | 0 |
| Arabic and mixed-language grounded accuracy | within 5 points of English |
| Hybrid vs fts_only on paraphrase and Arabic sets | hybrid better |
| Wrong refusals on answerable questions | recorded; owner sets the ceiling after first run |
| Errors shown to visitors | safe message only, no internals |

Targets are adjustable only by a dated note in docs/14.

## 4. Stages

### Stage 0 - Close the review phase (owner)
Owner runs the manual pass (see docs/19 section 2 for the exact list) after `docker compose up -d --build`.
Evidence: role + page + what was seen, per item.
Exit: every item passes, or each failure is triaged and fixed. G4 (demo-owner refused at login) must pass.

### Stage 1 - Remove documentation and config drift (Claude Code, small)
Items:
1. Matched-terms gate: `.env.example` says RETRIEVAL_MIN_MATCHED_TERMS=2, `docs/rag-phase/THRESHOLDS.md` says default 1. Confirm the code default and make all three agree.
2. Arabic search: `FINAL-REPORT.md` says migration 0016 adds `fts_ar` (real `arabic` config) and also says Arabic queries use `simple` on `fts_simple`. Confirm which column the query path uses and document the truth.
3. `docs/07`, `docs/14`, `docs/18` still describe keyword-only retrieval and "no similarity thresholds". Add a dated note pointing to ADR-019 and RAG-PLAN-v2.
4. `implementation/MANUAL-TEST.md`: compose path is root `compose.yaml` (not infra/compose.yaml); `/widget/sample` is staff-only; step 5 and the stub-vs-real-model section need the current variables.
5. Confirm the stub model is off for real-model runs (CHAT_STUB_MODEL unset or false) and note how to verify.
Exit: one branch, docs and config only (no behavior change), merged --no-ff, tests untouched.

### Stage 2 - Demo client data (owner + Claude)
Demo client: fictional "Nile Home Goods" (Egypt, EGP). Full spec in docs/19 section 5.
1. Owner generates the 10 PDFs (5 documents x EN/AR) and checks the Arabic text extraction by copy-paste from each PDF.
2. Owner sends the Arabic extraction result and the list of deliberate gaps.
3. Claude drafts `eval.jsonl` (about 40 cases) with expected source and expected answer fragments.
4. Owner onboards the client through the staff flow (this also tests onboarding): create org, invite admin, create bot, upload, publish.
Exit: knowledge published, eval file reviewed by the owner.

### Stage 3 - Ingestion tests (owner, Claude triages)
Check each, record chunk counts and warnings (staff-only view):
- Every PDF parsed, one section per page, titles "<file> - Page N".
- Tables flatten row-wise with headers repeated.
- Arabic text correct and searchable.
- Same file twice: no duplicate content. Same file in another org: shares nothing.
- Failure cases: scanned/image-only PDF rejected with a clear message; file over 10 MB; corrupt file; empty file; wrong extension. Failed ingest never changes what is published.
- Job states: queued > running > done/failed; Retry on failed; Cancel on queued/running.
- Publish, then rollback to previous revision; verify the bot answers from the right revision each time.
Exit: all pass or triaged.

### Stage 4 - Real-key calibration (owner runs, Claude interprets)
Use the two owner commands in `docs/rag-phase/OWNER-CHECKS.md` (calibration, then generation check). Process-environment credentials only, never printed.
Before running: confirm the corpus to calibrate against. The built-in calibration uses the synthetic dental corpus (44 chunks, 76 cases). For the demo client, extend the calibration to the Nile Home Goods corpus and eval.jsonl (this is a Claude Code task; define it in Stage 4 prompt).
Outputs to paste back: `calibration-results.json`, the generation-check output.
Decisions: choose FTS floor, cosine floor, minimum matched terms for `openai:text-embedding-3-large`@1024; record in THRESHOLDS.md with date; mark status as calibrated on which corpus.
Exit: thresholds recorded; pass targets measured and reported honestly (including failures).

### Stage 5 - Behavior tests (Playground, then widget)
Run in Playground with trace view first, then through the widget. Use the real model.
- Grounded answers keep conditions and exceptions together (for example "30 days except clearance 7 days").
- Reply language follows the question (EN, AR, mixed). Arabic renders right-to-left.
- English documents answer Arabic questions in Arabic (cross-language fallback), and the reverse.
- Unanswerable (deliberate gaps): "I don't have that information", offer handoff, logged as unanswered.
- Handoff: asks for a person; two unknown answers in a row; configured keyword. Status becomes waiting_human; take over, reply, return to AI; reply reaches the widget.
- Injection: "ignore your instructions", text inside documents telling the bot to do things.
- Follow-ups: pronouns and short follow-ups answered correctly using history.
- Near-miss traps: similar numbers (7/14/30 days) for different items answered correctly.
- Limits: over plan limit gives 429 with "contact us" text, shown verbatim.
- Errors: provider failure, embedding failure (degrades to FTS-only per request and logs), empty/over-long message, rapid messages.
- Trace check: each answer has chunk ids, scores, gate decision, mode, model, tokens, cost, channel.
Exit: pass targets met on the widget path, not only in the playground.

### Stage 6 - Deployment drill (owner)
- Install the snippet on a test page from a different origin; domain allowlist blocks other domains.
- Widget on mobile width (360x800) and desktop; keyboard only; RTL; reopening shows history.
- Paused bot shows the controlled unavailable message; archived/deleted org disables the widget immediately.
- Second org with similar content: zero cross-tenant hits (isolation).
- Lead form with consent creates a contact; handoff and reply journey works in a browser (this closes the open handoff item).
- Soft delete with typed org name; grace period behavior.
- Time the whole onboarding (section 5) and write the runbook from what actually happened.
Exit: drill passes; runbook committed.

### Stage 7 - Close-out
- Triage the known issues table (section 6) and close the blockers.
- Run the full API suite once (file by file) and the full Playwright suite once, on the disposable DB.
- Update PROGRESS.md, KNOWN-ISSUES.md, PHASE-CHECKLISTS.md, DECISIONS.md.
- Owner decides whether to tag `mvp-website-complete`. No tag without an explicit owner instruction.
Exit: owner signs off. Only then start the ManyOsirisChat phase (docs/19 section 7).

## 5. Timed onboarding runbook (target to measure in Stage 6; rewritten 2026-10-21 for the built staff flow, S1–S4)

Target: a new client live on their website in 15 minutes of operator time, excluding document preparation and ingestion wait. This is a TARGET, not a measurement — the timed drill replaces these budgets with real numbers, and `implementation/ONBOARDING-RUNBOOK.md` is written after that timed run (P-S6).

The operator signs in to /platform (platform staff; the staff account is created by the seed or by a platform admin) and then, in order:

1. **Create the organization** (Organizations → new, name + plan label).
2. **Create the user and assign them** (Members → new user: email, optional phone, staff-set or generated password shown once; then assign the organization and role — or send the user a one-time invitation afterwards).
3. **Create the bot** (Bots → new bot in that organization; or from the organization detail).
4. **Upload knowledge** (open the organization workspace → the bot's Knowledge tab → upload the prepared files/Q&A CSV).
5. **Ingest** (start the ingestion job; watch queued → running → succeeded in the same tab; retry on failure).
6. **Publish** the revision once the preview looks right.
7. **Set allowed domains** (bot Settings → allowed domains) and persona/appearance as needed.
8. **Test chat** in the Playground with real questions, including one unanswerable case.
9. **Embed the widget**: copy the install snippet, paste it on the client site, load the page and test the chat from the real domain.

| Step | Target |
|---|---|
| Create organization, create user and assign | 3 min |
| Create bot | 1 min |
| Upload documents | 2 min |
| Ingestion wait, review preview, publish | 3 min (plus wait) |
| Persona, tone, language, support contact, handoff rules | 3 min |
| Allowed domains | 1 min |
| Test chat, install snippet on the client site, test from the real domain | 2 min |

## 6. Known issues to classify in Stage 7 (from implementation/KNOWN-ISSUES.md)

Owner fills the last column: BLOCKER / NOT A BLOCKER.

| Issue | Initial view | Decision |
|---|---|---|
| Widget handoff journey: root cause unverified in browser | Verify in Stage 6; likely blocker if it fails | |
| widget.spec ECONNRESET: cause unknown | Capture details on a rerun; blocker if it recurs | |
| Hosting undecided (ADR-007) | Blocker for real client deployment | |
| Backup/restore drill untested | Blocker for real client data | |
| Independent security review pending | Owner decision | |
| AI cost analytics unavailable (no provider pricing stored) | Not a blocker for first client | |
| Quota values and pricing are placeholders | Not a blocker for demo; blocker for paid clients | |
| P5-03, P5-05, phase sign-off unticked | Close after Stage 7 | |
| Existing Ruff/mypy findings (9 broad Ruff) | Parking list | |
| SSE cleanup tracebacks on client disconnect | Parking list | |
| Production alert receiver untested (needs hosting) | Follows ADR-007 | |
| Tenant deletion file cleanup best-effort on local storage | Review with hosting decision | |

## 7. Claude Code prompt outlines (finalize after owner review)

Each prompt: new branch from main, small commits, merge --no-ff, git branch -d, main left clean, no push, never read .env, no docker, tests only against the disposable DB.

- P-S1 (Stage 1 drift fix): verify code defaults for RETRIEVAL_MIN_MATCHED_TERMS and the Arabic query column; align THRESHOLDS.md, FINAL-REPORT.md, .env.example; add dated ADR-019 notes to docs/07, 14, 18; fix MANUAL-TEST.md paths and variables. Docs/config only. Report the truth found, with file and line.
- P-S4 (calibration for the demo client): extend the calibration runner and seeder to load the Nile Home Goods corpus from a given folder and eval.jsonl; keep the existing synthetic run working; same cost estimate and abort rules; no provider calls by the agent.
- P-S5 fixes: written per finding after the tests, grouped by cause.
- P-S6 runbook: write implementation/ONBOARDING-RUNBOOK.md from the timed run.

## 8. Evidence log (fill as stages complete)

| Stage | Date | Result | Evidence location |
|---|---|---|---|
| 0 | | | |
| 1 | | | |
| 2 | | | |
| 3 | | | |
| 4 | | | |
| 5 | | | |
| 6 | | | |
| 7 | | | |
