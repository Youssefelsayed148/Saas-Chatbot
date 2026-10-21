# User journeys and exception paths
## Self-service (flag-gated, off by default)
When `self_serve_signup` is explicitly enabled: visitor registers, creates organization, chooses bot, uploads knowledge files (documents, Q&A CSV, or the folder prepared from their website by staff), observes queued/running/failed/completed processing, previews extracted pages, publishes, tests bot, copies embed code, observes sessions. With the flag off (the committed default), registration is closed: the login screen shows no Register link and only invited existing users can join; staff-managed onboarding below is the built path.
## Admin-managed (built, S1–S3)
Platform operator opens /platform and creates the organization (audited), creates the user with a staff-set or generated password (shown once), assigns organization and role, creates the bot, uploads knowledge through the bot's Knowledge tab, ingests and publishes, sets allowed domains, tests the chat and hands over the embed snippet. The user signs in with the staff-set password and should replace it on their Account page. Customer can subsequently log in and administer only their own tenant. Admin cannot silently impersonate the customer. No email provider: one-time invitation links and generated passwords are copied and sent by the operator; account recovery is a staff password reset (all sessions revoked), not an email flow.
## Bot lifecycle
Draft → configured → ingestion ready → published/active → paused/archived. Bot may have no knowledge yet; widget should display controlled unavailable behavior, not hallucinate.
## Source lifecycle
Uploaded → validated → queued → parsing → chunking → indexed draft → review → published, with failed/cancelled paths. Publication is an explicit tenant-authorized action.
## Visitor journey
Open page → load widget config → start visitor session → submit query → receive answer with cited URLs, or safe no-answer → optionally submit contact details with consent. Rate-limit abuse and handle invalid/expired sessions.
## Handoff and inbox journey
Visitor asks something the bot cannot answer (or asks for a person) → bot says so and offers the support contact; conversation appears in the inbox as waiting_human with a notification → an editor/admin opens it, takes over (AI goes silent), replies; the visitor sees the reply in the widget → agent adds a note and tag, sets the contact stage, resolves or returns the chat to the bot. A viewer can read but not reply. If two agents click take over, the second is told who owns it.
## Meta channel journey (P6)
Staff link a tenant's bot to a ManyOsirisChat channel (explicit connection) → a WhatsApp customer writes → Many forwards the signed event → the same bot answers or hands off → agent replies from the same inbox go out through Many → delivery status appears on each message; if the WhatsApp window is closed the failure and reason are visible.
## Follow-up journey
Agent or rule schedules a follow-up for a lead → job sends it at the time (website: shown on next visit; Meta: only with opt-in, through Many) → status and any reply land in the conversation.
## Edge cases
Agent leaves a conversation open (idle timeout flag), visitor returns after resolution (reopens with AI), duplicate or out-of-order Many events, Many down (queued with backoff, visible in inbox), expired WhatsApp window, contact merge conflicts, unsupported media from WhatsApp.
## General edge cases
Duplicate onboarding, duplicate files, corrupt or scanned files, bot disabled mid-chat, revoked membership, quota exhausted, provider timeout, crawl cancellation, source deletion, concurrent publish, malicious site content, unauthorized cross-tenant IDs, retries after process crash.
