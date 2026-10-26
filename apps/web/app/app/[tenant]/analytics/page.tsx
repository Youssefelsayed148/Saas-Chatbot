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
import {
  Card,
  DataTable,
  Empty,
  Loading,
  Notice,
  PageHeader,
  StatCard,
} from "@/lib/ui";
import { channelOptions, sortedCampaigns } from "@/lib/insights";
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
  const [channel, setChannel] = useState("");
  const [result, setResult] = useState<{
    days: number;
    channel: string;
    data: HandoffAnalytics;
  } | null>(null);
  const [error, setError] = useState<{
    days: number;
    channel: string;
    message: string;
  } | null>(null);
  const range = useMemo(() => lastDaysRange(days), [days]);

  useEffect(() => {
    let cancelled = false;
    const timer = setTimeout(() => {
      api
        .handoffAnalytics(tenantId, range.from, range.to, channel || undefined)
        .then((data) => {
          if (!cancelled) setResult({ days, channel, data });
        })
        .catch((caught: unknown) => {
          if (cancelled) return;
          setError({
            days,
            channel,
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
  }, [tenantId, days, range, channel]);

  const data =
    result?.days === days && result.channel === channel ? result.data : null;
  const failure =
    error?.days === days && error.channel === channel ? error.message : null;
  const total = data?.total_conversations ?? 0;
  const previous = data?.previous;
  const compare = `vs previous ${days} days`;

  const channels = toItems(data?.conversations_by_channel, true);
  const breakdown = (data?.channel_breakdown ?? []).filter(
    (row) => row.conversations > 0,
  );
  const campaigns = sortedCampaigns(data?.conversations_by_campaign ?? {});
  const hasMessagingChannels = breakdown.some(
    (row) => row.channel !== "website",
  );
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
        <label className="insights-channel-filter">
          <span>Channel</span>
          <select
            data-testid="insights-channel-filter"
            value={channel}
            onChange={(event) => setChannel(event.target.value)}
          >
            {channelOptions().map((option) => (
              <option key={option.value} value={option.value}>
                {option.value === "" ? "All channels" : option.label}
              </option>
            ))}
          </select>
        </label>
        <span className="insights-period-range muted" dir="ltr">
          {range.from} – {range.to}
        </span>
      </div>
      <p className="insights-lede">
        Measured from conversations created in the last {days} days
        {channel ? ` on ${humanLabel(channel)}` : ""}.
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
                delta={countDelta(
                  data.handoff_count ?? 0,
                  previous?.handoff_count,
                  {
                    upIsGood: false,
                    label: compare,
                  },
                )}
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
          {hasMessagingChannels && (
            <Card
              title="Channel performance"
              className="insights-wide"
              data-testid="channel-performance"
            >
              <DataTable
                data-testid="insights-channel-table"
                caption="Channel performance"
                rows={breakdown}
                rowKey={(row) => row.channel}
                columns={[
                  {
                    key: "channel",
                    header: "Channel",
                    cell: (row) => humanLabel(row.channel),
                  },
                  {
                    key: "conversations",
                    header: "Conversations",
                    className: "num",
                    cell: (row) => formatCount(row.conversations),
                  },
                  {
                    key: "handoff",
                    header: "Handoff rate",
                    className: "num",
                    cell: (row) => formatPercent(row.handoff_rate),
                  },
                  {
                    key: "unanswered",
                    header: "Unanswered",
                    className: "num",
                    cell: (row) => formatCount(row.unanswered_questions),
                  },
                  {
                    key: "response",
                    header: "First response",
                    className: "num",
                    cell: (row) =>
                      formatDuration(row.median_first_response_seconds),
                  },
                  {
                    key: "resolved",
                    header: "Resolved",
                    className: "num",
                    cell: (row) => formatPercent(row.resolved_rate),
                  },
                ]}
              />
            </Card>
          )}
          {campaigns.length > 0 && (
            <Card
              title="Conversations by campaign"
              data-testid="insights-campaign-list"
            >
              <BarList
                label="Conversations by campaign"
                items={campaigns.map((row) => ({
                  key: row.campaign,
                  label: row.campaign,
                  value: row.conversations,
                }))}
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
