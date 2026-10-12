# Expected behaviour — what the finished app does
Use this to judge, phase by phase, whether what was built is what you wanted. If you see something different, it's a bug or a scope change — not "close enough".

## The product in one paragraph
A business signs up, creates an organization and a bot, gives it its data (uploaded files and/or website pages), reviews what was learned, publishes it, tests the bot, pastes one script tag on its website, and then watches conversations, leads and analytics. The bot answers only from that business's published data, cites sources, and says "I don't know" otherwise. One deployment serves many businesses, fully isolated.

## What you should be able to do at the end of each phase
### After P1 — Foundation
- Open the web app, register, log in, log out. Wrong password → clear error; expired session → sent back to login.
- Create an organization; you are its owner. Create a second org and switch between them.
- Create, rename, edit settings of, and archive a bot. Archived bots disappear from the default list but are not deleted.
- Invite/membership roles exist in the data model; a viewer sees bots but has no create/edit buttons and the API rejects their writes.
- A user from org B who guesses an org-A bot ID gets "not found" — never the data.
- Nothing on screen is fake: all lists come from the API.
### After P2 — Knowledge
- Open a bot → Knowledge. Upload a PDF/DOCX/TXT/CSV (or paste a URL). See a job go queued → running → done, or failed with a readable reason and a Retry button.
- See the extracted documents and chunks (preview), counts, and which source each came from.
- Click Publish: the bot's knowledge switches to the new revision atomically. Roll back to the previous revision works. A failed ingest never changes what is published.
- Uploading the same file twice does not duplicate content. Another organization with the same file shares nothing.
### After P3 — Chat
- In the Playground, ask a question: streamed or complete answer with source citations (file/page or URL).
- Ask something not in the data: the bot says it doesn't have that information — no invention.
- Arabic and English questions both work, answers follow the question's language, Arabic renders right-to-left.
- A "page text" that says "ignore your instructions" does not change the bot's behaviour.
- Conversations and usage events are stored; a bot with nothing published says it is not ready.
### After P4 — Widget and client experience
- Install page gives one script snippet. Pasting it on a test HTML page shows a chat bubble; chatting works on mobile width and with keyboard only.
- Only the domains you allow can load the widget; a paused bot shows a controlled "unavailable" message.
- Rate limits stop a spammer; an expired visitor session is recovered gracefully.
- Dashboard shows conversations (with citations), leads captured with consent, and analytics: volume, top questions, unanswered questions, usage — real numbers only.
- Widget appearance settings (colour, name, greeting, language/RTL) change what visitors see.
### After P5 — Platform admin, quotas, staff onboarding, hardening
- Platform staff (flag set by you in the DB) see a /platform area: tenants, bots, job health. Non-staff get 403/404.
- Staff can onboard a customer: create tenant + owner invite + bot + upload their data, through the same service self-service uses. Every staff action is audited with a reason.
- Quotas (messages, pages, bots, seats) are enforced; hitting a limit shows a clear message, not a crash.
- A tenant owner can export or delete their data; a restore drill from backup succeeds; security review items are closed.
- You can deploy to staging (only after you approve hosting).

## Always-true rules (every phase)
1. Cross-tenant access is impossible by ID guessing. 2. Errors are specific and actionable. 3. No secrets or visitor PII in logs. 4. Loading, empty and error states exist on every screen. 5. Archived/paused things behave predictably. 6. No success state without a real backend result.

## Not in the product (yet)
Paid checkout, WhatsApp/Messenger channels, human handoff, password-reset emails, ManyOsirisChat connection.
