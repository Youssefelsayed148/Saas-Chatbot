"use client";

import { usePathname } from "next/navigation";

import { AppHeader } from "@/lib/app-header";

export default function TenantAppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  // /app/[tenant]/...
  const tenant =
    typeof pathname === "string" ? pathname.split("/")[2] : undefined;
  return (
    <>
      <AppHeader tenantId={tenant || undefined} />
      {children}
    </>
  );
}
