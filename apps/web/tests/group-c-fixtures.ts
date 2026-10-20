import { type Page } from "@playwright/test";
import { registerStaffSession } from "./e2e-helpers";

export const tenant = "11111111-1111-4111-8111-111111111111";
export const botId = "22222222-2222-4222-8222-222222222222";
export const conversationId = "33333333-3333-4333-8333-333333333333";
export const contactId = "44444444-4444-4444-8444-444444444444";
export const base = `/app/${tenant}`;
export const botBase = `${base}/bots/${botId}`;
export const statuses = [
  "pending",
  "running",
  "failed",
  "succeeded",
  "cancelled",
];
const now = "2026-10-17T09:00:00Z";
const actions = [
  "platform.onboarding.owner_invited",
  "platform.onboarding.admin_invited",
  "self_service.owner_assigned",
  "self_service.admin_assigned",
];
const events = actions.map((action, index) => ({
  id: String(index),
  action,
  created_at: now,
  at: now,
}));
const bot = {
  id: botId,
  name: "Safety bot",
  status: "active",
  config: {},
  widget_locator: "fixture-locator",
};
const contact = {
  id: contactId,
  display_name: "Safety contact",
  email: "contact@example.com",
  phone: null,
  stage: "new",
  tags: [],
  custom_fields: {},
  consent: {},
  source_channel: "website",
  created_at: now,
  updated_at: now,
};
const conversation = {
  id: conversationId,
  bot_id: botId,
  contact_id: contactId,
  channel: "website",
  mode: "human",
  status: "open",
  assigned_user_id: null,
  handoff_reason: null,
  tags: [],
  last_message: "Hello",
  last_message_at: now,
  unread_count: 0,
  contact_name: contact.display_name,
  message_count: 1,
  created_at: now,
};
const jobs = statuses.map((status) => ({
  id: `job-${status}`,
  tenant_id: tenant,
  bot_id: botId,
  type: `ingest-${status}`,
  status,
  attempts: 1,
  created_at: now,
  updated_at: now,
  run_at: now,
  error: null,
}));

export async function safetyFixture(page: Page, platform = false) {
  if (platform) await registerStaffSession(page, "group-c");
  const writes: { path: string; method: string; body: unknown }[] = [];
  const unexpected: string[] = [];
  await page.route("**/api/v1/**", (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname.replace("/api/v1/", "");
    const reply = (json: unknown) => route.fulfill({ json });
    const suffix = path.replace(`tenants/${tenant}`, "");
    if (request.method() !== "GET") {
      writes.push({
        path,
        method: request.method(),
        body: request.postDataJSON(),
      });
      if (request.method() === "DELETE") return route.fulfill({ status: 204 });
      if (path.endsWith(`/bots/${botId}`)) return reply(bot);
      return reply({});
    }
    if (path === "auth/me")
      return reply({
        id: "fixture-user",
        email: "staff@example.com",
        is_platform_staff: true,
        memberships: [],
      });
    if (path === "platform/tenants")
      return reply({
        tenants: [{ id: tenant, name: "Safety org", status: "active" }],
        total: 1,
      });
    if (path === `platform/tenants/${tenant}`)
      return reply({
        tenant: {
          id: tenant,
          name: "Safety org",
          slug: "safety",
          status: "active",
          plan_label: "starter",
          created_at: now,
        },
        counts: { members: 0, bots: 1 },
        quota: {
          placeholder: true,
          plan: "starter",
          usage: { bots: 1 },
          limits: { bots: 3 },
        },
        bots: [
          {
            ...bot,
            published: false,
            widget_state: "configured",
            source_count: 0,
            last_ingestion_job_status: null,
            published_revision_id: null,
            published_at: null,
          },
        ],
        members: [],
        pending_invitations: [],
        failed_jobs: [],
        recent_audit: events,
        usage_events: 0,
      });
    if (path === "platform/operations/jobs") return reply({ counts: {}, jobs });
    if (path === "platform/analytics")
      return reply({
        tenants: 1,
        bots: 1,
        conversations: 1,
        messages: 1,
        handoffs: 0,
        handoff_rate: 0,
        clients: [],
      });
    if (path === "platform/audit" || suffix === "/data/audit")
      return reply({ events });
    if (path === "platform/quotas")
      return reply({ placeholder: true, plans: { free: {} } });
    if (suffix === "/bots") return reply([bot]);
    if (suffix === `/bots/${botId}`) return reply(bot);
    if (suffix === "/members")
      return reply([
        {
          user_id: "fixture-user",
          email: "staff@example.com",
          role: "admin",
          is_last_admin: true,
        },
        {
          user_id: "remove-user",
          email: "member@example.com",
          role: "viewer",
          is_last_admin: false,
        },
      ]);
    if (suffix === "/invitations") return reply([]);
    if (suffix === "/quota")
      return reply({ plan: "starter", usage: {}, limits: {}, warnings: [] });
    if (suffix === "/inbox/counts")
      return reply({
        waiting_human: 0,
        assigned_to_me: 0,
        unread_messages: 0,
        unread_conversations: 0,
      });
    if (suffix === "/inbox/events")
      return route.fulfill({
        contentType: "text/event-stream",
        body: ": fixture\n\n",
      });
    if (suffix === `/bots/${botId}/conversations` || suffix === "/inbox")
      return reply({ conversations: [conversation], total: 1 });
    if (
      suffix === `/conversations/${conversationId}` ||
      suffix === `/bots/${botId}/conversations/${conversationId}`
    )
      return reply({ conversation, messages: [] });
    if (suffix === `/bots/${botId}/rag`)
      return reply({
        tier: "standard",
        limits: {},
        effective_limits: {},
        usage: {},
        backfill: null,
        retrieval_mode: "keyword",
      });
    if (suffix.endsWith("/rag/costs")) return reply({ costs: [] });
    if (suffix.endsWith("/rag/limits"))
      return reply({ limits: {}, effective_limits: {}, usage: {} });
    if (suffix.endsWith("/sources") || suffix.endsWith("/documents"))
      return reply([]);
    if (suffix.endsWith("/jobs")) return reply(jobs);
    if (suffix.endsWith("/revisions"))
      return reply({ revisions: [], published_revision_id: null });
    if (suffix === "/contacts") return reply({ contacts: [contact] });
    if (suffix === `/contacts/${contactId}`)
      return reply({
        contact,
        identities: [],
        timeline: [
          {
            type: "conversation",
            id: conversationId,
            channel: "website",
            status: "open",
            created_at: now,
          },
        ],
      });
    if (suffix === "/analytics")
      return reply({
        total_conversations: 0,
        handoff_count: 0,
        handoff_rate: 0,
        average_first_human_reply_seconds: null,
        conversations_by_channel: {},
        resolved_vs_open: {},
        sentiment_distribution: {},
        agent_workload: {},
      });
    if (suffix === "/follow-ups") return reply({ follow_ups: [] });
    if (suffix === "/data/deletion-preview")
      return reply({ counts: {}, name: "Safety org" });
    if (suffix === "")
      return reply({ id: tenant, name: "Safety org", retention_days: 30 });
    if (suffix === "/change-requests" || path === "platform/change-requests")
      return reply([]);
    unexpected.push(path);
    return route.fulfill({
      status: 404,
      json: { error: { code: "FIXTURE_MISSING", message: path } },
    });
  });
  return { writes, unexpected };
}
