# UI polish: batch prompts for clean sessions

Paste ONE prompt per fresh session, in order (B1 and B3 are independent and may run in either order or in parallel worktrees; B2 before B4/B5/B6; B7 last).
Plan and gap IDs: `implementation/UI-POLISH-PLAN.md`. Each session ends at the gate: report, wait for owner sign-off, commit locally only if the owner says so.

---

## B1 - Widget panel fix

```
You are executing Batch B1 (widget panel fix) of the UI polish track in D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai.

Read first, in this order: AGENTS.md, apps/web/AGENTS.md (and the Next.js guides it names), implementation/UI-POLISH-PLAN.md (Owner decisions, Common rules, gaps W-1..W-3), docs/09-WIDGET-SPECIFICATION.md, implementation/UI-REDESIGN-PLAN.md (widget sections), packages/widget/src/loader.js, apps/web/app/widget/frame/page.tsx, apps/web/lib/widget-styles.ts, apps/web/tests/widget-layout.spec.ts, apps/web/tests/widget.spec.ts.

Setup: if branch feat/ui-polish does not exist, create it from the current clean HEAD (git switch -c feat/ui-polish). The two untracked UI-POLISH docs stay untracked.

Problem (owner screenshot): on /widget/sample the open widget panel is only ~250px tall. The header and the "Leave your details" button fill it, the message thread is a sliver with native scrollbar arrows, and the composer is clipped at the bottom, so the user cannot read the conversation. The existing #113 test passes because it mocks the network and asserts different geometry.

Leading hypothesis, UNVERIFIED: the frame sets html,body{height:100%} and .widget-frame{position:absolute;inset:0}, so document.documentElement.scrollHeight equals the iframe's own current height. announceSize() therefore reports the iframe's current height back to the loader, and the first small value (sent before the thread renders) sticks and overrides the loader's 600px default.

Do, in order:
1. Reproduce in a real browser (chrome-devtools or playwright) against the running app on the sample page with the real loader, at 1920x1140, with a conversation that has several messages and the lead form open and closed. Capture the iframe height, the chatbot:size messages and the computed layout. Write down the actual root cause with evidence. Do not edit before this.
2. Write a failing-first Playwright test (new file or extend widget-layout.spec.ts) that uses the real loader.js and /widget/frame (mock only the public API network edge), asserts: panel height is bounded and at least a readable minimum, thread has a visible height of at least ~200px, composer fully inside the viewport, lead form open and closed, and sizes at 1920x1140, 1280x800, 375x667, RTL.
3. Fix the root cause. Direction (adapt to evidence): the loader owns the panel height (clamp such as min(640px, 100dvh minus bubble and margins) with a sensible minimum); the frame must not report a self-referential scrollHeight; if size messages remain, ignore values below the minimum. Keep the postMessage protocol backward compatible and origin-checked.
4. Style the thread scrollbar (thin, token colours) so no arrow buttons show; keep keyboard scrolling and focus order.
5. Regenerate/sync the served loader copy apps/web/public/widget/v1/loader.js using the repo's existing mechanism and run npm run check:public-asset.

Subagents (follow the Subagent protocol in implementation/UI-POLISH-PLAN.md; you are the orchestrator):
- Phase 1 in parallel, read-only: (a) one Explore agent maps how loader.js is generated, synced and served (packages/widget, apps/web/public/widget/v1/loader.js, scripts/check-public-asset.mjs) and lists every test that asserts widget geometry; (b) one general-purpose agent performs the browser reproduction of step 1 and returns measurements and the chatbot:size message log, no edits.
- You decide the root cause from their evidence, then write the failing test (step 2) and the fix (steps 3-4) yourself: this batch edits a handful of tightly coupled files, so do not parallelise the edits.
- Phase 4 in parallel after the fix: one agent captures before/after screenshots at the four viewports while you run the widget Playwright specs yourself.

Out of scope: widget features, copy, backend, theming editor, other pages.

Verify: run the new test plus widget-layout.spec.ts, widget.spec.ts, widget-streaming.spec.ts, widget-domain.spec.ts, install.spec.ts; npm run typecheck; npm run lint; npm run check:public-asset. Take before/after screenshots of the sample page. Append exact commands and real outcomes to PROGRESS.md.

Gate: summarise root cause, files changed, test results, screenshots. Do not commit until the owner approves. Stop.
```

