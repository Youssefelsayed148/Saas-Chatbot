# UI polish track: gaps, batches, frontend/backend split

Date: 2026-10-25. Status: **plan approved in chat by the owner; no batch started.**
Branch: `feat/ui-polish` (create from the clean `feat/rag-hardening-h1-h3` HEAD in Batch 1).
Companion file: `implementation/UI-POLISH-PROMPTS.md` (one prompt per batch, for clean sessions).
Builds on `implementation/UI-REDESIGN-PLAN.md` (S1-S7 shell, tokens, route and test inventory). That file's route/selector inventory stays the contract for tests.

## Owner decisions (2026-10-25)

1. Registration is turned off in the UI and the API (both). Accounts are created only by platform staff (ADR-021).
2. Platform staff keep every staff-only surface (AI costs and limits, RAG operator panel, tone and rules, diagnostics). They are redesigned, not hidden. Client roles must not reach them (UI and API).
3. Inbox and Conversations merge into ONE module with tabs (Inbox | History). Existing routes keep working.
4. A chart library is approved (Recharts, exact pinned version). Small read-only, tenant-scoped backend endpoints are approved where a chart needs data.
5. The screenshots were deliberately zoomed out. Text size and side margins are not gaps.

## Common rules (every batch)

- Source of truth order: latest owner instruction > docs/ > DECISIONS.md > repo code/tests (AGENTS.md).
- Frontend presentation only unless the batch lists backend work. Preserve routes, query params, forms, validation, role restrictions, API contracts, error behaviour and the Playwright selectors/test ids in `UI-REDESIGN-PLAN.md`.
- Before frontend code: read the applicable Next.js guides in `apps/web/node_modules/next/dist/docs/` (apps/web/AGENTS.md).
- Tenant scope on every tenant-owned query; hidden resources return 404; every new endpoint gets tenant A/B tests. Alembic only; none of these batches should need a migration (read-only aggregates). Stop and ask if one appears necessary.
- Charts: colours come from CSS tokens (dark and light), respect `prefers-reduced-motion`, expose a text/table alternative, never colour-only meaning, RTL-safe. Load the `dataviz` skill before chart code if available.
- Use only disposable test databases. No push, merge, deploy, paid API calls or cloud resources. Do not read or print `.env` or keys.
- Do not commit until the owner approves at the batch gate; commits are local. Co-author trailer per the session reminder.
- Record exact commands and real outcomes in PROGRESS.md (append only). Never fabricate results. If a test cannot run, say so.
- Stop at each batch gate for owner sign-off. Stop on blocking ambiguity or an OPEN decision in DECISIONS.md.

## Subagent protocol (every batch)

The batch session is the **orchestrator and integrator**. It may use the Agent tool to parallelise independent work; the batch prompt names the intended split. Subagents do not see the conversation, so every subagent prompt is self-contained.

Orchestrator duties
- Phase 1, alone: read the batch inputs, then define the contracts the agents will share (types in `apps/web/lib/api.ts`, primitive props, endpoint shapes, test-id lists) and edit the shared files first. Shared files are edited only by the orchestrator (or one named owner, in order, before fan-out): `lib/ui.tsx`, `lib/api.ts` types, `tokens.css`, `globals.css`, `lib/app-header.tsx`, `DECISIONS.md`, `PROGRESS.md`, `docs/*`, `package.json`/lockfile.
- Phase 2, fan-out: spawn independent agents in ONE message so they run in parallel (background). Use `Explore` for read-only mapping/audits (state the thoroughness) and `general-purpose` for implementation. Do not spawn for small edits (about 3 files or fewer) and keep at most 4 agents at once.
- Phase 3, integrate: read every diff yourself, resolve overlaps, run typecheck and lint.
- Phase 4, verify: only the orchestrator runs the full Playwright suite and the combined test runs, and records results in PROGRESS.md. Record only what you observed. A subagent's "done" or "tests pass" is a claim: re-run the command or label it "reported by subagent, not re-run".
- Phase 5, report at the gate.

