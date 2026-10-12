# Expected behaviour — what the finished app does
Use this to judge, phase by phase, whether what was built is what you wanted. If you see something different, it's a bug or a scope change — not "close enough".

## The product in one paragraph
A business signs up, creates an organization and a bot, gives it its data (uploaded files and/or website pages), reviews what was learned, publishes it, tests the bot, and pastes one script tag on its website. Visitors chat with an AI agent that answers only from the business's published data, cites sources and says "I don't know" otherwise. When it cannot help, a human takes over from a unified inbox; leads become contacts with stages; follow-ups can be scheduled. From P6 the same bot and inbox also serve WhatsApp, Messenger and Instagram through ManyOsirisChat, which owns the Meta connections. One deployment serves many businesses, fully isolated. The first sellable version is the end of P5.

## What you should be able to do at the end of each phase
### After P1 — Foundation
- Open the web app, register, log in, log out. Wrong password → clear error; expired session → sent back to login.
- Create an organization; you are its owner. Create a second org and switch between them.
- Create, rename, edit settings of, and archive a bot. Archived bots disappear from the default list but are not deleted.
- Owners/admins invite teammates with a one-time link (copy and send it yourself; there is no email). The invitee opens it, registers or logs in and joins with the chosen role. Links expire, work once and can be revoked. A viewer sees bots but has no create/edit buttons and the API rejects their writes.
- A user from org B who guesses an org-A bot ID gets "not found" — never the data.
- Nothing on screen is fake: all lists come from the API.
### After P2 — Knowledge
- Open a bot → Knowledge. Upload a PDF/DOCX/TXT/MD file, a Q&A CSV (download the template first; bad rows are listed with reasons). Website content is prepared by staff with the website-to-knowledge skill (a folder of page files + Q&A CSV) and uploaded here; there is no paste-a-URL box in the first release. Citations link back to each page's original URL. See a job go queued → running → done, or failed with a readable reason and a Retry button.
- See the extracted documents and chunks (preview), counts, and which source each came from.
- Click Publish: the bot's knowledge switches to the new revision atomically. Roll back to the previous revision works. A failed ingest never changes what is published.
- Uploading the same file twice does not duplicate content. Another organization with the same file shares nothing.
### After P3 — Chat
- In the Playground, ask a question: streamed or complete answer with source citations (file/page or URL).
- Ask something not in the data: the bot says it doesn't have that information — no invention.
- Arabic and English questions both work, answers follow the question's language, Arabic renders right-to-left. If your documents are only in English, an Arabic question is still answered (in Arabic) from them.
- Thumbs up/down on each answer; questions the bot could not answer are listed so you know what content to add.
- Search is keyword-based: exact wording matters more than for semantic search, so very loose paraphrases may miss. The eval report shows how often; a semantic upgrade is optional later.
- A "page text" that says "ignore your instructions" does not change the bot's behaviour.
- Conversations and usage events are stored; a bot with nothing published says it is not ready.
### After P4 — Widget (website channel)
- Install page gives one script snippet. Pasting it on a test HTML page shows a chat bubble; chatting works on mobile width and with keyboard only.
- Only the domains you allow can load the widget; a paused bot shows a controlled "unavailable" message.
- Rate limits stop a spammer; an expired visitor session is recovered gracefully.
- Dashboard shows conversations (with citations), leads captured with consent (they become contacts), and analytics: volume, top questions, unanswered questions, usage — real numbers only.
- Widget appearance settings (colour, name, greeting, language/RTL) change what visitors see.
- Each bot has its own workspace with a bot switcher: Overview (measured numbers with date range), Knowledge, Playground, Conversations, Settings, Install. Numbers for one bot never include another's.
- Admin console (/platform, staff only): you see every client with plan, status, bots, usage and last activity; open a client to see its bots, job status, members and audit trail; and onboard a new client in one form (tenant + owner invite link + bot + data upload). Non-staff cannot reach it; no impersonation.
### After P5 — Inbox, handoff and light CRM (first sellable cut)
- A visitor asks something the bot cannot answer, or asks for a person: the bot says so politely, gives the support contact, and the conversation appears in the Inbox as "waiting for a person" with a notification badge.
- An owner/admin/editor opens it, clicks Take over (the AI goes silent), types a reply; the visitor sees it in the widget within a few seconds, as plain text. The agent adds a note and a tag, then either Resolves it or Returns it to the bot. A viewer can read but cannot reply. If two agents click Take over, the second is told who has it.
- The Inbox lists every conversation with filters (status, mode, channel, assignee, tag, unread) and search; it updates live without refreshing.
- Contacts: a lead who filled the widget form appears with their details and consent; you can set a stage (new/qualified/customer/lost), add tags and custom fields, see their conversation timeline, merge duplicates, export CSV, and erase a contact.
- Follow-ups: schedule a message for a lead; on the website the visitor sees it the next time they open the widget.
- Analytics add handoff rate, time to first human reply, sentiment distribution, resolved vs open, agent workload — measured numbers only.
- Nothing about Meta exists yet: only the website channel.
### After P6 — ManyOsirisChat channel (WhatsApp, Messenger, Instagram)
- Staff link a bot to a Many channel (explicit connection, secret shown once). A customer writes on WhatsApp: the same bot answers or hands off, and the conversation shows a WhatsApp badge in the same Inbox.
- Agent replies from the Inbox reach the customer through Many; each message shows sent / delivered / read or the failure reason (for example "WhatsApp window closed — template required"). Voice and image messages get a polite "text only" reply and are flagged for a human.
- Duplicate or replayed events change nothing; a forged request is rejected; one tenant's connection can never touch another tenant's data. Pausing a connection stops AI replies and sends instantly.
- Follow-ups and broadcasts to WhatsApp go out only to contacts who opted in, only with an approved template, and only after you approve the first real send.
- Many handles all Meta-side concerns (tokens, webhooks, window, templates); this app never stores Meta credentials.
### After P7 — Platform admin, quotas, staff onboarding, hardening
- The admin console grows: job and delivery health, channel-connection health and secret rotation, plan assignment and quota warnings, platform analytics (usage and AI cost per client), audit review. Non-staff get 403/404.
- Staff can onboard a customer: create tenant + owner invite + bot + upload their data (+ request a channel connection), through the same service self-service uses. Every staff action is audited with a reason.
- Quotas (messages, pages, bots, seats, contacts, connections) are enforced; hitting a limit shows a clear message, not a crash.
- A tenant owner can export or delete their data; a restore drill from backup succeeds; security review items are closed.
- You can deploy to staging (only after you approve hosting).

## Always-true rules (every phase)
1. Cross-tenant access is impossible by ID guessing. 2. Errors are specific and actionable. 3. No secrets or visitor PII in logs. 4. Loading, empty and error states exist on every screen. 5. Archived/paused things behave predictably. 6. No success state without a real backend result.

## Not in the product (yet)
Paid checkout, voice/image messages, email notifications and password-reset emails, deals/pipelines with amounts, automation builder, any Meta API code in this repo (Many owns it).
