"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import * as api from "@/lib/api";
import BotWorkspaceNav from "@/lib/bot-workspace-nav";
import {
  BarList,
  TrendChart,
  formatCount,
  formatDay,
  formatMsAsSeconds,
  formatPercent,
  hasChartData,
} from "@/lib/charts";
import { roleSatisfies, useSession } from "@/lib/session";
import {
  Button,
  Card,
  DataTable,
  Field,
  LinkButton,
  Loading,
  Notice,
  PageHeader,
  StatCard,
} from "@/lib/ui";
import { Icon } from "@/lib/icons";

import "@/app/insights-screen.css";
import "@/app/bot-overview-screen.css";

/** Overview (P4-05, docs/14 §9 / docs/10): MEASURED numbers only — usage
 * events and real conversations; playground threads never count. Date range
 * + CSV exports. */

function isoDaysAgo(days: number): string {
  const time = new Date();
  time.setDate(time.getDate() - days);
  return time.toISOString().slice(0, 10);
}

export default function OverviewPage() {
  const params = useParams<{ tenant: string; botId: string }>();
  const tenantId = params.tenant;
  const botId = params.botId;
  const { roleIn } = useSession();
  const role = roleIn(tenantId);

  const [from, setFrom] = useState(isoDaysAgo(29));
  const [to, setTo] = useState(isoDaysAgo(0));
  const [summary, setSummary] = useState<api.AnalyticsSummaryResponse | null>(
    null,
  );
  const [volume, setVolume] = useState<api.AnalyticsVolumeResponse | null>(
    null,
  );
  const [topQuestions, setTopQuestions] =
    useState<api.AnalyticsTopQuestionsResponse | null>(null);
  const [unanswered, setUnanswered] =
    useState<api.AnalyticsUnansweredResponse | null>(null);
  const [leads, setLeads] = useState<api.AnalyticsLeadsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [applied, setApplied] = useState({
    from: isoDaysAgo(29),
    to: isoDaysAgo(0),
  });

  useEffect(() => {
    const timer = setTimeout(() => {
      void (async () => {
        setLoading(true);
        try {
          const [s, v, t, u, l] = await Promise.all([
            api.analyticsSummary(tenantId, botId, applied.from, applied.to),
            api.analyticsVolume(tenantId, botId, applied.from, applied.to),
            api.analyticsTopQuestions(
              tenantId,
              botId,
              applied.from,
              applied.to,
            ),
            api.analyticsUnanswered(tenantId, botId, applied.from, applied.to),
            api.analyticsLeads(tenantId, botId, applied.from, applied.to),
          ]);
          setSummary(s);
          setVolume(v);
          setTopQuestions(t);
          setUnanswered(u);
          setLeads(l);
          setError(null);
        } catch (caught) {
          setError(
            caught instanceof Error
              ? caught.message
              : "Could not load analytics.",
          );
        } finally {
          setLoading(false);
        }
      })();
    }, 0);
    return () => clearTimeout(timer);
  }, [tenantId, botId, applied]);

  const csvSuffix = `?from=${encodeURIComponent(applied.from)}&to=${encodeURIComponent(applied.to)}`;

  const canAdjust = roleSatisfies(role, "viewer");

  const volumeDays = volume?.days ?? [];
  const showVolume = hasChartData(
    volumeDays.flatMap((day) => [day.visitor, day.assistant]),
  );
  const distribution = Object.entries(summary?.message_distribution ?? {});
  const showDistribution = hasChartData(distribution.map(([, count]) => count));
  const topRows = topQuestions?.questions ?? [];
  const unansweredRows = unanswered?.questions ?? [];
  const leadTrend = leads?.trend ?? [];
  const leadContacts = leads?.contacts ?? [];
  const showLeadTrend = hasChartData(leadTrend.map((row) => row.leads));

  const thumbsUp = summary?.thumbs_up ?? 0;
  const thumbsDown = summary?.thumbs_down ?? 0;

  return (
    <main className="insights-page overview-page">
      <BotWorkspaceNav tenantId={tenantId} botId={botId} />
      <PageHeader
        title={<span data-testid="overview-title">Overview</span>}
        purpose="Measure conversations, answers and leads using stored activity."
      />
      <form
        aria-label="Date range"
        data-testid="overview-range"
        className="insights-range overview-range"
        onSubmit={(event) => {
          event.preventDefault();
          setApplied({ from, to });
        }}
      >
        <Field label="From">
          {(control) => (
            <input
              {...control}
              type="date"
              dir="ltr"
              data-testid="range-from"
              value={from}
              disabled={!role || !canAdjust}
              onChange={(event) => setFrom(event.target.value)}
            />
          )}
        </Field>
        <Field label="To">
          {(control) => (
            <input
              {...control}
              type="date"
              dir="ltr"
              data-testid="range-to"
              value={to}
              disabled={!role || !canAdjust}
              onChange={(event) => setTo(event.target.value)}
            />
          )}
        </Field>
        <div className="insights-range-actions">
          <Button type="submit" data-testid="range-apply">
            Apply
          </Button>
          {roleSatisfies(role, "admin") && (
            <>
              <LinkButton
                variant="secondary"
                className="insights-export"
                href={`/api/v1/tenants/${tenantId}/bots/${botId}/analytics/conversations.csv${csvSuffix}`}
                data-testid="export-conversations"
              >
                Export conversations CSV
              </LinkButton>
              <LinkButton
                variant="secondary"
                className="insights-export"
                href={`/api/v1/tenants/${tenantId}/bots/${botId}/analytics/leads.csv${csvSuffix}`}
                data-testid="export-leads"
              >
                Export leads CSV
              </LinkButton>
            </>
          )}
        </div>
      </form>
      {error && <Notice message={error} tone="error" />}
      {loading && <Loading label="Loading measured numbers…" />}
      {!loading && summary && (
        <>
          <div
            className="overview-kpis"
            aria-label="Summary"
            role="group"
            data-testid="overview-summary"
          >
            <StatCard
              data-test="messages"
              label="Messages"
              value={formatCount(summary.messages ?? 0)}
            />
            <StatCard
              data-test="conversations"
              label="Conversations"
              value={formatCount(summary.conversations ?? 0)}
            />
            <StatCard
              data-test="widget_opens"
              label="Widget opens"
              value={formatCount(summary.widget_opens ?? 0)}
            />
            <StatCard
              data-test="engagement"
              label="Engagement rate"
              value={formatPercent(summary.engagement_rate ?? 0)}
            />
            <StatCard
              data-test="avg_messages"
              label="Avg messages per conversation"
              value={String(Math.round((summary.avg_messages_per_conversation ?? 0) * 10) / 10)}
            />
            <StatCard
              data-test="fallback"
              label="Unanswered rate"
              value={formatPercent(summary.fallback_rate ?? 0)}
            />
            <StatCard
              data-test="cannot_answer"
              label="Cannot answer"
              value={formatCount(summary.cannot_answer ?? 0)}
            />
            <StatCard
              data-test="needs_human"
              label="Needs a person"
              value={formatCount(summary.needs_human ?? 0)}
            />
            <StatCard
              data-test="avg_response"
              label="Avg response"
              value={formatMsAsSeconds(summary.avg_response_ms ?? 0)}
            />
            <StatCard
              data-test="leads_summary"
              label="Leads"
              value={formatCount(summary.leads ?? 0)}
            />
            {(thumbsUp > 0 || thumbsDown > 0) && (
              <StatCard
                data-test="thumbs"
                label="Feedback"
                value={
                  <span className="overview-thumbs" dir="ltr">
                    <span>
                      <Icon name="thumbs-up" label="Thumbs up" />{" "}
                      {formatCount(thumbsUp)}
                    </span>
                    <span>
                      <Icon name="thumbs-down" label="Thumbs down" />{" "}
                      {formatCount(thumbsDown)}
                    </span>
                  </span>
                }
              />
            )}
          </div>

          {showVolume && (
            <Card
              title="Volume per day"
              aria-label="Volume per day"
              data-testid="volume"
            >
              <TrendChart
                label="Messages per day"
                data={volumeDays}
                xKey="day"
                variant="area"
                series={[
                  { key: "visitor", label: "Visitor messages" },
                  { key: "assistant", label: "Assistant messages" },
                ]}
              />
            </Card>
          )}

          <div className="overview-grid">
            {showDistribution && (
              <Card title="Reply length" aria-label="Reply length">
                <BarList
                  label="Replies by length"
                  items={distribution.map(([bucket, count]) => ({
                    key: bucket,
                    label: bucket,
                    value: count,
                  }))}
                  formatValue={formatCount}
                />
              </Card>
            )}

            {topRows.length > 0 && (
              <Card
                title="Top questions"
                aria-label="Top questions"
                data-testid="top-questions"
              >
                <BarList
                  label="Most asked questions"
                  ranked
                  items={topRows.map((row) => ({
                    key: row.question,
                    label: row.question,
                    value: row.asked,
                  }))}
                  formatValue={(count) => `${formatCount(count)}×`}
                />
              </Card>
            )}

            {unansweredRows.length > 0 && (
              <Card
                title="Unanswered questions"
                aria-label="Unanswered questions"
                data-testid="unanswered"
              >
                <BarList
                  label="Unanswered questions"
                  items={unansweredRows.map((row) => ({
                    key: row.question,
                    label: row.question,
                    value: row.asked,
                    hint: row.last
                      ? `last asked ${formatDay(row.last.slice(0, 10))}`
                      : undefined,
                  }))}
                  formatValue={(count) => `${formatCount(count)}×`}
                />
              </Card>
            )}
          </div>

          {(showLeadTrend || leadContacts.length > 0) && (
            <Card title="Leads" aria-label="Leads" data-testid="leads">
              {showLeadTrend && (
                <TrendChart
                  label="Leads per day"
                  data={leadTrend}
                  xKey="day"
                  variant="area"
                  height={140}
                  series={[{ key: "leads", label: "Leads" }]}
                />
              )}
              {leadContacts.length > 0 && (
                <DataTable
                  caption="Lead contacts"
                  rows={leadContacts}
                  rowKey={(row) => row.contact_id}
                  columns={[
                    {
                      key: "name",
                      header: "Name",
                      cell: (row) => (
                        <bdi dir="auto">{row.display_name || "—"}</bdi>
                      ),
                    },
                    {
                      key: "email",
                      header: "Email",
                      cell: (row) => <bdi dir="ltr">{row.email ?? "—"}</bdi>,
                    },
                    {
                      key: "phone",
                      header: "Phone",
                      cell: (row) => <bdi dir="ltr">{row.phone ?? "—"}</bdi>,
                    },
                    {
                      key: "conversations",
                      header: "Conversations",
                      className: "insights-num",
                      cell: (row) => <bdi dir="ltr">{row.conversations}</bdi>,
                    },
                  ]}
                />
              )}
            </Card>
          )}
        </>
      )}
    </main>
  );
}
