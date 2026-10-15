# Frontend redesign: Stage 0 inventory and approval plan

Date: 2026-10-15. Status: **Stage 0 complete; S1-S7 await owner approval.**
Branch: `feat/ui-redesign`, created from `feat/p1-01-foundation`.

## Scope and boundaries

- Frontend presentation only: `apps/web` and widget presentation in `packages/widget/src/loader.js` plus its served copy, `apps/web/public/widget/v1/loader.js`.
- Preserve every existing route, query parameter, form, action, validation, role restriction, API contract and error behavior. No backend, migration, infrastructure, provider or channel implementation changes.
- Do not read or print `.env`, keys or credentials. No paid calls, push, merge, deployment or cloud resources. Subsequent commits are local and limited to each approved stage.
- Existing owner edits in `README_START_HERE.md`, `docs/11*`, `docs/18*` and `implementation/*` must remain untouched and uncommitted. This new plan is the expressly requested exception. Defer the expressly requested `MANUAL-TEST.md` edits to S7 and preserve any owner changes there.
- Do not change `PROGRESS.md` during Stage 0: the latest request says to write only this plan and stop. Record Stage 0 evidence here. After approval, append exact verification commands/results to `PROGRESS.md` as required by repository rules, without changing existing entries.
- ADR-007 (hosting) and ADR-008 (billing) remain OPEN and outside this redesign. No hosting/pricing decisions are required; retain PLACEHOLDER pricing and limits disclosures. This work does not sign off existing roadmap gates or authorize P6.

## Current architecture, styling and dependencies

- Next.js App Router `16.4.0`, React/React DOM `19.3.0`, TypeScript `6.0.3`; npm workspaces, Node `>=24 <25`. Exact package versions and lockfile already exist.
- Tooling: Playwright `1.64.0`, ESLint `10.12.0`, eslint-config-next `16.4.0`, Prettier `3.9.10`. No Tailwind, component library, motion library, icon package or CSS preprocessor dependency.
- `app/globals.css`: small light-only stylesheet, system font, literal colors, broad element selectors, 48rem main width and 10vh top margin. Physical alignment/margins are present. No token system, viewer theme preference or reduced-motion system.
- Inbox and several other pages add inline styles, including literal colors and physical margins. Widget frame embeds a `widgetStyles` CSS string and config-driven header color. Loader injects CSS and inline launcher/frame styles; sample has inline presentation. These surfaces need scoped styling to prevent global form/table rules interfering with widget or shell.
- Root `app/layout.tsx` provides metadata and `SessionProvider`. `/app/layout.tsx` extracts the tenant from the pathname and renders `AppHeader`; pages own their content and requests.
- `lib/api.ts` is the existing typed same-origin request layer, with CSRF/session handling. Treat it as a contract boundary; reuse exports unchanged. Existing inline public widget fetch/polling behavior also stays unchanged.
- `/platform/layout.tsx` performs a server-side staff API check and redirect before rendering its separate wrapper. Preserve the guard, cookie forwarding, cache policy and separation from tenant permissions.
- Before implementation, read applicable installed Next.js guides under `node_modules/next/dist/docs/` as required by `apps/web/AGENTS.md`. Stage 0 writes no Next.js code.

### Reusable components

| File | Existing responsibility | Planned reuse |
| --- | --- | --- |
| `lib/ui.tsx` | `Loading`, `Notice`, `Empty`; status/alert semantics | Evolve presentation into skeleton/empty/error surfaces, retaining announcements; add focused shared presentation primitives |
| `lib/session.tsx` | Session provider, refresh, expired-session redirect, `roleIn`, `roleSatisfies` | Preserve logic; derive workspace name and role from memberships |
| `lib/app-header.tsx` | Dashboard link, organization selector, Bots/Inbox/Contacts/Team links, email, sign-out | Compose into sidebar/top bar; preserve switching and sign-out actions |
| `lib/bot-workspace-nav.tsx` | Six existing tabs with active state and stable selectors | Restyle; keep all paths, nested active state and selectors |
| `lib/api.ts` | Typed contracts and existing request helpers | Reuse without contract changes |

