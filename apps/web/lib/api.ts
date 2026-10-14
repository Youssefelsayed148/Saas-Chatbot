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

export type Role = "owner" | "admin" | "editor" | "viewer";

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
  tenant: { id: string; name: string; slug: string; status: string };
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

export async function register(email: string, password: string): Promise<Me> {
  return api<Me>("auth/register", {
    method: "POST",
    body: { email, password },
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
