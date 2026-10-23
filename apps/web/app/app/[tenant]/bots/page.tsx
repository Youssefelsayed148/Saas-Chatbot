"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import * as api from "@/lib/api";
import { roleSatisfies, useSession } from "@/lib/session";
import { humanLabel } from "@/lib/labels";
import {
  Card,
  DataTable,
  Empty,
  Loading,
  Notice,
  PageHeader,
  StatusBadge,
} from "@/lib/ui";
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
      <PageHeader
        eyebrow="Chatbots"
        title="Bots"
        purpose="Build, train and install the assistants that help your visitors."
        actions={
          canAdmin && (
            <Link href={`/app/${tenantId}/settings/data`}>
              Tenant data and audit
            </Link>
          )
        }
      />
      {sessionLoading && <Loading label="Loading session…" />}
      {!sessionLoading && sessionError && (
        <Notice message={sessionError} tone="error" />
      )}
      {!sessionLoading && !sessionError && quota && (
        <Card aria-label="Plan usage" title="Plan usage">
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
        </Card>
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
        <DataTable
          caption="Bots"
          rows={bots}
          rowKey={(bot) => bot.id}
          columns={[
            {
              key: "name",
              header: "Name",
              cell: (bot) => (
                <Link href={`/app/${tenantId}/bots/${bot.id}/settings`}>
                  {bot.name}
                </Link>
              ),
            },
            {
              key: "status",
              header: "Status",
              cell: (bot) => (
                <StatusBadge value={bot.status} data-status={bot.status}>
                  {humanLabel(bot.status)}
                </StatusBadge>
              ),
            },
            {
              key: "open",
              header: "Open",
              cell: (bot) => (
                <Link href={`/app/${tenantId}/bots/${bot.id}/settings`}>
                  Open bot
                </Link>
              ),
            },
          ]}
        />
      )}
      <label className="muted archived-toggle">
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
