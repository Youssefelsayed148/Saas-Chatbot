# Feature, screen and role inventory

> **Status: DRAFT, evidence-derived.** Generated from `implementation/inventory-data/` (commit b02dd95, run on 2026-10-17 against the local dev stack, demo tenant *Demo Dental Clinic*). Tables in sections 2, 3 and 4 are produced by script from those files, not typed by hand. Sections 5 to 8 (findings) are written separately and marked as judgment. Anything not covered by the evidence is listed under *Unverified* at the end.

## 0. How to read this
- **Evidence-based:** what the running app did for each of four identities (staff, client admin, client editor, client viewer) plus unauthenticated callers for the API.
- **Not covered:** results of actions (all non-GET requests were blocked or never sent), more than 2 instances per dynamic page type, content behind modals other than the two found, and anything for a second org (none exists).
- Route and status columns use `200` / `401` / `403` / `404` as returned by the API.

## 1. Agreed role model (from your notes; the reference for every verdict)
- **Platform staff (`is_platform_staff`):** alone controls bots, knowledge, persona, appearance, domains, widget snippet, tier, limits, playground, org create/delete (soft delete, 30-day grace, typed org name).
- **Client admin:** team and roles, audit, exports, contact edits, inbox on all channels, insights, change requests, read-only bot status.
- **Client editor:** inbox, contacts, insights. **Client viewer:** read-only.
- Clients see no bot data, settings, knowledge, traces, costs or citations. Org = one client, one bot by default.

## 2. Screen × role matrix
Legend: ✔ page renders · ⛔ page shell loads with HTTP 200 but shows a staff-only message · ↪ redirected · "no link; direct URL not tested" = the role's navigation never leads there and nobody opened the URL by hand (the API behind it is still guarded, see section 4) · "2-per-family cap" = the crawl visited at most 2 instances of a dynamic page type.

| Screen (`{tenant}`/`{bot}` = ids) | Staff | Admin | Editor | Viewer |
|---|---|---|---|---|
| `/app` | ✔ | ✔ | ✔ | ✔ |
| `/app/{tenant}` | ✔ | ⚠ crawled in error state (Unexpected server error + Retry page) | ⚠ crawled in error state (Unexpected server error + Retry page) | ✔ |
| `/app/{tenant}/analytics` | ✔ | ✔ | ✔ | ✔ |
| `/app/{tenant}/bots` | ✔ | ✔ | ✔ | ✔ |
| `/app/{tenant}/bots/{bot}/conversations` | ✔ | ✔ | ✔ | ✔ |
| `/app/{tenant}/bots/{bot}/conversations/{id}` | ✔ | ✔ | ✔ | ✔ |
| `/app/{tenant}/bots/{bot}/install` | ✔ | ⛔ shell loads (200), shows 'Platform staff access required.' | ⛔ shell loads (200), shows 'Platform staff access required.' | ⛔ shell loads (200), shows 'Platform staff access required.' |
| `/app/{tenant}/bots/{bot}/knowledge` | ✔ | ⛔ shell loads (200), shows 'Platform staff access required.' | ⛔ shell loads (200), shows 'Platform staff access required.' | ⛔ shell loads (200), shows 'Platform staff access required.' |
| `/app/{tenant}/bots/{bot}/overview` | ✔ | ✔ | ✔ | ✔ |
| `/app/{tenant}/bots/{bot}/playground` | ✔ | ⛔ shell loads (200), shows 'Platform staff access required.' | ⛔ shell loads (200), shows 'Platform staff access required.' | ⛔ shell loads (200), shows 'Platform staff access required.' |
| `/app/{tenant}/bots/{bot}/settings` | ✔ | ✔ | ✔ | ✔ |
| `/app/{tenant}/contacts` | ✔ | ✔ | ✔ | ✔ |
| `/app/{tenant}/contacts/{id}` | ✔ | ✔ | ✔ | ✔ |
| `/app/{tenant}/inbox` | ✔ | ⚠ crawled in error state (Unexpected server error + Retry page) | ⚠ crawled in error state (Unexpected server error + Retry page) | ✔ |
| `/app/{tenant}/inbox/{id}` | ✔ | — no link; direct URL not tested | — no link; direct URL not tested | ✔ |
| `/app/{tenant}/settings/data` | ✔ | ✔ | — no link; direct URL not tested | — no link; direct URL not tested |
| `/app/{tenant}/settings/members` | ✔ | ✔ | — no link; direct URL not tested | — no link; direct URL not tested |
| `/app/{tenant}/settings/requests` | ✔ | ✔ | — no link; direct URL not tested | — no link; direct URL not tested |
| `/platform` | ✔ | ↪ redirects to /app | ↪ redirects to /app | ↪ redirects to /app |
| `/platform/change-requests` | ✔ | — no link; direct URL not tested | — no link; direct URL not tested | — no link; direct URL not tested |
| `/platform/clients/{tenant}` | ✔ | — no link; direct URL not tested | — no link; direct URL not tested | — no link; direct URL not tested |
| `/platform/operations` | ✔ | ↪ redirects to /app | ↪ redirects to /app | ↪ redirects to /app |
| `/widget/sample?…` | ✔ | — no link; direct URL not tested | — no link; direct URL not tested | — no link; direct URL not tested |

### Sidebar per role (as rendered on the tenant overview page)
- **staff:** `◈ Overview`, `✧ Bots`, `▤ Inbox`, `◎ Contacts`, `? Request a change`, `♧ Team`, `▦ Tenant data and audit`, `▥ Handoff analytics`, `↗ Platform admin`
- **admin:** `◈ Overview`, `✧ Bots`, `▤ Inbox`, `◎ Contacts`, `? Request a change`, `♧ Team`, `▦ Tenant data and audit`, `▥ Handoff analytics`
- **editor:** `◈ Overview`, `✧ Bots`, `▤ Inbox`, `◎ Contacts`, `▥ Handoff analytics`
- **viewer:** `◈ Overview`, `✧ Bots`, `▤ Inbox`, `◎ Contacts`, `▥ Handoff analytics`

## 3. What each screen contains
For each screen: the staff view first, then what differs for the client roles. Global chrome on every page (not repeated): Appearance toggle, collapse and menu buttons, *Search pages* command palette (Ctrl/Cmd-K), *Sign out*, organization switcher.

