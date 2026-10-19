"use client";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { humanLabel, LabelBadge } from "@/lib/labels";
import * as api from "@/lib/api";
import { useSession } from "@/lib/session";
import { Empty, Loading, Notice } from "@/lib/ui";
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
    channels: api.TenantChannel[];
    published: boolean | null;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    try {
      const [counts, bots, quota, recent, channels] = await Promise.all([
        api.inboxCounts(tenant),
        api.listBots(tenant, false),
        api.tenantQuota(tenant),
        api.listInbox(tenant, { limit: "5" }),
        api.listTenantChannels(tenant).catch(() => ({ items: [] })),
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
        // listTenantChannels always returns {items: []}; some test fixtures
        // answer any other path with a bare array, so tolerate both shapes.
        channels: (channels as { items?: api.TenantChannel[] }).items ?? [],
        published: revisions ? Boolean(revisions.published_revision_id) : null,
      });
      setError(null);
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
  return (
    <main>
      <div className="page-heading">
        <div>
          <p className="eyebrow">YOUR WORKSPACE AT A GLANCE</p>
          <h1>Overview</h1>
          <p className="page-purpose">
            See what needs attention and keep your assistant ready to help.
          </p>
        </div>
        <Link className="primary-link" href={`${base}/inbox`}>
          Open inbox ↗
        </Link>
      </div>
      {error && (
        <Notice message={error} tone="error" onRetry={() => void load()} />
      )}
      {!data && !error && <Loading label="Loading workspace overview..." />}
      {data && (
        <>
          <div className="stat-grid" aria-label="Inbox counts">
            {[
              ["Waiting for a reply", data.counts.waiting_human],
              ["Assigned to me", data.counts.assigned_to_me],
              ["Unread conversations", data.counts.unread_conversations],
              ["Unread messages", data.counts.unread_messages],
            ].map(([label, value]) => (
              <section className="stat-card" key={label}>
                <span>{label}</span>
                <strong>{value}</strong>
                <small>Current inbox</small>
              </section>
            ))}
          </div>
          <div className="overview-grid">
            <section className="panel">
              <div className="section-heading">
                <h2>Recent conversations</h2>
                <Link href={`${base}/inbox`}>View inbox →</Link>
              </div>
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
                        <span dir="auto">
                          {row.last_message || "New conversation"}
                        </span>
                        <small>
                          {humanLabel(row.channel)} · {humanLabel(row.status)} ·{" "}
                          {row.last_message_at
                            ? new Date(row.last_message_at).toLocaleDateString()
                            : "No activity"}
                        </small>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </section>
            {canReadKnowledge && (
              <section className="panel">
                <p className="eyebrow">GET STARTED</p>
                <h2>Your first assistant</h2>
                <ol className="checklist">
                  <li>
                    <span aria-hidden="true">
                      {data.bots.length ? "✓" : "○"}
                    </span>
                    <Link href={`${base}/bots`}>
                      {data.bots.length
                        ? "First bot created"
                        : "Create your first bot"}
                    </Link>
                  </li>
                  {data.bots[0] && canReadKnowledge && (
                    <li>
                      <span aria-hidden="true">
                        {data.published ? "✓" : "○"}
                      </span>
                      <Link href={`${base}/bots/${data.bots[0].id}/knowledge`}>
                        {data.published
                          ? "Knowledge published"
                          : me?.is_platform_staff
                            ? "Publish knowledge"
                            : "Review knowledge"}
                        <small dir="auto">{data.bots[0].name}</small>
                      </Link>
                    </li>
                  )}
                </ol>
              </section>
            )}
          </div>
          {data.channels.length > 0 && (
            <section
              className="panel"
              aria-label="Connected channels"
              data-testid="connected-channels"
            >
              <div className="section-heading">
                <h2>Connected channels</h2>
              </div>
              <ul className="recent-list channels-overview-list">
                {data.channels.map((channel) => (
                  <li key={`${channel.channel}-${channel.display_name}`}>
                    <span data-testid="channel-overview-row">
                      {channel.display_name}{" "}
                      <span className="badge">
                        {humanLabel(channel.channel)}
                      </span>{" "}
                      <LabelBadge value={channel.status} />{" "}
                      <LabelBadge value={channel.health_status} />
                    </span>
                    <small>
                      {channel.last_event_at
                        ? `Last activity ${new Date(channel.last_event_at).toLocaleDateString()}`
                        : "No activity yet"}
                    </small>
                  </li>
                ))}
              </ul>
              <p className="muted">
                Managed by platform staff; read-only here.
              </p>
            </section>
          )}
          <section aria-label="Plan usage">
            <div className="section-heading">
              <h2>Plan usage</h2>
              <span className="badge">{data.quota.plan}</span>
            </div>
            <div className="usage-grid">
              {Object.entries(data.quota.usage)
                .filter(
                  ([key]) =>
                    Number.isFinite(data.quota.limits[key]) &&
                    (canReadKnowledge || key !== "bots"),
                )
                .map(([key, value]) => (
                  <label key={key}>
                    {humanLabel(key)}
                    <span>
                      {value} / {data.quota.limits[key]}
                    </span>
                    {data.quota.limits[key] > 0 && (
                      <progress
                        aria-label={humanLabel(key)}
                        value={Math.min(value, data.quota.limits[key])}
                        max={data.quota.limits[key]}
                      />
                    )}
                  </label>
                ))}
            </div>
            {data.quota.warnings.filter(
              (key) => canReadKnowledge || key !== "bots",
            ).length > 0 && (
              <p role="status">
                Approaching the plan limit for{" "}
                {data.quota.warnings
                  .filter((key) => canReadKnowledge || key !== "bots")
                  .map(humanLabel)
                  .join(", ")}
                .
              </p>
            )}
            {canReadKnowledge && (
              <p className="muted">
                Plan limits are provisional. Measured provider tokens this
                month: {data.quota.measured_tokens_this_month}.
              </p>
            )}
          </section>
        </>
      )}
    </main>
  );
}
