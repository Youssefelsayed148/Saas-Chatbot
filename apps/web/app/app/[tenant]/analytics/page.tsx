"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import * as api from "@/lib/api";
import type { HandoffAnalytics } from "@/lib/api";
import { Card, Empty, Loading, Notice, PageHeader } from "@/lib/ui";
import { useSession } from "@/lib/session";
import RagOperatorPanel from "@/lib/rag-operator-panel";

import "@/app/insights-screen.css";

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
    <main className="insights-page">
      <PageHeader
        title="Handoff analytics"
        purpose="Understand handoffs and your team’s response using measured activity."
      />
      <p className="insights-lede">
        Measured from website conversations created in the last 30 days.
      </p>
      {me?.is_platform_staff && <RagOperatorPanel tenantId={tenantId} />}
      {error && <Notice tone="error" message={error} />}
      {!data ? (
        error ? (
          <Empty>{error}</Empty>
        ) : (
          <Loading />
        )
      ) : (
        <div className="insights-grid">
          <Card title="Conversation outcomes" className="insights-wide">
            <div className="insights-kv">
              <div>
                Total:{" "}
                <span className="stat-value insights-num" dir="ltr">
                  {data.total_conversations}
                </span>
              </div>
              <div>
                Handoffs:{" "}
                <span className="stat-value insights-num" dir="ltr">
                  {data.handoff_count}
                </span>
              </div>
              <div>
                Handoff rate:{" "}
                <span className="stat-value insights-num" dir="ltr">
                  {data.handoff_rate === null
                    ? "No conversations"
                    : `${(data.handoff_rate * 100).toFixed(1)}%`}
                </span>
              </div>
              <div>
                First human reply:{" "}
                <span className="stat-value">
                  {duration(data.average_first_human_reply_seconds)}
                </span>
              </div>
              <div>
                Resolved / open:{" "}
                <span className="stat-value insights-num" dir="ltr">
                  {data.resolved_vs_open.resolved} /{" "}
                  {data.resolved_vs_open.open}
                </span>
              </div>
            </div>
          </Card>
          <Card title="Conversations by channel">
            {Object.keys(data.conversations_by_channel).length ? (
              <ul className="insights-rows">
                {Object.entries(data.conversations_by_channel).map(
                  ([channel, count]) => (
                    <li key={channel}>
                      <bdi>{channel}</bdi>: <bdi dir="ltr">{count}</bdi>
                    </li>
                  ),
                )}
              </ul>
            ) : (
              <Empty>No conversations recorded.</Empty>
            )}
          </Card>
          <Card title="Agent workload">
            {Object.keys(data.agent_workload).length ? (
              <ul className="insights-rows">
                {Object.entries(data.agent_workload).map(
                  ([memberName, count]) => (
                    <li key={memberName}>
                      <bdi dir="auto">{memberName}</bdi>:{" "}
                      <bdi dir="ltr">{count}</bdi> open assignments
                    </li>
                  ),
                )}
              </ul>
            ) : (
              <Empty>No active assignments recorded.</Empty>
            )}
          </Card>
          <Card title="Sentiment">
            {Object.keys(data.sentiment_distribution).length ? (
              <ul className="insights-rows">
                {Object.entries(data.sentiment_distribution).map(
                  ([sentiment, count]) => (
                    <li key={sentiment}>
                      <bdi>{sentiment}</bdi>: <bdi dir="ltr">{count}</bdi>
                    </li>
                  ),
                )}
              </ul>
            ) : (
              <Empty>Sentiment not measured yet.</Empty>
            )}
          </Card>
        </div>
      )}
    </main>
  );
}
