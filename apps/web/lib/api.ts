/**
 * Typed API client for the FastAPI backend (docs/05 contracts).
 *
 * All requests are relative (same origin) through the Next.js rewrite proxy.
 * Session cookies are sent with credentials: "include"; every write carries
 * the double-submit CSRF header read from the csrf cookie.
 */

export const SESSION_COOKIE = "chatbot_session";
export const CSRF_COOKIE = "chatbot_csrf";

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly requestId: string | undefined;

  constructor(
    code: string,
    status: number,
    message: string,
    requestId?: string,
  ) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.requestId = requestId;
  }
}

export type Role = "admin" | "editor" | "viewer";

export interface Contact {
  id: string;
  display_name: string;
  email: string | null;
  phone: string | null;
  stage: string;
  tags: string[];
  custom_fields: Record<string, unknown>;
  consent: Record<string, unknown>;
  source_channel: string | null;
  created_at: string;
  updated_at: string;
}

export interface ContactProfile {
  contact: Contact;
  identities: { channel: string; external_id: string; created_at: string }[];
  timeline: {
    type: string;
    id?: string;
    conversation_id?: string;
    channel?: string;
    status?: string;
    text?: string;
    created_at: string;
  }[];
}

export interface FollowUp {
  id: string;
  conversation_id: string;
  contact_id: string | null;
  send_at: string;
  text: string;
  status: "scheduled" | "ready" | "delivered" | "cancelled";
  created_at: string;
  delivered_at: string | null;
}

export interface HandoffAnalytics {
  total_conversations: number;
  handoff_count: number;
  handoff_rate: number | null;
  average_first_human_reply_seconds: number | null;
  conversations_by_channel: Record<string, number>;
  resolved_vs_open: { resolved: number; open: number };
  sentiment_distribution: Record<string, number>;
  agent_workload: Record<string, number>;
}

const CONTACTS = (tenantId: string) => `tenants/${tenantId}/contacts`;

export async function listContacts(tenantId: string): Promise<Contact[]> {
  const result = await api<{ contacts: Contact[] }>(CONTACTS(tenantId));
  return result.contacts;
}

export function getContact(
  tenantId: string,
  contactId: string,
): Promise<ContactProfile> {
  return api<ContactProfile>(`${CONTACTS(tenantId)}/${contactId}`);
}

export function createContact(
  tenantId: string,
  body: Partial<Contact>,
): Promise<Contact> {
  return api<Contact>(CONTACTS(tenantId), { method: "POST", body });
}

export function updateContact(
  tenantId: string,
  contactId: string,
  body: Partial<Contact>,
): Promise<Contact> {
  return api<Contact>(`${CONTACTS(tenantId)}/${contactId}`, {
    method: "PATCH",
    body,
  });
}

export function mergeContact(
  tenantId: string,
  sourceId: string,
  targetId: string,
): Promise<Contact> {
  return api<Contact>(
    `${CONTACTS(tenantId)}/${sourceId}/merge?target_id=${encodeURIComponent(targetId)}`,
    { method: "POST" },
  );
}

export function eraseContact(
  tenantId: string,
  contactId: string,
  eraseMessages: boolean,
): Promise<void> {
  return api<void>(
    `${CONTACTS(tenantId)}/${contactId}?erase_messages=${eraseMessages}`,
    { method: "DELETE" },
  );
}

export function renameContactStage(
  tenantId: string,
  oldName: string,
  name: string,
): Promise<{ name: string }> {
  return api<{ name: string }>(`${CONTACTS(tenantId)}/stages`, {
    method: "PATCH",
    body: { old_name: oldName, name },
  });
}

export function listFollowUps(
  tenantId: string,
): Promise<{ follow_ups: FollowUp[] }> {
  return api<{ follow_ups: FollowUp[] }>(`tenants/${tenantId}/follow-ups`);
}

export function createFollowUp(
  tenantId: string,
  body: {
    conversation_id: string;
    contact_id: string;
    send_at: string;
    text: string;
  },
): Promise<FollowUp> {
  return api<FollowUp>(`tenants/${tenantId}/follow-ups`, {
    method: "POST",
    body,
  });
}

export function cancelFollowUp(
  tenantId: string,
  followUpId: string,
): Promise<void> {
  return api<void>(`tenants/${tenantId}/follow-ups/${followUpId}`, {
    method: "DELETE",
  });
}

export function handoffAnalytics(tenantId: string): Promise<HandoffAnalytics> {
  return api<HandoffAnalytics>(`tenants/${tenantId}/analytics`);
}

export interface Membership {
  tenant_id: string;
  tenant_name: string;
  tenant_slug: string;
  role: Role;
}

export interface Me {
  id: string;
  email: string;
  is_platform_staff: boolean;
  memberships: Membership[];
}

export function authConfig(): Promise<{ self_serve_signup: boolean }> {
  return api<{ self_serve_signup: boolean }>("auth/config");
}