### `/app`
- **Reached by:** staff, admin, editor, viewer. **Title tag:** `Website Chatbot SaaS`.
- **staff headings:** `Your organizations`
- **staff buttons:** none
- **staff form fields (labels):** none
- **staff in-page links:** none
- **admin vs staff:** links +`Demo Dental Clinic → /app/{tenant}/bots`
- **editor vs staff:** links +`Demo Dental Clinic → /app/{tenant}/bots`
- **viewer vs staff:** links +`Demo Dental Clinic → /app/{tenant}/bots`

### `/app/{tenant}`
- **Reached by:** staff, admin, editor, viewer. **Title tag:** `Website Chatbot SaaS`.
- **staff headings:** `Overview`; `Recent conversations`; `Your first assistant`; `Plan usage`
- **staff buttons:** none
- **staff form fields (labels):** `Bots 1 / 30`; `Seats 3 / 50`; `Pages Per Bot 4 / 2000`; `Upload File Mb 0 / 25`; `Monthly Messages 5 / 60000`; `Contacts 3 / 100000`; `Channel Connections 1 / 10`; `Sentiment Runs 0 / 20000`
- **staff in-page links:** `Open inbox ↗ → /app/{tenant}/inbox`; `View inbox → → /app/{tenant}/inbox`; `سيساعدك أحد الموظفين قريباً. Website · Waiting for human · 10/15/2026 → /app/{tenant}/inbox/{id}`; `Your fictional booking is confirmed for Tuesday at 10:00. Website · Resolved · 10/15/2026 → /app/{tenant}/inbox/{id}`; `Your fictional booking is confirmed for Tuesday at 10:00. Website · Open · 10/15/2026 → /app/{tenant}/inbox/{id}`; `A human will help you shortly. Website · Waiting for human · 10/15/2026 → /app/{tenant}/inbox/{id}`; `A human will help with your question. Website · Waiting for human · 10/15/2026 → /app/{tenant}/inbox/{id}`; `First bot created → /app/{tenant}/bots`; `Knowledge published Demo Dental Assistant → /app/{tenant}/bots/{bot}/knowledge`
- **admin vs staff:** ⚠ captured in error state (Unexpected server error + Retry page); comparison not meaningful.
- **editor vs staff:** ⚠ captured in error state (Unexpected server error + Retry page); comparison not meaningful.
- **viewer vs staff:** links −`Knowledge published Demo Dental Assistant → /app/{tenant}/bots/{bot}/knowledge`

### `/app/{tenant}/analytics`
- **Reached by:** staff, admin, editor, viewer. **Title tag:** `Website Chatbot SaaS`.
- **staff headings:** `Handoff analytics`; `AI costs and limits`; `Conversation outcomes`; `Conversations by channel`; `Agent workload`; `Sentiment`
- **staff buttons:** `Save AI limits`; `Reset to plan defaults`
- **staff form fields (labels):** `Bot Demo Dental Assistant`; `Documents per revision Used: 4; effective limit: Uncapped`; `Chunks per revision Used: 4; effective limit: Uncapped`; `Stored upload bytes Used: 633; effective limit: Uncapped`; `AI messages per month Used: 5; effective limit: Uncapped`; `AI tokens per month Used: 73; effective limit: Uncapped`; `Embedding tokens per month Used: 73; effective limit: Uncapped`; `OCR pages per month Used: 0; effective limit: Uncapped`
- **staff in-page links:** none
- **admin vs staff:** headings −`AI costs and limits` · buttons −`Save AI limits`; `Reset to plan defaults` · fields −`Bot Demo Dental Assistant`; `Documents per revision Used: 4; effective limit: Uncapped`; `Chunks per revision Used: 4; effective limit: Uncapped`; `Stored upload bytes Used: 633; effective limit: Uncapped`; `AI messages per month Used: 5; effective limit: Uncapped`; `AI tokens per month Used: 73; effective limit: Uncapped`; `Embedding tokens per month Used: 73; effective limit: Uncapped`; `OCR pages per month Used: 0; effective limit: Uncapped`
- **editor vs staff:** headings −`AI costs and limits` · buttons −`Save AI limits`; `Reset to plan defaults` · fields −`Bot Demo Dental Assistant`; `Documents per revision Used: 4; effective limit: Uncapped`; `Chunks per revision Used: 4; effective limit: Uncapped`; `Stored upload bytes Used: 633; effective limit: Uncapped`; `AI messages per month Used: 5; effective limit: Uncapped`; `AI tokens per month Used: 73; effective limit: Uncapped`; `Embedding tokens per month Used: 73; effective limit: Uncapped`; `OCR pages per month Used: 0; effective limit: Uncapped`
- **viewer vs staff:** headings −`AI costs and limits` · buttons −`Save AI limits`; `Reset to plan defaults` · fields −`Bot Demo Dental Assistant`; `Documents per revision Used: 4; effective limit: Uncapped`; `Chunks per revision Used: 4; effective limit: Uncapped`; `Stored upload bytes Used: 633; effective limit: Uncapped`; `AI messages per month Used: 5; effective limit: Uncapped`; `AI tokens per month Used: 73; effective limit: Uncapped`; `Embedding tokens per month Used: 73; effective limit: Uncapped`; `OCR pages per month Used: 0; effective limit: Uncapped`

### `/app/{tenant}/bots`
- **Reached by:** staff, admin, editor, viewer. **Title tag:** `Website Chatbot SaaS`.
- **staff headings:** `Bots`; `Plan usage`
- **staff buttons:** none
- **staff form fields (labels):** `Show archived bots`
- **staff in-page links:** `Tenant data and audit → /app/{tenant}/settings/data`; `Demo Dental Assistant → /app/{tenant}/bots/{bot}/settings`; `Open bot → /app/{tenant}/bots/{bot}/settings`
- **admin vs staff:** identical
- **editor vs staff:** links −`Tenant data and audit → /app/{tenant}/settings/data`
- **viewer vs staff:** links −`Tenant data and audit → /app/{tenant}/settings/data`

