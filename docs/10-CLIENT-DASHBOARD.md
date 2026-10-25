# Client dashboard — one workspace per chatbot (ADR-018)
A tenant can have several bots; each bot has its own workspace at `/app/[tenant]/bots/[id]`, with a bot switcher. Tenant-level pages: `/app` (org selector), `/app/[tenant]/overview` (all bots at a glance: conversations, waiting-for-human count, usage vs plan), `/app/[tenant]/bots`, `/app/[tenant]/bots/new`, `/app/[tenant]/settings/members`, `/app/[tenant]/contacts` (all bots, filterable by bot).
## Per-bot workspace (tabs, built when their phase arrives — no fake tabs)
| Tab | Contents | Phase |
|---|---|---|
| Overview | conversations, messages, handoff rate, leads, thumbs up/down, unanswered and top questions, volume per day, date range, channel filter, CSV export; later sentiment, time to first human reply, agent workload | P4-05, extended P5-05 |
| Conversations > Inbox | live queue, filters (chips: waiting, mine, unread, all), thread, reply, takeover/return/resolve/assign, notes, tags | P5 |
| Contacts | this bot's leads: stage, tags, custom fields, timeline, merge, export | P5-04 |
| Knowledge | upload, job status, preview, publish/rollback, unanswered-questions list to guide new content | P2-04 |
| Playground | test chat with citations and errors | P3-04 |
| Conversations > History | all saved conversations (tenant-wide `/app/[tenant]/conversations`, per bot `/bots/[id]/conversations`): search, status/channel/date filters, pagination, read-only thread with citations, delete (admin, row menu), collapsible data retention (admin) | P4-04, merged module (owner-approved 2026-10-25) |
| Follow-ups | scheduled messages, status | P5-05 |
| Channels | link the bot to a Many channel; connection and delivery health | P6 |
| Settings and appearance | assistant/business info, welcome message, handoff rules, widget look, allowed domains, retention | P1-04, P4-03 |
| Install | verified script snippet, test page helper | P4-03 |
Bot create wizard: name → (optional website URL) → confirm → bot workspace. Source view shows status/errors/retry; publish is explicit; analytics show measured data only. Role restrictions are visible (viewer sees, cannot act). Every screen has loading, empty and error states.
## Rules
Only real API data; hidden resources 404; per-bot numbers never mix bots; tenant-level pages aggregate only the caller's tenant.

Conversations module (owner-approved 2026-10-25): Inbox and Conversations are ONE sidebar item "Conversations" with two tabs, Inbox (live work, `/app/[tenant]/inbox`, `/inbox/[conversation]`) and History (`/app/[tenant]/conversations`, `/bots/[id]/conversations`, thread). All of those routes keep the item active. The command palette also lists "Inbox" and "Conversation history".
