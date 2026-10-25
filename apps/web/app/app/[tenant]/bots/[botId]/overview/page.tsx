"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import * as api from "@/lib/api";
import BotWorkspaceNav from "@/lib/bot-workspace-nav";
import { roleSatisfies, useSession } from "@/lib/session";
import {
  Button,
  Card,
  DataTable,
  Empty,
  Field,
  LinkButton,
  Loading,
  Notice,
  PageHeader,
} from "@/lib/ui";
import { Icon } from "@/lib/icons";

import "@/app/insights-screen.css";

/** Overview (P4-05, docs/14 §9 / docs/10): MEASURED numbers only — usage
 * events and real conversations; playground threads never count. Date range
 * + CSV exports. */

type Summary = {
  messages: number;
  conversations: number;
  widget_opens: number;
  engagement_rate: number;
  avg_messages_per_conversation: number;
  message_distribution: Record<string, number>;
  fallback_rate: number;
  cannot_answer: number;
  needs_human: number;
  handoffs: number;
  avg_response_ms: number;
  leads: number;
  thumbs_up: number;
  thumbs_down: number;
};

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
  const [summary, setSummary] = useState<Summary | null>(null);
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

  return (
    <main className="insights-page">
      <BotWorkspaceNav tenantId={tenantId} botId={botId} />
      <PageHeader
        title={<span data-testid="overview-title">Overview</span>}
        purpose="Measure conversations, answers and leads using stored activity."
      />
      <form
        aria-label="Date range"
        data-testid="overview-range"
        className="insights-range"
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
          <Card
            title="Summary"
            aria-label="Summary"
            data-testid="overview-summary"
          >
            <ul className="insights-stats">
              <li data-test="messages">
                Messages:{" "}
                <span className="stat-value insights-num" dir="ltr">
                  {summary.messages}
                </span>
              </li>
              <li data-test="conversations">
                Conversations:{" "}
                <span className="stat-value insights-num" dir="ltr">
                  {summary.conversations}
                </span>
              </li>
              <li data-test="widget_opens">
                Widget opens:{" "}
                <span className="stat-value insights-num" dir="ltr">
                  {summary.widget_opens}
                </span>
              </li>
              <li data-test="engagement">
                Engagement rate:{" "}
                <span className="stat-value insights-num" dir="ltr">
                  {summary.engagement_rate}
                </span>
              </li>
              <li data-test="avg_messages">
                Avg messages/conversation:{" "}
                <span className="stat-value insights-num" dir="ltr">
                  {summary.avg_messages_per_conversation}
                </span>
              </li>
              <li data-test="fallback">
                Unanswered rate:{" "}
                <span className="stat-value insights-num" dir="ltr">
                  {summary.fallback_rate}
                </span>
              </li>
              <li data-test="cannot_answer">
                Cannot answer:{" "}
                <span className="stat-value insights-num" dir="ltr">
                  {summary.cannot_answer}
                </span>
              </li>
              <li data-test="needs_human">
                Needs human:{" "}
                <span className="stat-value insights-num" dir="ltr">
                  {summary.needs_human}
                </span>
              </li>
              <li data-test="avg_response">
                Avg response:{" "}
                <span className="stat-value insights-num" dir="ltr">
                  {summary.avg_response_ms} ms
                </span>
              </li>
              <li data-test="leads_summary">
                Leads:{" "}
                <span className="stat-value insights-num" dir="ltr">
                  {summary.leads}
                </span>
              </li>
              <li data-test="thumbs">
                <span className="stat-value insights-num" dir="ltr">
                  <Icon name="thumbs-up" label="Thumbs up" />{" "}
                  {summary.thumbs_up} ·{" "}
                  <Icon name="thumbs-down" label="Thumbs down" />{" "}
                  {summary.thumbs_down}
                </span>
              </li>
              <li data-test="distribution" className="stat-wide">
                Distribution:{" "}
                <span className="stat-value insights-num" dir="ltr">
                  {Object.entries(summary.message_distribution)
                    .map(([bucket, count]) => `${bucket}: ${count}`)
                    .join(" · ")}
                </span>
              </li>
            </ul>
          </Card>

          <Card
            title="Volume per day"
            aria-label="Volume per day"
            data-testid="volume"
          >
            {(volume?.days.length ?? 0) === 0 ? (
              <Empty>No messages in this range.</Empty>
            ) : (
              <DataTable
                caption="Messages per day"
                rows={volume?.days ?? []}
                rowKey={(day) => day.day}
                columns={[
                  {
                    key: "day",
                    header: "Day",
                    cell: (day) => <bdi dir="ltr">{day.day}</bdi>,
                  },
                  {
                    key: "visitor",
                    header: "Visitor",
                    className: "insights-num",
                    cell: (day) => <bdi dir="ltr">{day.visitor}</bdi>,
                  },
                  {
                    key: "assistant",
                    header: "Assistant",
                    className: "insights-num",
                    cell: (day) => <bdi dir="ltr">{day.assistant}</bdi>,
                  },
                ]}
              />
            )}
          </Card>

          <Card
            title="Top questions"
            aria-label="Top questions"
            data-testid="top-questions"
          >
            {(topQuestions?.questions.length ?? 0) === 0 ? (
              <Empty>No visitor questions in this range.</Empty>
            ) : (
              <ol className="insights-list is-ranked">
                {(topQuestions?.questions ?? []).map((row) => (
                  <li key={row.question}>
                    <bdi dir="auto">{row.question}</bdi> — {row.asked}×
                  </li>
                ))}
              </ol>
            )}
          </Card>

          <Card
            title="Unanswered questions"
            aria-label="Unanswered questions"
            data-testid="unanswered"
          >
            {(unanswered?.questions.length ?? 0) === 0 ? (
              <Empty>Nothing went unanswered in this range.</Empty>
            ) : (
              <ul className="insights-list">
                {(unanswered?.questions ?? []).map((row) => (
                  <li key={row.question}>
                    <bdi dir="auto">{row.question}</bdi> — asked {row.asked}×
                    (last {row.last.slice(0, 10)})
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card title="Leads trend" aria-label="Leads" data-testid="leads">
            {(leads?.trend.length ?? 0) === 0 &&
            (leads?.contacts.length ?? 0) === 0 ? (
              <Empty>No leads captured in this range.</Empty>
            ) : (
              <>
                <ul className="insights-trend">
                  {(leads?.trend ?? []).map((row) => (
                    <li key={row.day}>
                      <bdi dir="ltr">
                        {row.day}: {row.leads}
                      </bdi>
                    </li>
                  ))}
                </ul>
                {(leads?.contacts.length ?? 0) > 0 && (
                  <DataTable
                    caption="Lead contacts"
                    rows={leads?.contacts ?? []}
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
              </>
            )}
          </Card>
        </>
      )}
    </main>
  );
}