Proposed shared presentation modules: token stylesheet, theme provider/control, app/platform shell, breadcrumbs/page heading, buttons/fields/badges, skeletons, empty/error states, toast region, accessible dialog and navigation-only command palette. A single enum-label module maps display labels while retaining raw values in `title`/`data-*`. Do not convert server errors, especially widget plan-limit messages, through that mapping.

## Complete route and test inventory

All page paths below are relative to `apps/web/app`; each route corresponds to its `page.tsx`. `T` means `[tenant]`, `B` means `[botId]`. Specs are under `apps/web/tests`. Selectors listed are current hooks, not promised full coverage. “No test ID” means the page uses role/label/text selectors instead.

| Route / page file | Current content and actions to preserve | Existing Playwright coverage and selectors |
| --- | --- | --- |
| `/` (`page.tsx`) | Foundation landing, links into app/auth | `foundation.spec.ts`: title, H1 `Application foundation`, browser-error check. `security-headers.spec.ts`: headers. No test ID |
| `/login` (`login/page.tsx`) | Email/password, error, session refresh, safe `next`, registration link | `dashboard`, `playground`, `platform` specs exercise login/expiry/redirect; `security-headers` checks headers. Labels `Email`, `Password`; button/heading `Sign in`; no test ID |
| `/register` (`register/page.tsx`) | Organization + first bot provisioning; invitation signup variant; password validation and account recovery | `dashboard`, `knowledge`, `playground`, `widget`, `install`, `overview`, `conversations`, `contacts`, `followups` through signup helpers; header test. Labels `Organization name`, `First bot name`, `Email`, `Password`; `Create account`; no test ID |
| `/accept-invite` (`accept-invite/page.tsx`) | Token invitation, login/register continuation, accept, dashboard link | `dashboard.spec.ts` invitation journey and `playground`/`knowledge` viewer setup: `Accept invitation`, status `Welcome aboard`, registration/dashboard links; no test ID |
| `/app` (`app/page.tsx`) | Organization picker, role text, create organization, auth redirect | `dashboard.spec.ts`: `Your organizations`, organization link, expiry; invitation helpers also traverse it. No test ID |
| `/app/T/bots` (`app/[tenant]/bots/page.tsx`) | Tenant landing: bot list/create/archive/show archived, quota usage/warnings, data/audit link | `dashboard.spec.ts`: signup/archive, tenant A/B denial, viewer read-only; shared bot setup across specs. Bot row/name, `Bot name`, `Create bot`, `Archive`, `Show archived bots`, `Sign out`; no test ID |
| `/app/T/bots/B/overview` | Date-filtered measured summary, daily volume, questions/unanswered, leads, CSV exports | `overview.spec.ts` (2): per-bot/tenant scoping, CSV, measured values. `overview-title`, `overview-range`, `range-from`, `range-to`, `range-apply`, `overview-summary`, `volume`, `top-questions`, `unanswered`, `leads`, `export-conversations`, `export-leads` (some hooks exist without direct assertions) |
| `/app/T/bots/B/settings` | Bot name/config, allowed domains, EN/AR greetings/questions, appearance, activate/pause/archive, locator | `install.spec.ts`: activation, locator and color save; many specs open settings to get bot ID. `activate-bot`, `pause-bot`, `settings-locator`; `Save settings`, widget color label; broader settings not fully covered |
| `/app/T/bots/B/knowledge` | Upload/template/CSV errors, sources, jobs/retry/cancel, published/draft docs, chunk preview, publish/rollback via revision controls | `knowledge.spec.ts` (4): fresh signup controls, ingest/preview/publish, oversized upload 413, viewer restrictions. `sources-list`, `jobs-list`, `job-status`, `row-errors`, `documents-list`, `chunk-list`, `revisions-list`; labeled upload and role/button selectors |
| `/app/T/bots/B/playground` | Persisted thread, send, citations, feedback, not-ready/errors, viewer read-only | `playground.spec.ts` (3): answer/citation/feedback/persistence, expiry, viewer. `thread`, `playground-input`, `playground-send`, `citations`, `thumbs-up-${id}`, `thumbs-down-${id}`; `[data-role='ai']`, `Thumbs up` |
| `/app/T/bots/B/install` | Status guidance, real locator-based snippet, copy, sample-page link and instructions | `install.spec.ts` (1): draft/active snippet/sample journey. `install-status`, `install-snippet`, `copy-snippet`; link matching `sample page` |
| `/app/T/bots/B/conversations` | Bot conversation table, retention setting, delete action, thread links | `conversations.spec.ts` first test: lead/message appears and detail opens. `conversations`, `retention-input`, `retention-save`, `retention-saved`, `delete-${id}`. Retention/delete hooks are not directly asserted there |
| `/app/T/bots/B/conversations/[conversationId]` | Read-only saved thread and safe citation links | `conversations.spec.ts` first test: `conversation-thread`, `thread-citations`; available `conversation-detail-title` |
| `/app/T/inbox` | Counts, search/status/mode/channel/assignee/tag/unread filters, SSE refresh, conversation links | `conversations.spec.ts` handoff journey traverses list and opens thread. `inbox-list`; filter labels. No exhaustive filter/URL/unread/Arabic coverage |
| `/app/T/inbox/[conversation]` | Thread, mode/status, takeover/return/resolve/assign, tags, notes/reply, read marking, refresh | `conversations.spec.ts` second test: handoff, takeover, reply, note and return to AI with widget persistence. `inbox-status`, `inbox-mode`, `inbox-thread`, available `thread-citations`; role/label controls. Viewer action matrix not directly covered |
| `/app/T/contacts` | Contact table, create, CSV export | `contacts.spec.ts` (1): `Contacts`, `Name`, `Email`, `Create contact`, contact link/table row; no test ID |
| `/app/T/contacts/[contactId]` | Profile, stage/tags/custom fields, identities, timeline, merge/erasure, website follow-up schedule/cancel | `contacts.spec.ts`: profile save/tags/JSON/timeline; `followups.spec.ts`: Conversation/Send after/Message/Schedule follow-up. No test ID; merge/erasure/cancellation not directly covered |
| `/app/T/analytics` | Handoff/outcomes/channel/workload/stored sentiment analytics | `followups.spec.ts` (1): `Handoff analytics`, `Total: 1`; no test ID, broader analytics not directly covered |
| `/app/T/settings/members` | Team list, role changes/removal, invitation create/resend/revoke/copy | `dashboard.spec.ts` invitation/editor/viewer journey, viewer setup in knowledge/playground. Labels `Email`, `Role`, `Create invite link`, generated `code`; no test ID. Not every team operation is covered |
| `/app/T/settings/data` | Admin export/audit search; owner-only deletion with exact name and reason validation | No direct Playwright spec or test IDs. Existing labels/buttons/section aria labels available; add meaningful coverage in S5 |
| `/platform` (`platform/page.tsx`) | Staff badge, client search/status/list, onboarding + files + invite result | `platform.spec.ts` (2): non-staff server redirect and staff onboarding/detail. `platform-staff-badge`, `platform-search`, `platform-query`, `platform-status`, `platform-tenants`, `client-${slug}`, `onboarding-form`, `ob-client-name`, `ob-owner-email`, `ob-bot-name`, `ob-files`, `ob-submit`, `ob-invite-link` |
| `/platform/clients/[clientId]` | Client summary/status, bots/pause, plan/quota overrides with reason, jobs, members, audit | `platform.spec.ts`: `client-detail-name`, `client-detail-bots`; additional hooks `client-detail-status`, `client-plan`, `client-detail-jobs`, `client-detail-members`, `client-detail-audit`. Staff mutations not directly covered |
| `/platform/operations` | PLACEHOLDER quotas, platform analytics, jobs retry/cancel with reason, audit search | No direct Playwright spec. Existing `platform-analytics`, `platform-job-health`, `platform-audit-review` |
| `/widget/sample` (`widget/sample/page.tsx`) | Locator/site query helper embedding real loader; missing-locator guidance | `install`, `widget`, `conversations`, `overview` specs. `sample-snippet`, available `sample-missing-locator`, loader `widget-bubble` |
| `/widget/frame` (`widget/frame/page.tsx`) | Embedded public chat: configuration/session, opening chips, send/poll, citations, feedback, handoff, consent lead form, errors/limits, close | `widget.spec.ts` (2): two tenants/sites and unsafe citation URL; `conversations`, `overview` cover chat/lead/agent reply; `security-headers` checks scoped CSP. `widget-frame-body`, `widget-title`, `widget-input`, `widget-send`, `widget-ai-msg`, `widget-error`, `widget-typing`, `widget-chips`, `widget-thumbs-up-${id}`, `widget-thumbs-down-${id}`, `widget-lead-open`, `widget-lead-form`, `widget-lead-name`, `widget-lead-email`, `widget-lead-phone`, `widget-lead-consent`, `widget-lead-submit`, `widget-lead-error`, `widget-lead-done` (not all asserted) |