### `/app/{tenant}/bots/{bot}/conversations`
- **Reached by:** staff, admin, editor, viewer. **Title tag:** `Website Chatbot SaaS`.
- **staff headings:** `Conversations`
- **staff buttons:** `Save retention`; `Delete`
- **staff form fields (labels):** `Message retention (days, tenant-wide, 1–365)`
- **staff in-page links:** `10/15/2026, 2:01:30 PM → /app/{tenant}/bots/{bot}/conversations/{id}`; `10/15/2026, 1:57:30 PM → /app/{tenant}/bots/{bot}/conversations/{id}`; `10/15/2026, 1:53:30 PM → /app/{tenant}/bots/{bot}/conversations/{id}`; `10/15/2026, 1:49:30 PM → /app/{tenant}/bots/{bot}/conversations/{id}`; `10/15/2026, 1:45:32 PM → /app/{tenant}/bots/{bot}/conversations/{id}`; `10/15/2026, 1:41:30 PM → /app/{tenant}/bots/{bot}/conversations/{id}`
- **admin vs staff:** identical
- **editor vs staff:** buttons −`Save retention`; `Delete` · fields −`Message retention (days, tenant-wide, 1–365)`
- **viewer vs staff:** buttons −`Save retention`; `Delete` · fields −`Message retention (days, tenant-wide, 1–365)`

### `/app/{tenant}/bots/{bot}/conversations/{id}`
- **Reached by:** staff, admin, editor, viewer. **Title tag:** `Website Chatbot SaaS`.
- **staff headings:** `Conversation`
- **staff buttons:** none
- **staff form fields (labels):** none
- **staff in-page links:** `Back to conversations → /app/{tenant}/bots/{bot}/conversations`
- **admin vs staff:** identical
- **editor vs staff:** identical
- **viewer vs staff:** identical

### `/app/{tenant}/bots/{bot}/install`
- **Reached by:** staff. **Title tag:** `Website Chatbot SaaS`.
- **staff headings:** `Demo Dental Assistant — install`; `1. Paste this one script tag before </body> of your site`; `2. Test on a sample page`; `3. What your visitors get`
- **staff buttons:** `Copy snippet`
- **staff form fields (labels):** none
- **staff in-page links:** `Open a sample page with this bot embedded → /widget/sample?…`

### `/app/{tenant}/bots/{bot}/knowledge`
- **Reached by:** staff. **Title tag:** `Website Chatbot SaaS`.
- **staff headings:** `Knowledge`; `Upload files`; `Files`; `Jobs`; `Documents and chunks`; `Revisions`
- **staff buttons:** `Upload`; `Ingest files`; `Retry`; `Opening hours — Opening hours`; `Pricing — Pricing`; `Booking — Booking`; `Location — Location`
- **staff form fields (labels):** `Files (max 20, up to 25 MB each under current plan limits)`; `View Published knowledge Draft (latest ingest)`
- **staff in-page links:** `(download the template) → /api/v1/tenants/{tenant}/bots/{bot}/sources/qa-template`

### `/app/{tenant}/bots/{bot}/overview`
- **Reached by:** staff, admin, editor, viewer. **Title tag:** `Website Chatbot SaaS`.
- **staff headings:** `Overview`; `Volume per day`; `Top questions`; `Unanswered questions (the bot could not confirm)`; `Leads trend`
- **staff buttons:** `Apply`
- **staff form fields (labels):** `From`; `To`
- **staff in-page links:** `Export conversations CSV → /api/v1/tenants/{tenant}/bots/{bot}/analytics/conversations.csv?…`; `Export leads CSV → /api/v1/tenants/{tenant}/bots/{bot}/analytics/leads.csv?…`
- **admin vs staff:** identical
- **editor vs staff:** identical
- **viewer vs staff:** identical

### `/app/{tenant}/bots/{bot}/playground`
- **Reached by:** staff. **Title tag:** `Website Chatbot SaaS`.
- **staff headings:** `Playground`; `Answer traces`
- **staff buttons:** `Send`
- **staff form fields (labels):** `Message`
- **staff in-page links:** none

### `/app/{tenant}/bots/{bot}/settings`
- **Reached by:** staff, admin, editor, viewer. **Title tag:** `Website Chatbot SaaS`.
- **staff headings:** `Demo Dental Assistant — settings`; `AI tier`
- **staff buttons:** `Pause bot`; `Save settings`; `Start embedding backfill`
- **staff form fields (labels):** `Bot name`; `Assistant name`; `Business name`; `Business description`; `Welcome message (EN)`; `Welcome message (AR)`; `Opening questions (one per line, max 10)`; `Default language English العربية`; `Support email`; `Support phone`; `Widget colour (hex, e.g. #1a2b3c)`; `Widget avatar (public http(s) image URL)`; `Widget position (none) Left Right`; `Human handoff enabled`; `Allowed domains (one per line, max 50)`; `Tier Standard Premium`
- **staff in-page links:** none
- **admin vs staff:** headings +`Bot status` · headings −`Demo Dental Assistant — settings`; `AI tier` · buttons −`Pause bot`; `Save settings`; `Start embedding backfill` · fields −`Bot name`; `Assistant name`; `Business name`; `Business description`; `Welcome message (EN)`; `Welcome message (AR)`; `Opening questions (one per line, max 10)`; `Default language English العربية`; `Support email`; `Support phone`; `Widget colour (hex, e.g. #1a2b3c)`; `Widget avatar (public http(s) image URL)`; `Widget position (none) Left Right`; `Human handoff enabled`; `Allowed domains (one per line, max 50)`; `Tier Standard Premium`
- **editor vs staff:** headings +`Bot status` · headings −`Demo Dental Assistant — settings`; `AI tier` · buttons −`Pause bot`; `Save settings`; `Start embedding backfill` · fields −`Bot name`; `Assistant name`; `Business name`; `Business description`; `Welcome message (EN)`; `Welcome message (AR)`; `Opening questions (one per line, max 10)`; `Default language English العربية`; `Support email`; `Support phone`; `Widget colour (hex, e.g. #1a2b3c)`; `Widget avatar (public http(s) image URL)`; `Widget position (none) Left Right`; `Human handoff enabled`; `Allowed domains (one per line, max 50)`; `Tier Standard Premium`
- **viewer vs staff:** headings +`Bot status` · headings −`Demo Dental Assistant — settings`; `AI tier` · buttons −`Pause bot`; `Save settings`; `Start embedding backfill` · fields −`Bot name`; `Assistant name`; `Business name`; `Business description`; `Welcome message (EN)`; `Welcome message (AR)`; `Opening questions (one per line, max 10)`; `Default language English العربية`; `Support email`; `Support phone`; `Widget colour (hex, e.g. #1a2b3c)`; `Widget avatar (public http(s) image URL)`; `Widget position (none) Left Right`; `Human handoff enabled`; `Allowed domains (one per line, max 50)`; `Tier Standard Premium`