export interface Tenant {
  id: string;
  name: string;
  slug: string;
  status: string;
  created_at: string;
}

export interface Bot {
  id: string;
  tenant_id: string;
  name: string;
  status: "draft" | "active" | "paused" | "archived";
  config: {
    assistant_name?: string;
    business_name?: string;
    business_description?: string;
    welcome_message?: { en?: string; ar?: string };
    opening_questions?: string[];
    default_language?: "en" | "ar";
    support_email?: string;
    support_phone?: string;
    colour?: string;
    position?: "left" | "right";
    handoff_enabled?: boolean;
    allowed_domains?: string[];
    avatar?: string;
  };
  widget_locator?: string;
  created_at: string;
  updated_at: string;
}

export interface Conversation {
  id: string;
  channel: string;
  mode: string;
  status: string;
  contact_name: string | null;
  last_message_at: string | null;
  message_count: number;
  created_at: string;
}

export interface ConversationListResponse {
  conversations: Conversation[];
  total: number;
}

export interface AnalyticsSummaryResponse {
  messages: number;
  counted_messages: number;
  conversations: number;
  widget_opens: number;
  engagement_rate: number;
  avg_messages_per_conversation: number;
  message_distribution: Record<string, number>;
  fallback_rate: number;
  cannot_answer: number;
  needs_human: number;
  handoffs: number;
  avg_response_ms: number;
  leads: number;
  thumbs_up: number;
  thumbs_down: number;
}

export interface AnalyticsVolumeResponse {
  days: Array<{ day: string; visitor: number; assistant: number }>;
}

export interface AnalyticsTopQuestionsResponse {
  questions: Array<{ question: string; asked: number }>;
}

export interface AnalyticsUnansweredResponse {
  questions: Array<{ question: string; asked: number; last: string }>;
}

export interface AnalyticsLeadsResponse {
  trend: Array<{ day: string; leads: number }>;
  contacts: Array<{
    contact_id: string;
    display_name: string;
    email: string | null;
    phone: string | null;
    stage: string;
    created_at: string;
    conversations: number;
  }>;
}

export interface PlatformTenantRow {
  id: string;
  name: string;
  slug: string;
  status: string;
  plan_label: string;
  bots: number;
  seats: number;
  messages_this_month: number;
  last_activity: string | null;
}

export interface PlatformTenantDetail {
  tenant: {
    id: string;
    name: string;
    slug: string;
    status: string;
    plan_label: string;
  };
  bots: Array<{ id: string; name: string; status: string; published: boolean }>;
  failed_jobs: Array<{ id: string; type: string; error: string | null }>;
  members: Array<{ user_id: string; email: string; role: string }>;
  recent_audit: Array<{
    action: string;
    actor: string | null;
    target: string | null;
    at: string;
  }>;
  usage_events: number;
}

export interface PlatformJob {
  id: string;
  tenant_id: string;
  bot_id: string;
  type: string;
  status: string;
  attempts: number;
  run_at: string;
  updated_at: string;
  error: string | null;
}

export interface PlatformAnalytics {
  tenants: number;
  bots: number;
  conversations: number;
  messages: number;
  handoffs: number;
  handoff_rate: number;
  clients: Array<{
    tenant_id: string;
    name: string;
    plan_label: string;
    usage: Record<string, number>;
  }>;
}

export interface PlatformQuotaPlans {
  placeholder: true;
  plans: Record<string, Record<string, number>>;
}

export interface TenantQuotaStatus {
  placeholder: true;
  plan: string;
  usage: Record<string, number>;
  limits: Record<string, number>;
  warnings: string[];
  measured_tokens_this_month: number;
}

export async function tenantQuota(
  tenantId: string,
): Promise<TenantQuotaStatus> {
  return api(`tenants/${tenantId}/quota`);
}

export async function platformQuotas(): Promise<PlatformQuotaPlans> {
  return api("platform/quotas");
}

export async function platformJobHealth(): Promise<{
  counts: Record<string, number>;
  jobs: PlatformJob[];
}> {
  return api("platform/operations/jobs");
}

export async function platformJobAction(
  jobId: string,
  action: "retry" | "cancel",
  reason: string,
): Promise<{ id: string; status: string }> {
  return api(`platform/operations/jobs/${jobId}/${action}`, {
    method: "POST",
    body: { reason },
  });
}

export async function platformAnalytics(): Promise<PlatformAnalytics> {
  return api("platform/analytics");
}

export async function platformAudit(query: string): Promise<{
  events: Array<{
    tenant_id: string | null;
    action: string;
    actor_user_id: string | null;
    target_type: string | null;
    target_id: string | null;
    created_at: string;
  }>;
}> {
  const suffix = query ? `?q=${encodeURIComponent(query)}` : "";
  return api(`platform/audit${suffix}`);
}