---

## B2 - Foundation: primitives, auth screens, link-to-button sweep

```
You are executing Batch B2 (foundation) of the UI polish track in D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai on branch feat/ui-polish (create from clean HEAD if absent).

Read first: AGENTS.md, apps/web/AGENTS.md (+ Next.js guides), implementation/UI-POLISH-PLAN.md (Owner decisions, Common rules, gaps A-1..A-4, D-1..D-7, BE-8), implementation/UI-REDESIGN-PLAN.md (token system, route/test inventory), DECISIONS.md (ADR-021 and the ADR list/format), docs/06-AUTHORIZATION-AND-SECURITY.md registration paragraph, apps/web/lib/ui.tsx, apps/web/lib/icons.tsx, apps/web/app/tokens.css, apps/web/app/globals.css, apps/web/app/auth-screen.css, apps/web/app/page.tsx, apps/web/app/login/page.tsx, apps/web/app/register/page.tsx, apps/web/lib/app-header.tsx, apps/web/tests/login-register.spec.ts, apps/api/tests/test_self_service_signup.py, apps/api/app/auth/service.py (register), apps/api/app/core/config.py (self_serve_signup).

Owner decisions: registration is OFF in UI and API; accounts are created by platform staff; Recharts is approved; staff-only surfaces are kept (not hidden) for staff.

Do:
1. Dependency + ADR: check recharts' current stable version and its React peer range against React 19.3 with npm view; add it as an exact pinned dependency (no caret) to apps/web, update the lockfile, run the existing install the repo uses. Add the next free ADR to DECISIONS.md (Approved 2026-10-25, owner chat): Recharts dependency; Inbox+History single module; small read-only analytics endpoints for charts; registration stays off. Do not touch ADR-007/008 (OPEN).
2. Primitives in apps/web/lib/ui.tsx (or small sibling modules following the existing style): LinkButton/ButtonLink (primary, secondary, ghost, danger, icon, with Icon support, correct <a>/<Link> semantics), StatCard (label without trailing colon, value, optional delta and sparkline slot, optional hint hidden when absent), Meter (used/limit, accessible), Switch, ColorField (picker + hex + contrast message), LimitField (number with unit, stepper, "Uncapped" placeholder, used/limit meter), SectionNav, StickyActionBar (appears only when dirty), and a Status badge variant that is clearly non-interactive. Chart wrappers come in B4, but add chart colour tokens (categorical + sequential, dark and light, WCAG contrast checked) to tokens.css now.
3. Focus: replace sticky focus rings with :focus-visible rules; the sidebar active item and the main content region must not show a ring after pointer navigation; keyboard focus remains clearly visible; keep the skip link.
4. Link-to-button sweep: every underlined text link that acts as a button becomes LinkButton: "Open", "Account", "Fix", "View inbox", "Create organization", "Platform admin", "Tenant data and audit", "Open bot", and any similar in apps/web. Plain inline text links inside sentences stay links. Keep hrefs, ids and test selectors.
5. Entry and auth: remove the hardcoded Register link and the stray "·" from app/page.tsx; replace the "Application foundation" placeholder with a real welcome (product name, one-line value proposition, a single primary Sign in button); /register redirects to /login (invitation acceptance via /accept-invite must keep working; read it and keep its flows); redesign the login screen (clean card/split layout using tokens, PasswordField show/hide, inline field errors, loading state, "Contact your administrator" hint since there is no email reset per ADR-021, safe next param preserved). Update login-register.spec.ts and any test relying on the old Register link.
6. Backend (tiny): add or confirm an API test that with the default config POST /auth/register without a valid invitation returns 403 INVITATION_REQUIRED and that /auth/config reports self_serve_signup false. No behaviour change. Remind the owner in the report to verify their local .env does not turn the flag on.

Subagents (follow the Subagent protocol in implementation/UI-POLISH-PLAN.md; you are the orchestrator):
- Phase 1 yourself: step 1 (dependency, ADR) and step 2 (primitives, chart tokens) and step 3 (focus rules). You own lib/ui.tsx, tokens.css, globals.css, package.json and the lockfile. Finish and typecheck these BEFORE fan-out so agents can import the primitives.
- Phase 2 in parallel (3 agents, disjoint write scopes):
  A) Explore (read-only, very thorough): inventory every underlined text link or raw <a>/<Link> that acts as a button across apps/web (file, line, label, destination, suggested variant). Returns a table. Run this at the very start, in parallel with your phase 1.
  B) general-purpose, write scope app/page.tsx, app/login/**, app/register/**, app/auth-screen.css, tests/login-register.spec.ts and other auth-related spec edits: step 5 (landing, login, /register redirect). Must not touch accept-invite behaviour without reading it.
  C) general-purpose, write scope apps/api/tests/ (one new/extended auth test file only): step 6 backend test, using its own disposable database.
- Phase 2b after A returns and primitives are in: split the link-to-button sweep by directory across up to 3 general-purpose agents (app/app/[tenant]/**, app/platform/** + app/account + app/accept-invite, apps/web/lib/** excluding ui.tsx/api.ts/app-header.tsx); you edit app-header.tsx yourself. Each preserves hrefs, ids and test selectors.
- Phase 3-4 yourself: integrate, typecheck, lint, run the Playwright specs and screenshots.

Out of scope: dashboards, forms, settings, inbox, widget. No backend changes beyond the test.

Verify: npm run typecheck, npm run lint, relevant Playwright specs (login-register, dashboard, platform, account, foundation, ui-redesign, ui-characterization, group-b-client-visibility), the API test via pytest on a disposable test database. Screenshots of landing, login, /app, Bots (before/after). Append exact commands and outcomes to PROGRESS.md.

Gate: report with screenshots, new primitives list, test results. Do not commit until the owner approves. Stop.
```