There are **25 page files**. No `/app/[tenant]` home page or `/bots/[botId]` index page exists. The bot detail “tabs” above are separate page routes, not a single tabbed page.

Non-page widget asset `/widget/v1/loader.js` is the served loader copy. Loader selectors: `widget-bubble`, `widget-frame`; frame locator nesting is part of existing E2E assertions. Keep package and public loader copies synchronized.

Shared bot navigation selectors: `bot-workspace-nav`, `nav-overview`, `nav-conversations`, `nav-knowledge`, `nav-playground`, `nav-settings`, `nav-install`; `overview.spec.ts` checks the six links. Organization switcher uses `Organization selector` and navigation landmark `Organization`.

### Test baseline and gaps

Static source inventory: **25 tests in 12 specs**: foundation 1, dashboard 4, knowledge 4, playground 3, security-headers 2, widget 2, install 1, conversations 2, overview 2, platform 2, contacts 1, followups 1. This is a source count, **not a passing run**.

`playwright.config.ts`: Chromium only, one worker, retries 0, real production webServer on 3100, global setup/teardown boots the API and DB worker against disposable test storage. Existing setup uses an offline stub model. Do not enable unknown-server reuse or point tests at the development database. No API pytest run is needed for this frontend-only work.

Existing tests are journey-oriented and heavily depend on labels, bot table rows, DOM tag names and nesting. Preserve assertion strength when updating selectors. For example the unsafe-citation test requires non-clickable `SPAN`; changing source chips must retain that security property. Raw status checks should use stable attributes when human labels change. Keep all original 25 tests; add targeted tests for new presentation behavior and uncovered sensitive flows, so the total may exceed 25. Never skip/delete/weaken tests to reach a green report.

