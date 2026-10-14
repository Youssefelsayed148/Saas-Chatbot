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
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const timer = setTimeout(() => {
      void (async () => {
        try {
          setDetail(await api.platformTenantDetail(clientId));
          setError(null);
        } catch (caught) {
          setError(caught instanceof Error ? caught.message : "Not found.");
        }
      })();
    }, 0);
    return () => clearTimeout(timer);
  }, [clientId]);

  return (
    <main>
      <h1 data-testid="client-detail-name">
        {detail?.tenant.name ?? "Client"}
      </h1>
      <p className="eyebrow">
        <a href="/platform">← Back to clients</a>
      </p>
      {error && <Notice message={error} tone="error" />}
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
                  </li>
                ))}
              </ul>
            )}
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