---

## B3 - Backend analytics and list data

```
You are executing Batch B3 (backend data for charts and History) of the UI polish track in D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai on branch feat/ui-polish (create from clean HEAD if absent). Backend only.

Read first: AGENTS.md, implementation/UI-POLISH-PLAN.md (Common rules, BE-1..BE-7), docs/05-API-CONTRACTS.md, docs/06-AUTHORIZATION-AND-SECURITY.md, docs/10-CLIENT-DASHBOARD.md, docs/15-TESTING-AND-ACCEPTANCE.md, apps/api/app/analytics/router.py, analytics/handoff.py, analytics/service.py, apps/api/app/inbox/listing.py, apps/api/app/conversations/router.py, apps/api/app/quotas/service.py, quotas/rag.py, quotas/rag_contracts.py, apps/api/app/tenants/router.py (quota endpoint), existing analytics, inbox, quota and rag-limit tests under apps/api/tests, docs/LOCAL-DEVELOPMENT.md (how to run tests with a disposable database).

All additions are read-only, tenant-scoped, typed (pydantic response models where the neighbouring code uses them), measured data only (playground threads never count, website source as in handoff.py), viewer role or above like the existing reads. No migration. If a migration seems needed, stop and ask.

Do (each with tests, including tenant A/B isolation and a hidden-resource 404 where relevant):
1. BE-1 GET /api/v1/tenants/{tenant_id}/analytics/timeseries?from&to : per-day rows {day, conversations, handoffs, resolved} (add visitor/AI message counts only if a cheap single query), zero-filled across the window, same window validation as the existing endpoints (reuse _range_window).
2. BE-2 extend GET /api/v1/tenants/{tenant_id}/analytics with a "previous" block: the same totals for the equal-length window immediately before (total, handoffs, handoff_rate, average first human reply seconds). Existing fields unchanged (backward compatible).
3. BE-3 group near-duplicate questions in top-questions and unanswered (casefold, collapse whitespace, strip trailing punctuation incl. Arabic ? and ؟, normalise Arabic alef/yaa/teh-marbuta variants and strip diacritics for the grouping key only; show the most recent original text; sum counts; keep response shape). Tests with English and Arabic cases.
4. BE-4 inspect the rag cost endpoint shape (api.ragCosts consumer in apps/web/lib/api.ts). Events with unreported cost must not be presented as a measured $0: expose an explicit unreported count (or null cost) per row, keeping existing fields. If it already does, say so and change nothing.
5. BE-5 explain, with evidence from code and the test database, why quota.measured_tokens_this_month and the rag usage monthly_tokens / monthly_embedding_tokens differ (the owner saw 12,665 vs 97,647 and 45,832). If they measure different things by design, add precise field naming/docs; if they should match, fix with tests. Write the finding in PROGRESS.md.
6. BE-6 inbox list (GET /tenants/{id}/inbox): add total count in the response, optional created_from/created_to filters, and ensure each row carries contact name, last message preview, status, channel, mode, unread, bot_id (check what exists first; add only what is missing). Keep pagination via limit/offset. Do not change the delete endpoint.
7. BE-7 quota warnings: distinguish at-limit (used >= limit) from approaching, additively (e.g. an at_limit list next to warnings), keeping the existing field.

Subagents (follow the Subagent protocol in implementation/UI-POLISH-PLAN.md; you are the orchestrator):
- Phase 1 yourself: read the inputs, write down the exact response shapes you will add (field names, types, nullability, ordering) so agents implement against the same contract; you own docs/05, PROGRESS.md, DECISIONS.md.
- Phase 2 in parallel (up to 4 agents, disjoint write scopes, each with its OWN disposable database name and one pytest process at a time):
  A) general-purpose, write scope apps/api/app/analytics/handoff.py + its new test file: BE-1 timeseries and BE-2 previous-period block.
  B) general-purpose, write scope apps/api/app/analytics/service.py + router.py (top-questions/unanswered only) + its new test file: BE-3 grouping, English and Arabic cases.
  C) Explore (read-only, thorough) then report: BE-4 cost shape and BE-5 token-number reconciliation with code evidence; you then decide and either implement it yourself or hand a precise edit to a general-purpose agent with write scope apps/api/app/quotas/** and apps/api/app/tenants/router.py.
  D) general-purpose, write scope apps/api/app/inbox/listing.py + apps/api/app/quotas/service.py (warnings) + their new test files: BE-6 and BE-7. If BE-5 touches quotas/service.py, sequence D before the BE-5 edit.
- Phase 3-4 yourself: integrate, then run ruff, mypy on touched files and the combined pytest pass on your own database; confirm tenant A/B tests exist for every new endpoint.

Out of scope: any frontend change, write endpoints, migrations, model/provider calls.

Verify with exact commands on a disposable test database (single pytest process): the new tests plus existing analytics, inbox, conversations, quota and rag tests; ruff on touched files; mypy on touched files (record any pre-existing errors as pre-existing). Update docs/05 for new/changed contracts. Append exact commands and real outcomes to PROGRESS.md.

Gate: list endpoints with example responses, test results, the BE-5 finding. Do not commit until the owner approves. Stop.
```