export async function platformAssignPlan(
  tenantId: string,
  planLabel: string,
  reason: string,
): Promise<{ tenant_id: string; plan_label: string }> {
  return api(`platform/tenants/${tenantId}/plan`, {
    method: "PATCH",
    body: { plan_label: planLabel, reason },
  });
}

export async function platformQuotaOverride(
  tenantId: string,
  limits: Record<string, number>,
  reason: string,
): Promise<{ tenant_id: string; limits: Record<string, number> }> {
  return api(`platform/tenants/${tenantId}/quota-overrides`, {
    method: "PATCH",
    body: { limits, reason },
  });
}

export async function platformPauseBot(
  botId: string,
  reason: string,
): Promise<{ bot_id: string; status: string }> {
  return api(`platform/bots/${botId}/pause`, {
    method: "POST",
    body: { reason },
  });
}

export interface PlatformOnboardingResult {
  request_id: string;
  status: string;
  result?: {
    tenant_id?: string;
    tenant_slug?: string;
    bot_id?: string | null;
    owner_invite?: { link_path?: string };
    files?: Array<{ display?: string; bot_id?: string }>;
  };
  replayed?: boolean;
}

export interface ConversationDetailResponse {
  conversation: Conversation;
  messages: Array<{
    id: string;
    sender_type: string;
    text: string;
    citations: Array<{
      chunk_id: string;
      title?: string | null;
      heading?: string | null;
      source_url?: string | null;
      page_ref?: string | null;
    }>;
    can_answer: boolean | null;
    needs_human: boolean;
    created_at: string;
  }>;
}

export interface InboxConversation {
  id: string;
  bot_id: string;
  contact_id: string | null;
  channel: string;
  mode: string;
  status: string;
  assigned_user_id: string | null;
  handoff_reason: string | null;
  last_message_at: string | null;
  last_message?: string | null;
  unread_count?: number;
  tags?: string[];
}

export interface InboxResponse {
  conversations: InboxConversation[];
  total: number;
  limit: number;
  offset: number;
}

export interface InboxCounts {
  waiting_human: number;
  assigned_to_me: number;
  unread_messages: number;
  unread_conversations: number;
}

export interface InboxMessage {
  id: string;
  sender_type: string;
  sender_user_id?: string | null;
  text: string;
  citations: Array<{
    chunk_id: string;
    title?: string | null;
    heading?: string | null;
    source_url?: string | null;
    page_ref?: string | null;
  }>;
  can_answer: boolean | null;
  needs_human: boolean;
  feedback?: Array<"up" | "down">;
  created_at: string;
}

export interface InboxThread {
  conversation: InboxConversation;
  messages: InboxMessage[];
}

export async function listInbox(
  tenantId: string,
  filters: Record<string, string | boolean | undefined> = {},
): Promise<InboxResponse> {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== "") query.set(key, String(value));
  }
  const suffix = query.size ? `?${query.toString()}` : "";
  return api<InboxResponse>(`tenants/${tenantId}/inbox${suffix}`);
}

export async function inboxCounts(tenantId: string): Promise<InboxCounts> {
  return api<InboxCounts>(`tenants/${tenantId}/inbox/counts`);
}

export async function getInboxThread(
  tenantId: string,
  conversationId: string,
): Promise<InboxThread> {
  return api<InboxThread>(
    `tenants/${tenantId}/conversations/${conversationId}`,
  );
}

export async function inboxAction(
  tenantId: string,
  conversationId: string,
  action: "takeover" | "return-to-ai" | "resolve" | "assign",
  body?: unknown,
): Promise<unknown> {
  return api(`tenants/${tenantId}/conversations/${conversationId}/${action}`, {
    method: "POST",
    ...(body === undefined ? {} : { body }),
  });
}

export async function sendAgentReply(
  tenantId: string,
  conversationId: string,
  text: string,
): Promise<{ message: InboxMessage }> {
  return api(`tenants/${tenantId}/conversations/${conversationId}/messages`, {
    method: "POST",
    body: { text },
  });
}

export async function addConversationNote(
  tenantId: string,
  conversationId: string,
  text: string,
): Promise<void> {
  return api(`tenants/${tenantId}/conversations/${conversationId}/notes`, {
    method: "POST",
    body: { text },
  });
}

export async function markInboxRead(
  tenantId: string,
  conversationId: string,
): Promise<void> {
  return api(`tenants/${tenantId}/inbox/${conversationId}/read`, {
    method: "POST",
  });
}

export async function addInboxTag(
  tenantId: string,
  conversationId: string,
  tag: string,
): Promise<void> {
  return api(`tenants/${tenantId}/inbox/${conversationId}/tags`, {
    method: "POST",
    body: { tag },
  });
}

export async function removeInboxTag(
  tenantId: string,
  conversationId: string,
  tag: string,
): Promise<void> {
  return api(
    `tenants/${tenantId}/inbox/${conversationId}/tags/${encodeURIComponent(tag)}`,
    { method: "DELETE" },
  );
}

