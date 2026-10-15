import { cookies, headers } from "next/headers";
import { redirect } from "next/navigation";
import type { ReactNode } from "react";
import { AppShell } from "@/lib/app-header";

/**
 * /platform layout (P4-06, docs/11): the guard runs SERVER-SIDE on every
 * request — it calls the platform API (the same-origin auth proxy) with the
 * caller's cookie jar and redirects unless the session user holds
 * is_platform_staff. There is no client-side shortcut and no impersonation
 * path (docs/06: the flag never acts as a tenant role).
 *
 * The /platform area stays OUT of the dashboard chrome on purpose: staff
 * navigation is separate (docs/11).
 */

const PLATFORM_API = "/api/v1/platform/me";

export default async function PlatformLayout({
  children,
}: {
  children: ReactNode;
}) {
  const jar = (await cookies()).toString();
  const headerList = await headers();
  const host = headerList.get("host") ?? "127.0.0.1:3000";
  const forwardedProto = headerList.get("x-forwarded-proto") ?? "http";
  // Server Components cannot fetch relative URLs; build the caller's origin.
  const origin =
    process.env.PLATFORM_GUARD_ORIGIN ?? `${forwardedProto}://${host}`;
  // Self-fetch deadlock/redirect origins are avoided when the deployment sets
  // PLATFORM_GUARD_ORIGIN (e.g. http://127.0.0.1:8000 pointing at the API process).
  let ok = false;
  let reason = "status-unknown";
  try {
    const response = await fetch(`${origin}${PLATFORM_API}`, {
      headers: { cookie: jar },
      cache: "no-store",
    });
    reason = `status-${response.status}`;
    ok = response.ok;
  } catch (caught) {
    reason = caught instanceof Error ? `throw-${caught.name}` : "throw-unknown";
    ok = false;
  }
  if (!ok) {
    // The failure mode is surfaced in the redirect target for diagnosis;
    // the /platform console stays unrendered either way.
    redirect(`/login?next=/platform&guard=${reason}`);
  }
  return <AppShell platform>{children}</AppShell>;
}
