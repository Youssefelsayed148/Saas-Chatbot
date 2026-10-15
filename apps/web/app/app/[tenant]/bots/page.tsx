"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import * as api from "@/lib/api";
import { roleSatisfies, useSession } from "@/lib/session";
import { LabelBadge, humanLabel } from "@/lib/labels";
import { Empty, Loading, Notice, ConfirmAction } from "@/lib/ui";
import type { Bot } from "@/lib/api";

export default function BotsListPage() {
  const params = useParams<{ tenant: string }>();
  const tenantId = params.tenant;
  const router = useRouter();
  const {
    me,
    loading: sessionLoading,
    error: sessionError,
    refresh,
    roleIn,
  } = useSession();
  const [bots, setBots] = useState<Bot[] | null>(null);
  const [botsError, setBotsError] = useState<string | null>(null);
  const [showArchived, setShowArchived] = useState(false);
  const [name, setName] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [archiving, setArchiving] = useState<string | null>(null);
  const [quota, setQuota] = useState<api.TenantQuotaStatus | null>(null);

  const role = roleIn(tenantId);
  const canEdit = roleSatisfies(role, "editor");
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

  async function onCreate(event: React.FormEvent) {
    event.preventDefault();
    setCreateError(null);
    setCreating(true);
    try {
      await api.createBot(tenantId, name);
      setName("");
      await load();
    } catch (caught) {
      setCreateError(
        caught instanceof Error ? caught.message : "Could not create bot.",
      );
    } finally {
      setCreating(false);
    }
  }

  async function onArchive(bot: Bot) {
    setArchiving(bot.id);
    try {
      await api.archiveBot(tenantId, bot.id);
      await load();
      await refresh();
    } catch (caught) {
      setCreateError(
        caught instanceof Error ? caught.message : "Could not archive bot.",
      );
    } finally {
      setArchiving(null);
    }
  }

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
        <section aria-label="PLACEHOLDER plan usage">
          <h2>PLACEHOLDER plan usage</h2>
          <p>
            {quota.plan} plan · Bots {quota.usage.bots}/{quota.limits.bots} ·
            Seats {quota.usage.seats}/{quota.limits.seats} · Contacts{" "}
            {quota.usage.contacts}/{quota.limits.contacts} · Monthly messages{" "}
            {quota.usage.monthly_messages}/{quota.limits.monthly_messages}
          </p>
          {quota.warnings.length > 0 && (
            <p role="status">
              Approaching the PLACEHOLDER limit for{" "}
              {quota.warnings.map(humanLabel).join(", ")}.
            </p>
          )}
          <p className="muted">
            PLACEHOLDER limits for verification; final pricing and limits are
            TBD. Measured provider tokens this month:{" "}
            {quota.measured_tokens_this_month}.
          </p>
        </section>
      )}
      {!sessionLoading && !sessionError && (
        <section aria-label="Create bot" className="create-bot-panel">
          <h2>Create an assistant</h2>
          {canEdit ? (
            <form onSubmit={onCreate}>
              <label>
                Bot name
                <input
                  name="name"
                  required
                  maxLength={100}
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                />
              </label>
              <button
                type="submit"
                disabled={
                  creating ||
                  name.trim().length === 0 ||
                  Boolean(quota && quota.usage.bots >= quota.limits.bots)
                }
              >
                {creating ? "Creating…" : "Create bot"}
              </button>
            </form>
          ) : (
            role && (
              <p className="muted">
                Creating bots requires the editor role (you are {role}).
              </p>
            )
          )}
          {createError && <Notice message={createError} tone="error" />}
        </section>
      )}
      {bots === null && !sessionLoading && <Loading label="Loading bots…" />}
      {botsError && <Notice message={botsError} tone="error" />}
      {bots && bots.length === 0 && (
        <Empty>
          No bots yet{showArchived ? " (no archived bots either)." : "."}{" "}
          {canEdit
            ? "Create a bot above to get started."
            : "Ask an editor to create a bot."}
        </Empty>
      )}
      {bots && bots.length > 0 && (
        <table>
          <caption className="sr-only">Bots</caption>
          <thead>
            <tr>
              <th>Name</th>
              <th>Status</th>
              <th>Actions</th>
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
                <td>
                  {canEdit && bot.status !== "archived" && (
                    <ConfirmAction
                      title={`Archive ${bot.name}?`}
                      description="The bot will leave your default list. Its data is retained and it remains available in archived bots."
                      disabled={archiving === bot.id}
                      onConfirm={() => void onArchive(bot)}
                      confirmLabel="Archive bot"
                    >
                      {archiving === bot.id ? "Archiving..." : "Archive"}
                    </ConfirmAction>
                  )}
                </td>
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
