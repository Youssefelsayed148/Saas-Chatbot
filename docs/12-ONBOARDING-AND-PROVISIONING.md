# One provisioning service

Two entry points: self-service and admin-managed. Both invoke the same `ProvisioningService` with an authenticated actor, requested tenant/bot configuration, and an idempotency key. The service creates or reuses tenant/bot resources, records the request and audit event, and can schedule optional ingestion. The staff path changes actor authorization and the admin invitation workflow, not the core provisioning logic.

P7 self-service signup: `POST /api/v1/provisioning/self-service` requires an authenticated, CSRF-checked user and creates one Free PLACEHOLDER tenant, direct admin membership, and first draft bot. Signup registration calls it after account creation. A deterministic per-account idempotency key lets concurrent retries return the same tenant and bot; a changed payload on that key returns 409. Staff onboarding remains invite-based. Neither path requires a website URL. No email provider is configured.

State: requested → provisioning → ready; or failed. Durable request record; unique `(mode, idempotency_key)` plus payload hash; concurrent retries cannot duplicate a tenant/bot. No cross-product SKU branching for MVP. P1 implements plain tenant/bot CRUD; the shared ProvisioningService staff path was built in P4-06 and self-service signup is built in P7-03.
