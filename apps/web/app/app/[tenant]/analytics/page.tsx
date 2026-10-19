"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { channelOptions, formatMedian, formatRate, sortedCampaigns } from "@/lib/insights";
import { humanChannel } from "@/lib/insights";
import * as api from "@/lib/api";
import type { HandoffAnalytics } from "@/lib/api";
import { Empty, Loading, Notice } from "@/lib/ui";
import { useSession } from "@/lib/session";
import RagOperatorPanel from "@/lib/rag-operator-panel";

function duration(seconds: number | null): string {
  if (seconds === null) return "No replies recorded";
  if (seconds < 60) {
    const rounded = Math.round(seconds);
    return `${rounded} ${rounded === 1 ? "second" : "seconds"}`;
  }
  if (seconds < 3600) return `${Math.round(seconds / 60)} minutes`;
  return `${(seconds / 3600).toFixed(1)} hours`;
}

export default function HandoffAnalyticsPage() {
  const { tenant: tenantId } = useParams<{ tenant: string }>();
  const { me } = useSession();
  const [data, setData] = useState<HandoffAnalytics | null>(null);
  const [channel, setChannel] = useState("");
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    try {
      setData(
        await api.handoffAnalytics(tenantId, {
          channel: channel || undefined,
        }),
      );
      setError(null);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Could not load analytics.",
      );
    }
  }, [channel, tenantId]);
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
      <p>Measured from conversations created in the last 30 days.</p>
      <section aria-label="Insights filter" className="filter-toolbar">
        <label>
          Channel{" "}
          <select
            aria-label="Filter insights by channel"
            data-testid="insights-channel-filter"
            value={channel}
            onChange={(e) => setChannel(e.target.value)}
          >
            {channelOptions().map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
      </section>
      {me?.is_platform_staff && <RagOperatorPanel tenantId={tenantId} />}
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
          <section className="card" data-testid="insights-channel-breakdown">
            <h2>Channels</h2>
            <p>
              Per-channel outcomes (handoff = human mode or waiting for a
              human; unanswered = assistant replies that could not answer).
            </p>
            {data.channel_breakdown?.length ? (
              <table data-testid="insights-channel-table">
                <thead>
                  <tr>
                    <th>Channel</th>
                    <th>Conversations</th>
                    <th>Handoff rate</th>
                    <th>Unanswered</th>
                    <th>Median first response</th>
                    <th>Resolved rate</th>
                  </tr>
                </thead>
                <tbody>
                  {data.channel_breakdown.map((row) => (
                    <tr key={row.channel} data-testid={`insights-row-${row.channel}`}>
                      <td>{humanChannel(row.channel)}</td>
                      <td>{row.conversations}</td>
                      <td>{formatRate(row.handoff_rate)}</td>
                      <td>{row.unanswered_questions}</td>
                      <td>{formatMedian(row.median_first_response_seconds)}</td>
                      <td>{formatRate(row.resolved_rate)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <Empty>No conversations recorded.</Empty>
            )}
          </section>
          <section className="card">
            <h2>Conversations by campaign</h2>
            {data.conversations_by_campaign &&
            Object.keys(data.conversations_by_campaign).length ? (
              <ul data-testid="insights-campaign-list">
                {sortedCampaigns(data.conversations_by_campaign).map((row) => (
                  <li key={row.campaign}>
                    {row.campaign}: {row.conversations}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="muted">No campaign conversations recorded.</p>
            )}
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
                {Object.entries(data.agent_workload).map(
                  ([memberName, count]) => (
                    <li key={memberName}>
                      {memberName}: {count} open assignments
                    </li>
                  ),
                )}
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