Coverage to add during relevant stages: theme persistence by viewer; palette/dialog keyboard focus and Escape; mobile drawer; tenant/platform context and staff separation; all inbox filters plus existing `?status=` behavior; viewer controls; Arabic conversation rows; widget 429 verbatim message; sensitive tenant/platform workflows using disposable fixtures. Screenshots alone do not prove authorization or keyboard behavior.

## Proposed information architecture (no new routes)

1. **Public/auth**: retain landing `/`, centered login/register/invite screens and all safe redirect/provisioning behavior. Use current product name; do not invent a brand or marketing claims.
2. **Organization selection**: `/app` stays the picker and organization creation screen. Switching an organization continues to its existing `/bots` route.
3. **Client workspace**: persistent collapsible sidebar, mobile drawer and top bar; badge `Client workspace · <tenant name> · <role>` from the authenticated membership. Group links into Overview, Bots, Inbox, Contacts, Team, Tenant data and audit. Expose existing Handoff analytics as a secondary Insights link. Keep existing visibility/access rules, including admin-only team/data controls.
4. **Tenant overview without a new route**: add overview content to the current `/app/T/bots` landing page above the bot collection. Overview links to `/app/T/bots#overview`; Bots links to `/app/T/bots#bots`. Keep the existing page's bot forms, actions, links and destination behavior. This uses sections of one existing route, avoids creating a new product route and leaves per-bot Overview separate. This navigation choice is proposed for owner approval with this plan.
5. **Bot context**: clear bot name and breadcrumb, followed by the existing six tabs. Preserve direct links and the current settings destination from the bots list. Keep playground, retention and conversation deletion discoverable.
6. **Inbox**: desktop list/thread split pane reusing shared presentation components on the existing list/detail routes. Mobile keeps list-to-thread navigation and a back link. A direct detail URL must still load independently; preserve status/filter context where present. Existing filters are status, mode, channel, assignee, tag, unread and search (`q`); currently only `status` is initialized from the browser URL. Do not reinterpret or remove URL behavior while restyling. Chips reflect existing filters, not new server filters.
7. **Platform**: distinct staff shell/accent and `Platform admin` badge, links to existing clients/operations pages, clearly labeled return to client workspaces. No impersonation or reliance on tenant role for staff access. Retain server guard unchanged.
8. **Widget**: retain standalone iframe presentation rather than app navigation. Reuse visual tokens scoped to the frame/loader; apply existing bot config color, position, language and direction only. Do not introduce theme config fields or parent messaging.