export interface WidgetSendMessageResponse {
  conversation_id: string;
  visitor_message: { id: string; text: string; created_at: string };
  ai_message: {
    id: string;
    text: string;
    citations: Array<{
      chunk_id: string;
      title?: string | null;
      source_url?: string | null;
    }>;
    can_answer: boolean | null;
    needs_human: boolean;
    created_at: string;
  };
  kind: string;
  language: string;
}

export interface Member {
  user_id: string;
  email: string;
  role: Role;
  status: string;
  joined_at: string;
}

export interface Invitation {
  id: string;
  email: string;
  role: Role;
  expires_at: string;
  created_at: string;
  expired: boolean;
  // Only present in create/resend responses (one-time link).
  link_path?: string;
}

export interface AuthPayload {
  me: Me;
}

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const entry = document.cookie
    .split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith(`${name}=`));
  return entry ? decodeURIComponent(entry.slice(name.length + 1)) : null;
}

function extractCsrfFromSetCookie(headers: Headers): string | null {
  // Some responses set the csrf cookie while the document.cookie mirror may not
  // be ready yet right after login; prefer the live cookie, fall back to the header.
  const raw = headers.get("set-cookie");
  if (!raw) return null;
  const match = raw
    .split(", ")
    .find((cookie) => cookie.startsWith(`${CSRF_COOKIE}=`));
  if (!match) return null;
  return decodeURIComponent(match.slice(CSRF_COOKIE.length + 1).split(";")[0]);
}

let csrfToken: string | null = null;

export function rememberCsrfFrom(headers: Headers): void {
  csrfToken =
    readCookie(CSRF_COOKIE) ?? extractCsrfFromSetCookie(headers) ?? csrfToken;
}

export function csrfHeader(): Record<string, string> {
  const value = readCookie(CSRF_COOKIE) ?? csrfToken;
  return value ? { "X-CSRF-Token": value } : {};
}

interface ApiOptions {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  body?: unknown;
  /** Accept 401 responses instead of triggering the global sign-out redirect. */
  tolerate401?: boolean;
}

const WRITES_REQUIRING_CSRF = new Set(["POST", "PATCH", "DELETE"]);

export async function api<T>(
  path: string,
  options: ApiOptions = {},
): Promise<T> {
  const method = options.method ?? "GET";
  const headers: Record<string, string> = {};
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (WRITES_REQUIRING_CSRF.has(method)) Object.assign(headers, csrfHeader());

  const response = await fetch(`/api/v1/${path}`, {
    method,
    headers,
    credentials: "same-origin",
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });
  rememberCsrfFrom(response.headers);

  if (response.status === 204) return undefined as T;

  let payload: unknown = null;
  const text = await response.text();
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = null;
    }
  }

  if (!response.ok) {
    const error = (
      payload as {
        error?: { code?: string; message?: string; request_id?: string };
      }
    )?.error;
    // Global rule: an expired/invalid session sends the user back to the login page.
    // The SessionProvider listens for this event and navigates (no hard reload needed).
    if (
      !options.tolerate401 &&
      response.status === 401 &&
      typeof window !== "undefined"
    ) {
      window.dispatchEvent(new CustomEvent("session-expired"));
    }
    throw new ApiError(
      error?.code ?? "UNKNOWN_ERROR",
      response.status,
      error?.message ?? `Request failed (${response.status}).`,
      error?.request_id,
    );
  }
  return payload as T;
}

// --- contract helpers ------------------------------------------------------

export async function register(
  email: string,
  password: string,
  inviteToken?: string,
): Promise<Me> {
  return api<Me>("auth/register", {
    method: "POST",
    body: { email, password, invite_token: inviteToken },
  });
}

export async function selfServiceSignup(
  clientName: string,
  botName: string,
): Promise<{
  result: { tenant_id: string; tenant_slug: string; bot_id: string };
}> {
  return api("provisioning/self-service", {
    method: "POST",
    body: { client_name: clientName, bot_name: botName },
  });
}

export async function login(email: string, password: string): Promise<Me> {
  return api<Me>("auth/login", { method: "POST", body: { email, password } });
}

export async function logout(): Promise<void> {
  // Logout may already be signed out; never surface an error here.
  try {
    await api<unknown>("auth/logout", { method: "POST", tolerate401: true });
  } finally {
    void 0;
  }
}

export async function me(): Promise<Me> {
  return api<Me>("auth/me", { tolerate401: true });
}

export async function createTenant(name: string): Promise<Tenant> {
  return api<Tenant>("tenants", { method: "POST", body: { name } });
}

export async function getTenant(tenantId: string): Promise<Tenant> {
  return api<Tenant>(`tenants/${tenantId}`);
}

