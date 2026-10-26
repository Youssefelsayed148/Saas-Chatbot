"use client";

import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import * as api from "@/lib/api";
import type { HandoffAnalytics } from "@/lib/api";
import {
  BarList,
  DonutChart,
  StackedBar,
  countDelta,
  durationDelta,
  formatCount,
  formatDuration,
  formatPercent,
  hasChartData,
  lastDaysRange,
  rateDelta,
} from "@/lib/charts";
import { humanLabel } from "@/lib/labels";
import { Card, Empty, Loading, Notice, PageHeader, StatCard } from "@/lib/ui";
import { useSession } from "@/lib/session";
import RagOperatorPanel from "@/lib/rag-operator-panel";

import "@/app/insights-screen.css";

const PERIODS = [7, 30, 90] as const;

function toItems(counts: Record<string, number> | undefined, label: boolean) {
  return Object.entries(counts ?? {})
    .map(([key, value]) => ({
      key,
      label: label ? humanLabel(key) : key,
      value: Number(value) || 0,
    }))
    .filter((item) => item.value > 0)
    .sort((a, b) => b.value - a.value);
}

export default function HandoffAnalyticsPage() {
  const { tenant: tenantId } = useParams<{ tenant: string }>();
  const { me } = useSession();
  const [days, setDays] = useState<number>(30);
  const [result, setResult] = useState<{
    days: number;
    data: HandoffAnalytics;
  } | null>(null);
  const [error, setError] = useState<{ days: number; message: string } | null>(
    null,
  );
  const range = useMemo(() => lastDaysRange(days), [days]);

  useEffect(() => {
    let cancelled = false;
    const timer = setTimeout(() => {
      api
        .handoffAnalytics(tenantId, range.from, range.to)
        .then((data) => {
          if (!cancelled) setResult({ days, data });
        })
        .catch((caught: unknown) => {
          if (cancelled) return;
          setError({
            days,
            message:
              caught instanceof Error
                ? caught.message
                : "Could not load analytics.",
          });
        });
    }, 0);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [tenantId, days, range]);

  const data = result?.days === days ? result.data : null;
  const failure = error?.days === days ? error.message : null;
  const total = data?.total_conversations ?? 0;
  const previous = data?.previous;
  const compare = `vs previous ${days} days`;

  const channels = toItems(data?.conversations_by_channel, true);
  const workload = toItems(data?.agent_workload, false);
  const sentiment = toItems(data?.sentiment_distribution, true);
  const resolved = data?.resolved_vs_open?.resolved ?? 0;
  const open = data?.resolved_vs_open?.open ?? 0;

  return (
    <main className="insights-page">
      <PageHeader
        title="Insights"
        purpose="Understand handoffs and your team’s response using measured activity."
      />
      <div className="insights-period">
        <div role="group" aria-label="Period" className="insights-period-group">
          {PERIODS.map((option) => (
            <button
              key={option}
              type="button"
              className="insights-period-btn"
              aria-pressed={days === option}
              onClick={() => setDays(option)}
            >
              {option} days
            </button>
          ))}
        </div>
        <span className="insights-period-range muted" dir="ltr">
          {range.from} – {range.to}
        </span>
      </div>
      <p className="insights-lede">
        Measured from website conversations created in the last {days} days.
      </p>
      {me?.is_platform_staff && <RagOperatorPanel tenantId={tenantId} />}
      {failure && <Notice tone="error" message={failure} />}
      {!data ? (
        failure ? null : (
          <Loading />
        )
      ) : total <= 0 ? (
        <Empty>No conversations in this period.</Empty>
      ) : (
        <div className="insights-grid">
          <Card title="Conversation outcomes" className="insights-wide">
            <div className="insights-kpis">
              <StatCard
                label="Conversations"
                value={formatCount(total)}
                delta={countDelta(total, previous?.total_conversations, {
                  label: compare,
                })}
              />
              <StatCard
                label="Handoffs"
                value={formatCount(data.handoff_count ?? 0)}
                delta={countDelta(data.handoff_count ?? 0, previous?.handoff_count, {
                  upIsGood: false,
                  label: compare,
                })}
              />
              <StatCard
                label="Handoff rate"
                value={formatPercent(data.handoff_rate)}
                delta={
                  data.handoff_rate == null
                    ? undefined
                    : rateDelta(data.handoff_rate, previous?.handoff_rate, {
                        upIsGood: false,
                        label: compare,
                      })
                }
              />
              <StatCard
                label="First human reply"
                value={formatDuration(data.average_first_human_reply_seconds)}
                delta={
                  data.average_first_human_reply_seconds == null
                    ? undefined
                    : durationDelta(
                        data.average_first_human_reply_seconds,
                        previous?.average_first_human_reply_seconds,
                        { upIsGood: false, label: compare },
                      )
                }
              />
            </div>
            {hasChartData([resolved, open]) && (
              <DonutChart
                label="Resolved and open conversations"
                slices={[
                  { key: "resolved", label: "Resolved", value: resolved },
                  { key: "open", label: "Open", value: open },
                ]}
                center={{ value: formatCount(total), caption: "Conversations" }}
              />
            )}
          </Card>
          {channels.length > 0 && (
            <Card title="Conversations by channel">
              <BarList
                label="Conversations by channel"
                items={channels}
                formatValue={formatCount}
              />
            </Card>
          )}
          {workload.length > 0 && (
            <Card title="Agent workload">
              <BarList
                label="Open assignments by team member"
                items={workload}
                formatValue={(n) => `${n}`}
              />
            </Card>
          )}
          {sentiment.length > 0 && (
            <Card title="Sentiment">
              <StackedBar
                label="Conversation sentiment"
                segments={sentiment}
                formatValue={formatCount}
              />
            </Card>
          )}
        </div>
      )}
    </main>
  );
}
