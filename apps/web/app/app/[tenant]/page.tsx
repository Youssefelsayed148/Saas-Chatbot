"use client";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import "@/app/overview-screen.css";
import {
  DonutChart,
  TrendChart,
  countDelta,
  formatCount,
  formatPercent,
  formatRelativeTime,
  hasChartData,
  lastDaysRange,
  rateDelta,
} from "@/lib/charts";
import { humanLabel } from "@/lib/labels";
import * as api from "@/lib/api";
import { useSession } from "@/lib/session";
import {
  Card,
  Empty,
  LinkButton,
  Loading,
  Meter,
  Notice,
  PageHeader,
  StatCard,
  StatusBadge,
} from "@/lib/ui";
import { Icon } from "@/lib/icons";

type Extras = {
  days: api.ConversationTimeseriesDay[];
  analytics: api.HandoffAnalytics | null;
  modelAlert: string | null;
};

const EMPTY_EXTRAS: Extras = { days: [], analytics: null, modelAlert: null };
const PREVIOUS_LABEL = "vs previous 30 days";

export default function TenantOverview() {
  const { tenant } = useParams<{ tenant: string }>();
  const { me, loading } = useSession();
  const canReadKnowledge = !!me?.is_platform_staff;
  const router = useRouter();
  const [data, setData] = useState<{
    counts: api.InboxCounts;
    bots: api.Bot[];
    quota: api.TenantQuotaStatus;
    recent: api.InboxResponse;
    published: boolean | null;
  } | null>(null);
  const [extras, setExtras] = useState<Extras>(EMPTY_EXTRAS);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    try {
      const [counts, bots, quota, recent] = await Promise.all([
        api.inboxCounts(tenant),
        api.listBots(tenant, false),
        api.tenantQuota(tenant),
        api.listInbox(tenant, { limit: "5" }),
      ]);
      // The checklist refers to the first current bot only; no per-bot request fan-out.
      const revisions =
        bots[0] && canReadKnowledge
          ? await api.listRevisions(tenant, bots[0].id)
          : null;
      setData({
        counts,
        bots,
        quota,
        recent,
        published: revisions ? Boolean(revisions.published_revision_id) : null,
      });
      setError(null);
      // Charts and the health alert are optional: a failure leaves them out.
      const { from, to } = lastDaysRange(30);
      const firstBot = bots[0];
      const [series, analytics, readiness] = await Promise.allSettled([
        api.conversationTimeseries(tenant, from, to),
        api.handoffAnalytics(tenant, from, to),
        canReadKnowledge && firstBot
          ? api.getBotReadiness(tenant, firstBot.id)
          : Promise.resolve(null),
      ]);
      const days =
        series.status === "fulfilled" && Array.isArray(series.value?.days)
          ? series.value.days
          : [];
      const stats =
        analytics.status === "fulfilled" &&
        analytics.value &&
        typeof analytics.value.total_conversations === "number"
          ? analytics.value
          : null;
      const model =
        readiness.status === "fulfilled" &&
        Array.isArray(readiness.value?.items)
          ? readiness.value.items.find((item) => item.id === "model_reachable")
          : undefined;
      setExtras({
        days,
        analytics: stats,
        modelAlert: model && model.status !== "ok" ? model.detail : null,
      });
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Could not load overview.",
      );
    }
  }, [tenant, canReadKnowledge]);
  useEffect(() => {
    if (!loading && !me) router.replace("/login");
    if (!me) return;
    const timer = setTimeout(() => void load(), 0);
    return () => clearTimeout(timer);
  }, [me, loading, router, load]);
  const base = `/app/${tenant}`;
  const firstBot = data?.bots[0];
  const { days, analytics, modelAlert } = extras;
  const resolved = analytics?.resolved_vs_open?.resolved ?? 0;
  const open = analytics?.resolved_vs_open?.open ?? 0;
  const showTrend = hasChartData(days.map((day) => day.conversations));
  const showOutcomes = hasChartData([resolved, open]);
  const visibleKeys = (keys: string[] | undefined) =>
    (Array.isArray(keys) ? keys : []).filter(
      (key) => canReadKnowledge || key !== "bots",
    );
  const atLimit = visibleKeys(data?.quota.at_limit);
  const approaching = visibleKeys(data?.quota.warnings).filter(
    (key) => !atLimit.includes(key),
  );
  const setupDone = !!data && data.bots.length > 0 && !!data.published;
  return (
    <main className="overview-screen">
      <PageHeader
        eyebrow="YOUR WORKSPACE AT A GLANCE"
        title="Overview"
        purpose="See what needs attention and keep your assistant ready to help."
        actions={
          <LinkButton
            variant="primary"
            iconEnd="external"
            href={`${base}/inbox`}
          >
            Open inbox
          </LinkButton>
        }
      />
      {error && (
        <Notice message={error} tone="error" onRetry={() => void load()} />
      )}
      {!data && !error && <Loading label="Loading workspace overview..." />}
      {data && (
        <>
          {canReadKnowledge && modelAlert && firstBot && (
            <div className="overview-alert" role="alert">
              <Icon name="alert" size={18} />
              <p dir="auto">{modelAlert}</p>
              <LinkButton
                variant="secondary"
                size="sm"
                href={`${base}/bots/${firstBot.id}/settings`}
              >
                Open settings
              </LinkButton>
            </div>
          )}
          <div className="overview-kpis" aria-label="Inbox counts">
            <StatCard
              label="Waiting for a reply"
              value={formatCount(data.counts.waiting_human)}
            />
            <StatCard
              label="Assigned to me"
              value={formatCount(data.counts.assigned_to_me)}
            />
            <StatCard
              label="Unread conversations"
              value={formatCount(data.counts.unread_conversations)}
            />
            <StatCard
              label="Unread messages"
              value={formatCount(data.counts.unread_messages)}
            />
            {analytics && (
              <>
                <StatCard
                  label="Conversations (last 30 days)"
                  value={formatCount(analytics.total_conversations)}
                  delta={countDelta(
                    analytics.total_conversations,
                    analytics.previous?.total_conversations,
                    { label: PREVIOUS_LABEL },
                  )}
                />
                <StatCard
                  label="Handoff rate"
                  value={formatPercent(analytics.handoff_rate)}
                  delta={rateDelta(
                    analytics.handoff_rate,
                    analytics.previous?.handoff_rate,
                    { upIsGood: false, label: PREVIOUS_LABEL },
                  )}
                />
              </>
            )}
          </div>
          {(showTrend || showOutcomes) && (
            <div className="overview-charts">
              {showTrend && (
                <Card title="Conversations over time">
                  <TrendChart
                    label="Conversations per day"
                    data={days.map((day) => ({ ...day }))}
                    xKey="day"
                    variant="area"
                    height={220}
                    series={[
                      { key: "conversations", label: "Conversations" },
                      { key: "handoffs", label: "Handoffs" },
                    ]}
                  />
                </Card>
              )}
              {showOutcomes && (
                <Card title="Outcomes">
                  <DonutChart
                    label="Resolved and open conversations"
                    slices={[
                      { key: "resolved", label: "Resolved", value: resolved },
                      { key: "open", label: "Open", value: open },
                    ]}
                    center={{
                      value: formatCount(resolved + open),
                      caption: "conversations",
                    }}
                  />
                </Card>
              )}
            </div>
          )}
          <div className="overview-grid">
            <Card
              title="Recent conversations"
              actions={
                <LinkButton
                  variant="ghost"
                  size="sm"
                  iconEnd="arrow-right"
                  href={`${base}/inbox`}
                >
                  View inbox
                </LinkButton>
              }
            >
              {!data.recent.conversations.length ? (
                <Empty>
                  No conversations yet. New visitor conversations will appear
                  here.
                </Empty>
              ) : (
                <ul className="recent-list">
                  {data.recent.conversations.slice(0, 5).map((row) => (
                    <li key={row.id}>
                      <Link href={`${base}/inbox/${row.id}`}>
                        <span className="recent-main">
                          <strong dir="auto">
                            {row.contact_name || "Visitor"}
                          </strong>
                          <span className="recent-preview" dir="auto">
                            {row.last_message || "New conversation"}
                          </span>
                        </span>
                        <span className="recent-meta">
                          <StatusBadge value={row.status} />
                          <small>
                            {formatRelativeTime(row.last_message_at)}
                          </small>
                        </span>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
            {canReadKnowledge && !setupDone && (
              <Card title="Your first assistant">
                <p className="eyebrow">GET STARTED</p>
                <ol className="checklist">
                  <li>
                    <span aria-hidden="true">
                      {data.bots.length ? (
                        <Icon name="check" />
                      ) : (
                        <Icon name="circle" />
                      )}
                    </span>
                    <LinkButton
                      variant="secondary"
                      size="sm"
                      href={`${base}/bots`}
                    >
                      {data.bots.length
                        ? "First bot created"
                        : "Create your first bot"}
                    </LinkButton>
                  </li>
                  {data.bots[0] && (
                    <li>
                      <span aria-hidden="true">
                        {data.published ? (
                          <Icon name="check" />
                        ) : (
                          <Icon name="circle" />
                        )}
                      </span>
                      <LinkButton
                        variant="secondary"
                        size="sm"
                        href={`${base}/bots/${data.bots[0].id}/knowledge`}
                      >
                        {data.published
                          ? "Knowledge published"
                          : "Publish knowledge"}
                        <small dir="auto">{data.bots[0].name}</small>
                      </LinkButton>
                    </li>
                  )}
                </ol>
              </Card>
            )}
          </div>
          <section className="overview-usage" aria-label="Plan usage">
            <div className="section-heading">
              <h2>Plan usage</h2>
              <span className="badge">{data.quota.plan}</span>
            </div>
            <div className="usage-meters">
              {Object.entries(data.quota.usage)
                .filter(
                  ([key]) =>
                    Number.isFinite(data.quota.limits[key]) &&
                    (canReadKnowledge || key !== "bots"),
                )
                .map(([key, value]) => (
                  <div key={key} className="usage-item">
                    <span className="usage-label">{humanLabel(key)}</span>
                    <Meter
                      label={humanLabel(key)}
                      used={value}
                      limit={data.quota.limits[key]}
                    />
                  </div>
                ))}
            </div>
            {atLimit.length > 0 && (
              <p role="status" className="usage-warning" data-tone="danger">
                Plan limit reached for {atLimit.map(humanLabel).join(", ")}.
              </p>
            )}
            {approaching.length > 0 && (
              <p role="status" className="usage-warning" data-tone="warning">
                Approaching the plan limit for{" "}
                {approaching.map(humanLabel).join(", ")}.
              </p>
            )}
            {canReadKnowledge && (
              <p className="usage-footnote">
                Plan limits are provisional. Chat tokens reported by the
                provider this month (all bots):{" "}
                {data.quota.measured_tokens_this_month}
              </p>
            )}
          </section>
        </>
      )}
    </main>
  );
}
