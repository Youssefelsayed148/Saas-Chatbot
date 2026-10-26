"use client";

import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import * as api from "@/lib/api";
import { roleSatisfies, useSession } from "@/lib/session";
import { humanLabel } from "@/lib/labels";
import {
  Card,
  Empty,
  LinkButton,
  Loading,
  Meter,
  Notice,
  PageHeader,
  StatusBadge,
} from "@/lib/ui";
import type { Bot } from "@/lib/api";
import "@/app/bots-list.css";

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
            <>
              <LinkButton
                variant="secondary"
                href={`/app/${tenantId}/settings/requests`}
              >
                Request a change
              </LinkButton>
              <LinkButton
                variant="secondary"
                href={`/app/${tenantId}/settings/data`}
              >
                Tenant data and audit
              </LinkButton>
            </>
          )
        }
      />
      {sessionLoading && <Loading label="Loading session…" />}
      {!sessionLoading && sessionError && (
        <Notice message={sessionError} tone="error" />
      )}
      {!sessionLoading && !sessionError && quota && (
        <Card aria-label="Plan usage" title="Plan usage">
          <p className="muted">{quota.plan} plan</p>
          <div className="bots-quota">
            {(
              [
                ["Bots", "bots"],
                ["Seats", "seats"],
                ["Contacts", "contacts"],
                ["Monthly messages", "monthly_messages"],
              ] as const
            ).map(([label, key]) => (
              <div key={key} className="bots-quota-item">
                <span className="muted">{label}</span>
                <Meter
                  label={label}
                  used={quota.usage[key]}
                  limit={quota.limits[key]}
                />
              </div>
            ))}
          </div>
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
      {bots === null && !sessionLoading && <Loading label="Loading bots…" />}
      {botsError && <Notice message={botsError} tone="error" />}
      {bots && bots.length === 0 && (
        <Empty>
          No bots yet{showArchived ? " (no archived bots either)." : "."}
        </Empty>
      )}
      {bots && bots.length > 0 && (
        <ul className="bots-grid" aria-label="Bots">
          {bots.map((bot) => (
            <li key={bot.id} className="bot-card" data-testid="bot-card">
              <h2 className="bot-card-name">{bot.name}</h2>
              <StatusBadge value={bot.status} data-status={bot.status}>
                {humanLabel(bot.status)}
              </StatusBadge>
              <LinkButton
                variant="primary"
                size="sm"
                href={`/app/${tenantId}/bots/${bot.id}/settings`}
                aria-label={`Open ${bot.name}`}
              >
                Open
              </LinkButton>
            </li>
          ))}
        </ul>
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
