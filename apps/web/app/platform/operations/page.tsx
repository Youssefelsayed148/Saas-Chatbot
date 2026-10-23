"use client";

import { useEffect, useState } from "react";

import { auditActionLabel, humanLabel } from "@/lib/labels";
import * as api from "@/lib/api";
import {
  Button,
  Card,
  DataTable,
  Empty,
  Field,
  Loading,
  Notice,
  PageHeader,
  StatusBadge,
} from "@/lib/ui";

import "@/app/ops-screen.css";

export default function PlatformOperationsPage() {
  const [health, setHealth] = useState<Awaited<
    ReturnType<typeof api.platformJobHealth>
  > | null>(null);
  const [analytics, setAnalytics] = useState<api.PlatformAnalytics | null>(
    null,
  );
  const [audit, setAudit] = useState<Awaited<
    ReturnType<typeof api.platformAudit>
  > | null>(null);
  const [quotas, setQuotas] = useState<api.PlatformQuotaPlans | null>(null);
  const [query, setQuery] = useState("");
  const [reason, setReason] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      const [nextHealth, nextAnalytics, nextAudit, nextQuotas] =
        await Promise.all([
          api.platformJobHealth(),
          api.platformAnalytics(),
          api.platformAudit(query),
          api.platformQuotas(),
        ]);
      setHealth(nextHealth);
      setAnalytics(nextAnalytics);
      setAudit(nextAudit);
      setQuotas(nextQuotas);
      setError(null);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Could not load operations.",
      );
    }
  }

  useEffect(() => {
    const timer = setTimeout(() => void load(), 0);
    return () => clearTimeout(timer);
    // The query is submitted explicitly below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function act(jobId: string, action: "retry" | "cancel") {
    try {
      await api.platformJobAction(jobId, action, reason.trim());
      setReason("");
      await load();
      setNotice("Changes saved.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Operation failed.");
    }
  }

  return (
    <main className="platform-operations ops-page">
      <PageHeader
        title="Platform operations"
        purpose="Review measured platform activity, job health and audited operations."
        actions={
          <a className="quiet-button" href="/platform">
            Back to Organizations
          </a>
        }
      />
      {error && <Notice message={error} tone="error" />}
      {notice && <Notice message={notice} />}
      {!health || !analytics || !audit || !quotas ? (
        <Loading label="Loading platform operations…" />
      ) : (
        <>
          <Card
            title="Provisional quota limits"
            aria-label="Provisional quota plans"
          >
            <p className="ops-copy">
              These values are for verification. Pricing and final plan limits
              are still under review; no token or currency spend cap is
              enforced.
            </p>
            <DataTable
              caption="Quota limits by plan"
              rows={Object.keys(quotas.plans.free)}
              rowKey={(limit) => limit}
              columns={[
                {
                  key: "limit",
                  header: "Limit",
                  cell: (limit) => limit.replaceAll("_", " "),
                },
                ...Object.entries(quotas.plans).map(([plan, values]) => ({
                  key: plan,
                  header: plan,
                  className: "num",
                  cell: (limit: string) => values[limit],
                })),
              ]}
            />
          </Card>
          <Card
            title="Platform analytics"
            aria-label="Platform analytics"
            data-testid="platform-analytics"
          >
            <dl className="ops-stats">
              {[
                ["Tenants", analytics.tenants],
                ["Bots", analytics.bots],
                ["Conversations", analytics.conversations],
                ["Messages", analytics.messages],
                ["Handoffs", analytics.handoffs],
                [
                  "Handoff rate",
                  `${(analytics.handoff_rate * 100).toFixed(1)}%`,
                ],
              ].map(([label, value]) => (
                <div key={label}>
                  <dt>{label}</dt>
                  <dd>{value}</dd>
                </div>
              ))}
            </dl>
            <DataTable
              caption="Measured usage by organization"
              rows={analytics.clients}
              rowKey={(client) => client.tenant_id}
              columns={[
                {
                  key: "organization",
                  header: "Organization",
                  cell: (client) => <bdi>{client.name}</bdi>,
                },
                {
                  key: "plan",
                  header: "Plan",
                  cell: (client) => client.plan_label,
                },
                {
                  key: "usage",
                  header: "Measured usage",
                  cell: (client) =>
                    Object.entries(client.usage)
                      .map(([kind, count]) => `${kind}: ${count}`)
                      .join(" · ") || "No usage yet",
                },
              ]}
            />
            <p className="muted ops-copy">
              AI cost is not reported because provider token usage and price
              data are not stored.
            </p>
          </Card>
          <Card
            title="Job queue"
            aria-label="Job queue health"
            data-testid="platform-job-health"
          >
            <p className="ops-copy">
              {Object.entries(health.counts)
                .map(([status, count]) => `${status}: ${count}`)
                .join(" · ") || "No jobs"}
            </p>
            <Field
              label="Reason for job action"
              hint="Enter at least 3 characters to enable Retry and Cancel."
              className="ops-reason"
            >
              {(control) => (
                <input
                  {...control}
                  dir="auto"
                  value={reason}
                  onChange={(event) => setReason(event.target.value)}
                  minLength={3}
                  maxLength={500}
                />
              )}
            </Field>
            {health.jobs.length === 0 ? (
              <Empty>No jobs in the queue.</Empty>
            ) : (
              <div
                className="table-scroll"
                role="region"
                aria-label="Jobs"
                tabIndex={0}
              >
                <table>
                  <caption className="sr-only">Jobs</caption>
                  <thead>
                    <tr>
                      <th scope="col">Type</th>
                      <th scope="col">Status</th>
                      <th scope="col" className="num">
                        Attempts
                      </th>
                      <th scope="col">Error</th>
                      <th scope="col">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {health.jobs.map((job) => (
                      <tr key={job.id}>
                        <td>{job.type}</td>
                        <td data-status={job.status}>
                          <StatusBadge value={job.status}>
                            {humanLabel(job.status)}
                          </StatusBadge>
                        </td>
                        <td className="num">{job.attempts}</td>
                        <td className="ops-error">
                          {job.error ? <bdi>{job.error}</bdi> : "—"}
                        </td>
                        <td>
                          <div className="row-actions">
                            {job.status === "failed" && (
                              <Button
                                variant="quiet"
                                disabled={reason.trim().length < 3}
                                onClick={() => void act(job.id, "retry")}
                              >
                                Retry
                              </Button>
                            )}
                            {["pending", "running"].includes(job.status) && (
                              <Button
                                variant="quiet"
                                disabled={reason.trim().length < 3}
                                onClick={() => void act(job.id, "cancel")}
                              >
                                Cancel
                              </Button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
          <Card
            title="Audit review"
            aria-label="Audit review"
            data-testid="platform-audit-review"
          >
            <form
              className="ops-search"
              onSubmit={(event) => {
                event.preventDefault();
                void load();
              }}
            >
              <Field label="Search audit actions">
                {(control) => (
                  <input
                    {...control}
                    dir="auto"
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                  />
                )}
              </Field>
              <Button type="submit">Search</Button>
            </form>
            <DataTable
              caption="Audit events"
              rows={audit.events.map((event, index) => ({ event, index }))}
              rowKey={({ event, index }) => `${event.created_at}-${index}`}
              empty={<Empty>No audit actions match this search.</Empty>}
              columns={[
                {
                  key: "when",
                  header: "When",
                  cell: ({ event }) => (
                    <span dir="ltr">{event.created_at.slice(0, 19)}</span>
                  ),
                },
                {
                  key: "action",
                  header: "Action",
                  cell: ({ event }) => auditActionLabel(event.action),
                },
                {
                  key: "target",
                  header: "Target",
                  cell: ({ event }) => (
                    <span dir="ltr">
                      {event.target_type ?? "platform"}:{event.target_id ?? ""}
                    </span>
                  ),
                },
              ]}
            />
          </Card>
        </>
      )}
    </main>
  );
}