---

## B4 - Dashboards and charts

```
You are executing Batch B4 (Overview, Bot overview, Insights with charts) of the UI polish track in D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai on branch feat/ui-polish. B2 (primitives, Recharts, chart tokens) and B3 (backend data) must already be done; verify that first and stop if not.

Read first: AGENTS.md, apps/web/AGENTS.md (+ Next.js guides), implementation/UI-POLISH-PLAN.md (Common rules, gaps H-1..H-14, X-1), implementation/UI-REDESIGN-PLAN.md (route/test inventory: overview.spec.ts ids overview-title, overview-range, range-from, range-to, range-apply, overview-summary, volume, top-questions, unanswered, leads, export-conversations, export-leads), docs/10-CLIENT-DASHBOARD.md, apps/web/app/app/[tenant]/page.tsx, .../analytics/page.tsx, .../bots/[botId]/overview/page.tsx, apps/web/lib/ui.tsx, apps/web/app/insights-screen.css, apps/web/lib/api.ts (analytics, quota and inbox types). Load the dataviz and modern-web-guidance skills if available BEFORE writing chart or CSS code.

Do:
1. Chart components (small, reusable, client components): TrendChart (area/line), DonutChart, BarList/BarChart, Sparkline. Tokens only for colour, dark and light themes, prefers-reduced-motion disables animation, legend/labels not colour-only, tooltip keyboard-reachable, RTL-safe, ResponsiveContainer sizing, a visually-hidden data table or aria summary for each chart, loading and empty states that hide the card when there is no data (do not render an empty card).
2. Tenant Overview: KPI StatCards (no filler subtitle; deltas where B3 provides them), conversations-over-time TrendChart from the timeseries endpoint, outcomes donut, recent conversations as contact name + preview (dir="auto" per item) + status badge + relative time, no duplicates of identical consecutive bot replies as titles, the Get-started checklist only while incomplete, compact plan-usage Meters (shared component) with the "Plan limits are provisional" disclosure kept as a small footnote, warning wording that distinguishes at-limit from approaching (B3), and for platform staff a health alert when readiness says recent model calls failed (reuse the existing readiness data; no new endpoint).
3. Bot overview: volume per day as TrendChart (keep id volume on the container), rates as percentages, avg response in seconds, reply-length distribution as bars, unanswered/top questions as ranked lists using the grouped data (keep ids), thumbs tile hidden when 0/0. Keep date range controls, CSV exports and all listed test ids.
4. Insights: title and nav both "Insights"; 7/30/90-day period selector using from/to; outcomes donut + KPI row with previous-period deltas; channel bars; agent workload bars; sentiment stacked bar; cards without data are hidden, not shown empty; keep the staff RagOperatorPanel in place (its redesign is B6).
5. Preserve all roles: viewers can read; staff-only items remain staff-only.

Subagents (follow the Subagent protocol in implementation/UI-POLISH-PLAN.md; you are the orchestrator):
- Phase 1 yourself: add the analytics/quota/inbox types to lib/api.ts and the api functions for the B3 endpoints (you own lib/api.ts); define the chart component props (TrendChart, DonutChart, BarList, Sparkline), shared formatters (percent, duration, relative time) and the StatCard/Meter usage contract in a short comment block.
- Phase 2 (one agent): general-purpose, write scope apps/web/lib/charts/** + app/charts.css: build the four chart components and a text-alternative table helper, with typecheck. Run it first; the page agents depend on it.
- Phase 3 in parallel (3 agents, disjoint write scopes) once charts exist:
  A) tenant Overview: app/app/[tenant]/page.tsx and its css.
  B) Bot overview: app/app/[tenant]/bots/[botId]/overview/page.tsx and its css.
  C) Insights: app/app/[tenant]/analytics/page.tsx and app/insights-screen.css (leave the RagOperatorPanel import in place).
  Each must keep the listed test ids and return screenshots-ready routes to open.
- Phase 4 yourself: integrate, typecheck, lint, run the Playwright specs, take the screenshots (or delegate screenshot capture only, not test runs, to one agent).

Out of scope: forms/settings, inbox/history, widget, backend (if an endpoint is missing, stop and report; do not invent one).

Verify: npm run typecheck, npm run lint, Playwright specs overview.spec.ts, dashboard.spec.ts, group-b-client-visibility.spec.ts, ui-redesign.spec.ts, ui-characterization.spec.ts plus new specs for chart presence/alternatives, period selector and hidden empty cards; screenshots at 1280 and 375 wide, dark and light, and one Arabic/RTL case. Append exact commands and real outcomes to PROGRESS.md.

Gate: report with before/after screenshots; list any data gap discovered. Do not commit until the owner approves. Stop.
```

