# Website Chatbot SaaS — MVP Closeout Plan

Owner: Youssef (AI & ML Engineer, The Osiris Labs) · Repo: `SAAS-chats-ai`, branch `main`, local only · Date: 2026-10-22
Companion file: `MVP-CLOSEOUT-BATCH-PROMPTS-2026-10-22.md` (one build prompt per batch).

This plan is the single source of truth for finishing the MVP. It records what passed, what we agreed, every logged issue (#1–#40), the batches that fix them, the order, the guardrails for the redesign, and the exit gates. Phase 6 (ManyOsirisChat) is out of scope.

---

## 1. Where we are

**Passed in manual testing**
- Staff login; organization, bot and member creation (member phone needs `+20…` for now, see #1b); member sees only their own organization (menu level).
- 10 PDFs ingested (5 documents × EN/AR, the `_1` set): 40 pages, 41 chunks. Arabic extracts as real Arabic text.
- Grounded answers (refund, delivery to Alexandria) on the **Premium** tier. Correct abstain (CEO question).

**Failed or blocked**
- Widget does not render on `/widget/sample`: `/widget/v1/loader.js` returns 404 in Docker (#40). The settings form also still fails to save if the allowed-domains box holds a URL (#22/#23).
- Standard tier answers "busy" (free OpenRouter chain, #16/#19).
- Retrieval gate drops the right page on some in-document questions (#29).

**Not yet tested (Batch 0):** widget render, Arabic Q&A, Arabic abstain, prompt injection, near-miss traps, follow-ups, handoff/contact capture, cross-tenant leakage, hybrid vs `fts_only`, ingestion edge cases, member roles and direct URL access, onboarding stopwatch.

## 2. Exit targets (unchanged)

| Target | Gate |
|---|---|
| Grounded answers | ≥ 90 % |
| Abstain correctly | ≥ 95 % |
| Prompt injection | 100 % resisted |
| Cross-tenant leakage | 0 |
| Arabic vs English | within 5 points |
| Hybrid vs `fts_only` | hybrid better |
| Errors shown to users | safe messages only |
| Onboarding a new client | ≤ 15 minutes |
| Wrong-refusal ceiling (new) | ≤ 10 % of answerable questions (to be confirmed after the first calibration; was open in `docs/19` §12) |

## 3. Agreements (binding)

1. Signup off. Staff create organizations, members and bots. Invites for existing users only. Knowledge is staff-only. Password change at `/account`.
2. Test on **Premium** for now. A **tier-matrix test** on Standard (free models) runs later (#37). The default tier for new bots is decided after it.
3. **Merge Bot name + Assistant name** into one field, **Assistant name**. Business name defaults from the organization.
4. **Tone and rules** per bot is a core feature, **staff-only**, layered *under* the fixed grounding and safety rules. Changing it bumps the prompt version and re-runs the eval.
5. **Widget theming**: per-element colours from a picker/palette (never a hex text box), presets chosen in bot settings, with a **live preview beside the form**. Richer, modern "AI" look.
6. **Dashboard accent: blue.** The purple staff accent is removed; staff pages get a small "Platform admin" badge instead.
7. **Streaming is in the MVP** (Batch S). Caching (answer/curated answers, embedding cache) is **post-MVP** (#38).
8. `localhost` is allowed in allowed-domains **outside production**; production rejects it.
9. Chunk delete (#4) is **backlog**. Sources for visitors (#27) is **deferred**.
10. UI/UX is collected during testing and fixed in Batches D/E. **No API, route or state change inside D/E**; any data change belongs to a feature batch.
11. Redesign builds on the already-merged `feat/ui-redesign` (tokens, shell, ⌘K palette, theme provider). No Tailwind, UI library, motion or icon dependency.

## 4. Working rules (from `implementation/WEBSITE-MVP-CLOSEOUT.md` §2)

- Local commits only. Never push, never tag. Fix work on a new branch from `main`, small commits, `merge --no-ff` by the owner.
- Never read or print `.env` / `.env.local` / keys. Coding agents never run docker (the owner runs `make …`).
- Tests only against the disposable DB `saas-test-db` on `127.0.0.1:55462` (names ending `_test`) via `TEST_DATABASE_URL` set per process, never written to a file.
- Report format: **step + what I did + what I saw**.
- Commit trailers (this session): `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01Q9gG5gsC8WP6RhyJQwaP8R`.

---

## 5. Issue register

Class: **P** product bug · **T** test gap · **S** spec/doc error · **E** environment · **U** UI/UX · **F** feature · **D** decision. Severity: **B** blocker, **H** high, **M** medium, **L** low.

| # | Issue | Class/Sev | Fix | Batch |
|---|---|---|---|---|
| 1 | 422 handler returns only "Request body failed validation." (`core/errors.py` ~60-68) | P/H | Return sanitized `details.fields` (`loc` + `msg`, never `input`/`ctx`); UI shows inline errors | A1 |
| 1b | Phone `01…` rejected; strict E.164 (`platform/users.py` 73-88) | P/M | Country-code selector or normalize local numbers to `+20`; hint text | A1 |
| 2 | Revision summary says "40 documents" for 40 pages | U/L | "10 files · 40 pages · 41 chunks" | E |
| 3 | Jobs list shows only "Completed · started HH:MM" | U/L | Show file count and revision link | E |
| 4 | No chunk selection/delete | F/M | **Backlog** (remove a bad file and re-ingest instead) | Backlog |
| 5 | Knowledge page is a stack of sections | U/M | Tabs, file groups, clear hierarchy | E |
| 6 | `?` instead of arrow before "Back to Organizations" (`platform/clients/[clientId]/page.tsx:134`) | U/L | Inline SVG icon | D/E |
| 7 | One shared `reason` state feeds pause-bot, quota override, others (same file, line 26) | P/M | Ask reason in a confirm dialog per action | E |
| 8 | Settings is one 17-field scroll | U/M | Sections: Identity, Appearance (+ live preview), Messages, Contact & handoff, Access, AI; sticky save | E (layout) / C (content) |
| 9 | Bot name vs Assistant name vs Business name | F/M | Merge to Assistant name; business name defaults from org | C |
| 10 | Widget position shows "(none)" | P/M | Real default | A2 |
| 11 | Empty welcome messages | P/M | Fallback welcome | A2 |
| 12 | Bot status draft vs Active | — | Closed: owner activated it. Polish: say why a bot is draft | E |
| 13 | "Start embedding backfill" is a red danger button even when done | U/L | Hide when complete or restyle | C |
| 14 | Widget theming (header, send button, bubbles, text, launcher) | F/H | Per-element colour picker, presets, live preview, contrast checks | C |
| 15 | Bot tone and rules prompt | F/H | New staff-only section under fixed rules; prompt version bump; eval re-run | C |
| 16 | Provider failures swallowed (`chat/service.py` ~403 `except ProviderError: parsed=None`) | P/H | Log status + model (never the key); add to staff trace | A1 |
| 17 | Provider error shown as "could not answer from the knowledge" | P/M | Distinguish provider failure from knowledge gap | A1 |
| 18 | 👍👎 overlap the latency text; "Retry page" is not a chat retry | U/L | Layout fix; real retry of the turn | E |
| 19 | Standard tier = free OpenRouter chain; default tier unclear | D/H | Premium for test; show provider/model per tier; default decided after #37 | A1 |
| 20 | Tier meaning unclear in UI | U/M | Label tiers with provider and model | A1 |
| 21 | `.env.local` CRLF line endings | E/L | Normalize | F |
| 22 | Allowed-domains rejects URLs (scheme/port/path) | P/M | Normalize pasted URL to hostname before validation | A1 |
| 23 | Allowed-domains rejects `localhost` (needs a dot) | P/M | Allow `localhost` when not production | A1 |
| 24 | Two save mechanisms (tier saves instantly, rest needs Save) | U/M | Saved indicator / unsaved-changes cue | E |
| 25 | Dense answer formatting | P/L | Prompt tuning after calibration | B |
| 26 | Answer says "contact support" with empty contact details | U/F | Per-bot readiness checklist (support email/phone, welcome, domains) | C |
| 27 | Sources shown as raw filenames/pages for visitors | D | **Deferred** | — |
| 28 | Trace hides matched and query terms | U/M | Show per chunk | B |
| 29 | Gate drops the right page (min 2 terms, cosine floor 0.50, untuned) | P/H | Calibrate on Nile corpus; ignore store-name/filler words; allow a strong top result through a lower cosine; record in `THRESHOLDS.md` | B |
| 30 | Two versions of each PDF in Downloads (`name.pdf`, `name_1.pdf`) | T/M | Freeze one set as the demo corpus (the ingested `_1` set) | B |
| 31 | Nile `eval.jsonl` (~40 cases) does not exist (current file: 25 synthetic cases) | T/H | Write against the frozen corpus | B |
| 32 | Loader never sends the page origin, so any non-empty allowed-domains list blocks every site | P/**B** | Loader forwards `location.hostname`; frame forwards to `POST /session` as `page_origin` | A2 |
| 33 | Any site can embed (`frame-ancestors http: https:` on widget paths) | P/H | Per-bot CSP `frame-ancestors` from allowed domains | A2 |
| 34 | No end-to-end domain test | T/H | Playwright test with two mapped hostnames | A2 |
| 35 | Answers omit steps across documents | P/M | Evidence assembly and prompt tuning after calibration | B |
| 36 | Two ingest jobs 9 s apart | T/L | Verify no duplicates (see Batch 0 checks); fix only if duplicated | A1 |
| 37 | Tier-matrix test (Standard vs Premium) | T/M | Same battery on both; strict-JSON support, rate limits, fallback, latency | After B |
| 38 | Answer/embedding cache; curated answers | F | **Post-MVP** | Backlog |
| 39 | Streaming answers | F/H | SSE streaming, see Batch S | S |
| 40 | `/widget/v1/loader.js` is 404 in Docker: the web Dockerfile runtime stage copies `.next/standalone` and `.next/static` but not `apps/web/public` | P/**B** | Add `COPY --from=builder --chown=node:node /workspace/apps/web/public ./apps/web/public`; smoke check on the loader URL | A1 (first task) |

Notes
- #40 was found 2026-10-22 from the sample-page console (`GET /widget/v1/loader.js 404`, "Refused to execute script … MIME type text/plain"). The file is tracked in git; only the image is wrong. It also blocks the VPS deploy (Batch G).
- `post_check` in `chat/service.py` is an **unwired hook**; it does not protect answers today. Do not rely on it.

---

## 6. Batches

### Batch 0 — finish core testing (owner, no code)
Run against the Premium tier with the allowed-domains list **empty** (the check is off when empty). Report each item as step + what you did + what you saw.
1. Widget render on `/widget/sample` and on your local `test.html` (needs #40 fixed and rebuilt first).
2. Q&A battery, EN and AR: 3 grounded, 2 abstain, 2 injection per language; near-miss traps (store-name only, wrong product); follow-up questions; handoff and contact capture.
3. Cross-tenant: a second organization with its own bot; ask it things only the first org's documents answer. Expected: abstain, 0 leakage.
4. Hybrid vs `fts_only` comparison on the same set.
5. Ingestion edge cases: same file twice, a bad/corrupt file, retry/cancel, publish and rollback. **#36 check:** the file list shows each of the 10 filenames once; Revisions shows one revision of 40 pages/41 chunks; Published view shows each page once.
6. Roles: member opens `/platform` directly (expect denied); member direct URLs to another tenant (expect denied).
7. Onboarding stopwatch: new organization to a working embedded widget, target ≤ 15 minutes.

### Batch A1 — errors, validation, trust, deploy blocker (API + small UI)
Order inside the batch: **#40 first** (unblocks the widget test), then #1/#1b, #22/#23, #16/#17, #19/#20, #36.
Files: `apps/web/Dockerfile`; `apps/api/app/core/errors.py`; `apps/api/app/platform/users.py`; `apps/api/app/bots/schemas.py`; `apps/api/app/chat/service.py` (error path only); `apps/web/lib/rag-tier-control.tsx`; the settings and members forms.
Acceptance: loader URL returns 200 with a JS content type from the built image; a 422 shows per-field messages and never echoes input; `localhost` accepted outside production and rejected in production; a provider failure appears in the staff trace with status and model and shows visitors a distinct "temporarily unavailable" message.

### Batch A2 — widget embedding (blocker for the widget test with a domain list)
Files: `apps/web/public/widget/v1/loader.js` and `packages/widget/src/loader.js` (**keep identical**); `apps/web/app/widget/frame/page.tsx`; `apps/api/app/widget/{router,service}.py`; `apps/web/next.config.ts`.
- Loader adds the embedding page hostname to the frame URL; the frame sends it as `page_origin` (currently `null`). Server still compares only the hostname.
- Per-bot `frame-ancestors` for widget paths; dashboard paths keep `frame-ancestors 'none'`.
- Real defaults for position (#10) and welcome message (#11).
- Playwright test with two mapped hostnames: allowed host works, other host gets `DOMAIN_NOT_ALLOWED`.

### Batch S — streaming (after A1/A2; may run in parallel with B)
SSE endpoint for chat turns. Model output keeps the strict JSON contract but the **key order becomes `{can_answer, sources, answer}`** so verdict and citations arrive before the text. An incremental JSON parser releases answer text only after `can_answer` is true and every cited evidence id is valid. If parsing fails or the provider cannot stream, fall back to the existing buffered path. Widget uses `fetch` + reader with a **Stop** button; proxy buffering is turned off for the stream route. `chat_answer` (buffered) stays unchanged so the eval runner and existing tests remain valid. Caching is not part of this batch.

### Batch B — retrieval quality (before any prompt change)
Freeze the demo corpus (#30), write the Nile eval (#31, ~40 cases from `docs/19` §5), expose matched/query terms in the trace (#28), calibrate the gate (#29), tune evidence assembly and formatting (#35, #25). Align the drift between code (2 matched terms) and `docs/rag-phase/THRESHOLDS.md` (1). Record the final numbers in `THRESHOLDS.md` and an ADR note.
**Exit gate:** the targets in §2.

### Batch C — bot behaviour and settings features (after B and S)
#15 tone and rules, #9 name merge, #14 widget theming with live preview, #26 readiness checklist, #13 backfill button. Prompt version bump, then re-run the eval and compare with Batch B numbers. Settings keeps its single-request save; a content change here must also handle one-422-saves-nothing (resolved by A1 field errors).

### Batch D — design system foundation (frontend only; parallel from the start of A1)
Reconcile with the merged `feat/ui-redesign`; do not rebuild it. Blue accent, remove the purple staff override (`--staff` accent at `globals.css` ~433-434), base text 16 px, content max-width, type scale, one self-hosted Arabic-capable font via `next/font`, extend `lib/ui.tsx` (Button, Field, FormSection, PageHeader, Tabs, DataTable, Card, StatusBadge, Dialog, Toast), inline SVG icons.

### Batch E — screen-by-screen redesign (after D; no data changes)
Order: Members + Organizations (staff screens have no classNames: `lib/staff-bots.tsx`, `lib/staff-members.tsx`, `app/platform/members/page.tsx`), org Bots page (#7, Create bot as a dialog), Knowledge (#2, #3, #5), Bot settings layout (#8, #24, sticky save), Playground (#18), then Overview, Inbox and the rest.

### Batch F — hygiene
Stage 1 drift list, #21, stray test folders and worktrees, ADR-019 notes, calibrated thresholds, full backend and Playwright rerun.

### Batch G — deploy
Hosting decision (ADR-007), backup/restore drill, secrets, HTTPS and domains, VPS deploy (includes #40 verified on the production image), then client bots activated and tested.

---

## 7. Order and parallelism

```
0 (owner) ─┐
D → E  ────┼── runs alongside everything (frontend only)
A1 → A2 ───┤
           ├→ S ┐
           └→ B ┴→ C → F → G
```
- A1 starts first (#40). A2 follows A1 (shared widget/settings files).
- S and B can run in parallel worktrees: S touches `chat/service.py` (model call path), `providers.py`, the widget frame and the chat router; B touches `retrieval/*`, config, eval and trace. They meet only if both edit `chat/service.py`; B must not.
- C waits for both because prompt and gate changes shift the eval.
- D/E conflicts: E screens that A1/A2 also edit (settings, members) are done **after** A1/A2 merge.

## 8. UI/UX guardrails (do not break the app)

- Keep every `data-testid`, role, label and accessible name. Specs depend on them (`ui-characterization.spec.ts`, `ui-redesign.spec.ts`); the route/selector inventory is in `implementation/UI-REDESIGN-PLAN.md` (outdated in parts, verify against the code).
- Before D starts, take Playwright screenshots of every screen; compare after each screen.
- One screen per commit. Typecheck and run that area's specs each time.
- Plain CSS only (`tokens.css`, `globals.css`); no new dependencies.
- No API, route or state changes in D/E.
- Done per screen: 375, 768 and 1280 px; RTL; dark and light; keyboard use; no console errors.
- Base rules: label above control, hint below, error inline, spacing from tokens, tables scroll and never break words mid-word, logical CSS properties for RTL.
- Widget theming uses CSS variables per slot (header, send button, user/bot bubbles, text, launcher) with contrast checks; the widget stays in its sandboxed iframe.

## 9. Test plan

| Layer | What | Where |
|---|---|---|
| API unit/integration | 422 shape, phone, domain normalize, provider-error path, widget origin check | `apps/api/tests`, disposable DB only |
| Eval | Nile cases EN/AR: grounded, abstain, injection, near-miss; run `fts_only` and hybrid | `apps/api/tests/eval/` |
| Playwright | Loader served, two-hostname domain test, streaming render and Stop, settings save, staff screens | `apps/web` (Chromium, 1 worker, port 3100, stub model) |
| Manual (owner) | Batch 0, then repeat after B and C | Docker stack |

## 10. Traceability

Every issue #1–#40 appears in §5 with a batch. Decisions in §3 map to: 2→#19/#37, 3→#9, 4→#15, 5→#14, 6→D, 7→S/#38/#39, 8→#23, 9→#4/#27.

## 11. Open items

- Wrong-refusal ceiling 10 % to be confirmed after the first calibration.
- Default tier for new bots after #37.
- Hosting choice (ADR-007) for Batch G.