### `/app/{tenant}/contacts`
- **Reached by:** staff, admin, editor, viewer. **Title tag:** `Website Chatbot SaaS`.
- **staff headings:** `Contacts`; `Add contact`
- **staff buttons:** `Create contact`
- **staff form fields (labels):** `Name`; `Email`; `Phone`
- **staff in-page links:** `Export CSV → /api/v1/tenants/{tenant}/contacts/export.csv`; `Fictional Visitor 3 → /app/{tenant}/contacts/{id}`; `Fictional Visitor 1 → /app/{tenant}/contacts/{id}`; `Fictional Visitor 2 → /app/{tenant}/contacts/{id}`
- **admin vs staff:** identical
- **editor vs staff:** identical
- **viewer vs staff:** headings −`Add contact` · buttons −`Create contact` · fields −`Name`; `Email`; `Phone`

### `/app/{tenant}/contacts/{id}`
- **Reached by:** staff, admin, editor, viewer. **Title tag:** `Website Chatbot SaaS`.
- **staff headings:** `Fictional Visitor 3`; `Channel identities`; `Timeline`; `Website follow-ups`; `Merge contacts`; `Erase contact`; `Erase this contact?`
- **staff buttons:** `Save contact`; `Schedule follow-up`; `Merge into selected contact`; `Erase contact`; `Cancel`; `Confirm erasure`
- **staff form fields (labels):** `Name`; `Email`; `Phone`; `Stage`; `Tags (comma separated)`; `Custom fields (JSON, up to 20 keys)`; `Conversation Choose conversation website Â· waiting_human Â· 10/15/2026 website Â· waiting_human Â· 10/15/2026`; `Send after`; `Message`; `Move this contact into Choose contact Fictional Visitor 1 Fictional Visitor 2`; `Also erase messages in this contact’s conversations`
- **staff in-page links:** `← Contacts → /app/{tenant}/contacts`
- **admin vs staff:** identical
- **editor vs staff:** headings −`Merge contacts`; `Erase contact`; `Erase this contact?` · buttons −`Merge into selected contact`; `Erase contact`; `Cancel`; `Confirm erasure` · fields −`Move this contact into Choose contact Fictional Visitor 1 Fictional Visitor 2`; `Also erase messages in this contact’s conversations`
- **viewer vs staff:** headings −`Merge contacts`; `Erase contact`; `Erase this contact?` · buttons −`Save contact`; `Schedule follow-up`; `Merge into selected contact`; `Erase contact`; `Cancel`; `Confirm erasure` · fields −`Conversation Choose conversation website Â· waiting_human Â· 10/15/2026 website Â· waiting_human Â· 10/15/2026`; `Send after`; `Message`; `Move this contact into Choose contact Fictional Visitor 1 Fictional Visitor 2`; `Also erase messages in this contact’s conversations`

### `/app/{tenant}/inbox`
- **Reached by:** staff, admin, editor, viewer. **Title tag:** `Website Chatbot SaaS`.
- **staff headings:** `Inbox`; `Every conversation, in context`
- **staff buttons:** none
- **staff form fields (labels):** `Search`; `Status All Waiting for human Open Resolved`
- **staff in-page links:** `Fictional Visitor 3 10/15/2026 سيساعدك أحد الموظفين قريباً. ◎ Website Waiting for human ● 1 Human · Visitor requested a person → /app/{tenant}/inbox/{id}`; `Fictional Visitor 2 10/15/2026 Your fictional booking is confirmed for Tuesday at 10:00. ◎ Website Resolved ● 2 Human · Manual takeover → /app/{tenant}/inbox/{id}`; `Fictional Visitor 1 10/15/2026 Your fictional booking is confirmed for Tuesday at 10:00. ◎ Website Open ● 2 Human · Manual takeover → /app/{tenant}/inbox/{id}`; `Fictional Visitor 3 10/15/2026 A human will help you shortly. ◎ Website Waiting for human ● 1 Human · Visitor requested a person → /app/{tenant}/inbox/{id}`; `Fictional Visitor 2 10/15/2026 A human will help with your question. ◎ Website Waiting for human ● 2 Human · Repeated unanswered questions → /app/{tenant}/inbox/{id}`; `Fictional Visitor 1 10/15/2026 We are open Monday to Friday from 09:00 to 17:00. ◎ Website Open ● 1 AI → /app/{tenant}/inbox/{id}`
- **admin vs staff:** ⚠ captured in error state (Unexpected server error + Retry page); comparison not meaningful.
- **editor vs staff:** ⚠ captured in error state (Unexpected server error + Retry page); comparison not meaningful.
- **viewer vs staff:** identical

### `/app/{tenant}/inbox/{id}`
- **Reached by:** staff, viewer. **Title tag:** `Website Chatbot SaaS`.
- **staff headings:** `Inbox`; `Conversation`
- **staff buttons:** none
- **staff form fields (labels):** `Search`; `Status All Waiting for human Open Resolved`
- **staff in-page links:** `Fictional Visitor 3 10/15/2026 سيساعدك أحد الموظفين قريباً. ◎ Website Waiting for human ● 1 Human · Visitor requested a person → /app/{tenant}/inbox/{id}`; `Fictional Visitor 2 10/15/2026 Your fictional booking is confirmed for Tuesday at 10:00. ◎ Website Resolved ● 2 Human · Manual takeover → /app/{tenant}/inbox/{id}`; `Fictional Visitor 1 10/15/2026 Your fictional booking is confirmed for Tuesday at 10:00. ◎ Website Open ● 2 Human · Manual takeover → /app/{tenant}/inbox/{id}`; `Fictional Visitor 3 10/15/2026 A human will help you shortly. ◎ Website Waiting for human ● 1 Human · Visitor requested a person → /app/{tenant}/inbox/{id}`; `Fictional Visitor 2 10/15/2026 A human will help with your question. ◎ Website Waiting for human ● 2 Human · Repeated unanswered questions → /app/{tenant}/inbox/{id}`; `Fictional Visitor 1 10/15/2026 We are open Monday to Friday from 09:00 to 17:00. ◎ Website Open ● 1 AI → /app/{tenant}/inbox/{id}`; `← Back to inbox → /app/{tenant}/inbox`
- **viewer vs staff:** identical

