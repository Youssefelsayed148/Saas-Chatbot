"use client";

import { useEffect, useState } from "react";

import { auditActionLabel, LabelBadge } from "@/lib/labels";
import * as api from "@/lib/api";
import { Loading, Notice } from "@/lib/ui";

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
    <main className="platform-operations">
      <h1>Platform operations</h1>
      <p className="page-purpose">
        Review measured platform activity, job health and audited operations.
      </p>
      <p>
        <a href="/platform">Back to Organizations</a>
      </p>
      {error && <Notice message={error} tone="error" />}
      {notice && <Notice message={notice} />}
      {!health || !analytics || !audit || !quotas ? (
        <Loading label="Loading platform operations…" />
      ) : (
        <>
          <section aria-label="Provisional quota plans">
            <h2>Provisional quota limits</h2>
            <p>
              These values are for verification. Pricing and final plan limits
              are still under review; no token or currency spend cap is
              enforced.
            </p>
            <table>
              <thead>
                <tr>
                  <th>Limit</th>
                  {Object.keys(quotas.plans).map((plan) => (
                    <th key={plan}>{plan}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {Object.keys(quotas.plans.free).map((limit) => (
                  <tr key={limit}>
                    <th>{limit.replaceAll("_", " ")}</th>
                    {Object.entries(quotas.plans).map(([plan, values]) => (
                      <td key={plan}>{values[limit]}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
          <section
            aria-label="Platform analytics"
            data-testid="platform-analytics"
          >
            <h2>Platform analytics</h2>
            <p>
              Tenants {analytics.tenants} · Bots {analytics.bots} ·
              Conversations {analytics.conversations} · Messages{" "}
              {analytics.messages} · Handoffs {analytics.handoffs} · Handoff
              rate {(analytics.handoff_rate * 100).toFixed(1)}%
            </p>
            <table>
              <thead>
                <tr>
                  <th>Client</th>
                  <th>Plan</th>
                  <th>Measured usage</th>
                </tr>
              </thead>
              <tbody>
                {analytics.clients.map((client) => (
                  <tr key={client.tenant_id}>
                    <td>{client.name}</td>
                    <td>{client.plan_label}</td>
                    <td>
                      {Object.entries(client.usage)
                        .map(([kind, count]) => `${kind}: ${count}`)
                        .join(" · ") || "No usage yet"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="muted">
              AI cost is not reported because provider token usage and price
              data are not stored.
            </p>
          </section>
          <section
            aria-label="Job queue health"
            data-testid="platform-job-health"
          >
            <h2>Job queue</h2>
            <p>
              {Object.entries(health.counts)
                .map(([status, count]) => `${status}: ${count}`)
                .join(" · ") || "No jobs"}
            </p>
            <label>
              Reason for job action
              <input
                value={reason}
                onChange={(event) => setReason(event.target.value)}
                minLength={3}
                maxLength={500}
              />
            </label>
            <table>
              <thead>
                <tr>
                  <th>Type</th>
                  <th>Status</th>
                  <th>Attempts</th>
                  <th>Error</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {health.jobs.map((job) => (
                  <tr key={job.id}>
                    <td>{job.type}</td>
                    <td data-status={job.status}>
                      <LabelBadge value={job.status} />
                    </td>
                    <td>{job.attempts}</td>
                    <td>{job.error ?? "—"}</td>
                    <td>
                      {job.status === "failed" && (
                        <button
                          type="button"
                          disabled={reason.trim().length < 3}
                          onClick={() => void act(job.id, "retry")}
                        >
                          Retry
                        </button>
                      )}
                      {["pending", "running"].includes(job.status) && (
                        <button
                          type="button"
                          disabled={reason.trim().length < 3}
                          onClick={() => void act(job.id, "cancel")}
                        >
                          Cancel
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
          <section
            aria-label="Audit review"
            data-testid="platform-audit-review"
          >
            <h2>Audit review</h2>
            <form
              onSubmit={(event) => {
                event.preventDefault();
                void load();
              }}
            >
              <label>
                Search audit actions{" "}
                <input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                />
              </label>
              <button type="submit">Search</button>
            </form>
            <ul>
              {audit.events.map((event, index) => (
                <li key={`${event.created_at}-${index}`}>
                  {event.created_at.slice(0, 19)} ·{" "}
                  {auditActionLabel(event.action)} ·{" "}
                  {event.target_type ?? "platform"}:{event.target_id ?? ""}
                </li>
              ))}
            </ul>
          </section>
        </>
      )}
    </main>
  );
}
