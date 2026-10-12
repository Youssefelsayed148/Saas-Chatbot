# User journeys and exception paths
## Self-service
Visitor registers, verifies identity as configured, creates organization, chooses bot, uploads knowledge files (documents, Q&A CSV, or the folder prepared from their website by staff), observes queued/running/failed/completed processing, previews extracted pages, publishes, tests bot, copies embed code, observes sessions. Errors must be actionable and retryable.
## Admin-managed
Platform operator creates an onboarding request for a customer with audited actor identity, invites owner, and uses the SAME provisioning service and job/state handling. Customer can subsequently log in and administer only their own tenant. Admin cannot silently impersonate the customer.
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