Every subagent prompt must contain
1. The goal and the batch gap IDs it covers.
2. Its **write scope**: the exact files/directories it may edit. No two agents share a file. Everything else is read-only for it.
3. The contracts to assume (props, types, endpoint shapes, test ids to preserve) copied in, not referenced from the chat.
4. The Common rules in short form: tenant scope and A/B tests, no migrations, no `.env` reads, no paid calls, no push/merge, **no commits**, no spawning further agents, real results only, stop and report on blocking ambiguity.
5. Test limits: it may run `tsc`, lint and targeted unit tests for its own files. It must not run the full Playwright suite. Backend agents each use their own disposable database (a distinct database name on the same disposable server) and run one pytest process at a time; the orchestrator runs the final combined pass on its own database.
6. The return format: files changed, exact commands run with a short factual outcome, open questions, anything it noticed outside its scope (reported, not fixed).

Isolation: prefer disjoint write scopes in the same tree. Use `isolation: "worktree"` only if overlap is unavoidable, and then the orchestrator merges the result explicitly.

## Frontend vs backend split

| Area | Frontend | Backend (read-only, tenant-scoped) |
|---|---|---|
| Widget | B1: frame/loader sizing, scrollbar, test | none |
| Auth/entry | B2: landing, login, `/register` redirect | B2: test that default config refuses registration (code already returns 403 `INVITATION_REQUIRED`) |
| Design system | B2: primitives, link-to-button sweep, focus-visible | none |
| Analytics data | B4 consumes | B3: tenant time series, previous-period comparison, question grouping, cost/token clarity, quota "at limit" vs "approaching" |
| Dashboards | B4: Overview, Bot overview, Insights + charts | (B3) |
| Inbox/History | B5: module with tabs, list/detail layout, row actions | B3: inbox list total count, optional date filters, row fields needed by History |
| Settings/forms/bots | B6: AI limits/costs, bot settings, readiness, bots list, org list | none (staff diagnostics reuse existing endpoints) |
| Hygiene/QA | B7: hide empties, consistency, a11y/RTL/light-theme pass, docs | none |

## Gap register

IDs are used by the prompts. "Evidence" = owner screenshot number from the review.

### Widget (B1)
- W-1 Open panel is ~250px tall: thread is a sliver, "Leave your details" and header take the space, composer clipped (screenshot 13). The #113 test passes on mocks, so the real case is untested. Leading hypothesis (unverified): `html,body{height:100%}` + `.widget-frame{position:absolute;inset:0}` make `document.documentElement.scrollHeight` equal the iframe's own current height, so the first small `chatbot:size` value sticks and overrides the loader's 600px. Reproduce first.
- W-2 Native scrollbar with arrow buttons inside the thread.
- W-3 Add a regression test that uses the real loader + frame (not only a mocked layout) including the lead-form open state and a short viewport.

### Entry and auth (B2)
- A-1 Landing `/` hardcodes a Register link and a stray "·" between links.
- A-2 Landing shows the developer placeholder "Application foundation".
- A-3 `/register` still reachable; redirect to `/login` (invitation acceptance keeps working). API: flag `self_serve_signup=false` already returns 403; add/confirm a test for the default config. Owner action: check the local `.env` does not set the flag on.
- A-4 Login screen UX (review the real screen; not yet screenshotted): layout and brand panel, password show/hide, inline field errors, loading state, "contact your administrator" hint (no email reset per ADR-021).

### Design system (B2, used by all later batches)
- D-1 Underlined text links used as buttons: "Open", "Account", "Fix", "View inbox", "Create organization", "Platform admin", "Tenant data and audit", "Open bot", date-as-link in tables.
- D-2 Focus ring appears on the active sidebar item and on the whole main region after navigation. Use `:focus-visible`; keep keyboard visibility; keep the skip link.
- D-3 Stat tiles: trailing colons ("Total:"), filler subtitle "Current inbox", no delta/sparkline support.
- D-4 Readiness pills ("To do/Check/Done") look like buttons.
- D-5 Missing primitives: LinkButton variants, Switch, ColorField, LimitField (unit, stepper, "Uncapped" placeholder, used/limit meter), Meter, SectionNav, StickyActionBar, chart wrappers (trend, donut, bars) using tokens.
- D-6 Unequal action weight (blue filled Save vs red outlined Reset): define primary/secondary/ghost/danger/icon.
- D-7 Add the Recharts dependency (exact pinned version; check React 19.3 peer range with `npm view`), ADR in DECISIONS.md.

