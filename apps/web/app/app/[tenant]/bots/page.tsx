"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import * as api from "@/lib/api";
import { roleSatisfies, useSession } from "@/lib/session";
import { LabelBadge, humanLabel } from "@/lib/labels";
import { Empty, Loading, Notice } from "@/lib/ui";
import type { Bot } from "@/lib/api";

export default function BotsListPage() {
  const params = useParams<{ tenant: string }>();
  const tenantId = params.tenant;
  const router = useRouter();
  const {
    me,
    loading: sessionLoading,
    error: sessionError,
    roleIn,
  } = useSession();
  const [bots, setBots] = useState<Bot[] | null>(null);
  const [botsError, setBotsError] = useState<string | null>(null);
  const [showArchived, setShowArchived] = useState(false);
  const [quota, setQuota] = useState<api.TenantQuotaStatus | null>(null);

  const role = roleIn(tenantId);
  const canAdmin = roleSatisfies(role, "admin");

  const load = useCallback(async () => {
    try {
      const nextBots = await api.listBots(tenantId, showArchived);
      const nextQuota = await api.tenantQuota(tenantId);
      setBotsError(null);
      setBots(nextBots);
      setQuota(nextQuota);
    } catch (caught) {
      setBotsError(
        caught instanceof Error ? caught.message : "Could not load bots.",
      );
    }
  }, [tenantId, showArchived]);

  useEffect(() => {
    // Wait for the session; loaders run deferred so no state updates synchronously.
    if (!me) return;
    const timer = setTimeout(() => {
      void load();
    }, 0);
    return () => clearTimeout(timer);
  }, [me, load]);

  useEffect(() => {
    if (!sessionLoading && !me) router.replace("/login");
  }, [sessionLoading, me, router]);

  return (
    <main>
      <p className="eyebrow">Chatbots</p>
      <h1>Bots</h1>
      <p className="page-purpose">
        Build, train and install the assistants that help your visitors.
      </p>
      {canAdmin && (
        <p>
          <Link href={`/app/${tenantId}/settings/data`}>
            Tenant data and audit
          </Link>
        </p>
      )}
      {sessionLoading && <Loading label="Loading session…" />}
      {!sessionLoading && sessionError && (
        <Notice message={sessionError} tone="error" />
      )}
      {!sessionLoading && !sessionError && quota && (
        <section aria-label="Plan usage">
          <h2>Plan usage</h2>
          <p>
            {quota.plan} plan · Bots {quota.usage.bots}/{quota.limits.bots} ·
            Seats {quota.usage.seats}/{quota.limits.seats} · Contacts{" "}
            {quota.usage.contacts}/{quota.limits.contacts} · Monthly messages{" "}
            {quota.usage.monthly_messages}/{quota.limits.monthly_messages}
          </p>
          {quota.warnings.length > 0 && (
            <p role="status">
              Approaching the plan limit for{" "}
              {quota.warnings.map(humanLabel).join(", ")}.
            </p>
          )}
          <p className="muted">
            Plan limits are provisional. Measured provider tokens this month:{" "}
            {quota.measured_tokens_this_month}.
          </p>
        </section>
      )}
      {!sessionLoading && !sessionError && (
        <p className="muted">Contact us to add or change bots.</p>
      )}
      {bots === null && !sessionLoading && <Loading label="Loading bots…" />}
      {botsError && <Notice message={botsError} tone="error" />}
      {bots && bots.length === 0 && (
        <Empty>
          No bots yet{showArchived ? " (no archived bots either)." : "."}
        </Empty>
      )}
      {bots && bots.length > 0 && (
        <table>
          <caption className="sr-only">Bots</caption>
          <thead>
            <tr>
              <th>Name</th>
              <th>Status</th>
              <th>Open</th>
            </tr>
          </thead>
          <tbody>
            {bots.map((bot) => (
              <tr key={bot.id}>
                <td>
                  <Link href={`/app/${tenantId}/bots/${bot.id}/settings`}>
                    {bot.name}
                  </Link>
                </td>
                <td data-status={bot.status}>
                  <LabelBadge value={bot.status} />
                </td>
                <td><Link href={`/app/${tenantId}/bots/${bot.id}/settings`}>Open bot</Link></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <label className="muted">
        <input
          type="checkbox"
          checked={showArchived}
          onChange={(event) => setShowArchived(event.target.checked)}
        />
        Show archived bots
      </label>
    </main>
  );
}
