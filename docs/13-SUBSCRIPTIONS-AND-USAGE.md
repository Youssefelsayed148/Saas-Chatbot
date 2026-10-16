# Usage and billing
# Usage and billing

## PLACEHOLDER plans (owner decision, 2026-10-14)

These values are **PLACEHOLDER** limits for building and verification. They are not prices or final plan promises. All numeric plan limits live in `apps/api/app/quotas/plans.py` so they can be changed in one place. The platform admin UI marks them PLACEHOLDER. Final pricing and limits are TBD until the product is working and verified.

| Limit | Free | Starter | Pro | Business |
|---|---:|---:|---:|---:|
| Bots | 1 | 3 | 10 | 30 |
| Seats | 2 | 5 | 15 | 50 |
| Knowledge pages per bot | 25 | 150 | 600 | 2000 |
| Maximum upload file size (MB) | 5 | 10 | 20 | 25 |
| Messages per month | 200 | 3000 | 15000 | 60000 |
| Contacts | 100 | 2000 | 20000 | 100000 |
| Channel connections | 1 | 1 | 3 | 10 |
| Sentiment runs per month | 0 | 1000 | 5000 | 20000 |

No token cap is enforced. Provider-returned token usage is recorded and shown only when the provider returns measured usage. No currency spend cap is enforced until usage and pricing data exist. Sentiment count is the cost guard for now.

## Enforcement and operations

Warn at 80%; block new creation at 100% with a message naming the limit and plan. Never delete or hide existing data at a limit; existing bots continue working. Platform-staff overrides require a reason and an audit event. Counts use measured records. The widget reports “temporarily unavailable” on monthly message exhaustion and exposes no billing details. Channel connections count website bot widgets until P6 adds Many connections.

Sentiment runs only in a background job, never in the chat reply path. Only resolved conversations are queued in this phase; one conversation is classified at most once. Use a cheap model or configured OpenRouter `:free` chain; at the monthly run limit, do not enqueue and preserve the empty “Sentiment not measured yet” state. No separate currency cap applies while token pricing data is unavailable.

Billing checkout is deferred pending provider approval for merchant country, currency, recurring support and fees. Do not invent prices or a payment vendor. Later billing requires webhook signature verification, replay protection, cancellation/grace state, invoice reconciliation and admin-only billing actions. Many keeps its own subscription; the SaaS only counts messages and connections on its side. No shared entitlements.
