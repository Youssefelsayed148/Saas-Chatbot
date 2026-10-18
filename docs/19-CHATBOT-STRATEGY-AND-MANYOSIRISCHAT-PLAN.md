# Chatbot strategy and ManyOsirisChat plan (decisions record)

Status: DRAFT for owner review after testing. Written 2026-10-17 from the triage session.
Companion: `implementation/WEBSITE-MVP-CLOSEOUT.md` (the staged plan to close the website bot).
Authority: where this conflicts with docs/07, 14, 17 or 18, the owner decides after review; ADR-019 and RAG-PLAN-v2 already supersede the keyword-only parts of docs/07, 14 and 18.

## 1. Product scope and sequence

1. Review phase closes (manual pass).
2. Website chatbot tested and closed out on a demo client (answers only from the client's published data).
3. ManyOsirisChat integration: one SaaS bot answers on Meta channels connected through Many.
4. Later: outreach and campaign control, and bot actions (booking, purchasing).

MVP behavior is grounded Q&A: answer only from published knowledge, cite internally, say "I don't have that information" otherwise, hand off to a human when asked or when it cannot answer. Actions (booking, purchasing) are explicitly out of the MVP. To avoid blocking them later, keep the answer contract extensible (tool calls with confirmation steps and audit rows) and do not hard-code answer-only assumptions beyond what the MVP needs.

## 2. Role model and manual pass (source of truth: implementation/ROLE-MATRIX.md)

Login at http://localhost:3000/login. Demo password for demo accounts: FakeDemoOnly!123. Staff: staff@example.com / 12345678 (dev only).

G4 (all): demo-owner@example.com must get the generic invalid-credentials message.

Viewer (demo-viewer):
- Sidebar: Overview, Conversations, Inbox, Contacts, Insights only.
- Overview shows read-only Plan usage, no limit editing, no AI internals.
- Inbox thread: no reply, takeover, resolve, tag or assign controls. Contacts: no create/edit.
- Direct URLs /app/{tenant}/bots, settings, knowledge, playground, install redirect to /app/{tenant}.
- No citations or source links in Conversations or Inbox.

Editor (demo-editor):
- Inbox: take over, reply, return to AI, resolve, tag, assign all work with no 500 errors (the M1 fix).
- Contacts: create, edit, follow-ups work; merge and erase hidden.
- Absent (sidebar and direct URL): Team, Tenant data and audit, Request a change, CSV exports, conversation delete, retention.

Admin (demo-admin):
- Sidebar adds Request a change, Team, Tenant data and audit.
- Everything editor can do, plus contact merge and erase, CSV exports, conversation delete, retention.
- Cancel then confirm: member Remove, conversation Delete, contact erase. Cancel writes nothing; confirm writes.
- Audit search works for both "owner" and "admin" vocabulary, only for this tenant.
- Request a change with attachment: status pending, icons correct.
- Team: onboarding invite grants admin.

Staff:
- /platform lists client orgs; revoked members hidden; create org; open org.
- Inside the org: bots, knowledge, playground, install visible; Inbox read-only with a note.
- Bot settings: change colour, Save settings, reload widget config: live without publish.
- Cancel and confirm: Pause bot (both pages), embedding backfill, Reset to plan defaults.
- Jobs lists: Failed shows Retry only; queued/running show Cancel only; succeeded/cancelled show none.
- /widget/sample renders for staff; logged out or client role redirects.
- Tenant deletion dialog requires exact name; cancel writes nothing.
- /platform/change-requests triage queue.
- Page titles, favicon, contact Conversation dropdown middle dots, Arabic encoding.

Login rule: zero memberships can log in; pending valid invite can log in; all memberships revoked cannot.

## 3. Current chatbot state (verified from the repo on 2026-10-17)

Built (ADR-019, RAG-PLAN-v2):
- Knowledge, documents, chunks, revisions and settings are scoped by tenant_id + bot_id; each bot has one published_revision_id.
- Hybrid retrieval: Postgres FTS plus pgvector, merged with RRF; tenant/bot/revision filter inside the same SQL statement.
- Relevance gate: cosine floor OR FTS floor with minimum matched terms; RRF never passes the gate. Refusal path with inbox handoff offer; no generation call on refusal.
- Grounded generation with citation validation; traces per answer; metering and limits (429 QUOTA_EXCEEDED, "contact us").
- Degradation: embedding failure or backfill runs FTS-only per request, logged.
- Arabic: normalisation plus a PostgreSQL arabic text-search config added by migration 0016 (which column queries actually use is to be confirmed in Stage 1).
- Conversations carry channel (website | whatsapp | messenger | instagram), connection_id, mode (ai | human), status (open | waiting_human | resolved), assigned_user_id. The pipeline is channel-agnostic.

Not proven:
- Thresholds (cosine 0.50 OR FTS 0.01, min matched terms 2 per .env.example) are UNTUNED.
- No real-provider calibration or groundedness run has been done.
- Arabic recall is unverified on a real corpus.
- Real-model answer quality and language behavior are unmeasured.

## 4. Ideal setup for a client deployment (website)

1. Staff create org, invite client admin, create bot, set tier and limits.
2. Staff upload the client's documents; review parsed documents and chunk counts; publish.
3. Staff set persona, tone, language, support contact, handoff rules, appearance, allowed domains.
4. Playground test with trace view, then install the snippet and test from the real domain.
5. Go live; client sees conversations, inbox, contacts, insights, and sends "request a change" to improve knowledge (clients never edit knowledge).
6. Thresholds calibrated per embedding model on that client's own questions before go-live (first client: during the demo-client stage).

## 5. Demo client spec: "Nile Home Goods"

Fictional Egyptian e-commerce store selling consumer goods, currency EGP. Fix one set of store facts (name, support email, phone, hours, address) and use it identically in every document.

Documents (5), each in English and Arabic (10 files), 2 to 4 pages each, one topic per page (the PDF parser makes one section per page):

| Document | Must contain |
|---|---|
| Shipping | zones (Cairo/Giza, Alexandria, Delta, Upper Egypt, remote), fee table per zone, free-shipping threshold, carrier, cut-off time, processing time, no international shipping, tracking |
| Delivery | delivery times per zone (working days), delivery hours, failed-delivery attempts and what happens next, cash on delivery rules and fee, inspect-before-signing, damaged or lost parcel, alternate address |
| Terms of use | account and ordering rules, pricing and availability disclaimer, payment methods, cancellation window, intellectual property, liability limits, privacy summary, governing law, how terms change |
| Returns and replacement | return window in days, eligible and non-eligible items, condition requirements, who pays return shipping per reason, replacement rules and stock-out fallback, numbered how-to-return steps |
| Refund | method per payment type (card, wallet, COD), processing days per method, partial refunds, restocking fee or none, shipping fee refundable or not, timeline from receipt, what to do if late |

Content rules:
- Exceptions live in the same section as the rule.
- Deliberate overlaps across documents with identical values (return window in returns and terms; COD refund in delivery and refund).
- At least five deliberate gaps customers would ask about (for example warranty length, gift wrapping, price matching, international shipping details, loyalty points). These are the unanswerable cases.
- Near-miss traps: similar numbers for different things (7 / 14 / 30 days).
- At least two tables (shipping fees, refund timing), one FAQ section, one numbered procedure.
- Every document starts with a header: store name, title, effective date, version.
- No placeholders, brackets or "X days".

Format rules:
- Real selectable text, not scans (scanned PDFs are rejected).
- Arabic PDFs are a risk: many generators produce PDFs where text extraction returns reversed or broken Arabic. Copy-paste from each Arabic PDF to verify; if broken, also provide DOCX for Arabic.
- Under 10 MB each. For DOCX use real Heading styles.
- Names like 01-shipping-en.pdf, 01-shipping-ar.pdf.

Eval file `eval.jsonl` (about 40 cases), fields: question, language, kind, expected_source, expected_answer_contains.
Counts: grounded 15, paraphrase 8, Arabic 6, mixed-language 3, follow-up 4 (with previous turn), unanswerable 8 (pointing at the gaps), prompt-injection 3.

Note on real-world PDFs: public policy PDFs found by search were generic templates full of placeholders and have no known right answers, so they were rejected as test data.

## 6. ManyOsirisChat findings (repo inspected read-only on 2026-10-17)

How Many's AI works today:
- One function, `ai_service.generate_reply`: system prompt = free-text business profile + tone + vertical safety text + handoff sentence; last 10 messages; gpt-4o-mini; max 300 tokens. No knowledge base, no retrieval, no citations, no answer validation.
- Only the cold-DM prompt says "answer only from the business profile". The campaign-origin prompt does not.
- "Hand off to a human" is only a prompt sentence. In the Instagram handler read, handoff is triggered by turn limit (default 8), daily cap, AI disabled, campaign inactive, or manual Take Over. Nothing detects a request for a human or a failed answer.
- Model failure is silent: no message sent, the conversation stays bot_active.
- Controls: global kill switch AI_ENABLED_GLOBAL, per-account ai_enabled, cold-DM toggle, per-campaign ai_enabled and ai_handoff_after_turns, daily cap, Take Over / Resume Bot.
- Instagram, WhatsApp and Facebook each have their own copy of the turn handler.
- WhatsApp outreach (templates, consent) was only skimmed, not reviewed.
- Tested so far only on Instagram DMs with profile data.
- No SaaS integration exists in Many's code.

Security flag: the Many repo tracks a file named `popeye access token.txt`. It was not opened. If it contains a real token: rotate it and remove it from git history.

Also noted: loose .patch files and prompt files in the Many repo root (cleanup candidate).

## 7. Integration architecture (decided in session)

Principles:
- The SaaS is the single brain for replies on every channel: website, and every Meta channel connected through Many.
- Many keeps everything Meta: connections, tokens, webhooks, campaigns, automations, templates, outreach, 24-hour window handling, sending. Many's routes and working setup stay as they are.
- The SaaS never talks to Meta and never stores Meta tokens.
- One bot = one knowledge base = all channels. Each channel connection links to exactly one bot; a tenant may have several bots.

Delegated mode (per Many channel):
- Many flags a channel as delegated. For that channel, the reply-generation step is replaced by a call to the SaaS; nothing else in Many is removed. Reversible per channel. Many-only clients are unaffected.
- On a delegated channel Many forwards every inbound message (signed) to the SaaS and sends whatever the SaaS returns.
- Handoff, takeover, resolve, assignment and turn limits are handled ONLY in the SaaS. Many's Take Over / Resume Bot are disabled on delegated channels ("Managed in the SaaS inbox"). Many's own gates (turn limit, daily cap, campaign ai_enabled) do not apply on delegated channels.
- Human replies from the SaaS inbox use the same send endpoint as bot replies (kind=agent).
- If the SaaS is unreachable, Many retries with backoff and does NOT fall back to its own AI (inconsistent answers). The channel shows degraded health in both apps.
- The SaaS owns the AI on/off toggle per connection. Pausing a connection stops AI replies and sends.

Campaign context (MVP):
- When a conversation started from a Many campaign, the forwarded event carries campaign_name and the campaign's opening message text. The SaaS shows "From campaign: <name>" in the thread and gives the bot that context.
- Outreach and campaign sending are not controlled from the SaaS in the MVP. Many keeps its own campaign analytics.

Connection health (MVP):
- Many pushes `channel.status` events: connected, token expiring, token expired, webhook unhealthy, disconnected.
- The SaaS can also pull health on demand.
- SaaS Channels page: staff see all connections and can pause; client roles see read-only health for their own channels.
- Connections are created explicitly by platform staff; the SaaS never performs Meta login.

Leads and contacts: leads from Meta channels arrive as contacts with a channel identity (contact_identities). Website and Meta identities merge only by explicit action (or an exact verified match if the client admin enabled it).

Insights: the SaaS shows conversations, answered/unanswered, handoffs and health for the channels it handles.

Meta constraints still apply: WhatsApp 24-hour window and templates, Instagram messaging windows, text only in v1. Many enforces them and reports error codes; the SaaS shows them in the inbox and never retries blindly.

Deferred: outreach and campaign control from the SaaS; the "message sent by Many" mirror event for non-campaign sends; bot actions (booking, purchasing); voice/image/media.

## 8. SaaS schema: implemented vs needed (verified in apps/api)

Implemented:
- Bot-scoped knowledge (documents, chunks, knowledge_revisions, published_revision_id) with no channel dimension; retrieval filters tenant + bot + published revision.
- conversations.channel (website | whatsapp | messenger | instagram), connection_id (plain text, no FK), mode, status, assigned_user_id.
- contact_identities with a channel check constraint; inbox channel badges and filters.
- Channel flows into metering and traces.

Missing (Phase 3):
- A real `channel_connections` table (tenant, bot, channel, Many reference, status, per-connection AI toggle, encrypted signing secret, health fields) with a foreign key from conversations.connection_id.
- Inbound events endpoint, outbound sender, status callbacks, Channels health page.
- Meta-channel conversations cannot be created yet (only website and playground).
- The channel_connections plan limit is a placeholder that counts bots.
- Per-channel style hints (for example DM reply length, handoff wording) as bot or connection settings; no separate knowledge per channel.

## 9. Contract additions to docs/17 (to be written after review)

- `channel.status` events (Many to SaaS) and a health pull endpoint.
- Delegated-mode flag per Many channel; Many forwards every inbound message on delegated channels.
- campaign_name and opening-message text on `message.received` for campaign-origin conversations.
- Statement that handoff and takeover are SaaS-only on delegated channels; Many disables its Take Over / Resume Bot there.
- AI toggle owned by the SaaS per connection; pause semantics.
- Retry behavior and the no-fallback-to-Many-AI rule.
- Update the "Assumption to confirm" line in docs/17: delegated mode is now the decided design.

## 10. Many-side work list (separate workstream in the Many repo, after the website bot closes)

- Delegated-mode flag per channel (Instagram, WhatsApp, Facebook).
- Signed event forwarder to the SaaS; retry with backoff; dedupe by event_id.
- Inbound endpoint for SaaS messages (idempotent by message_id); status callbacks.
- Health events and health pull endpoint.
- Disable Take Over / Resume Bot on delegated channels (UI and route guard).
- Include campaign_name and opening message text in forwarded events.
- Remove the tracked token file from git history after rotating, and clean loose patch files.

## 11. Documentation drift to fix (Stage 1)

- RETRIEVAL_MIN_MATCHED_TERMS: .env.example says 2; THRESHOLDS.md says 1.
- Arabic FTS: FINAL-REPORT.md describes both a real `arabic` config (fts_ar) and `simple` on fts_simple.
- docs/07, 14, 18 still describe keyword-only retrieval and no thresholds.
- MANUAL-TEST.md: compose path, staff-only /widget/sample, current model variables.
- FEATURE-INVENTORY / PHASE-CHECKLISTS: refresh after Stage 7.

## 12. Open questions for the owner

- Which known issues are MVP blockers (list in the closeout plan, section 6)?
- Hosting choice (ADR-007) and backup target: needed before real client data.
- Acceptable ceiling for wrong refusals after the first calibration run.
- Quota values and pricing for the first paying client.
- Whether existing Many-only clients should ever be moved to delegated mode.

## 13. Change log

- 2026-10-17: created from the triage session. No code or configuration was changed by this document.
