# Product vision and scope
## Goal
A Mojeeb-style SaaS for businesses with a website: a business registers (or is onboarded by staff), gives the AI agent its data (files and the pages of its site, prepared by the website-to-knowledge skill), tests and publishes it, and installs one script on its website. Visitors get grounded answers in Arabic or English; when the bot cannot help, a human takes over from a unified inbox; leads become contacts in a light CRM; follow-ups are scheduled. WhatsApp, Messenger and Instagram are added by connecting the tenant to ManyOsirisChat, which owns all Meta connectivity (docs/17). Platform staff oversee tenants, jobs, plans and support.
## Personas
Visitor (anonymous or known contact), client owner/admin/editor (editors work as inbox agents)/viewer, platform operator, self-service applicant.
## V1 success journey
Create account → organization → bot → upload knowledge → review and publish → test in the playground → customize and embed the widget → a visitor chats → bot hands off → agent takes over in the inbox and replies in the widget → returns it to the bot → lead is a contact with a stage → follow-up scheduled → analytics. Then (P6) the same bot answers on WhatsApp through ManyOsirisChat. Staff can run the same provisioning on a customer's behalf.
## Non-goals
No Meta integration code, tokens or webhooks in this repo (Many owns them); no in-app crawler; no per-client deployment; no enterprise microservice fabric; no arbitrary agent tool execution or live catalogue lookups; no voice/image messages in v1; no deals/pipelines with amounts; no automatic paid billing before provider approval; no email notifications in v1.
## Success measures (targets, not established SLAs)
Setup without developer intervention; one deployment serves many isolated tenants; every AI answer traces to published tenant content or abstains; a human can take over within seconds and the visitor sees the reply; staff can diagnose failed ingestion and failed deliveries; no known cross-tenant exposure.
