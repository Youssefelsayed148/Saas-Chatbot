# Product vision and scope
## Goal
A SaaS where a business registers or is onboarded by staff, enters its website, automatically builds a grounded AI knowledge base, configures an assistant, and installs a single script on its website. Clients manage their own bot, sources, conversations, leads, analytics and usage. Platform staff oversee tenants, jobs, plans and support.
## Personas
Visitor (anonymous chat), client owner, client admin/editor/viewer, platform operator/admin, self-service applicant.
## V1 success journey
Create account → create organization → create bot → add verified/approved website → crawl and review knowledge → publish revision → test answers → customize widget → embed → monitor chats and leads. A staff member can initiate the same provisioning operation on behalf of a customer.
## Non-goals
No cloning or migrating the three reference products; no ManyOsirisChat runtime dependency; no per-client deployment; no enterprise microservice fabric; no direct social messaging in V1; no arbitrary agent tool execution; no automatic paid billing before provider approval.
## Success measures (targets, not established SLAs)
A customer can complete setup without developer intervention; one deployment serves multiple isolated tenants; every answer traces to published tenant content or abstains; staff can diagnose failed ingestion; installation is copy/paste; no known cross-tenant exposure.
