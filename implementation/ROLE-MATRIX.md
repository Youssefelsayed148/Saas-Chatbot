# Dashboard role matrix

Group B owner scope, 2026-10-17. Client visibility follows this matrix; existing
server authorization remains authoritative. Staff access spans all organizations
without requiring membership. Hidden tenant resources continue to return 404.

| Screen or control | Operator / staff | Admin | Editor | Viewer |
| --- | --- | --- | --- | --- |
| Overview and read-only organization Plan usage | Yes | Yes | Yes | Yes |
| Connected channels health (read-only Overview card) | Yes | Yes | Yes | Yes |
| ManyOsirisChat connection lifecycle and secret management | Yes | No | No | No |
| Conversations: list and read | Yes | Yes | Yes | Yes |
| Inbox: view | Yes | Yes | Yes | Yes |
| Inbox: reply, takeover, resolve, return to AI, tag, note, assign | Read-only operator view* | Yes | Yes | No |
| Contacts: view | Yes | Yes | Yes | Yes |
| Contacts: create, edit and follow-ups | Yes | Yes | Yes | No |
| Contacts: merge and erase | Yes | Yes | No | No |
| Insights | Yes | Yes | Yes | Yes |
| CSV exports: conversations, leads and contacts | Yes | Yes | No | No |
| Conversation delete and organization retention | Yes | Yes | No | No |
| Request a change | Triage queue | Yes | No | No |
| Team | Yes | Yes | No | No |
| Tenant data and audit | Yes | Yes | No | No |
| Bots list and bot status/settings | Yes | No | No | No |
| Knowledge, playground and install | Yes | No | No | No |
| Domains, appearance, AI tier, AI cost and limit editing | Yes | No | No | No |
| Platform tools and organization provisioning | Yes | No | No | No |

*Group A's explicit read-only staff Inbox behavior and the existing API guards
remain unchanged. Staff privilege does not authorize sending client replies.

Client sidebar order: Overview, Conversations, Inbox, Contacts, Insights. Admins
add Request a change, Team, Tenant data and audit. Conversations links directly
to the organization's first current bot's conversation list; bot management is
never exposed to clients. With no current bot, show a conversation empty state.

Client visits to bot settings, knowledge, playground, install or the legacy Bots
list redirect to `/app/{tenant}` before rendering the shell or page controls.
Client Plan usage shows the organization's actual plan and readable usage labels,
without editable limits, AI internals or provisional/under-review notices.

The matrix changes UI visibility only: no API guard, entitlement, schema, billing
decision or deployment authorization changes. This owner instruction supersedes
older client bot-status wording in historical documentation.
