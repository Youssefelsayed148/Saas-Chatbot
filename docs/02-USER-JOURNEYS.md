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
## Edge cases
Duplicate onboarding, duplicate files, corrupt or scanned files, bot disabled mid-chat, revoked membership, quota exhausted, provider timeout, crawl cancellation, source deletion, concurrent publish, malicious site content, unauthorized cross-tenant IDs, retries after process crash.