### Backend data (B3)
- BE-1 Tenant time series: `GET /api/v1/tenants/{id}/analytics/timeseries?from&to` returning per-day conversations, handoffs, resolved (and visitor/AI message counts if cheap), website source only like the existing handoff endpoint.
- BE-2 Handoff analytics previous-period comparison (same length window immediately before) so the UI can show deltas.
- BE-3 Top/unanswered questions: group near-duplicates (case, trailing punctuation, whitespace, Arabic diacritics/alef variants) so "how can i return an item?" and "...item" count once. Keep display text of the most recent variant.
- BE-4 Cost telemetry: events with unreported cost must not be summed as `$0`; expose an explicit unreported count/flag per row (check current `ragCosts` shape first; may already be present and a frontend fix only).
- BE-5 Token numbers: `quota.measured_tokens_this_month` (12,665 in the review) disagrees with the RAG usage `monthly_tokens` (97,647) and `monthly_embedding_tokens` (45,832). Find the definitions; either unify or label precisely. Report to the owner if they are different by design.
- BE-6 Inbox list for History: add `total` count, optional `created_from`/`created_to`, and make sure each row carries contact name, last message preview, status, channel, mode, bot id (for the existing bot-scoped delete). No new write paths.
- BE-7 Quota warnings: distinguish "at limit" (used >= limit) from "approaching" so 1/1 does not read "Approaching".
- BE-8 Registration: default-config test only (see A-3).

### Dashboards (B4)
- H-1 Tenant Overview has no chart: add conversations-over-time area chart (BE-1) and outcomes donut.
- H-2 KPI cards: remove filler "Current inbox"; show delta where available.
- H-3 Recent conversations: title is the bot's last reply, duplicates appear, Arabic row alignment differs from its meta. Use contact name + preview + status badge, `dir="auto"` per item.
- H-4 Completed "Get started" checklist stays forever: hide when done.
- H-5 Plan usage is repeated on Overview and Bots and the 1/1 warning wording is wrong (BE-7); the "Plan limits are provisional" disclosure is REQUIRED by the UI plan: keep it, make it a compact footnote.
- H-6 Staff-only health alert on Overview when the readiness check says recent model calls failed.
- H-7 Bot overview: daily volume is a one-row table -> chart.
- H-8 Bot overview rates show "1" (should be 100%), "2408 ms" -> "2.4 s", engagement/unanswered formatting.
- H-9 Reply-length distribution raw text -> bars.
- H-10 Unanswered list shows near-duplicates (BE-3).
- H-11 Insights: page title "Handoff analytics" vs nav "Insights"; unify.
- H-12 Insights kv rows -> donut (outcomes), bars (channel, workload), stacked bar (sentiment). Hide cards with no data instead of empty-state cards.
- H-13 Insights ignores a period: add 7/30/90 day selector (API already takes from/to) and previous-period deltas (BE-2).
- H-14 Staff panel (RagOperatorPanel) keeps its slot on Insights; its redesign is F-1/F-2 in B6.

### Conversations module (B5)
- I-1 Inbox and Conversations overlap: one module "Conversations" with tabs Inbox | History. Sidebar shows a single item. Existing routes (`/inbox`, `/inbox/[id]`, `/conversations`, `/bots/B/conversations`, detail) keep working; `/conversations` becomes the History tab.
- I-2 Inbox: stat tiles + search + filters push the first conversation ~700px down while the right pane is empty. Tiles become filter tabs/chips with counts (Waiting, Mine, Unread, All); compact toolbar; More filters in a popover.
- I-3 List scrolls on its own, starts at the top; detail pane fills the height; a smaller empty state.
- I-4 List item: avatar/initials, name, preview, time, unread dot, status badge; RTL per item.
- I-5 History: search, status/channel filters, pagination, total (BE-6), row click, preview.
- I-6 Heavy red Delete on every row -> overflow menu + existing ConfirmAction; keep `delete-${id}` test ids reachable.
- I-7 Retention card sits above the list and shows a greyed "30" (unclear if saved): collapsible "Data retention" in History showing the saved value; keep `retention-input/save/saved` ids.

