"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import * as api from "@/lib/api";
import BotWorkspaceNav from "@/lib/bot-workspace-nav";
import { roleSatisfies, useSession } from "@/lib/session";
import { Empty, Loading, Notice } from "@/lib/ui";
import { Icon } from "@/lib/icons";

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
    <main>
      <BotWorkspaceNav tenantId={tenantId} botId={botId} />
      <h1 data-testid="overview-title">Overview</h1>
      <p className="page-purpose">
        Measure conversations, answers and leads using stored activity.
      </p>
      <form
        aria-label="Date range"
        data-testid="overview-range"
        onSubmit={(event) => {
          event.preventDefault();
          setApplied({ from, to });
        }}
      >
        <label>
          From
          <input
            type="date"
            data-testid="range-from"
            value={from}
            disabled={!role || !canAdjust}
            onChange={(event) => setFrom(event.target.value)}
          />
        </label>
        <label>
          To
          <input
            type="date"
            data-testid="range-to"
            value={to}
            disabled={!role || !canAdjust}
            onChange={(event) => setTo(event.target.value)}
          />
        </label>
        <button type="submit" data-testid="range-apply">
          Apply
        </button>
        {roleSatisfies(role, "admin") && (
          <>
            <a
              href={`/api/v1/tenants/${tenantId}/bots/${botId}/analytics/conversations.csv${csvSuffix}`}
              data-testid="export-conversations"
            >
              Export conversations CSV
            </a>
            <a
              href={`/api/v1/tenants/${tenantId}/bots/${botId}/analytics/leads.csv${csvSuffix}`}
              data-testid="export-leads"
            >
              Export leads CSV
            </a>
          </>
        )}
      </form>
      {error && <Notice message={error} tone="error" />}
      {loading && <Loading label="Loading measured numbers…" />}
      {!loading && summary && (
        <>
          <section aria-label="Summary" data-testid="overview-summary">
            <ul>
              <li data-test="messages">Messages: {summary.messages}</li>
              <li data-test="conversations">
                Conversations: {summary.conversations}
              </li>
              <li data-test="widget_opens">
                Widget opens: {summary.widget_opens}
              </li>
              <li data-test="engagement">
                Engagement rate: {summary.engagement_rate}
              </li>
              <li data-test="avg_messages">
                Avg messages/conversation:{" "}
                {summary.avg_messages_per_conversation}
              </li>
              <li data-test="distribution">
                Distribution:{" "}
                {Object.entries(summary.message_distribution)
                  .map(([bucket, count]) => `${bucket}: ${count}`)
                  .join(" · ")}
              </li>
              <li data-test="fallback">
                Unanswered rate: {summary.fallback_rate}
              </li>
              <li data-test="cannot_answer">
                Cannot answer: {summary.cannot_answer}
              </li>
              <li data-test="needs_human">
                Needs human: {summary.needs_human}
              </li>
              <li data-test="avg_response">
                Avg response: {summary.avg_response_ms} ms
              </li>
              <li data-test="leads_summary">Leads: {summary.leads}</li>
              <li data-test="thumbs">
                <Icon name="thumbs-up" label="Thumbs up" /> {summary.thumbs_up}{" "}
                · <Icon name="thumbs-down" label="Thumbs down" />{" "}
                {summary.thumbs_down}
              </li>
            </ul>
          </section>

          <section aria-label="Volume per day" data-testid="volume">
            <h2>Volume per day</h2>
            {(volume?.days.length ?? 0) === 0 ? (
              <Empty>No messages in this range.</Empty>
            ) : (
              <table>
                <thead>
                  <tr>
                    <th>Day</th>
                    <th>Visitor</th>
                    <th>Assistant</th>
                  </tr>
                </thead>
                <tbody>
                  {(volume?.days ?? []).map((day) => (
                    <tr key={day.day}>
                      <td>{day.day}</td>
                      <td>{day.visitor}</td>
                      <td>{day.assistant}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>

          <section aria-label="Top questions" data-testid="top-questions">
            <h2>Top questions</h2>
            {(topQuestions?.questions.length ?? 0) === 0 ? (
              <Empty>No visitor questions in this range.</Empty>
            ) : (
              <ol>
                {(topQuestions?.questions ?? []).map((row) => (
                  <li key={row.question}>
                    {row.question} — {row.asked}×
                  </li>
                ))}
              </ol>
            )}
          </section>

          <section aria-label="Unanswered questions" data-testid="unanswered">
            <h2>Unanswered questions</h2>
            {(unanswered?.questions.length ?? 0) === 0 ? (
              <Empty>Nothing went unanswered in this range.</Empty>
            ) : (
              <ul>
                {(unanswered?.questions ?? []).map((row) => (
                  <li key={row.question}>
                    {row.question} — asked {row.asked}× (last{" "}
                    {row.last.slice(0, 10)})
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section aria-label="Leads" data-testid="leads">
            <h2>Leads trend</h2>
            {(leads?.trend.length ?? 0) === 0 &&
            (leads?.contacts.length ?? 0) === 0 ? (
              <Empty>No leads captured in this range.</Empty>
            ) : (
              <>
                <ul>
                  {(leads?.trend ?? []).map((row) => (
                    <li key={row.day}>
                      {row.day}: {row.leads}
                    </li>
                  ))}
                </ul>
                {(leads?.contacts.length ?? 0) > 0 && (
                  <table>
                    <thead>
                      <tr>
                        <th>Name</th>
                        <th>Email</th>
                        <th>Phone</th>
                        <th>Conversations</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(leads?.contacts ?? []).map((row) => (
                        <tr key={row.contact_id}>
                          <td>{row.display_name || "—"}</td>
                          <td>{row.email ?? "—"}</td>
                          <td>{row.phone ?? "—"}</td>
                          <td>{row.conversations}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </>
            )}
          </section>
        </>
      )}
    </main>
  );
}