---

## B5 - Conversations module (Inbox + History)

```
You are executing Batch B5 (merge Inbox and Conversations into one module) of the UI polish track in D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai on branch feat/ui-polish. B2 and B3 must be done; verify and stop if not.

Read first: AGENTS.md, apps/web/AGENTS.md (+ Next.js guides), implementation/UI-POLISH-PLAN.md (Common rules, gaps I-1..I-7), implementation/UI-REDESIGN-PLAN.md (route/test inventory: inbox-list, inbox-status, inbox-mode, inbox-thread, retention-input, retention-save, retention-saved, delete-${id}, conversations, conversation-thread, thread-citations), docs/10-CLIENT-DASHBOARD.md, docs/18-EXPECTED-BEHAVIOUR.md (inbox/conversation sections), apps/web/app/app/[tenant]/inbox/page.tsx, .../inbox/[conversation]/page.tsx, apps/web/lib/inbox-list.tsx, .../conversations/page.tsx, .../bots/[botId]/conversations/page.tsx and its [conversationId] page, apps/web/lib/app-header.tsx (nav), apps/web/app/inbox-screen.css, apps/web/app/convo-screen.css, apps/web/tests/conversations.spec.ts, apps/web/lib/api.ts (inbox types).

Owner decision: ONE module with its own tabs. Module name "Conversations"; tabs: Inbox (live work) | History (all saved conversations, retention, deletion). The sidebar shows a single item.

Do:
1. Shared module layout with accessible Tabs (existing Tabs/TabPanel in ui.tsx) so both tabs share the page header. Routes preserved: /app/T/inbox and /app/T/inbox/[conversation] (Inbox tab; thread view keeps the list context), /app/T/conversations (History tab; replace today's redirect-to-first-bot behaviour with a real tenant-wide list), /app/T/bots/B/conversations and its detail keep working (link or redirect into History filtered by bot only if tests and the detail route stay intact).
2. Inbox: stat tiles become filter tabs/chips with counts (Waiting for a reply, Assigned to me, Unread, All) wired to the existing filter query params; compact toolbar (search + status + "More filters" popover for mode/channel/assignee/tag/unread); list scrolls independently and starts at the top; detail pane fills the available height; smaller empty state; list item = initials avatar, contact name, one-line preview (dir="auto"), time, unread dot, status badge; SSE refresh behaviour unchanged.
3. History: search, status/channel filters, date range (B3), pagination with total, row click opens the thread (read-only saved thread page stays), columns: last activity, visitor, preview, status badge, channel, messages; Delete moves to a row overflow menu with the existing ConfirmAction (keep delete-${id} reachable); Retention becomes a collapsible "Data retention" panel showing the saved value (not a greyed placeholder), keeping retention-input/save/saved ids and the 1-365 validation.
4. Keep role behaviour: viewers read-only; destructive actions only for roles that have them today.
5. Sidebar: one "Conversations" item active for both tabs and all child routes; update app-header nav and any command-palette entries.
6. Update docs/10 and docs/18 minimally for the merged module (the owner approved it); do not edit unrelated owner text.

Subagents (follow the Subagent protocol in implementation/UI-POLISH-PLAN.md; you are the orchestrator):
- Phase 1 yourself: build the shared module layout and tab bar (new layout/component), update lib/app-header.tsx nav and command palette, and add the inbox/History types and api calls (you own lib/api.ts and app-header.tsx). Define the filter query-param contract and the list-row component props in a comment block.
- Phase 2 in parallel (3 agents, disjoint write scopes):
  A) Inbox: lib/inbox-list.tsx, app/app/[tenant]/inbox/page.tsx, app/app/[tenant]/inbox/[conversation]/page.tsx, app/inbox-screen.css (steps 2).
  B) History: app/app/[tenant]/conversations/page.tsx, app/app/[tenant]/bots/[botId]/conversations/** , app/convo-screen.css (step 3, retention, delete confirm).
  C) general-purpose, write scope apps/web/tests/** only: write the new Playwright specs from the acceptance list while A and B build, against the contracts you defined; it must not edit app code.
- Phase 3-4 yourself: integrate, update docs/10 and docs/18, typecheck, lint, run the Playwright specs, screenshots.

Out of scope: dashboards, settings, widget, new backend (use B3 endpoints; if something is missing, stop and report).

Verify: typecheck, lint, Playwright conversations.spec.ts, contacts.spec.ts, followups.spec.ts, dashboard.spec.ts, roles-control.spec.ts, group-b-client-visibility.spec.ts, ui-characterization.spec.ts plus new specs: tab navigation and old URLs, first conversation visible without scrolling at 1920x1140 and 1280x800, filter chips update the list, History search/filter/pagination, delete confirm, retention save. Screenshots at 1280 and 375, dark and light, one RTL. Append exact commands and real outcomes to PROGRESS.md.

Gate: report with before/after screenshots. Do not commit until the owner approves. Stop.
```

