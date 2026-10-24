# MVP Closeout — Batch Build Prompts

Date: 2026-10-22 · Companion to `MVP-CLOSEOUT-PLAN-2026-10-22.md` (issue numbers #1–#40 refer to its register).
Each prompt below is pasted to a coding agent on its own. Paste the **Standing preamble** first, then one batch prompt.

---

## Standing preamble (paste before every batch)

```
You are working in the repo SAAS-chats-ai on a NEW branch created from main. Rules:
- Local commits only. Never push, never tag, never merge. Small commits, one concern each.
- Commit messages end with these two lines:
  Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01Q9gG5gsC8WP6RhyJQwaP8R
- Never read or print .env, .env.local or any key. Never put a secret in a file or a commit.
- Never run docker or make targets that start containers. The owner rebuilds the stack.
- Tests run only against the disposable database saas-test-db on 127.0.0.1:55462 (database names end in _test). Pass it as TEST_DATABASE_URL in the environment of the process, never in a file.
- Do not change anything outside the files and behaviours listed in your batch. If you find something else wrong, write it in your report; do not fix it.
- Keep every data-testid, role, label and accessible name unchanged unless the batch says otherwise.
- No new dependencies (no Tailwind, UI library, motion or icon packages).
- Finish with a report in this format, one entry per step: "step + what I did + what I saw" (commands run and their real output summary, test counts, files changed). State anything you could not verify.
```

---

## Batch A1 — Errors, validation, trust, widget-asset blocker

**Branch:** `fix/a1-errors-validation` · **Issues:** #40, #1, #1b, #22, #23, #16, #17, #19, #20, #36

**Goal:** the widget loader is served from the Docker image, validation errors tell the user which field is wrong without leaking input, allowed-domains accepts what people actually paste, and provider failures are visible to staff and distinct for visitors.

### Task A1.1 — Serve `apps/web/public` in the production image (#40) — do this first, commit separately
- File: `apps/web/Dockerfile`, runtime stage. It copies `.next/standalone` and `.next/static` only; Next's standalone output does not include `public/`.
- Add `COPY --from=builder --chown=node:node /workspace/apps/web/public ./apps/web/public` after the static copy.
- Do not edit `.dockerignore` (it does not exclude `apps`).
- Add a check script or Playwright/vitest-level test that asserts the repo file `apps/web/public/widget/v1/loader.js` exists and that the Dockerfile contains the public copy line (the agent cannot build images). Document in the report that the owner must verify with `curl -i http://localhost:3000/widget/v1/loader.js` after `make rebuild SVC=web`, expecting `200` and a JavaScript content type.
- Confirm `packages/widget/src/loader.js` and `apps/web/public/widget/v1/loader.js` are identical (diff them); report the result, do not change them here.

### Task A1.2 — Field-level 422 details (#1)
- File: `apps/api/app/core/errors.py` (~lines 60-68). Today the handler returns only the generic message "Request body failed validation."
- Keep the generic `message` and error `code`. Add `details.fields`: a list of `{ "field": "<dotted loc without 'body'>", "message": "<pydantic msg>" }`.
- Never include `input`, `ctx`, `url` or raw values. Strip anything that could echo a password, token or email body.
- Web: find the shared fetch/error helper in `apps/web/lib` and surface `details.fields` as inline messages under the matching input in the forms that already exist (members create, bot settings). If a field has no matching input, show the messages in the form-level error area.
- Tests: API test that posts an invalid phone and asserts `details.fields[0].field == "phone"`, the message is present, and the serialized response contains no submitted value. A web test (existing Playwright/vitest style) that an inline message renders.

### Task A1.3 — Phone input (#1b)
- File: `apps/api/app/platform/users.py` (`CreateUser.phone`, `normalize_phone`, regex `\+[1-9][0-9]{1,14}`). Keep strict E.164 on the API.
- Web (members create form): add a country-code selector defaulting to `+20` plus a national-number input; the form joins them before sending. Hint text: "Enter the number without the leading 0." If a user pastes a number starting with `0` and a country is selected, strip the leading `0`.
- Do not loosen the API validator. Update its message only if a test requires it.

### Task A1.4 — Allowed-domains normalization (#22, #23)
- Files: `apps/api/app/bots/schemas.py` (validator ~lines 73-85, field at line 43); `apps/web/app/app/[tenant]/bots/[botId]/settings/page.tsx` (`onSave`, lowercases lines).
- Normalize each entry before validation (both client and server): trim, lowercase, strip scheme (`http://`, `https://`), strip path/query/fragment, strip port, strip trailing dot. `http://localhost:5500/` → `localhost`.
- Validation: hostnames need a dot, **except** `localhost`, which is accepted only when the app environment is not production (use the existing environment setting in `apps/api/app/core/config.py`; do not read env files). In production `localhost` is rejected with the same style of message.
- Keep `origin_allowed` in `apps/api/app/widget/service.py` comparing hostnames only; an empty list still means "check off".
- Tests: table-driven normalization cases (URL with port and path, uppercase, trailing dot, duplicate entries, `localhost` in non-production vs production, IP addresses stay rejected unless already allowed today).

### Task A1.5 — Provider failures visible, not misleading (#16, #17)
- File: `apps/api/app/chat/service.py`: the model call near line 396 has `except ProviderError: parsed=None` (~403), which turns a provider failure into the "could not answer from the knowledge" reply.
- Log `status`, model name and tier on failure at warning level. Never log keys, headers or the full prompt.
- Add a field to the staff trace (the same trace the Playground shows) such as `provider_error: { status, model }`.
- Return a distinct canned visitor message in `apps/api/app/chat/prompts.py` `CANNED` (there is already a "busy" entry; reuse it if it fits, otherwise add `provider_unavailable`). It must be different from the `cannot_confirm` message.
- Do **not** change `_parse_reply` or the retrieval path. Do not change `chat_answer` signature.
- Tests: stub the model to raise `ProviderError`; assert the visitor message, the trace field, and that no secret appears in logs.

### Task A1.6 — Tier labels (#19, #20)
- Files: `apps/web/lib/rag-tier-control.tsx`, `apps/api/app/embeddings/router.py` (`patch_rag` maps tier to provider), `apps/api/app/chat/models.py`.
- Show the provider and model each tier maps to (Standard → free OpenRouter chain, Premium → OpenAI `gpt-4.1-nano`) under the select, read from the API, not hard-coded in the UI. Add a one-line note that Standard uses free models and may be slower or unavailable.
- Do not change the default tier and do not change which models are used.

### Task A1.7 — Ingest job duplication check (#36)
- Read-only investigation first: from `apps/api` ingestion code, determine whether two uploads in quick succession create two jobs by design (batched upload) or whether one click can enqueue twice. Report the answer with file/line references.
- Only if a double-enqueue is possible, add idempotency (same file hash + same revision → reuse the job) with a test. Otherwise change nothing and say so.

**Acceptance criteria**
1. Dockerfile copies `public`; loader file present; the diff between the two loader copies is reported.
2. An invalid request returns per-field details with no input echo; UI shows them inline.
3. `+20` selector works; API still strict.
4. `http://localhost:5500/` saves as `localhost` outside production; production rejects it.
5. A provider failure appears in the trace and shows a distinct visitor message.
6. Tier select shows provider/model.
7. Backend tests and the Playwright specs for members and bot settings pass (run only with the disposable DB).

**Do not touch:** retrieval, gate, evidence assembly, prompts other than `CANNED`, widget loader/frame (that is A2), CSS design tokens.

---

## Batch A2 — Widget embedding and domain enforcement

**Branch:** `fix/a2-widget-embedding` (from main after A1 is merged) · **Issues:** #32, #33, #34, #10, #11

**Goal:** a bot with an allowed-domains list works on the listed sites and fails on others; unlisted sites cannot frame the widget; the widget has sane defaults.

### Task A2.1 — Forward the embedding page host (#32)
- `apps/web/public/widget/v1/loader.js` builds the frame URL with only `locator` and `v`. Add the embedding page's `location.hostname` as a query parameter (for example `host`). Apply the **same edit** to `packages/widget/src/loader.js`; the two files must be byte-identical afterwards (report `diff` output).
- `apps/web/app/widget/frame/page.tsx` (~line 198) posts `{ page_origin: null }`. Read the host parameter and send it as `page_origin`. The API field `SessionCreateRequest.page_origin` (max 300) already exists.
- Server side: `origin_allowed` in `apps/api/app/widget/service.py` compares the hostname from `page_origin`. Keep that logic; confirm `_host_of` handles a bare hostname as well as a full origin. If it does not, extend it with tests.
- Security note for the report: the host comes from the page and can be spoofed by a non-browser client; the CSP in A2.2 is what protects embedding by browsers. Do not claim the check is authentication.

### Task A2.2 — Per-bot `frame-ancestors` (#33)
- `apps/web/next.config.ts`: dashboard paths use `frame-ancestors 'none'` (lines ~20-26); widget paths use `frame-ancestors http: https:` (~31-44).
- Because `headers()` in `next.config.ts` is static, implement the per-bot value where the frame route can compute it: either set the header in the frame route/page response from the bot's allowed domains (fetched server-side by locator) or via the existing `proxy.ts` extended to the widget frame path. Choose the smallest change and explain it.
- Behaviour: empty list → keep permissive (`http: https:`) so unconfigured bots still work in testing; non-empty list → `frame-ancestors` lists only those hosts (both `http://` and `https://` forms, and the port wildcard for `localhost` outside production).
- Keep the sandbox attribute `allow-scripts allow-same-origin allow-forms` unchanged.
- Do not alter dashboard CSP.

### Task A2.3 — Defaults (#10, #11)
- Position: if the stored value is null, the API config returns the default (bottom-right) and the settings UI shows it selected, not "(none)".
- Welcome message: if empty, the widget shows the existing `hello_default` canned text from `chat/prompts.py`. Do not require staff to fill it.

### Task A2.4 — End-to-end test (#34)
- Playwright (Chromium, 1 worker, port 3100, stub model): serve two static pages on different hostnames (use `127.0.0.1` and `localhost` mapping, or a `--host-resolver-rules` launch arg in the test config) that each embed the loader for the same bot. Bot allows only one.
- Assert the allowed host shows the launcher and an answer; the other host gets the blocked state (`DOMAIN_NOT_ALLOWED` handled with a safe message). Add a case with an empty list (both work).
- Do not run docker; use the existing Playwright web server config.

**Acceptance criteria:** loader copies identical; session creation carries the page host; allowed host works, other host is refused; CSP differs by list state; defaults show; new Playwright test passes with existing specs.

**Do not touch:** retrieval, prompts, CSS tokens, Docker files.

---

## Batch S — Streaming answers

**Branch:** `feat/s-streaming` (from main after A1/A2) · **Issue:** #39 · **Decision:** streaming is in the MVP; caching is not.

**Goal:** visitors see the answer appear as it is generated, with no loss of grounding guarantees and with a safe fallback to today's buffered reply.

### Design (fixed)
- Transport: Server-Sent Events from a new streaming chat endpoint next to the existing chat route in `apps/api`. The existing buffered endpoint stays.
- Model output contract stays strict JSON but key order changes to `{ "can_answer", "sources", "answer" }` (update `SYSTEM_TEMPLATE` in `apps/api/app/chat/prompts.py` and bump the prompt version constant). Verdict and citations arrive before text.
- Incremental parser: a small streaming JSON reader that emits events: `verdict(can_answer)`, `sources([...])`, then `delta(text)` chunks of `answer`, then `done`.
- Release rules (same guarantees as `_parse_reply`, lines ~175-202): do not emit any `delta` until `can_answer` is true **and** every id in `sources` is a valid evidence id **and** at least one citation exists. If `can_answer` is false or validation fails, emit the canned `cannot_confirm` message as a single event and no model text.
- Fallback: if the provider does not stream, returns malformed JSON, or the parser errors before release, run the existing buffered path and send the result as one `done` event.
- `chat_answer` (buffered) must remain unchanged in behaviour; the eval runner (`apps/api/tests/eval/runner.py`) and existing tests depend on it. Share the retrieval, gate and evidence steps by calling the same helpers; do not duplicate or modify them.

### Tasks
- **S.1 Provider streaming:** `apps/api/app/chat/providers.py` (`OpenAICompatibleModel`) gets a streaming method (`stream=True`) with the same model/fallback/blocked logic. Provider errors before the first byte may fall back; after release begins, send an `error` event with a safe message.
- **S.2 Parser + validator:** new module under `apps/api/app/chat/` with unit tests: split chunks mid-token, escaped quotes and unicode (Arabic), keys out of order (treat as invalid → fallback), duplicate keys, truncated stream.
- **S.3 Endpoint:** SSE route with the same auth/session/origin checks as the buffered chat route; per-turn persistence (message, sources, latency) written at `done`; stream cancel (client disconnect) stops the provider call and does not persist a partial answer as final.
- **S.4 Proxy and headers:** `apps/web/next.config.ts` rewrites `/api/:path*`. Ensure the stream is not buffered: response headers `Cache-Control: no-cache, no-transform`, `X-Accel-Buffering: no`, and verify compression does not hold chunks (report how you verified; if Next's rewrite buffers, add a dedicated route handler that pipes the body).
- **S.5 Widget client:** `apps/web/app/widget/frame/page.tsx`: use `fetch` + `ReadableStream` reader (not EventSource, to send POST and headers). Render deltas into the current bubble, show a **Stop** button that aborts the request, keep the existing typing indicator until the first delta, keep accessible live-region behaviour (announce on `done`, not per delta), and show sources only as today. If the stream fails before any text, fall back to the buffered endpoint once.
- **S.6 Staff trace:** include `streamed: true/false` and time-to-first-token in the trace.
- **S.7 Tests:** API tests with a stub streaming model (including the failure cases above); Playwright test with the stub model: text appears progressively, Stop works, fallback path works.

**Acceptance criteria:** no text reaches the visitor before verdict + valid citations; abstain and injection cases behave exactly as buffered (run the eval through `chat_answer`, unchanged, and a streaming-path equivalent on the same cases, report both); Stop works; fallback works; no new dependency.

**Do not touch:** `retrieval/*`, gate thresholds, CSS tokens, settings forms.

---

## Batch B — Retrieval quality calibration

**Branch:** `fix/b-retrieval-calibration` · **Issues:** #30, #31, #28, #29, #35, #25

**Goal:** meet the exit targets on the Nile Home Goods corpus. Measure first, change second.

### Tasks
- **B.1 Freeze the corpus (#30):** Downloads holds two variants per PDF (`name.pdf`, `name_1.pdf`). The ingested set is the `_1` set. Copy that set into the repo test fixtures (a folder under `apps/api/tests/eval/` such as `corpus/`) with a short README stating the origin and a SHA-256 list. Do not alter the PDFs. Never commit anything from `.env*`.
- **B.2 Write the eval (#31):** a new file next to `eval.jsonl` (keep the existing 25-case file untouched) with about 40 Nile cases following `docs/19-CHATBOT-STRATEGY-AND-MANYOSIRISCHAT-PLAN.md` §5: grounded (EN and AR in matching pairs), abstain (EN and AR), prompt injection, near-miss traps (store-name only, similar product, wrong policy), and follow-ups. Each case: question, language, expected behaviour (`grounded` | `abstain` | `injection`), expected source file(s)/page(s) for grounded cases.
- **B.3 Trace visibility (#28):** extend the staff trace to show, per candidate chunk: query terms, matched content terms, cosine score, FTS score, and gate decision with the reason (which rule passed or failed). Source: `apps/api/app/retrieval/gate.py`, `hybrid.py`, `service.py` (`score_lexical`, `assemble_evidence`), `query.py` (`term_queries`, `build_tsquery`). Read-only data surfaces; no behaviour change in this task.
- **B.4 Baseline run:** run the new eval in `fts_only` and hybrid, on Premium (the owner supplies the key in the environment; never read it). Save results under the eval folder with the date. Report grounded %, abstain %, injection %, Arabic-vs-English gap, wrong-refusal %.
- **B.5 Calibrate the gate (#29):** current rule: passes if cosine ≥ 0.50 **or** at least 2 matched content terms (`RETRIEVAL_FTS_MATCH` 0.01). Known failure: the right shipping page matches only one content term and its cosine is under the floor, while a weaker page is kept. Investigate options, one at a time, re-running the eval after each: (1) ignore store-name and filler words when counting matched terms; (2) let the top fused result through at a lower cosine when it is clearly ahead of the second; (3) tune the floor. Keep the change that moves the numbers without raising wrong answers on abstain/injection/near-miss cases. Settings live in `apps/api/app/core/config.py` (~106-120).
- **B.6 Evidence and formatting (#35, #25):** after B.5, check cross-document step omission (the evidence set uses `retrieval_final_k` = 4 from `decision.passed[: retrieval_final_k]`, `chat/service.py` ~297-298) and answer formatting (prompt asks for short paragraphs and hyphen bullets but adherence is weak). Make the smallest prompt/evidence change that fixes it, and bump the prompt version.
- **B.7 Docs:** record final thresholds and the drift fix between code (2 terms) and `docs/rag-phase/THRESHOLDS.md` (1); add an ADR note in `DECISIONS.md` (ADR-019 area) summarizing the measurements.

**Acceptance criteria:** grounded ≥ 90 %, abstain ≥ 95 %, injection 100 %, Arabic within 5 points of English, hybrid better than `fts_only`, wrong-refusal ≤ 10 % (propose the ceiling if the data says otherwise and explain). Every threshold change is backed by a before/after table in the report.

**Do not touch:** UI files, widget, streaming code, the unwired `post_check` hook (report if you think it should be wired, do not wire it).

---

## Batch C — Bot behaviour and settings features

**Branch:** `feat/c-bot-settings` (after A1, A2, S, B are merged) · **Issues:** #15, #9, #14, #26, #13

### Task C.1 — Tone and rules (#15)
- Staff-only. Add a per-bot text field `tone_and_rules` (migration with Alembic; nullable; length cap, e.g. 2000 chars) editable only by platform staff (reuse the existing staff-vs-member permission pattern used for knowledge; members must get 403 server-side, not just a hidden UI).
- Prompt: add a section in `system_prompt(...)` (`apps/api/app/chat/prompts.py`) **after** the fixed grounding and safety rules, with a heading that states these instructions cannot override the grounding or safety rules above. Escape or fence the staff text; treat it as untrusted relative to the rules.
- Bump the prompt version. Re-run the Batch B eval with the field empty (must equal the Batch B numbers) and with a sample tone (grounded, abstain and injection must not drop).
- UI: staff-only section in bot settings with a textarea, character counter, and a short guidance text.

### Task C.2 — Merge names (#9)
- One field, **Assistant name**. Business name defaults from the organization name and stays editable. Remove the duplicate Bot name field from the settings UI; keep the stored columns working (read the old value as a fallback, write to the one field). No data loss; migration/backfill if needed with a test.

### Task C.3 — Widget theming (#14)
- Theme slots: header, send button, user bubble, bot bubble, text, launcher. Presets (a handful of curated looks, including a modern dark/glass style) selectable in bot settings, plus per-slot colour pickers (a palette and picker, never a free hex text box as the only control).
- Live preview beside the form that renders the same widget markup/CSS with the draft values; the saved config is applied to the widget through CSS variables in the sandboxed frame.
- Contrast check: warn (or auto-pick readable text) when a text/background pair is below WCAG AA.
- API: extend the bot widget settings schema with validated colour values (hex only, server-validated) and a preset id; `widget_config` in `apps/api/app/widget/service.py` returns them. Widget frame applies them; defaults equal today's look.

### Task C.4 — Readiness checklist (#26)
- Per-bot checklist on the bot overview/settings: support email or phone set, welcome message, allowed domains (or "open" warning), knowledge published, tier chosen. Read-only computed on the API; links to the right section.

### Task C.5 — Backfill button (#13)
- `apps/web/lib/rag-tier-control.tsx`: hide the "Start embedding backfill" danger button when nothing needs backfilling; when needed, use the normal style and keep the ConfirmAction.

**Acceptance criteria:** eval numbers unchanged with empty tone; members cannot read or write `tone_and_rules` through the API; theme round-trips and the preview matches the widget; checklist reflects real state; Playwright specs for settings pass.

**Do not touch:** gate thresholds, streaming internals, global design tokens (D).

---

## Batch D — Design system foundation (frontend only)

**Branch:** `feat/d-design-system` (can start with A1) · **Issues:** #6 and design tasks

**Goal:** finish the system the merged `feat/ui-redesign` started, without changing behaviour.

### Before any change
- Read `apps/web/app/tokens.css`, `globals.css` (1608 lines), `lib/ui.tsx`, `lib/theme.tsx`, `playwright.config.ts`, `ui-characterization.spec.ts` and `ui-redesign.spec.ts`. List which shared components already exist (there are four) and which `data-testid`s the specs use.
- Capture a baseline: Playwright screenshots of every route at 375, 768 and 1280 px, light and dark. Commit them under a baseline folder only if the repo already tracks screenshots; otherwise keep them out of git and refer to them in the report.

### Tasks
- **D.1 Tokens:** base text 16 px (currently ~14.8 px), content max-width, a clear type scale, one blue accent. Remove the purple staff accent override (`--staff` set as accent at `globals.css` ~433-434); mark staff areas with a small "Platform admin" badge in the shell instead.
- **D.2 Font:** one self-hosted Arabic-capable font through `next/font`, applied to dashboard and widget so both languages look consistent. No external font requests at runtime.
- **D.3 Base rules:** label above control, hint below, error inline, spacing from tokens, tables scroll and never break words mid-word, logical properties for RTL.
- **D.4 Components in `lib/ui.tsx`:** Button, Field, FormSection, PageHeader, Tabs, DataTable, Card, StatusBadge, Dialog, Toast. Each accepts and forwards `data-testid`, `aria-*`, `className`. Keyboard and focus handling for Dialog, Tabs, Toast.
- **D.5 Icons:** a small inline-SVG icon set in a local file (no package). Replace emoji and glyph characters used as icons (`?` arrow in `platform/clients/[clientId]/page.tsx:134`, 👍👎, 💬) with icons that keep the same accessible names.
- **D.6 Verification:** typecheck, lint, the two UI specs, and screenshot comparison; fix any differences that are not intentional.

**Acceptance:** all existing specs pass untouched; no API/route/state change (`git diff --stat` shows only `apps/web` styling/components); no new dependency (report `package.json` diff = none); per-screen done list in the plan §8.

**Do not touch:** `apps/api`, route files' logic, form state.

---

## Batch E — Screen-by-screen redesign

**Branch:** `feat/e-screens-<screen>` per screen (after D; screens that A1/A2 also touch only after those merge) · **Issues:** #2, #3, #5, #7, #8, #12, #18, #24 and layout polish

**Rule for every screen:** one commit per screen; typecheck + that area's Playwright specs after each; compare screenshots with the D baseline; no API, route or state change. If a screen needs new data, stop and report; it becomes a feature task.

**Order and scope**
1. **Members and Organizations** (`app/platform/members/page.tsx`, `lib/staff-members.tsx`, `lib/staff-bots.tsx`, org list): add classNames (staff screens have zero), DataTable with wrapped cells, tidy filters, StatusBadge.
2. **Organization detail / Bots** (`app/platform/clients/[clientId]/page.tsx`, 543 lines): #7 replace the single shared `reason` state (line 26; inputs at ~238-266 and ~414-461) with a confirm Dialog per action holding its own reason field; Create bot as a Dialog; consistent spacing; explain why a bot is draft (#12).
3. **Knowledge:** #5 tabs and file groups; #2 summary "10 files · 40 pages · 41 chunks"; #3 jobs list with file count and revision link. Display-only changes to labels using data already returned by the API; if a count is not in the response, show it from existing fields or report.
4. **Bot settings** (`app/app/[tenant]/bots/[botId]/settings/page.tsx`, 399 lines): group into sections (Identity, Appearance, Messages, Contact & handoff, Access, AI), sticky save bar, #24 saved/unsaved indicator that distinguishes the instantly-saved tier from the form. Keep the **single `onSave` PATCH** behaviour exactly. Appearance gets its final content in Batch C; leave a clearly marked section.
5. **Playground:** #18 fix 👍👎 overlap with latency; replace the "Retry page" banner action with a real retry of the last turn only if the existing handler already supports it, otherwise label it honestly and report.
6. **Overview, Inbox, remaining pages.**

**Per-screen done list:** 375/768/1280, RTL, dark and light, keyboard only, no console errors, selectors preserved.

---

## Batch F — Hygiene

**Branch:** `chore/f-hygiene`
- Stage 1 drift list from `implementation/WEBSITE-MVP-CLOSEOUT.md`: reconcile each item and report.
- #21: normalize `.env.local` line endings only by telling the owner the command; the agent must not open the file.
- List stray test folders and worktrees (`.test-storage*`, `.pytest-tmp*`, `.worktrees`); propose removal, do not delete without the owner's approval.
- ADR-019 notes and calibrated thresholds in docs.
- Final full backend test run and full Playwright run (disposable DB only). Report counts.

---

## Batch G — Deploy (owner-led; the agent prepares)

- Decide hosting (ADR-007). Write the VPS runbook: build images, environment variable names (no values), HTTPS and domains, reverse proxy rules for the SSE route (buffering off), backup/restore drill steps, rollback.
- Verify on the **production image**: `/widget/v1/loader.js` returns 200 JavaScript (#40), widget loads on a real client domain, allowed-domains and `frame-ancestors` behave, streaming works through the proxy.
- Then: activate client bots, run the Batch 0 battery on each, and run the tier-matrix test (#37) before choosing the default tier.

---

## Owner checklist after each merge
1. `make rebuild SVC=web` (and `SVC=api` when API changed). Agents never run this.
2. Re-run the Batch 0 items touched by the batch.
3. Report to the triage layer in the format "step + what I did + what I saw".