### `/app/{tenant}/settings/data`
- **Reached by:** staff, admin. **Title tag:** `Website Chatbot SaaS`.
- **staff headings:** `Tenant data and audit`; `Export tenant data`; `Audit review`; `Delete organization and data`; `Delete this organization?`
- **staff buttons:** `Download export`; `Search`; `Schedule organization deletion`; `Cancel`; `Delete organization now`
- **staff form fields (labels):** `Search actions`; `Type Demo Dental Clinic to confirm`; `Reason for deletion`; `Type the organization name`
- **staff in-page links:** `Back to bots → /app/{tenant}/bots`
- **admin vs staff:** headings −`Delete organization and data`; `Delete this organization?` · buttons −`Schedule organization deletion`; `Cancel`; `Delete organization now` · fields −`Type Demo Dental Clinic to confirm`; `Reason for deletion`; `Type the organization name`

### `/app/{tenant}/settings/members`
- **Reached by:** staff, admin. **Title tag:** `Website Chatbot SaaS`.
- **staff headings:** `Team`; `Invite a teammate`; `Pending invitations`; `Members`
- **staff buttons:** `Create invite link`; `Remove`
- **staff form fields (labels):** `Email`; `Role Admin Editor Viewer`
- **staff in-page links:** none
- **admin vs staff:** identical

### `/app/{tenant}/settings/requests`
- **Reached by:** staff, admin. **Title tag:** `Website Chatbot SaaS`.
- **staff headings:** `Request a change`
- **staff buttons:** `Submit request`
- **staff form fields (labels):** `Request type Knowledge Text change Domain Delete organization Other`; `Describe the change`; `Attachments`
- **staff in-page links:** none
- **admin vs staff:** identical

### `/platform`
- **Reached by:** staff. **Title tag:** `Website Chatbot SaaS`.
- **staff headings:** `Platform — clients`; `Onboard a new client`
- **staff buttons:** `Search`; `Onboard client`
- **staff form fields (labels):** `Search`; `Status All active archived`; `Client name`; `Admin email (one-time invite link, no email)`; `Bot name`; `Website-to-knowledge skill output (optional files)`
- **staff in-page links:** `Operations, analytics, and audit review → /platform/operations`; `Demo Dental Clinic → /platform/clients/{tenant}`

### `/platform/change-requests`
- **Reached by:** staff. **Title tag:** `Website Chatbot SaaS`.
- **staff headings:** `Operator change queue`
- **staff buttons:** none
- **staff form fields (labels):** none
- **staff in-page links:** none

### `/platform/clients/{tenant}`
- **Reached by:** staff. **Title tag:** `Website Chatbot SaaS`.
- **staff headings:** `Demo Dental Clinic`; `Bots`; `Plan assignment`; `Knowledge/ingest failures`; `Members`; `Recent audit`
- **staff buttons:** `Pause bot`; `Save plan`; `Save override with reason`
- **staff form fields (labels):** `Plan label`; `Reason`; `Quota overrides (JSON)`
- **staff in-page links:** `Operate bots → /app/{tenant}/bots`; `Organization data and deletion → /app/{tenant}/settings/data`; `← Back to clients → /platform`

### `/platform/operations`
- **Reached by:** staff. **Title tag:** `Website Chatbot SaaS`.
- **staff headings:** `Platform operations`; `Provisional quota limits`; `Platform analytics`; `Job queue`; `Audit review`
- **staff buttons:** `Retry`; `Cancel`; `Search`
- **staff form fields (labels):** `Reason for job action`; `Search audit actions`
- **staff in-page links:** `Back to clients → /platform`

### `/widget/sample?…`
- **Reached by:** staff. **Title tag:** `Website Chatbot SaaS`.
- **staff headings:** `Store A (sample site)`
- **staff buttons:** none
- **staff form fields (labels):** none
- **staff in-page links:** none

## 4. API routes × role (116 operations)
Guard = declared minimum role from the code (`staff-only` = `PlatformStaffDep` or `require_operator`). Status columns exist only for GET routes (real ids where available, see README for placeholder caveats); non-GET routes were not called, so their guard is from code only.

