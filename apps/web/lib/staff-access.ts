import "server-only";
import { cookies, headers } from "next/headers";
import { redirect } from "next/navigation";

/** Fail closed on the server; a tenant admin role never grants staff access. */
export async function requirePlatformStaff(nextPath: string): Promise<void> {
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
    const response = await fetch(`${origin}/api/v1/platform/me`, {
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
    redirect(`/login?next=${encodeURIComponent(nextPath)}&guard=${reason}`);
  }
}
