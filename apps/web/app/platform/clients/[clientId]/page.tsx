"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import * as api from "@/lib/api";
import { Loading, Notice } from "@/lib/ui";

const TABS = ["Overview", "Members", "Bots", "Knowledge"] as const;
type Tab = (typeof TABS)[number];

export default function OrganizationDetailPage() {
  const { clientId } = useParams<{ clientId: string }>();
  const [detail, setDetail] = useState<api.PlatformTenantDetail | null>(null);
  const [tab, setTab] = useState<Tab>("Overview");
  const [name, setName] = useState("");
  const [plan, setPlan] = useState("starter");
  const [status, setStatus] = useState("active");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const load = useCallback(async () => {
    try {
      const value = await api.platformTenantDetail(clientId);
      setDetail(value);
      setName(value.tenant.name);
      setPlan(value.tenant.plan_label);
      setStatus(value.tenant.status);
    } catch {
      setError("Could not load this organization.");
    }
  }, [clientId]);
  useEffect(() => {
    const timer = setTimeout(() => {
      void load();
    }, 0);
    return () => clearTimeout(timer);
  }, [load]);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setPending(true);
    setNotice(null);
    setError(null);
    try {
      await api.platformUpdateOrganization(clientId, {
        name,
        plan_label: plan,
        status,
      });
      await load();
      setNotice("Organization updated.");
    } catch {
      setError(
        "Could not update the organization. Check the entered values and try again.",
      );
    } finally {
      setPending(false);
    }
  }

  return (
    <main className="platform-client-detail">
      <a href="/platform">← Back to Organizations</a>
      {error && <Notice message={error} tone="error" />}
      {!detail ? (
        <Loading label="Loading organization…" />
      ) : (
        <>
          <h1 data-testid="client-detail-name">{detail.tenant.name}</h1>
          <p>
            {detail.tenant.slug} · Created{" "}
            {new Date(detail.tenant.created_at).toLocaleDateString()}
          </p>
          <nav aria-label="Organization tabs" role="tablist">
            {TABS.map((item) => (
              <button
                key={item}
                role="tab"
                aria-selected={tab === item}
                onClick={() => setTab(item)}
              >
                {item}
              </button>
            ))}
          </nav>
          {notice && <Notice message={notice} />}
          {tab === "Overview" && (
            <section aria-label="Overview" role="tabpanel">
              <p>
                {detail.counts.members} members · {detail.counts.bots} bots
              </p>
              <h2>Quota usage</h2>
              <table aria-label="Quota usage versus limits">
                <thead>
                  <tr>
                    <th>Quota</th>
                    <th>Used</th>
                    <th>Limit</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(detail.quota.usage).map(([key, used]) => (
                    <tr key={key}>
                      <td>{key.replaceAll("_", " ")}</td>
                      <td>{used}</td>
                      <td>{detail.quota.limits[key]}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <form onSubmit={(e) => void save(e)}>
                <label>
                  Name
                  <input
                    value={name}
                    maxLength={200}
                    required
                    onChange={(e) => setName(e.target.value)}
                  />
                </label>
                <label>
                  Plan
                  <select
                    value={plan}
                    onChange={(e) => setPlan(e.target.value)}
                  >
                    {["free", "starter", "pro", "business"].map((value) => (
                      <option key={value}>{value}</option>
                    ))}
                  </select>
                </label>
                <label>
                  Status
                  <select
                    value={status}
                    onChange={(e) => setStatus(e.target.value)}
                  >
                    <option value="active">Active</option>
                    <option value="archived">Archived</option>
                  </select>
                </label>
                <button disabled={pending}>
                  {pending ? "Saving…" : "Save changes"}
                </button>
              </form>
            </section>
          )}
          {tab === "Members" && (
            <section
              aria-label="Members"
              role="tabpanel"
              data-testid="client-detail-members"
            >
              <h2>Members</h2>
              {detail.members.length ? (
                <table>
                  <thead>
                    <tr>
                      <th>Email</th>
                      <th>Role</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detail.members.map((member) => (
                      <tr key={member.user_id}>
                        <td>{member.email}</td>
                        <td>{member.role}</td>
                        <td>{member.status}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <p>No members yet.</p>
              )}
            </section>
          )}
          {tab === "Bots" && (
            <section
              aria-label="Bots"
              role="tabpanel"
              data-testid="client-detail-bots"
            >
              <h2>Bots</h2>
              {detail.bots.length ? (
                <table>
                  <thead>
                    <tr>
                      <th>Name</th>
                      <th>Status</th>
                      <th>Widget</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detail.bots.map((bot) => (
                      <tr key={bot.id}>
                        <td>{bot.name}</td>
                        <td>{bot.status}</td>
                        <td>
                          {bot.widget_state === "configured"
                            ? "Configured"
                            : "Not configured"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <p>No bots yet.</p>
              )}
            </section>
          )}
          {tab === "Knowledge" && (
            <section aria-label="Knowledge" role="tabpanel">
              <h2>Knowledge</h2>
              {detail.bots.length ? (
                <table>
                  <thead>
                    <tr>
                      <th>Bot</th>
                      <th>Sources</th>
                      <th>Last ingestion</th>
                      <th>Published revision</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detail.bots.map((bot) => (
                      <tr key={bot.id}>
                        <td>{bot.name}</td>
                        <td>{bot.source_count}</td>
                        <td>{bot.last_ingestion_job_status ?? "None"}</td>
                        <td>
                          {bot.published_revision_id ? (
                            <>
                              {bot.published_revision_id} ·{" "}
                              {bot.published_at
                                ? new Date(
                                    bot.published_at,
                                  ).toLocaleDateString()
                                : "Date unavailable"}
                            </>
                          ) : (
                            "None"
                          )}
                        </td>
                        <td>
                          <a href={`/app/${clientId}/bots/${bot.id}/knowledge`}>
                            Open Knowledge
                          </a>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <p>No bots in this organization yet.</p>
              )}
            </section>
          )}
        </>
      )}
    </main>
  );
}