export interface TenantAuditEvent {
  id: string;
  action: string;
  actor_user_id: string | null;
  target_type: string | null;
  target_id: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

export async function tenantAudit(
  tenantId: string,
  query = "",
): Promise<{ events: TenantAuditEvent[] }> {
  const suffix = query ? `?q=${encodeURIComponent(query)}` : "";
  return api(`tenants/${tenantId}/data/audit${suffix}`);
}

export async function exportTenantData(
  tenantId: string,
): Promise<Record<string, unknown>> {
  return api(`tenants/${tenantId}/data/export`);
}

export async function deleteTenantData(
  tenantId: string,
  confirmName: string,
  reason: string,
): Promise<void> {
  await api(`tenants/${tenantId}/data`, {
    method: "DELETE",
    body: { confirm_name: confirmName, reason },
  });
}

export async function listBots(
  tenantId: string,
  includeArchived = false,
): Promise<Bot[]> {
  return api<Bot[]>(
    `tenants/${tenantId}/bots${includeArchived ? "?include_archived=true" : ""}`,
  );
}

export async function createBot(tenantId: string, name: string): Promise<Bot> {
  return api<Bot>(`tenants/${tenantId}/bots`, {
    method: "POST",
    body: { name },
  });
}

export async function getBot(tenantId: string, botId: string): Promise<Bot> {
  return api<Bot>(`tenants/${tenantId}/bots/${botId}`);
}

export async function patchBot(
  tenantId: string,
  botId: string,
  patch: {
    name?: string;
    status?: "active" | "paused";
    config?: Record<string, unknown>;
  },
): Promise<Bot> {
  return api<Bot>(`tenants/${tenantId}/bots/${botId}`, {
    method: "PATCH",
    body: patch,
  });
}

export async function archiveBot(
  tenantId: string,
  botId: string,
): Promise<Bot> {
  return api<Bot>(`tenants/${tenantId}/bots/${botId}`, { method: "DELETE" });
}

export async function listConversations(
  tenantId: string,
  botId: string,
  status?: string,
): Promise<ConversationListResponse> {
  const suffix = status ? `?status=${encodeURIComponent(status)}` : "";
  return api<ConversationListResponse>(
    `tenants/${tenantId}/bots/${botId}/conversations${suffix}`,
  );
}

export async function getConversation(
  tenantId: string,
  botId: string,
  conversationId: string,
): Promise<ConversationDetailResponse> {
  return api<ConversationDetailResponse>(
    `tenants/${tenantId}/bots/${botId}/conversations/${conversationId}`,
  );
}

export async function deleteConversation(
  tenantId: string,
  botId: string,
  conversationId: string,
): Promise<{ status: string }> {
  return api<{ status: string }>(
    `tenants/${tenantId}/bots/${botId}/conversations/${conversationId}`,
    { method: "DELETE" },
  );
}

export async function updateTenant(
  tenantId: string,
  patch: { retention_days?: number | null },
): Promise<Tenant> {
  return api<Tenant>(`tenants/${tenantId}`, { method: "PATCH", body: patch });
}

function analyticsPath(
  tenantId: string,
  botId: string,
  view: string,
  from: string,
  to: string,
): string {
  return `tenants/${tenantId}/bots/${botId}/analytics/${view}?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`;
}

export async function analyticsSummary(
  tenantId: string,
  botId: string,
  from: string,
  to: string,
): Promise<AnalyticsSummaryResponse> {
  return api<AnalyticsSummaryResponse>(
    analyticsPath(tenantId, botId, "summary", from, to),
  );
}

export async function analyticsVolume(
  tenantId: string,
  botId: string,
  from: string,
  to: string,
): Promise<AnalyticsVolumeResponse> {
  return api<AnalyticsVolumeResponse>(
    analyticsPath(tenantId, botId, "volume", from, to),
  );
}

export async function analyticsTopQuestions(
  tenantId: string,
  botId: string,
  from: string,
  to: string,
): Promise<AnalyticsTopQuestionsResponse> {
  return api<AnalyticsTopQuestionsResponse>(
    analyticsPath(tenantId, botId, "top-questions", from, to),
  );
}

export async function analyticsUnanswered(
  tenantId: string,
  botId: string,
  from: string,
  to: string,
): Promise<AnalyticsUnansweredResponse> {
  return api<AnalyticsUnansweredResponse>(
    analyticsPath(tenantId, botId, "unanswered", from, to),
  );
}

export async function analyticsLeads(
  tenantId: string,
  botId: string,
  from: string,
  to: string,
): Promise<AnalyticsLeadsResponse> {
  return api<AnalyticsLeadsResponse>(
    analyticsPath(tenantId, botId, "leads", from, to),
  );
}

// --- platform console (P4-06; staff-only, guarded server-side) -------------

export async function platformMe(): Promise<Me> {
  return api<Me>("platform/me");
}

export async function platformTenants(query: string): Promise<{
  tenants: PlatformTenantRow[];
  total: number;
}> {
  const suffix = query ? `?${query}` : "";
  return api<{ tenants: PlatformTenantRow[]; total: number }>(
    `platform/tenants${suffix}`,
  );
}

export async function platformTenantDetail(
  tenantId: string,
): Promise<PlatformTenantDetail> {
  return api<PlatformTenantDetail>(`platform/tenants/${tenantId}`);
}

export async function platformOnboard(
  payload: {
    client_name: string;
    owner_email: string;
    bot_name: string | null;
  },
  idempotencyKey: string,
  files: FileList | null,
): Promise<PlatformOnboardingResult> {
  const form = new FormData();
  form.set("client_name", payload.client_name);
  form.set("owner_email", payload.owner_email);
  if (payload.bot_name) form.set("bot_name", payload.bot_name);
  if (files) Array.from(files).forEach((file) => form.append("files", file));
  const headerValue = readCookie(CSRF_COOKIE) ?? csrfToken;
  const response = await fetch(`/api/v1/platform/onboarding`, {
    method: "POST",
    headers: {
      "Idempotency-Key": idempotencyKey,
      ...(headerValue ? { "X-CSRF-Token": headerValue } : {}),
    },
    credentials: "same-origin",
    body: form,
  });
  if (!response.ok) {
    const errorPayload = (await response.json().catch(() => null)) as {
      error?: { code?: string; message?: string };
    } | null;
    throw new ApiError(
      errorPayload?.error?.code ?? "UNKNOWN_ERROR",
      response.status,
      errorPayload?.error?.message ?? `Onboarding failed (${response.status}).`,
    );
  }
  return (await response.json()) as PlatformOnboardingResult;
}

export async function listMembers(tenantId: string): Promise<Member[]> {
  return api<Member[]>(`tenants/${tenantId}/members`);
}

export async function updateMemberRole(
  tenantId: string,
  userId: string,
  role: Role,
): Promise<Member> {
  return api<Member>(`tenants/${tenantId}/members/${userId}`, {
    method: "PATCH",
    body: { role },
  });
}

export async function removeMember(
  tenantId: string,
  userId: string,
): Promise<void> {
  await api<unknown>(`tenants/${tenantId}/members/${userId}`, {
    method: "DELETE",
  });
}

export async function listInvitations(tenantId: string): Promise<Invitation[]> {
  return api<Invitation[]>(`tenants/${tenantId}/invitations`);
}

export async function createInvitation(
  tenantId: string,
  email: string,
  role: Role,
): Promise<Invitation> {
  return api<Invitation>(`tenants/${tenantId}/invitations`, {
    method: "POST",
    body: { email, role },
  });
}

export async function resendInvitation(
  tenantId: string,
  invitationId: string,
): Promise<Invitation> {
  return api<Invitation>(
    `tenants/${tenantId}/invitations/${invitationId}/resend`,
    {
      method: "POST",
    },
  );
}

export async function revokeInvitation(
  tenantId: string,
  invitationId: string,
): Promise<void> {
  await api<unknown>(`tenants/${tenantId}/invitations/${invitationId}`, {
    method: "DELETE",
  });
}

export async function acceptInvitation(token: string): Promise<Me> {
  return api<Me>("invitations/accept", {
    method: "POST",
    body: { token },
    tolerate401: true,
  });
}

// --- knowledge (P2) ---------------------------------------------------------

export type KnowledgeSourceKind = "pdf" | "docx" | "txt" | "md" | "qa_csv";
export type KnowledgeSourceStatus = "stored" | "queued" | "ingested" | "failed";

export interface KnowledgeSource {
  id: string;
  kind: KnowledgeSourceKind;
  original_name: string;
  storage_key: string;
  size_bytes: number;
  sha256: string;
  status: KnowledgeSourceStatus;
  error: string | null;
  row_errors: { row: number; reason: string }[] | null;
  valid_rows: number | null;
  total_rows: number | null;
  created_at: string;
}

export type KnowledgeJobStatus =
  "pending" | "running" | "succeeded" | "failed" | "cancelled";

export interface KnowledgeJob {
  id: string;
  status: KnowledgeJobStatus;
  type: string;
  source_ids: string[];
  attempts: number;
  max_attempts: number;
  error: string | null;
  cancel_requested: boolean;
  run_at: string;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

export interface KnowledgeDocument {
  id: string;
  source_id: string;
  title: string;
  heading: string | null;
  source_url: string | null;
  page_ref: string;
  language: string;
  priority: number;
  text: string;
  total_chars: number;
  chunk_count: number;
  status: string;
  warnings: string[];
  created_at: string;
}

export interface KnowledgeChunk {
  id: string;
  document_id: string;
  title: string;
  heading: string | null;
  text: string;
  language: string;
  priority: number;
  ordinal: number;
}

export interface KnowledgeRevision {
  id: string;
  status: "draft" | "published" | "archived";
  published_at: string | null;
  created_at: string;
  is_current: boolean;
  document_count: number;
  chunk_count: number;
}

export interface RevisionsResponse {
  revisions: KnowledgeRevision[];
  published_revision_id: string | null;
}

const KNOWLEDGE_ROOT = (tenantId: string, botId: string): string =>
  `tenants/${tenantId}/bots/${botId}`;

export async function listSources(
  tenantId: string,
  botId: string,
): Promise<KnowledgeSource[]> {
  return api<KnowledgeSource[]>(`${KNOWLEDGE_ROOT(tenantId, botId)}/sources`);
}

/** Multipart upload; the CSRF header is added like every write. */
export async function uploadSources(
  tenantId: string,
  botId: string,
  files: File[],
): Promise<KnowledgeSource[]> {
  const form = new FormData();
  for (const file of files) {
    form.append("files", file);
  }
  const method = "POST";
  const headers: Record<string, string> = csrfHeader();
  const response = await fetch(
    `/api/v1/${KNOWLEDGE_ROOT(tenantId, botId)}/sources/files`,
    { method, headers, credentials: "same-origin", body: form },
  );
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const error = (
      payload as { error?: { code?: string; message?: string } } | null
    )?.error;
    throw new ApiError(
      error?.code ?? "UNKNOWN_ERROR",
      response.status,
      error?.message ?? `Upload failed (${response.status}).`,
    );
  }
  return (payload ?? []) as KnowledgeSource[];
}

export async function qaTemplateHref(
  tenantId: string,
  botId: string,
): Promise<string> {
  return `/api/v1/${KNOWLEDGE_ROOT(tenantId, botId)}/sources/qa-template`;
}

export async function startIngestion(
  tenantId: string,
  botId: string,
  sourceIds: string[] | null = null,
): Promise<KnowledgeJob> {
  return api<KnowledgeJob>(`${KNOWLEDGE_ROOT(tenantId, botId)}/ingestion`, {
    method: "POST",
    body: sourceIds ? { source_ids: sourceIds } : {},
  });
}

export async function listJobs(
  tenantId: string,
  botId: string,
): Promise<KnowledgeJob[]> {
  return api<KnowledgeJob[]>(`${KNOWLEDGE_ROOT(tenantId, botId)}/jobs`);
}

export async function retryJob(
  tenantId: string,
  botId: string,
  jobId: string,
): Promise<KnowledgeJob> {
  return api<KnowledgeJob>(
    `${KNOWLEDGE_ROOT(tenantId, botId)}/jobs/${jobId}/retry`,
    { method: "POST" },
  );
}

export async function cancelJob(
  tenantId: string,
  botId: string,
  jobId: string,
): Promise<KnowledgeJob> {
  return api<KnowledgeJob>(
    `${KNOWLEDGE_ROOT(tenantId, botId)}/jobs/${jobId}/cancel`,
    { method: "POST" },
  );
}

export async function listDocuments(
  tenantId: string,
  botId: string,
  options: { sourceId?: string; revision?: "published" | "draft" } = {},
): Promise<KnowledgeDocument[]> {
  const params = new URLSearchParams();
  if (options.sourceId) params.set("source_id", options.sourceId);
  params.set("revision", options.revision ?? "published");
  return api<KnowledgeDocument[]>(
    `${KNOWLEDGE_ROOT(tenantId, botId)}/documents?${params.toString()}`,
  );
}

export async function listDocumentChunks(
  tenantId: string,
  botId: string,
  documentId: string,
): Promise<KnowledgeChunk[]> {
  return api<KnowledgeChunk[]>(
    `${KNOWLEDGE_ROOT(tenantId, botId)}/documents/${documentId}/chunks`,
  );
}

export async function listRevisions(
  tenantId: string,
  botId: string,
): Promise<RevisionsResponse> {
  return api<RevisionsResponse>(`${KNOWLEDGE_ROOT(tenantId, botId)}/revisions`);
}

export async function publishRevision(
  tenantId: string,
  botId: string,
  revisionId: string,
): Promise<{ revision_id: string; status: string; changed: boolean }> {
  return api<{
    revision_id: string;
    status: string;
    changed: boolean;
  }>(`${KNOWLEDGE_ROOT(tenantId, botId)}/revisions/${revisionId}/publish`, {
    method: "POST",
  });
}

// --- playground (P3-04) ------------------------------------------------------

export interface PlaygroundMessage {
  id: string;
  sender_type: "visitor" | "ai" | "agent" | "system";
  text: string;
  citations:
    | {
        chunk_id: string;
        title: string;
        heading?: string | null;
        source_url?: string | null;
      }[]
    | null;
  can_answer: boolean | null;
  needs_human: boolean;
  response_ms: number | null;
  created_at: string;
}

export interface PlaygroundTurnResponse {
  conversation_id: string;
  mode: string;
  status: string;
  visitor_message: { id: string; text: string; created_at: string };
  ai_message: {
    id: string;
    text: string;
    citations: {
      chunk_id: string;
      title: string;
      heading?: string | null;
      source_url?: string | null;
    }[];
    can_answer: boolean;
    needs_human: boolean;
    response_ms: number | null;
    created_at: string;
  };
  kind: string;
  language: string;
}

export async function playgroundTurn(
  tenantId: string,
  botId: string,
  text: string,
): Promise<PlaygroundTurnResponse> {
  return api<PlaygroundTurnResponse>(
    `tenants/${tenantId}/bots/${botId}/playground/messages`,
    { method: "POST", body: { text } },
  );
}

export interface PlaygroundConversation {
  conversation_id: string;
  message_count: number;
  messages: PlaygroundMessage[];
}

export interface RagTrace {
  message_id: string;
  created_at: string;
  trace: {
    retrieval_mode: string;
    gate: string;
    rewrite_used: boolean;
    model: string | null;
    tokens: Record<string, number> | null;
    cost_usd: string | null;
    chunks: {
      chunk_id: string;
      title: string;
      locator: string;
      vector_similarity: number | null;
      fts_match: number;
      accepted: boolean;
    }[];
  };
}

export async function ragTraces(
  tenantId: string,
  botId: string,
): Promise<RagTrace[]> {
  const result = await api<{ traces: RagTrace[] }>(
    `tenants/${tenantId}/bots/${botId}/rag/traces`,
  );
  return result.traces;
}

export const RAG_LIMIT_NAMES = [
  "documents",
  "chunks",
  "storage_bytes",
  "monthly_messages",
  "monthly_tokens",
  "monthly_embedding_tokens",
  "monthly_ocr_pages",
] as const;
export type RagLimitName = (typeof RAG_LIMIT_NAMES)[number];
export type RagLimits = Partial<Record<RagLimitName, number | null>>;
export interface RagCost {
  channel: string;
  model: string;
  event_type: string;
  events: number;
  measured_tokens: number;
  reserved_or_accounted_tokens: number;
  cost_usd: string;
  unmeasured_events: number;
}
export async function ragLimits(
  tenantId: string,
  botId: string,
): Promise<{
  limits: RagLimits;
  effective_limits: RagLimits;
  usage: Record<string, number>;
}> {
  return api(`tenants/${tenantId}/bots/${botId}/rag`);
}
export async function patchRagLimits(
  tenantId: string,
  botId: string,
  limits: RagLimits | null,
): Promise<void> {
  await api(`tenants/${tenantId}/bots/${botId}/rag`, {
    method: "PATCH",
    body: { limits },
  });
}
export async function ragCosts(
  tenantId: string,
  botId: string,
): Promise<RagCost[]> {
  const result = await api<{ costs: RagCost[] }>(
    `tenants/${tenantId}/bots/${botId}/rag/costs`,
  );
  return result.costs;
}

export async function playgroundConversation(
  tenantId: string,
  botId: string,
): Promise<PlaygroundConversation> {
  return api<PlaygroundConversation>(
    `tenants/${tenantId}/bots/${botId}/playground/conversation`,
  );
}

export async function messageFeedback(
  tenantId: string,
  botId: string,
  messageId: string,
  rating: "up" | "down",
): Promise<void> {
  await api<unknown>(
    `tenants/${tenantId}/bots/${botId}/messages/${messageId}/feedback`,
    { method: "POST", body: { rating } },
  );
}

export interface ChangeRequest {
  id: string;
  tenant_id: string;
  requester_id: string | null;
  type: "knowledge" | "text_change" | "domain" | "delete_org" | "other";
  text: string;
  attachments: { id: string; name: string; size_bytes: number }[];
  status: "pending" | "triaged" | "in_progress" | "completed" | "rejected";
  created_at: string;
  updated_at: string;
}

export function deletionPreview(
  tenantId: string,
): Promise<{ name: string; counts: Record<string, number> }> {
  return api(`tenants/${tenantId}/data/deletion-preview`);
}

export function listChangeRequests(
  tenantId?: string,
): Promise<ChangeRequest[]> {
  return api(
    tenantId
      ? `tenants/${tenantId}/change-requests`
      : "platform/change-requests",
  );
}

export function triageChangeRequest(
  id: string,
  status: ChangeRequest["status"],
): Promise<ChangeRequest> {
  return api(`platform/change-requests/${id}`, {
    method: "PATCH",
    body: { status },
  });
}

export async function createChangeRequest(
  tenantId: string,
  type: ChangeRequest["type"],
  text: string,
  files: File[],
): Promise<ChangeRequest> {
  const form = new FormData();
  form.set("type", type);
  form.set("text", text);
  for (const file of files) form.append("files", file);
  const response = await fetch(`/api/v1/tenants/${tenantId}/change-requests`, {
    method: "POST",
    headers: csrfHeader(),
    credentials: "same-origin",
    body: form,
  });
  const payload = await response.json();
  if (!response.ok)
    throw new ApiError(
      payload.error?.code ?? "REQUEST_FAILED",
      response.status,
      payload.error?.message ?? "Request could not be saved.",
    );
  return payload as ChangeRequest;
}

export function listAssignees(tenantId: string): Promise<Member[]> {
  return api(`tenants/${tenantId}/inbox/assignees`);
}
