"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import * as api from "@/lib/api";
import { Loading, Notice } from "@/lib/ui";

/** Client detail (P4-06, docs/11): bots + status, failed jobs, members and
 * roles, recent audit rows, usage. Read-only staff view (no impersonation). */

export default function PlatformClientPage() {
  const params = useParams<{ clientId: string }>();
  const clientId = params.clientId;
  const [detail, setDetail] = useState<api.PlatformTenantDetail | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [planLabel, setPlanLabel] = useState("");
  const [reason, setReason] = useState("");
  const [quotaOverrides, setQuotaOverrides] = useState('{"bots": 4}');

  useEffect(() => {
    const timer = setTimeout(() => {
      void (async () => {
        try {
          const loaded = await api.platformTenantDetail(clientId);
          setDetail(loaded);
          setPlanLabel(loaded.tenant.plan_label);
          setError(null);
        } catch (caught) {
          setError(caught instanceof Error ? caught.message : "Not found.");
        }
      })();
    }, 0);
    return () => clearTimeout(timer);
  }, [clientId]);

  async function assignPlan(event: React.FormEvent) {
    event.preventDefault();
    if (!detail) return;
    try {
      const updated = await api.platformAssignPlan(
        detail.tenant.id,
        planLabel,
        reason,
      );
      setDetail({
        ...detail,
        tenant: { ...detail.tenant, plan_label: updated.plan_label },
      });
      setError(null);
      setNotice("Changes saved.");
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Plan update failed.",
      );
    }
  }

  async function pauseBot(botId: string) {
    if (!detail) return;
    try {
      await api.platformPauseBot(botId, reason);
      setDetail({
        ...detail,
        bots: detail.bots.map((bot) =>
          bot.id === botId ? { ...bot, status: "paused" } : bot,
        ),
      });
      setError(null);
      setNotice("Changes saved.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Bot pause failed.");
    }
  }

  async function saveQuotaOverrides(event: React.FormEvent) {
    event.preventDefault();
    if (!detail) return;
    try {
      const limits = JSON.parse(quotaOverrides) as Record<string, number>;
      await api.platformQuotaOverride(detail.tenant.id, limits, reason);
      setError(null);
      setNotice("Changes saved.");
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Quota override failed.",
      );
    }
  }

  return (
    <main className="platform-client-detail">
      <h1 data-testid="client-detail-name">
        {detail?.tenant.name ?? "Client"}
      </h1>
      <p className="page-purpose">
        Review client health and manage plans, quotas and bot availability.
      </p>
      <p className="eyebrow">
        <a href="/platform">← Back to clients</a>
      </p>
      {error && <Notice message={error} tone="error" />}
      {notice && <Notice message={notice} />}
      {!error && detail === null && <Loading label="Loading client…" />}
      {detail && (
        <>
          <p data-testid="client-detail-status">
            {detail.tenant.slug} ·{" "}
            <span data-status={detail.tenant.status}>
              {detail.tenant.status}
            </span>{" "}
            · usage events: {detail.usage_events}
          </p>
          <section aria-label="Bots" data-testid="client-detail-bots">
            <h2>Bots</h2>
            {detail.bots.length === 0 ? (
              <p className="muted">No bots yet.</p>
            ) : (
              <ul>
                {detail.bots.map((bot) => (
                  <li key={bot.id}>
                    {bot.name} —{" "}
                    <span data-status={bot.status}>{bot.status}</span>
                    {bot.published
                      ? " · knowledge published"
                      : " · nothing published"}
                    {bot.status !== "paused" && bot.status !== "archived" && (
                      <>
                        {" "}
                        <button
                          type="button"
                          disabled={reason.trim().length < 3}
                          onClick={() => void pauseBot(bot.id)}
                        >
                          Pause bot
                        </button>
                      </>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>
          <section aria-label="Plan assignment" data-testid="client-plan">
            <h2>Plan assignment</h2>
            <p>
              PLACEHOLDER plans and limits; final pricing and limits are TBD.
            </p>
            <form onSubmit={(event) => void assignPlan(event)}>
              <label>
                Plan label{" "}
                <input
                  value={planLabel || detail.tenant.plan_label}
                  onChange={(event) => setPlanLabel(event.target.value)}
                  maxLength={40}
                  required
                />
              </label>
              <label>
                Reason{" "}
                <input
                  value={reason}
                  onChange={(event) => setReason(event.target.value)}
                  minLength={3}
                  maxLength={500}
                  required
                />
              </label>
              <button type="submit">Save plan</button>
            </form>
            <form onSubmit={(event) => void saveQuotaOverrides(event)}>
              <label>
                PLACEHOLDER quota overrides (JSON)
                <textarea dir="auto"
                  value={quotaOverrides}
                  onChange={(event) => setQuotaOverrides(event.target.value)}
                  rows={3}
                  maxLength={1000}
                  required
                />
              </label>
              <button type="submit" disabled={reason.trim().length < 3}>
                Save override with reason
              </button>
            </form>
          </section>
          <section aria-label="Failed jobs" data-testid="client-detail-jobs">
            <h2>Knowledge/ingest failures</h2>
            {detail.failed_jobs.length === 0 ? (
              <p className="muted">No failed jobs.</p>
            ) : (
              <ul>
                {detail.failed_jobs.map((job) => (
                  <li key={job.id}>
                    {job.type}: {job.error ?? "failed"}
                  </li>
                ))}
              </ul>
            )}
          </section>
          <section aria-label="Members" data-testid="client-detail-members">
            <h2>Members</h2>
            <ul>
              {detail.members.map((member) => (
                <li key={member.user_id}>
                  {member.email} — {member.role}
                </li>
              ))}
            </ul>
          </section>
          <section aria-label="Recent audit" data-testid="client-detail-audit">
            <h2>Recent audit</h2>
            {detail.recent_audit.length === 0 ? (
              <p className="muted">No audit rows.</p>
            ) : (
              <ul>
                {detail.recent_audit.map((row, index) => (
                  <li key={`${row.at}-${index}`}>
                    {row.at.slice(0, 19)} — {row.action}
                    {row.target ? ` (${row.target})` : ""}
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </main>
  );
}
