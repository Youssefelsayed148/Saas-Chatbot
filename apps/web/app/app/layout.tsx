"use client";

import { redirect, usePathname } from "next/navigation";

import { AppShell } from "@/lib/app-header";
import { useSession } from "@/lib/session";

export default function TenantAppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const { me, loading, error } = useSession();
  // /app/[tenant]/...
  const tenant =
    typeof pathname === "string" ? pathname.split("/")[2] : undefined;
  // Gate before mounting the shell or child pages, including direct URL visits.
  const segments = pathname.split("/").filter(Boolean);
  const operatorPage =
    segments[2] === "bots" &&
    (segments.length === 3 ||
      ["settings", "knowledge", "playground", "install"].includes(segments[4]));
  if (loading) return null;
  if (!me && !error) redirect("/login");
  if (me && !me.is_platform_staff && operatorPage) redirect(`/app/${tenant}`);
  return <AppShell tenantId={tenant || undefined}>{children}</AppShell>;
}
