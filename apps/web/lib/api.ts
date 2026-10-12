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
  };
  created_at: string;
  updated_at: string;
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
  patch: { name?: string; config?: Record<string, unknown> },
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
