"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import * as api from "@/lib/api";
import type { HandoffAnalytics } from "@/lib/api";
import { Empty, Loading, Notice } from "@/lib/ui";

function duration(seconds: number | null): string {
  if (seconds === null) return "No replies recorded";
  if (seconds < 60) return `${Math.round(seconds)} seconds`;
  if (seconds < 3600) return `${Math.round(seconds / 60)} minutes`;
  return `${(seconds / 3600).toFixed(1)} hours`;
}

export default function HandoffAnalyticsPage() {
  const { tenant: tenantId } = useParams<{ tenant: string }>();
  const [data, setData] = useState<HandoffAnalytics | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    try {
      setData(await api.handoffAnalytics(tenantId));
      setError(null);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Could not load analytics.",
      );
    }
  }, [tenantId]);
  useEffect(() => {
    const timer = setTimeout(() => void load(), 0);
    return () => clearTimeout(timer);
  }, [load]);

  return (
    <main className="handoff-analytics">
      <h1>Handoff analytics</h1>
      <p className="page-purpose">
        Understand handoffs and your team’s response using measured activity.
      </p>
      <p>Measured from website conversations created in the last 30 days.</p>
      {error && <Notice tone="error" message={error} />}
      {!data ? (
        error ? (
          <Empty>{error}</Empty>
        ) : (
          <Loading />
        )
      ) : (
        <>
          <section className="card">
            <h2>Conversation outcomes</h2>
            <p>Total: {data.total_conversations}</p>
            <p>Handoffs: {data.handoff_count}</p>
            <p>
              Handoff rate:{" "}
              {data.handoff_rate === null
                ? "No conversations"
                : `${(data.handoff_rate * 100).toFixed(1)}%`}
            </p>
            <p>
              First human reply:{" "}
              {duration(data.average_first_human_reply_seconds)}
            </p>
            <p>
              Resolved: {data.resolved_vs_open.resolved} · Open:{" "}
              {data.resolved_vs_open.open}
            </p>
          </section>
          <section className="card">
            <h2>Conversations by channel</h2>
            {Object.keys(data.conversations_by_channel).length ? (
              <ul>
                {Object.entries(data.conversations_by_channel).map(
                  ([channel, count]) => (
                    <li key={channel}>
                      {channel}: {count}
                    </li>
                  ),
                )}
              </ul>
            ) : (
              <Empty>No conversations recorded.</Empty>
            )}
          </section>
          <section className="card">
            <h2>Agent workload</h2>
            {Object.keys(data.agent_workload).length ? (
              <ul>
                {Object.entries(data.agent_workload).map(([userId, count]) => (
                  <li key={userId}>
                    {userId}: {count} open assignments
                  </li>
                ))}
              </ul>
            ) : (
              <Empty>No active assignments recorded.</Empty>
            )}
          </section>
          <section className="card">
            <h2>Sentiment</h2>
            {Object.keys(data.sentiment_distribution).length ? (
              <ul>
                {Object.entries(data.sentiment_distribution).map(
                  ([sentiment, count]) => (
                    <li key={sentiment}>
                      {sentiment}: {count}
                    </li>
                  ),
                )}
              </ul>
            ) : (
              <Empty>Sentiment not measured yet.</Empty>
            )}
          </section>
        </>
      )}
    </main>
  );
}
