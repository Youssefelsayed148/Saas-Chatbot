"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { auditActionLabel } from "@/lib/labels";
import * as api from "@/lib/api";
import { ConfirmAction, Loading, Notice } from "@/lib/ui";
import { OrganizationMembers } from "@/lib/staff-members";
import { BotLinks, CreateBotForm } from "@/lib/staff-bots";

/** Client detail (P4-06, docs/11): bots + status, failed jobs, members and
 * roles, recent audit rows, usage. Read-only staff view (no impersonation). */

export default function PlatformClientPage() {
  const params = useParams<{ clientId: string }>();
  const clientId = params.clientId;
  const [detail, setDetail] = useState<api.PlatformTenantDetail | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState("Overview");
  const [name, setName] = useState("");
  const [status, setStatus] = useState("active");
  const [saving, setSaving] = useState(false);
  const [planLabel, setPlanLabel] = useState("");
  const [reason, setReason] = useState("");
  const [quotaOverrides, setQuotaOverrides] = useState('{"bots": 4}');

  useEffect(() => {
    const timer = setTimeout(() => {
      void (async () => {
        try {
          const loaded = await api.platformTenantDetail(clientId);
          setDetail(loaded);
          setName(loaded.tenant.name);
          setStatus(loaded.tenant.status);
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
      const refreshed = await api.platformTenantDetail(clientId);
      setDetail({
        ...refreshed,
        tenant: { ...refreshed.tenant, plan_label: updated.plan_label },
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
      setDetail(await api.platformTenantDetail(clientId));
      setError(null);
      setNotice("Changes saved.");
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Quota override failed.",
      );
    }
  }

  async function saveOrganization(event: React.FormEvent) {
    event.preventDefault();
    if (!detail || saving) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await api.platformUpdateOrganization(clientId, {
        name,
        status,
      });
      setDetail({ ...detail, tenant: updated });
      setNotice("Organization updated.");
    } catch {
      setError(
        "Could not update the organization. Check the entered values and try again.",
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <main className="platform-client-detail">
      <h1 data-testid="client-detail-name">
        {detail?.tenant.name ?? "Organization"}
      </h1>
      <p className="page-purpose">
        Inspect organization health and manage plans, quotas and bot
        availability.
      </p>
      <p className="eyebrow">
        <a href="/platform">? Back to Organizations</a>
      </p>
      {error && <Notice message={error} tone="error" />}
      {notice && <Notice message={notice} />}
      {!error && !detail && <Loading label="Loading organization?" />}
      {detail && (
        <>
          <nav role="tablist" aria-label="Organization tabs">
            {["Overview", "Members", "Bots", "Knowledge"].map((item) => (
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
          {tab === "Overview" && (
            <div role="tabpanel" aria-label="Overview">
              <p data-testid="client-detail-status">
                {detail.tenant.slug} ?{" "}
                <span data-status={detail.tenant.status}>
                  {detail.tenant.status}
                </span>{" "}
                ? usage events: {detail.usage_events}
              </p>
              <p>
                Created{" "}
                {new Date(detail.tenant.created_at).toLocaleDateString()} ?{" "}
                {detail.counts.members} members ? {detail.counts.bots} bots
              </p>
              <p>
                <a href={`/app/${clientId}/bots`}>Operate bots</a> ?{" "}
                <a href={`/app/${clientId}/settings/data`}>
                  Organization data and deletion
                </a>
              </p>
              <form
                aria-label="Organization settings"
                onSubmit={(event) => void saveOrganization(event)}
              >
                <label>
                  Name
                  <input
                    required
                    maxLength={200}
                    value={name}
                    onChange={(event) => setName(event.target.value)}
                  />
                </label>
                <label>
                  Status
                  <select
                    value={status}
                    onChange={(event) => setStatus(event.target.value)}
                  >
                    <option value="active">Active</option>
                    <option value="archived">Archived</option>
                  </select>
                </label>
                <button type="submit" disabled={saving}>
                  {saving ? "Saving?" : "Save changes"}
                </button>
              </form>
              <section aria-label="Quota usage">
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
              </section>
              <section aria-label="Plan assignment" data-testid="client-plan">
                <h2>Plan assignment</h2>
                <p>
                  Plan limits are provisional; pricing and final limits are
                  still under review.
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
                  <button type="submit" disabled={reason.trim().length < 3}>
                    Save plan
                  </button>
                </form>
                <form onSubmit={(event) => void saveQuotaOverrides(event)}>
                  <label>
                    Quota overrides (JSON)
                    <textarea
                      dir="auto"
                      value={quotaOverrides}
                      onChange={(event) =>
                        setQuotaOverrides(event.target.value)
                      }
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
              <section
                aria-label="Recent audit"
                data-testid="client-detail-audit"
              >
                <h2>Recent audit</h2>
                {detail.recent_audit.length === 0 ? (
                  <p className="muted">No audit rows.</p>
                ) : (
                  <ul>
                    {detail.recent_audit.map((row, index) => (
                      <li key={`${row.at}-${index}`}>
                        {row.at.slice(0, 19)} — {auditActionLabel(row.action)}
                        {row.target ? ` (${row.target})` : ""}
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            </div>
          )}
          {tab === "Members" && (
            <div role="tabpanel" aria-label="Members">
              <OrganizationMembers
                organization={clientId}
                refresh={async () =>
                  setDetail(await api.platformTenantDetail(clientId))
                }
              />
              <section aria-label="Members" data-testid="client-detail-members">
                <h2>Members</h2>
                {detail.members.length ? (
                  <table>
                    <thead>
                      <tr>
                        <th>Email</th>
                        <th>Role</th>
                        <th>Status</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {detail.members.map((member) => (
                        <tr key={member.user_id}>
                          <td>{member.email}</td>
                          <td>
                            <select
                              aria-label={`Role for ${member.email}`}
                              value={member.role}
                              onChange={(event) => {
                                void api
                                  .platformUserRole(
                                    member.user_id,
                                    clientId,
                                    event.target.value as api.ClientRole,
                                  )
                                  .then(() =>
                                    api.platformTenantDetail(clientId),
                                  )
                                  .then(setDetail)
                                  .catch((caught) =>
                                    setError(
                                      caught instanceof Error
                                        ? caught.message
                                        : "Role update failed.",
                                    ),
                                  );
                              }}
                            >
                              {["admin", "editor", "viewer"].map((role) => (
                                <option key={role}>{role}</option>
                              ))}
                            </select>
                          </td>
                          <td>{member.status}</td>
                          <td>
                            <ConfirmAction
                              title="Remove membership"
                              description={`Remove ${member.email} from this organization?`}
                              onConfirm={() => {
                                void api
                                  .platformRemoveUser(member.user_id, clientId)
                                  .then(() =>
                                    api.platformTenantDetail(clientId),
                                  )
                                  .then(setDetail)
                                  .catch((caught) =>
                                    setError(
                                      caught instanceof Error
                                        ? caught.message
                                        : "Removal failed.",
                                    ),
                                  );
                              }}
                            >
                              Remove membership
                            </ConfirmAction>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <p>No members yet.</p>
                )}
              </section>
              <section aria-label="Pending invitations">
                <h2>Pending invitations</h2>
                <ul aria-label="Pending invitations">
                  {detail.pending_invitations.map((invite) => (
                    <li key={invite.id}>
                      {invite.email} — {invite.role} (pending invite)
                      <button
                        type="button"
                        onClick={() => {
                          void api
                            .revokeInvitation(clientId, invite.id)
                            .then(() => api.platformTenantDetail(clientId))
                            .then(setDetail)
                            .catch((caught) =>
                              setError(
                                caught instanceof Error
                                  ? caught.message
                                  : "Could not revoke invitation.",
                              ),
                            );
                        }}
                      >
                        Revoke invitation
                      </button>
                    </li>
                  ))}
                </ul>
              </section>
            </div>
          )}
          {tab === "Bots" && (
            <div role="tabpanel" aria-label="Bots">
              <CreateBotForm
                organization={{ id: clientId, name: detail.tenant.name }}
                onCreated={async () =>
                  setDetail(await api.platformTenantDetail(clientId))
                }
              />
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
              <section aria-label="Bots" data-testid="client-detail-bots">
                <h2>Bots</h2>
                {detail.bots.length ? (
                  <table>
                    <thead>
                      <tr>
                        <th>Name</th>
                        <th>Status</th>
                        <th>Widget</th>
                        <th>Knowledge</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {detail.bots.map((bot) => (
                        <tr key={bot.id}>
                          <td>{bot.name}</td>
                          <td data-status={bot.status}>{bot.status}</td>
                          <td>
                            {bot.widget_state === "configured"
                              ? "Configured"
                              : "Not configured"}
                          </td>
                          <td>
                            {bot.published
                              ? "knowledge published"
                              : "nothing published"}
                          </td>
                          <td>
                            <BotLinks organization={clientId} bot={bot.id} />
                            {bot.status !== "paused" &&
                              bot.status !== "archived" && (
                                <ConfirmAction
                                  title="Pause bot?"
                                  description="The website widget will become unavailable and this bot will stop answering visitors until activated again."
                                  disabled={reason.trim().length < 3}
                                  onConfirm={() => void pauseBot(bot.id)}
                                >
                                  Pause bot
                                </ConfirmAction>
                              )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <p className="muted">No bots yet.</p>
                )}
              </section>
            </div>
          )}
          {tab === "Knowledge" && (
            <section aria-label="Knowledge" role="tabpanel">
              <h2>Knowledge</h2>
              <section
                aria-label="Failed jobs"
                data-testid="client-detail-jobs"
              >
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
