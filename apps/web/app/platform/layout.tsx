import type { ReactNode } from "react";
import { requirePlatformStaff } from "@/lib/staff-access";
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

export default async function PlatformLayout({
  children,
}: {
  children: ReactNode;
}) {
  await requirePlatformStaff("/platform");
  return <AppShell platform>{children}</AppShell>;
}