| Method | Path | Declared guard | Staff | Admin | Editor | Viewer | Unauth |
|---|---|---|---|---|---|---|---|
| POST | `/api/public/v1/sessions/{session_id}/lead` | none/public | not probed | not probed | not probed | not probed | not probed |
| GET | `/api/public/v1/sessions/{session_id}/messages` | none/public | 401 | 401 | 401 | 401 | 401 |
| POST | `/api/public/v1/sessions/{session_id}/messages` | none/public | not probed | not probed | not probed | not probed | not probed |
| POST | `/api/public/v1/sessions/{session_id}/messages/{message_id}/feedback` | none/public | not probed | not probed | not probed | not probed | not probed |
| GET | `/api/public/v1/widgets/{locator}/config` | none/public | 200 | 200 | 200 | 200 | 200 |
| POST | `/api/public/v1/widgets/{locator}/sessions` | none/public | not probed | not probed | not probed | not probed | not probed |
| GET | `/api/v1/auth/config` | none/public | 200 | 200 | 200 | 200 | 200 |
| POST | `/api/v1/auth/login` | none/public | not probed | not probed | not probed | not probed | not probed |
| POST | `/api/v1/auth/logout` | none/public | not probed | not probed | not probed | not probed | not probed |
| GET | `/api/v1/auth/me` | authenticated(any) | 200 | 200 | 200 | 200 | 401 |
| POST | `/api/v1/auth/register` | none/public | not probed | not probed | not probed | not probed | not probed |
| POST | `/api/v1/invitations/accept` | authenticated(any) | not probed | not probed | not probed | not probed | not probed |
| GET | `/api/v1/platform/analytics` | staff-only | 200 | 403 | 403 | 403 | 401 |
| GET | `/api/v1/platform/audit` | staff-only | 200 | 403 | 403 | 403 | 401 |
| POST | `/api/v1/platform/bots/{bot_id}/pause` | staff-only | not probed | not probed | not probed | not probed | not probed |
| GET | `/api/v1/platform/change-requests` | staff-only | 200 | 403 | 403 | 403 | 401 |
| PATCH | `/api/v1/platform/change-requests/{request_id}` | staff-only | not probed | not probed | not probed | not probed | not probed |
| GET | `/api/v1/platform/me` | staff-only | 200 | 403 | 403 | 403 | 401 |
| POST | `/api/v1/platform/onboarding` | staff-only | not probed | not probed | not probed | not probed | not probed |
| GET | `/api/v1/platform/onboarding.csv` | staff-only | 200 | 403 | 403 | 403 | 401 |
| GET | `/api/v1/platform/onboarding/{request_id}` | staff-only | 404 | 403 | 403 | 403 | 401 |
| GET | `/api/v1/platform/operations/jobs` | staff-only | 200 | 403 | 403 | 403 | 401 |
| POST | `/api/v1/platform/operations/jobs/{job_id}/cancel` | staff-only | not probed | not probed | not probed | not probed | not probed |
| POST | `/api/v1/platform/operations/jobs/{job_id}/retry` | staff-only | not probed | not probed | not probed | not probed | not probed |
| GET | `/api/v1/platform/quotas` | staff-only | 200 | 403 | 403 | 403 | 401 |
| GET | `/api/v1/platform/tenants` | staff-only | 200 | 403 | 403 | 403 | 401 |
| GET | `/api/v1/platform/tenants/{tenant_id}` | staff-only | 200 | 403 | 403 | 403 | 401 |
| POST | `/api/v1/platform/tenants/{tenant_id}/bots` | staff-only | not probed | not probed | not probed | not probed | not probed |
| DELETE | `/api/v1/platform/tenants/{tenant_id}/bots/{bot_id}` | staff-only | not probed | not probed | not probed | not probed | not probed |
| PATCH | `/api/v1/platform/tenants/{tenant_id}/plan` | staff-only | not probed | not probed | not probed | not probed | not probed |
| PATCH | `/api/v1/platform/tenants/{tenant_id}/quota-overrides` | staff-only | not probed | not probed | not probed | not probed | not probed |
| POST | `/api/v1/provisioning/self-service` | authenticated(any) | not probed | not probed | not probed | not probed | not probed |
| POST | `/api/v1/tenants` | authenticated | not probed | not probed | not probed | not probed | not probed |
| GET | `/api/v1/tenants/{tenant_id}` | viewer | 200 | 200 | 200 | 200 | 401 |
| PATCH | `/api/v1/tenants/{tenant_id}` | admin | not probed | not probed | not probed | not probed | not probed |
| GET | `/api/v1/tenants/{tenant_id}/analytics` | viewer | 200 | 200 | 200 | 200 | 401 |
| GET | `/api/v1/tenants/{tenant_id}/bots` | viewer | 200 | 200 | 200 | 200 | 401 |
| POST | `/api/v1/tenants/{tenant_id}/bots` | staff-only | not probed | not probed | not probed | not probed | not probed |
| DELETE | `/api/v1/tenants/{tenant_id}/bots/{bot_id}` | staff-only | not probed | not probed | not probed | not probed | not probed |
| GET | `/api/v1/tenants/{tenant_id}/bots/{bot_id}` | viewer | 200 | 200 | 200 | 200 | 401 |
| PATCH | `/api/v1/tenants/{tenant_id}/bots/{bot_id}` | staff-only | not probed | not probed | not probed | not probed | not probed |
| GET | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/analytics/conversations.csv` | admin | 200 | 200 | 403 | 403 | 401 |
| GET | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/analytics/leads` | viewer | 200 | 200 | 200 | 200 | 401 |
| GET | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/analytics/leads.csv` | admin | 200 | 200 | 403 | 403 | 401 |
| GET | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/analytics/summary` | viewer | 200 | 200 | 200 | 200 | 401 |
| GET | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/analytics/top-questions` | viewer | 200 | 200 | 200 | 200 | 401 |
| GET | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/analytics/unanswered` | viewer | 200 | 200 | 200 | 200 | 401 |
| GET | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/analytics/volume` | viewer | 200 | 200 | 200 | 200 | 401 |
| GET | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/conversations` | viewer | 200 | 200 | 200 | 200 | 401 |
| DELETE | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/conversations/{conversation_id}` | admin | not probed | not probed | not probed | not probed | not probed |
| GET | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/conversations/{conversation_id}` | viewer | 200 | 200 | 200 | 200 | 401 |
| GET | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/documents` | platform_staff_only | 200 | 403 | 403 | 403 | 401 |
| GET | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/documents/{document_id}/chunks` | platform_staff_only | 200 | 403 | 403 | 403 | 401 |
| POST | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/ingestion` | staff-only | not probed | not probed | not probed | not probed | not probed |
| GET | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/jobs` | platform_staff_only | 200 | 403 | 403 | 403 | 401 |
| GET | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/jobs/{job_id}` | platform_staff_only | 200 | 403 | 403 | 403 | 401 |
| POST | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/jobs/{job_id}/cancel` | staff-only | not probed | not probed | not probed | not probed | not probed |
| POST | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/jobs/{job_id}/retry` | staff-only | not probed | not probed | not probed | not probed | not probed |
| POST | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/messages/{message_id}/feedback` | staff-only | not probed | not probed | not probed | not probed | not probed |
| GET | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/playground/conversation` | platform_staff_only | 200 | 403 | 403 | 403 | 401 |
| POST | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/playground/messages` | staff-only | not probed | not probed | not probed | not probed | not probed |
| GET | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/quota` | viewer | 200 | 200 | 200 | 200 | 401 |
| GET | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/rag` | staff-only | 200 | 403 | 403 | 403 | 401 |
| PATCH | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/rag` | staff-only | not probed | not probed | not probed | not probed | not probed |
| POST | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/rag/backfill` | staff-only | not probed | not probed | not probed | not probed | not probed |
| GET | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/rag/costs` | staff-only | 200 | 403 | 403 | 403 | 401 |
| GET | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/rag/traces` | staff-only | 200 | 403 | 403 | 403 | 401 |
| GET | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/revisions` | platform_staff_only | 200 | 403 | 403 | 403 | 401 |
| POST | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/revisions/{revision_id}/publish` | staff-only | not probed | not probed | not probed | not probed | not probed |
| GET | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/sources` | platform_staff_only | 200 | 403 | 403 | 403 | 401 |
| POST | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/sources/files` | staff-only | not probed | not probed | not probed | not probed | not probed |
| GET | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/sources/qa-template` | staff-only | 200 | 403 | 403 | 403 | 401 |
| GET | `/api/v1/tenants/{tenant_id}/bots/{bot_id}/sources/{source_id}` | platform_staff_only | 200 | 403 | 403 | 403 | 401 |
| GET | `/api/v1/tenants/{tenant_id}/change-requests` | admin | 200 | 200 | 403 | 403 | 401 |
| POST | `/api/v1/tenants/{tenant_id}/change-requests` | admin | not probed | not probed | not probed | not probed | not probed |
| GET | `/api/v1/tenants/{tenant_id}/change-requests/{request_id}/attachments/{attachment_id}` | admin | 404 | 404 | 403 | 403 | 401 |
| GET | `/api/v1/tenants/{tenant_id}/contacts` | viewer | 200 | 200 | 200 | 200 | 401 |
| POST | `/api/v1/tenants/{tenant_id}/contacts` | editor | not probed | not probed | not probed | not probed | not probed |
| GET | `/api/v1/tenants/{tenant_id}/contacts/export.csv` | admin | 200 | 200 | 403 | 403 | 401 |
| GET | `/api/v1/tenants/{tenant_id}/contacts/stages` | viewer | 200 | 200 | 200 | 200 | 401 |
| PATCH | `/api/v1/tenants/{tenant_id}/contacts/stages` | admin | not probed | not probed | not probed | not probed | not probed |
| DELETE | `/api/v1/tenants/{tenant_id}/contacts/{contact_id}` | admin | not probed | not probed | not probed | not probed | not probed |
| GET | `/api/v1/tenants/{tenant_id}/contacts/{contact_id}` | viewer | 200 | 200 | 200 | 200 | 401 |
| PATCH | `/api/v1/tenants/{tenant_id}/contacts/{contact_id}` | editor | not probed | not probed | not probed | not probed | not probed |
| POST | `/api/v1/tenants/{tenant_id}/contacts/{contact_id}/merge` | admin | not probed | not probed | not probed | not probed | not probed |
| GET | `/api/v1/tenants/{tenant_id}/conversations/{conversation_id}` | viewer | 200 | 200 | 200 | 200 | 401 |
| POST | `/api/v1/tenants/{tenant_id}/conversations/{conversation_id}/assign` | editor | not probed | not probed | not probed | not probed | not probed |
| POST | `/api/v1/tenants/{tenant_id}/conversations/{conversation_id}/messages` | editor | not probed | not probed | not probed | not probed | not probed |
| POST | `/api/v1/tenants/{tenant_id}/conversations/{conversation_id}/notes` | editor | not probed | not probed | not probed | not probed | not probed |
| POST | `/api/v1/tenants/{tenant_id}/conversations/{conversation_id}/resolve` | editor | not probed | not probed | not probed | not probed | not probed |
| POST | `/api/v1/tenants/{tenant_id}/conversations/{conversation_id}/return-to-ai` | editor | not probed | not probed | not probed | not probed | not probed |
| POST | `/api/v1/tenants/{tenant_id}/conversations/{conversation_id}/takeover` | editor | not probed | not probed | not probed | not probed | not probed |
| DELETE | `/api/v1/tenants/{tenant_id}/data` | staff-only | not probed | not probed | not probed | not probed | not probed |
| GET | `/api/v1/tenants/{tenant_id}/data/audit` | admin | 200 | 200 | 403 | 403 | 401 |
| GET | `/api/v1/tenants/{tenant_id}/data/deletion-preview` | staff-only | 200 | 403 | 403 | 403 | 401 |
| GET | `/api/v1/tenants/{tenant_id}/data/export` | admin | 200 | 200 | 403 | 403 | 401 |
| GET | `/api/v1/tenants/{tenant_id}/follow-ups` | viewer | 200 | 200 | 200 | 200 | 401 |
| POST | `/api/v1/tenants/{tenant_id}/follow-ups` | editor | not probed | not probed | not probed | not probed | not probed |
| DELETE | `/api/v1/tenants/{tenant_id}/follow-ups/{follow_up_id}` | editor | not probed | not probed | not probed | not probed | not probed |
| GET | `/api/v1/tenants/{tenant_id}/inbox` | viewer | 200 | 200 | 200 | 200 | 401 |
| GET | `/api/v1/tenants/{tenant_id}/inbox/assignees` | editor | 200 | 200 | 200 | 403 | 401 |
| GET | `/api/v1/tenants/{tenant_id}/inbox/counts` | viewer | 200 | 200 | 200 | 200 | 401 |
| GET | `/api/v1/tenants/{tenant_id}/inbox/events` | viewer | 200 | 200 | 200 | 200 | 401 |
| POST | `/api/v1/tenants/{tenant_id}/inbox/{conversation_id}/read` | editor | not probed | not probed | not probed | not probed | not probed |
| POST | `/api/v1/tenants/{tenant_id}/inbox/{conversation_id}/tags` | editor | not probed | not probed | not probed | not probed | not probed |
| DELETE | `/api/v1/tenants/{tenant_id}/inbox/{conversation_id}/tags/{tag}` | editor | not probed | not probed | not probed | not probed | not probed |
| GET | `/api/v1/tenants/{tenant_id}/invitations` | admin | 200 | 200 | 403 | 403 | 401 |
| POST | `/api/v1/tenants/{tenant_id}/invitations` | admin | not probed | not probed | not probed | not probed | not probed |
| DELETE | `/api/v1/tenants/{tenant_id}/invitations/{invitation_id}` | admin | not probed | not probed | not probed | not probed | not probed |
| POST | `/api/v1/tenants/{tenant_id}/invitations/{invitation_id}/resend` | admin | not probed | not probed | not probed | not probed | not probed |
| GET | `/api/v1/tenants/{tenant_id}/members` | admin | 200 | 200 | 403 | 403 | 401 |
| DELETE | `/api/v1/tenants/{tenant_id}/members/{user_id}` | admin | not probed | not probed | not probed | not probed | not probed |
| PATCH | `/api/v1/tenants/{tenant_id}/members/{user_id}` | admin | not probed | not probed | not probed | not probed | not probed |
| GET | `/api/v1/tenants/{tenant_id}/quota` | viewer | 200 | 200 | 200 | 200 | 401 |
| GET | `/health` | none/public | 200 | 200 | 200 | 200 | 200 |
| GET | `/ready` | none/public | 200 | 200 | 200 | 200 | 200 |


---

# Findings (judgment, not generated)

Each finding cites the evidence it rests on. Priority is a suggestion: **P1** = blocks or misleads a client or a demo, **P2** = wrong but workable, **P3** = polish.

## 5. Mismatches against the agreed role model

| # | Finding | Evidence | Priority | Type |
|---|---|---|---|---|
| M1 | **Overview and Inbox loaded in an error state for client admin and client editor** ("Unexpected server error", Retry page). Viewer and staff loaded both pages normally. The Overview makes the same four GET calls for every role (`inbox/counts`, `bots`, tenant quota, `inbox?limit=5`), and the plain API probe returned 200 for admin and editor on the related routes, so this is either role-dependent (for example per-user read state) or transient. **Reproduce first** by logging in as `demo-admin` and opening Overview and Inbox. Every admin/editor row for those two pages in section 3 is invalid until then, and the admin/editor inbox reply UI was never captured. This is also why admin and editor show no inbox item pages in the matrix. | `ui-admin.json`, `ui-editor.json`, `screens/admin/app_T.png` | P1 until reproduced | Possible product bug |
| M2 | **Export links shown to roles that get 403.** The bot Overview page (`/bots/{bot}/overview`) renders *Export conversations CSV* and *Export leads CSV*, and the Contacts page renders *Export CSV*, identically for viewer and editor, while the three CSV routes are admin-only and return 403 to editor and viewer. | section 3 (viewer identical to staff on Overview and Contacts), section 4 | P2 | Product bug (UI vs guard) |
| M3 | **Clients see plan limits.** The viewer's Overview shows a *Plan usage* panel (bots, seats, pages per bot, upload size, monthly messages, contacts, channel connections, sentiment runs) plus "Plan limits are provisional. Measured provider tokens this month: 0." The Bots page shows a *Plan usage* heading to all client roles. The agreed model says clients see no limits or costs. Admin's Overview could not be captured (M1). | `screens/viewer/app_T.png`, section 3 `/app/{tenant}/bots` | P2 | Spec decision needed: keep for clients or staff-only |
| M4 | **Staff-only pages open for clients with a message.** `knowledge`, `install` and `playground` load the page shell (HTTP 200) and show "Platform staff access required." The APIs behind them return 403, so no data leaks, but the shell tells a client the page exists. | section 2, `direct_url_checks` | P3 | UX |
| M5 | **Staff has no way to act in the inbox.** Staff opens `/inbox/{id}` read-only (no reply or takeover controls); the API requires a real membership for inbox actions. | section 3 `/inbox/{id}`, `core/tenancy.py` | P2 | Spec decision (G3) |
| M6 | **Spec step vs UI:** the test checklist says "appearance draft then publish", but the bot Settings page has only *Save settings* (no draft or publish control for the widget look). | section 3 `/bots/{bot}/settings` | P2 | Spec error or missing feature, decide which |
| M7 | **Revoked member still listed.** `demo-owner@example.com` has status `revoked` in the database, yet the staff client detail page (`/platform/clients/{tenant}`) lists it as an admin member (from the staff-run README). Whether the client's own Team page also lists it was not checked. | README (staff run), DB query earlier | P2 | Product bug |
| M8 | **Destructive actions with no confirmation:** member *Remove*, conversation *Delete*, *Pause bot*, *Start embedding backfill*, and the settings saves. Only contact erase and organization delete ask for confirmation. | `ui-clicks.json` | P2 | Product gap |
| M9 | **Naming:** the onboarding form already says "Admin email", but the request field (`owner_email`), the invite code path, the constant `OWNER_INVITATION_EXPIRY_DAYS` and the audit actions (`platform.onboarding.owner_invited`, `self_service.owner_assigned`) still say owner. Which role the invitation grants is unverified. | `platform/router.py`, `provisioning/service.py`, `platform/page.tsx` | P3 | Cleanup (G2, narrowed) |
| M10 | **Staff empty state (G1):** `/app` shows "Your account needs an invitation to join an organization." for staff, with an empty organization switcher. | `ui-staff.json` | P1 for the owner experience | Product gap |

### Checked and matching the model
- Staff-only guards: every `platform_staff_only` route returns 403 to admin, editor and viewer and 401 to anonymous callers. No contradiction in 60 GET routes (README).
- `/platform` and `/platform/operations` redirect all client roles to `/app`; the *Platform admin* tab appears for staff only.
- Bot Settings for clients shows only "Bot status" plus "Contact your operator to request settings changes"; no persona, appearance, domain or tier fields. Analytics *AI costs and limits* is staff-only.
- Editor and viewer sidebars omit Request a change, Team and Tenant data and audit; viewer has no *Add contact*, *Save contact* or follow-up controls; editor has no merge or erase.
- Organization deletion needs the typed org name and is staff-only.

## 6. Cleanup candidates
- `?` placeholder icon on *Change requests* and *Request a change*.
- `/widget/sample` demo page shipped in the app and linked from Install (keep only if it is the intended test page).
- Provisional banners: "Pricing and final plan limits are still under review", "AI cost is not reported…", "Plan limits are provisional".
- *Retry* and *Cancel* offered on a completed job (Operations and Knowledge jobs list).
- Empty *Switch organization* select for staff.
- One `<title>` ("Website Chatbot SaaS") on every page.
- Revoked demo-owner shown as a member (M7); demo seed docs still mention it.
- `GET …/data/export` writes an audit row on every call (intentional audit, but a GET with a side effect; my probes created several).

## 7. Suggested additions (decision needed on each; none are in the code)
Marked **Pilot** = I would want it before a first real client, **Later** = can wait.

| Suggestion | Why | When |
|---|---|---|
| Staff organization list on `/app` with Open, Create and a link to Platform admin | Fixes M10; staff is the owner of everything | Pilot |
| Per-client onboarding checklist for staff (create org, invite admin, upload knowledge, publish, set appearance and domains, copy snippet, test) | The client Overview already has a "Your first assistant" checklist, but only one step ("First bot created") was visible; staff gets no guided path | Pilot |
| Staff reply and takeover in the inbox, attributed to the staff user in the audit | Resolves M5 | Pilot or Later (your call, G3) |
| Confirmation step on Remove member, Delete conversation, Pause bot | Resolves M8 | Pilot |
| Live widget preview next to the appearance fields | Appearance is edited as hex and URL text fields with no preview (M6 is related) | Later |
| Per-page browser titles | Polish, helps support and browser history | Later |

## 8. Unverified (not covered by the evidence)
- Admin and editor Overview and Inbox (M1), including the inbox reply controls.
- Editor and viewer opening `/settings/members`, `/settings/data` and `/settings/requests` by direct URL (the APIs return 403, but the page shells were not opened).
- The result of any action: all POST, PUT, PATCH and DELETE calls were blocked or never sent (116 routes, 60 GET). The guards for the 56 non-GET routes come from the code only.
- Placeholder ids remained for change requests, attachments, follow-ups and widget sessions.
- Visual quality and responsiveness; screenshots exist but were not reviewed except three.
- A second organization (none exists), so cross-tenant isolation is untested here.
- Widget appearance and behavior on a customer site (`test.html` run not done yet).