## Available data, derivations and Skipped

| Requested presentation | Existing frontend contract / safe derivation | Decision |
| --- | --- | --- |
| Waiting/assigned/unread tiles | `inboxCounts`: waiting_human, assigned_to_me, unread_conversations, unread_messages | Render exact returned counts; retain viewer-specific meaning |
| Usage progress | `tenantQuota`: plan, usage, limits, warnings, measured_tokens_this_month | Use returned keys, guard zero/missing denominators, accessible meters; keep PLACEHOLDER and “final pricing and limits are TBD” |
| Recent conversations | `listInbox`: conversations, last_message, timestamp, channel/mode/status, unread_count | Render a small view of returned rows; do not invent timestamps or sorting guarantees |
| Bot exists checklist | `listBots` result | Derive only after successful load, with clear archived handling |
| Knowledge published checklist | `listRevisions` per bot: published_revision_id / current revision | Only declare completion from successful existing-endpoint responses; bounded/lazy reads, no invented bot fields |
| Widget installed checklist | No installation/heartbeat flag in current contracts; widget_locator/snippet or conversations do not prove installation | **Skipped: installation detection/status** |
| Inbox contact identity | `InboxConversation` has contact_id but no display name; existing contacts endpoint provides display_name | Resolve names from permitted contact data when available; fall back to visitor/short ID, without per-row request fan-out |
| Citations | Existing thread/playground/widget responses include source metadata | Expandable chips for returned citations only; retain safe http/https linking and raw text rendering |
| Ingestion progress | Jobs expose status, attempts, errors and timestamps; no completion percentage | **Skipped: numeric ingestion progress/ETA**. Use indeterminate pending/running states and actual attempts/failures; no simulated percentage |
| Typing/streaming feel | Current requests expose pending state, widget typing state; no token stream | Animate actual pending indicators only; **skip token-stream claims/fake incremental server output** |
| Sentiment, plans, channels | Display returned measured sentiment or existing empty state; placeholder quota plans; existing channel values/filters | No fabricated sentiment, billing checkout, new Meta connections, channels tab or providers |

No new analytics, installation tracking, avatars/online presence data or backend aggregation endpoints will be introduced. Failed data requests show errors/retry rather than false zero counts or incomplete onboarding steps presented as facts.