---

## B6 - Settings, forms, bots, organizations

```
You are executing Batch B6 (forms, settings, bots list, organizations) of the UI polish track in D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai on branch feat/ui-polish. B2 must be done; verify and stop if not.

Read first: AGENTS.md, apps/web/AGENTS.md (+ Next.js guides), implementation/UI-POLISH-PLAN.md (Common rules, gaps F-1..F-9, B-1..B-3), implementation/UI-REDESIGN-PLAN.md (route/test inventory: activate-bot, pause-bot, settings-locator, Save settings, retention ids unaffected), implementation/ROLE-MATRIX.md, apps/web/app/app/[tenant]/bots/[botId]/settings/page.tsx, apps/web/app/app/[tenant]/bots/page.tsx, apps/web/app/app/page.tsx, apps/web/lib/rag-operator-panel.tsx, rag-tier-control.tsx, bot-readiness-card.tsx, bot-tone-field.tsx, widget-theme-editor.tsx, widget-preview.tsx, widget-theme.ts, apps/web/app/bot-settings-c.css, apps/web/app/settings-screen.css, apps/web/tests/c-bot-settings.spec.ts, group-a-operator.spec.ts, group-b-client-visibility.spec.ts, roles-control.spec.ts, install.spec.ts. Load the modern-web-guidance skill if available before CSS/HTML work.

Owner decision: platform staff keep every staff-only item (AI costs and limits, RAG operator panel, tone and rules, diagnostics); redesign them, do not hide them. Client roles must not see or reach them.

Do:
1. AI costs and limits (RagOperatorPanel): grouped LimitField rows (Content, Monthly usage, Embedding/OCR) with used value, meter, unit and "Uncapped" placeholder; StickyActionBar shows only when dirty; "Reset to plan defaults" is a secondary action with the existing ConfirmAction; cost telemetry becomes a compact table (stage, model, tokens, cost, unreported-cost indicator; use B3 semantics, never show an unreported cost as a measured $0); the bot selector stays; keep the same API calls and ids.
2. Bot settings: SectionNav (Identity, Appearance, Messages, Handoff, Access, AI) with sticky Save bar and dirty state; two-column field grouping on wide screens, one column on narrow; helper text, placeholders, counters; widget colour via ColorField; "Human handoff enabled" via Switch; keep the live widget preview and light/dark toggle working; keep Save settings label/behaviour, activate/pause/archive actions and settings-locator.
3. One consistent save model: the AI tier select must give explicit feedback (toast or inline status) and sit in the AI section; if it must stay instant-save, say so in the control and keep the F-6 pattern consistent; do not leave a detached dashed box.
4. Staff Diagnostics: retrieval mode, active embedding model, backfill state in a collapsible "Diagnostics" visible to platform staff only.
5. Launch readiness: "n/7 ready" Meter, failing items first, "Fix" as button-style links, non-interactive status badges, failing-model-calls row promoted to a banner.
6. Bots list: cards (name, status badge, plan-usage Meters compact, actions as buttons), remove the duplicate "Open bot" link, "Contact us to add or change bots" becomes a "Request a change" button to the existing change-request route, keep archive controls and "Show archived bots". Organizations list: Open / Create organization / Platform admin as buttons.
7. Verify client roles cannot reach staff-only surfaces by URL or API (UI hides AND the API refuses): extend group-b-client-visibility / roles-control specs if a case is missing. Report if you find a server-side gap; do not fix backend silently, stop and ask.

Subagents (follow the Subagent protocol in implementation/UI-POLISH-PLAN.md; you are the orchestrator):
- Phase 1 yourself: confirm which primitives exist from B2 and add any missing ones to lib/ui.tsx (you own ui.tsx, api.ts, tokens/globals css).
- Phase 2 in parallel (3 agents, disjoint write scopes):
  A) AI limits and costs: lib/rag-operator-panel.tsx, lib/rag-tier-control.tsx (only if the AI tier pattern from step 3 requires it; coordinate with B by having B own that decision and A not touch it), plus its css (steps 1).
  B) Bot settings: app/app/[tenant]/bots/[botId]/settings/page.tsx (765 lines, ONE agent only), lib/bot-readiness-card.tsx, lib/bot-tone-field.tsx, lib/widget-theme-editor.tsx, lib/widget-preview.tsx, app/bot-settings-c.css, app/settings-screen.css (steps 2-5).
  C) Bots and organizations lists plus the role-visibility audit: app/app/[tenant]/bots/page.tsx, app/app/page.tsx, apps/web/tests/group-b-client-visibility.spec.ts and roles-control.spec.ts additions (steps 6-7). Also an Explore pass over apps/api role checks for the staff-only endpoints, report only.
- Phase 3-4 yourself: integrate, typecheck, lint, run the Playwright specs, screenshots.

Out of scope: dashboards/charts, inbox/history, widget internals, backend changes.

Verify: typecheck, lint, Playwright c-bot-settings, group-a-operator, group-a-members, group-b-client-visibility, roles-control, install, staff-bots, platform, organizations, dashboard, ui-redesign, ui-characterization plus new specs (dirty save bar, section nav, switch/colour field, limits save/reset with confirm). Screenshots at 1280 and 375, dark and light. Append exact commands and real outcomes to PROGRESS.md.

Gate: report with before/after screenshots and the role-visibility test results. Do not commit until the owner approves. Stop.
```

