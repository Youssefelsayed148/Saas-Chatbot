"use client";

import { redirect, useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import * as api from "@/lib/api";
import { Empty, Loading, Notice } from "@/lib/ui";

/** Fallback while the sidebar resolves the organization's default conversation list. */
export default function ConversationsLanding() {
  const { tenant } = useParams<{ tenant: string }>();
  const [bots, setBots] = useState<api.Bot[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    try {
      setBots(await api.listBots(tenant, false));
      setError(null);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Could not load conversations.",
      );
    }
  }, [tenant]);
  useEffect(() => {
    const timer = setTimeout(() => void load(), 0);
    return () => clearTimeout(timer);
  }, [load]);
  if (bots?.[0]) redirect(`/app/${tenant}/bots/${bots[0].id}/conversations`);
  return (
    <main>
      <h1>Conversations</h1>
      {error ? (
        <Notice message={error} tone="error" onRetry={() => void load()} />
      ) : bots ? (
        <Empty>No conversations available yet.</Empty>
      ) : (
        <Loading label="Loading conversations..." />
      )}
    </main>
  );
}
