"use client";

import { useParams } from "next/navigation";
import { ChangeRequests } from "@/lib/change-requests";

export default function RequestsPage() {
  const { tenant } = useParams<{ tenant: string }>();
  return <ChangeRequests tenantId={tenant} />;
}