### Settings, forms, bots (B6)
- F-1 AI costs and limits: 7 stacked empty full-width inputs -> grouped LimitField rows (Content / Monthly usage / Embedding) with used, meter, "Uncapped" placeholder; Save bar only when dirty; Reset as secondary with confirm.
- F-2 Cost telemetry bullets -> compact table (stage, model, tokens, cost, "cost unreported") with BE-4 semantics.
- F-3 Bot settings: one long single-column form -> SectionNav (Identity, Appearance, Messages, Handoff, Access, AI) + sticky Save bar + dirty state.
- F-4 Widget colour hex text box -> ColorField (picker + hex + contrast result).
- F-5 "Human handoff enabled" checkbox -> Switch.
- F-6 Two save models (form Save and instant "AI tier saves instantly" box) -> one coherent pattern with clear feedback.
- F-7 Retrieval mode, active embedding model, backfill state -> staff-only collapsible "Diagnostics".
- F-8 Launch readiness: "5/7 ready" meter, failing items first, "Fix" as buttons, non-interactive status badges (D-4), failing-model banner promoted.
- F-9 Messages/Handoff/Access sections: group related fields (two-column on wide, one on narrow), placeholders and helper text, character counters; staff-only "Tone and rules" stays staff-only.
- B-1 Bots list: table -> cards (status, plan usage compact, last activity if available); remove duplicate "Open bot" link; "Contact us to add or change bots" -> "Request a change" button.
- B-2 Organizations list: "Open", "Create organization", "Platform admin" as buttons.
- B-3 Verify client roles cannot reach staff-only surfaces by URL (UI and API); add tests if missing.

### Consistency and hygiene (B7)
- X-1 Token number consistency across Overview, Bots, Insights (BE-5).
- X-2 Local config, not code: the AI tier box showed `gpt-4.1-nano`; repo default and `.env.example` are `gpt-5.4-nano` (gpt-4.1-nano is deprecated). Owner to update their local `.env`; do not read it.
- X-3 Hide anything with no value: empty cards, repeated warnings, internal wording ("Measured provider tokens" only for staff), completed onboarding.
- Q-1 Playwright suite green with preserved selectors; new tests per batch.
- Q-2 Light theme, RTL, 375px and 1280px checks for every redesigned page, including charts.
- Q-3 Docs: docs/10 (client dashboard), docs/18 (expected behaviour) for Register/landing and the Inbox+History module; PROGRESS.md entries.

## Batches

| Batch | Name | Type | Depends on | Gaps |
|---|---|---|---|---|
| B1 | Widget panel fix | FE + loader | none | W-1..W-3 |
| B2 | Foundation: primitives, auth, link sweep | FE (+1 backend test) | none | A-1..A-4, D-1..D-7, BE-8 |
| B3 | Backend analytics and list data | BE | none (can run in parallel with B1) | BE-1..BE-7 |
| B4 | Dashboards and charts | FE | B2, B3 | H-1..H-14, X-1 part |
| B5 | Conversations module (Inbox + History) | FE | B2, B3 | I-1..I-7 |
| B6 | Settings, forms, bots, organizations | FE | B2 | F-1..F-9, B-1..B-3 |
| B7 | Hygiene, consistency, QA, docs | FE + docs | B1-B6 | X-1..X-3, Q-1..Q-3 |

Gate after every batch: owner reviews screenshots/diff and signs off before the next session starts.

## Batch acceptance (summary; full prompts in UI-POLISH-PROMPTS.md)

- B1: with the real loader on the sample page the open panel is bounded (about 70-80% of viewport height up to a cap), the thread is readable and scrolls, composer fully visible with the lead form open and closed, at 1920x1140, 1280x800, 375x667, and RTL. New failing-first Playwright test. Served copy `apps/web/public/widget/v1/loader.js` regenerated and `npm run check:public-asset` passes.
- B2: `/` has no Register and no placeholder headline; `/register` redirects; login screen redesigned; no underlined text link acts as a button anywhere; focus ring only on keyboard focus; primitives documented in a short comment block and used by at least one page each; Recharts pinned and ADR recorded.
- B3: new/changed endpoints typed, tenant A/B tested, no migration; grouping/unreported/at-limit behaviours covered by tests; token mismatch explained in PROGRESS.md.
- B4: three dashboards show real charts from measured data with text alternatives, deltas, period selector, formatted rates, hidden empties.
- B5: single "Conversations" nav item; tabs Inbox | History; old URLs work; Inbox first row visible without scrolling; History search/filter/paginate/delete-with-confirm/retention.
- B6: forms sectioned with sticky save, pickers/switches, AI limits and costs readable; staff panels intact; client cannot reach them.
- B7: no empty/redundant blocks, consistent naming, full Playwright run recorded, docs updated, owner-facing screenshot set.