## Visual, accessibility and dependency plan

- One canonical token definition file for semantic colors, spacing, radii, typography and elevation. Scope widget application of those tokens to prevent dashboard leakage. Remove literal component colors; existing validated bot brand configuration supplies a CSS custom property. Loader must remain standalone and cannot depend on customer site CSS.
- Dark-first visual language with restrained accents and both light/dark token sets. First load follows system preference as requested; an explicit light/dark choice persists locally per authenticated viewer ID. Anonymous preference uses a separate key; do not transfer another viewer's choice on a shared device. No server persistence, theme endpoint or cookie/session logic changes.
- Keep system fonts for English/Arabic; no remote font loads. Use logical CSS, `dir="auto"` for user content, directional isolation for timestamps/IDs, visible focus, 44px practical touch targets, labeled fields, landmarks, skip link and semantic tables. Check WCAG AA contrast in both themes, including configured widget brand colors.
- Dialogs use labeled native `<dialog>` with focus entry/return, cancellation and keyboard tests; retain all validation and request payloads. Tenant deletion already has typed-name/reason protection; preserve that when presenting it in a modal. Bot archive currently executes directly, so the requested confirmation modal adds presentation confirmation without changing the archive operation. Contact erasure's existing confirm selects whether to erase messages; preserve that choice explicitly rather than converting Cancel into an unintended abort/erase behavior.
- Navigation-only Ctrl/Cmd+K palette lists existing authorized routes, not commands that perform mutations. Use accessible labels, keyboard selection, Escape and focus restoration. Drawer and palette are mutually managed so overlays do not trap focus together.
- Skeletons/toasts must keep existing error/status semantics without duplicate announcements. Motion respects `prefers-reduced-motion`; no animated fake data, progress or responses.
- **Dependencies proposed: none.** Existing React, CSS, native controls and small local SVG icons cover this scope. No version/lockfile changes planned. If a package becomes necessary, justify purpose, exact version, accessibility and bundle effect in a revised plan before adding it.

## Ordered implementation stages (after approval)

| Stage | Scope and output | Additional validation emphasis |
| --- | --- | --- |
| S1 | Tokens/themes, shared presentation primitives, client shell/sidebar/top bar, organization context, navigation-only palette, distinct platform chrome while preserving guard | Viewer-scoped theme persistence, focus/keyboard/drawer, existing navigation; check all routes for global CSS regressions and widget isolation |
| S2 | Landing, login/register/invite, organization picker, tenant overview section at existing bots landing; existing per-bot overview analytics styling | Provisioning/invitation/redirect validation, no role drift, real counts/usage/checklist derivation; avoid duplicate bot-form work reserved for S3 |
| S3 | Bots collection/create/archive confirmation, all six bot tabs: settings, knowledge, playground, install, saved conversations list/detail and overview consistency | Role restrictions, upload errors/job lifecycle/revisions, source-link security, locator and copy controls, retention/delete actions |
| S4 | Inbox toolbar/chips/list + desktop thread split pane, conversation bubbles/mode/actions, assignment/tags/notes, shared enum labels | All filters and routes, live refresh/read state, handoff/reply/resolve/return, viewer mode, Arabic counts/badges/snippets |
| S5 | Contacts/profile/follow-ups, team, existing handoff analytics, tenant export/delete/audit, platform clients/detail/operations | Preserve every role gate and typed confirmation/reason; add direct coverage of currently untested sensitive pages |
| S6 | Widget frame, launcher and synchronized loader copy, sample page | Same sandbox/CSP/origin checks and protocol, config theming, lead consent, polling/session/error behavior, 429 verbatim server text, keyboard/RTL/mobile |
| S7 | Full responsive/RTL/accessibility pass; update only requested manual-test instructions/labels, web command working directory, seed mojibake and `runon` typo | All pages in both themes; Arabic row with unread marker/count/status; no page-wide horizontal scroll; documentation edits preserve owner changes |

