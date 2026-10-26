import { redirect } from "next/navigation";

/**
 * ADR-021 / ADR-022: registration is closed in the UI. Accounts are created by
 * platform staff, so /register only forwards to /login. A same-origin relative
 * `next` (for example an /accept-invite link) is preserved.
 */
export default async function RegisterPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string | string[] }>;
}) {
  const params = await searchParams;
  const raw = Array.isArray(params.next) ? params.next[0] : params.next;
  const safe =
    typeof raw === "string" &&
    raw.startsWith("/") &&
    !raw.startsWith("//") &&
    !raw.includes("\\");
  redirect(safe ? `/login?next=${encodeURIComponent(raw)}` : "/login");
}