---

## B7 - Hygiene, consistency, QA, docs

```
You are executing Batch B7 (final hygiene and QA) of the UI polish track in D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai on branch feat/ui-polish. B1-B6 must be done and signed off; verify via PROGRESS.md and git log and stop if not.

Read first: AGENTS.md, apps/web/AGENTS.md, implementation/UI-POLISH-PLAN.md (all gaps, especially X-1..X-3, Q-1..Q-3), implementation/UI-REDESIGN-PLAN.md, implementation/MANUAL-TEST.md, docs/10-CLIENT-DASHBOARD.md, docs/18-EXPECTED-BEHAVIOUR.md, PROGRESS.md (B1-B6 entries), apps/web/screenshots/capture.spec.ts.

Do:
1. Hygiene sweep across every page: remove or hide anything with no value (empty cards, filler subtitles, repeated warnings, completed onboarding, internal wording shown to clients); consistent naming (Insights, Conversations, Request a change...), consistent number/date/duration/percent formatting through shared helpers, consistent empty and error states, consistent button hierarchy; no remaining underlined text link acting as a button (grep for patterns and fix).
2. Token consistency (X-1): confirm the token numbers shown on Overview, Bots, Insights and the staff panel agree with the B3 finding and are labelled precisely.
3. Quality passes: light theme, dark theme, RTL (Arabic), 375px, 768px, 1280px and 1920px for every redesigned page, keyboard-only navigation of nav, tabs, dialogs, forms and charts, contrast of chart tokens, reduced motion. Fix defects found; list anything deferred.
4. Tests: run the FULL Playwright suite and the API tests touched by B3 on disposable databases; fix regressions caused by this track; record failures that pre-exist as pre-existing with evidence (git stash or main comparison), never hide them.
5. Docs: update docs/10 and docs/18 for behaviour changes not already covered (landing/register, merged Conversations module, charts and period selector), add a short UI-POLISH closeout in PROGRESS.md; refresh the screenshot capture spec/outputs if the repo keeps them; update implementation/MANUAL-TEST.md steps that changed.
6. Owner-facing summary: before/after screenshot set per page.

Subagents (follow the Subagent protocol in implementation/UI-POLISH-PLAN.md; you are the orchestrator):
- Phase 1 in parallel, read-only audits (Explore, very thorough, one per area, each returns a prioritised defect list with file:line): (a) formatting and naming consistency across apps/web; (b) leftover underlined link-buttons, empty-state/redundant blocks and internal wording shown to clients; (c) accessibility and RTL/light-theme issues found by reading CSS and components; (d) docs and MANUAL-TEST.md steps that no longer match the UI.
- Phase 2 in parallel fixes, disjoint write scopes by directory: app/app/[tenant]/** (client pages), app/platform/** and app/account, lib/** (excluding ui.tsx/api.ts, which you own), and implementation/MANUAL-TEST.md plus docs/10 and docs/18 (agent d only). Each fixes only items from its audit list, no feature work.
- Phase 3 in parallel, capture only: up to 2 agents capture screenshots per page across viewports and themes into a scratch directory outside the repo. They do not run tests.
- Phase 4 yourself: run the FULL Playwright suite and the touched API tests, compare failures against the pre-change baseline, write the closeout.

Out of scope: new features, backend changes (report instead), anything under the RAG hardening track.

Gate: final report with full test results, deferred list, screenshots. Do not commit, push or merge until the owner approves; no push or merge in any case without separate approval. Stop.
```