Every stage ends with verification evidence, a local stage commit, a report under 25 lines, and an owner gate before proceeding. Never include owner edits in a stage commit; stage exact file paths/hunks and inspect the staged diff. Large screenshots remain uncommitted. S7's manual-test edits must be isolated from pre-existing owner edits; if overlapping edits cannot be separated safely, stop and resolve that concrete conflict with the owner.

## Verification gates and evidence conventions

Run heavy commands sequentially, never concurrent builds or test suites:

1. From repository root: `npm.cmd run typecheck`, then `npm.cmd run lint`, then `npm.cmd run build`.
2. From repository root: `npm.cmd run test`, then a second `npm.cmd run test` only after the first finishes. Each run must retain all original 25 cases plus any additions, no skips, retries hiding failures or weaker assertions. Playwright already builds its production web server; account for that extra build. Ensure safe disposable test configuration is available without reading `.env` or exposing credentials. If unavailable, report the gate blocked rather than claiming success.
3. Capture changed pages in dark/light at desktop (e.g. 1440x900) and mobile (360x800), plus intermediate widths/wide desktop checks. For widgets use isolated frame/sample captures and configured RTL/brand variants; widget theme coverage uses frontend token/system modes, not a new API setting. Retain representative error, empty, loading, modal, handoff and Arabic states. No production customer data in screenshots.
4. Save screenshots to `implementation/ui-screens/S<n>/`, named by route/state/theme/viewport. If large, keep them uncommitted using local git exclude rather than changing shared ignore rules merely for evidence. Report exact paths, commands, outcomes and flaky failures.
5. Review diffs for backend/API/security-boundary changes, secrets, owner edits and unexpected generated files. Keep `next.config.ts` CSP, proxy behavior, iframe sandbox string `allow-scripts allow-same-origin allow-forms`, both directions of existing origin checks and `postMessage` target origins unchanged. Do not broaden messaging or convert plain message text into unsafe HTML.

Stage reports: changed pages; dependencies and reasons (expected none); exact checks/results; screenshot path; Skipped for missing API data; uncertainties/remaining work. No “green” claim without successful command output. No API pytest suite for this scope.

## Stage 0 evidence and approval notes

- Read repository/web agent rules, decision register, roadmap/prompt/checklist guidance, relevant expected behavior, frontend routes/shared helpers/API types, loader/frame security handling, package manifests, Playwright config/setup/helpers/spec sources. Did not read `.env` or backend implementation files.
- `git branch --show-current`: initially `feat/p1-01-foundation`. `git diff --name-only` and `git diff --cached --name-only`: empty at inventory time. Preserve protected files regardless of their current Git status.
- `rg -n 'test\(' apps/web/tests -g '*.spec.ts' | Measure-Object`: **25** source declarations. `(rg --files apps/web/app -g page.tsx | Measure-Object).Count`: **25**; `(rg --files apps/web/tests -g '*.spec.ts' | Measure-Object).Count`: **12**.
- Initial `git switch -c feat/ui-redesign feat/p1-01-foundation` failed because `.git/index.lock` was sandbox-protected. Repeated via approved escalation: succeeded, `Switched to a new branch 'feat/ui-redesign'`.
- Read-only discovery had a missing `tests` root / PowerShell wildcard lookup error; corrected searches target `apps/web/tests` with `-g '*.spec.ts'`. Git status also warned about inaccessible `.pytest-tmp-p5/`; no changes to that directory.
- No build, lint, typecheck, browser tests, API tests, screenshot capture or runtime claims in Stage 0; no application code or dependency changes. Stage 0 creates only this document and no commit.
- `git diff --check`: exit 0, no output. `git status --short --untracked-files=normal`: only this new plan listed (plus the existing inaccessible-directory warning).
- Approval covers the proposed existing-route tenant overview sections, zero-dependency approach and stage order. No S1 implementation starts until the owner approves this plan.
