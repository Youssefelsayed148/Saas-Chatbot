"use client";

import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { auditActionLabel } from "@/lib/labels";
import * as api from "@/lib/api";
import {
  Button,
  Card,
  ConfirmAction,
  DataTable,
  Field,
  Loading,
  Notice,
  PageHeader,
  StatusBadge,
  TabPanel,
  Tabs,
} from "@/lib/ui";
import { OrganizationMembers, focusAfterRemoval } from "@/lib/staff-members";
import { BotLinks, CreateBotForm } from "@/lib/staff-bots";
import { Icon } from "@/lib/icons";
import "@/app/staff-screens.css";

/** Client detail (P4-06, docs/11): bots + status, failed jobs, members and
 * roles, recent audit rows, usage. Read-only staff view (no impersonation). */

const TABS = ["Overview", "Members", "Bots", "Knowledge"] as const;

/** Why a bot is still a draft, derived only from fields the API already
 * returns (a draft bot is not answering visitors yet). */
function draftNote(bot: api.PlatformTenantDetail["bots"][number]): string {
  const missing: string[] = [];
  if (!bot.published) missing.push("no published knowledge");
  if (bot.widget_state !== "configured") missing.push("widget not configured");
  return missing.length
    ? `Not live yet: ${missing.join(", ")}.`
    : "Not live yet: waiting to be activated.";
}

export default function PlatformClientPage() {
  const params = useParams<{ clientId: string }>();
  const clientId = params.clientId;
  const [detail, setDetail] = useState<api.PlatformTenantDetail | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<string>("Overview");
  const [name, setName] = useState("");
  const [status, setStatus] = useState("active");
  const [saving, setSaving] = useState(false);
  const [planLabel, setPlanLabel] = useState("");
  const [reason, setReason] = useState("");
  const [quotaOverrides, setQuotaOverrides] = useState('{"bots": 4}');
  const membersSection = useRef<HTMLElement>(null);
  const invitationsSection = useRef<HTMLElement>(null);

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
    <main className="platform-client-detail staff-page">
      <PageHeader
        title={
          <span data-testid="client-detail-name">
            {detail?.tenant.name ?? "Organization"}
          </span>
        }
        eyebrow={
          <a href="/platform">
            <Icon name="arrow-left" /> Back to Organizations
          </a>
        }
        purpose="Inspect organization health and manage plans, quotas and bot availability."
      />
      {error && <Notice message={error} tone="error" />}
      {notice && <Notice message={notice} />}
      {!error && !detail && <Loading label="Loading organization…" />}
      {detail && (
        <>
          <Tabs
            aria-label="Organization tabs"
            idPrefix="org"
            tabs={TABS.map((item) => ({ id: item, label: item }))}
            value={tab}
            onChange={setTab}
          />
          <TabPanel idPrefix="org" tabId="Overview" active={tab === "Overview"}>
            <p data-testid="client-detail-status" className="status-line">
              {detail.tenant.slug} ·{" "}
              <StatusBadge
                value={detail.tenant.status}
                data-status={detail.tenant.status}
              />{" "}
              · usage events: {detail.usage_events}
            </p>
            <p className="muted">
              Created {new Date(detail.tenant.created_at).toLocaleDateString()}{" "}
              · {detail.counts.members} members · {detail.counts.bots} bots
            </p>
            <p className="action-row">
              <a className="primary-link" href={`/app/${clientId}/bots`}>
                Operate bots
              </a>
              <a href={`/app/${clientId}/settings/data`}>
                Organization data and deletion
              </a>
            </p>
            <section className="form-section">
              <header>
                <h2>Organization settings</h2>
              </header>
              <form
                aria-label="Organization settings"
                onSubmit={(event) => void saveOrganization(event)}
              >
                <Field label="Name">
                  {(control) => (
                    <input
                      {...control}
                      required
                      maxLength={200}
                      value={name}
                      onChange={(event) => setName(event.target.value)}
                    />
                  )}
                </Field>
                <Field label="Status">
                  {(control) => (
                    <select
                      {...control}
                      value={status}
                      onChange={(event) => setStatus(event.target.value)}
                    >
                      <option value="active">Active</option>
                      <option value="archived">Archived</option>
                    </select>
                  )}
                </Field>
                <Button type="submit" disabled={saving}>
                  {saving ? "Saving…" : "Save changes"}
                </Button>
              </form>
            </section>
            <section aria-label="Quota usage" className="form-section">
              <header>
                <h2>Quota usage</h2>
              </header>
              <DataTable
                caption="Quota usage versus limits"
                rows={Object.entries(detail.quota.usage)}
                rowKey={([key]) => key}
                columns={[
                  {
                    key: "quota",
                    header: "Quota",
                    cell: ([key]) => key.replaceAll("_", " "),
                  },
                  {
                    key: "used",
                    header: "Used",
                    className: "num",
                    cell: ([, used]) => used,
                  },
                  {
                    key: "limit",
                    header: "Limit",
                    className: "num",
                    cell: ([key]) => detail.quota.limits[key],
                  },
                ]}
              />
            </section>
            <section
              aria-label="Plan assignment"
              data-testid="client-plan"
              className="form-section"
            >
              <header>
                <h2>Plan assignment</h2>
                <p>
                  Plan limits are provisional; pricing and final limits are
                  still under review.
                </p>
              </header>
              <Field
                label="Reason"
                hint="Required (3+ characters) for plan, quota and pause actions. It is recorded in the audit log."
              >
                {(control) => (
                  <input
                    {...control}
                    value={reason}
                    onChange={(event) => setReason(event.target.value)}
                    minLength={3}
                    maxLength={500}
                    required
                  />
                )}
              </Field>
              <form onSubmit={(event) => void assignPlan(event)}>
                <Field label="Plan label">
                  {(control) => (
                    <input
                      {...control}
                      value={planLabel || detail.tenant.plan_label}
                      onChange={(event) => setPlanLabel(event.target.value)}
                      maxLength={40}
                      required
                    />
                  )}
                </Field>
                <Button type="submit" disabled={reason.trim().length < 3}>
                  Save plan
                </Button>
              </form>
              <form onSubmit={(event) => void saveQuotaOverrides(event)}>
                <Field label="Quota overrides (JSON)">
                  {(control) => (
                    <textarea
                      {...control}
                      dir="auto"
                      value={quotaOverrides}
                      onChange={(event) =>
                        setQuotaOverrides(event.target.value)
                      }
                      rows={3}
                      maxLength={1000}
                      required
                    />
                  )}
                </Field>
                <Button type="submit" disabled={reason.trim().length < 3}>
                  Save override with reason
                </Button>
              </form>
            </section>
            <section
              aria-label="Recent audit"
              data-testid="client-detail-audit"
              className="form-section"
            >
              <header>
                <h2>Recent audit</h2>
              </header>
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
          </TabPanel>
          <TabPanel idPrefix="org" tabId="Members" active={tab === "Members"}>
            <OrganizationMembers
              organization={clientId}
              refresh={async () =>
                setDetail(await api.platformTenantDetail(clientId))
              }
            />
            <section
              ref={membersSection}
              aria-label="Members"
              data-testid="client-detail-members"
              className="form-section"
            >
              <header>
                <h2>Members</h2>
              </header>
              {detail.members.length ? (
                <DataTable
                  caption="Organization members"
                  rows={detail.members}
                  rowKey={(member) => member.user_id}
                  columns={[
                    {
                      key: "email",
                      header: "Email",
                      cell: (member) => member.email,
                    },
                    {
                      key: "role",
                      header: "Role",
                      cell: (member) => (
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
                              .then(() => api.platformTenantDetail(clientId))
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
                      ),
                    },
                    {
                      key: "status",
                      header: "Status",
                      cell: (member) => <StatusBadge value={member.status} />,
                    },
                    {
                      key: "actions",
                      header: "Actions",
                      cell: (member) => (
                        <ConfirmAction
                          title="Remove membership"
                          description={`Remove ${member.email} from this organization?`}
                          onConfirm={() => {
                            void api
                              .platformRemoveUser(member.user_id, clientId)
                              .then(() => api.platformTenantDetail(clientId))
                              .then((next) => {
                                setDetail(next);
                                focusAfterRemoval(membersSection.current);
                              })
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
                      ),
                    },
                  ]}
                />
              ) : (
                <p>No members yet.</p>
              )}
            </section>
            <section
              ref={invitationsSection}
              aria-label="Pending invitations"
              className="form-section"
            >
              <header>
                <h2>Pending invitations</h2>
              </header>
              {detail.pending_invitations.length === 0 && (
                <p className="muted">No pending invitations.</p>
              )}
              <ul aria-label="Pending invitations" className="plain-list">
                {detail.pending_invitations.map((invite) => (
                  <li key={invite.id}>
                    <span>
                      {invite.email} — {invite.role} (pending invite)
                    </span>
                    <Button
                      variant="quiet"
                      onClick={() => {
                        void api
                          .revokeInvitation(clientId, invite.id)
                          .then(() => api.platformTenantDetail(clientId))
                          .then((next) => {
                            setDetail(next);
                            focusAfterRemoval(
                              invitationsSection.current,
                              "ul button",
                            );
                          })
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
                    </Button>
                  </li>
                ))}
              </ul>
            </section>
          </TabPanel>
          <TabPanel idPrefix="org" tabId="Bots" active={tab === "Bots"}>
            <CreateBotForm
              organization={{ id: clientId, name: detail.tenant.name }}
              onCreated={async () =>
                setDetail(await api.platformTenantDetail(clientId))
              }
            />
            <section
              aria-label="Bots"
              data-testid="client-detail-bots"
              className="form-section"
            >
              <header>
                <h2>Bots</h2>
              </header>
              <Field
                label="Reason"
                hint="Required (3+ characters) to pause a bot. It is recorded in the audit log."
              >
                {(control) => (
                  <input
                    {...control}
                    value={reason}
                    onChange={(event) => setReason(event.target.value)}
                    minLength={3}
                    maxLength={500}
                    required
                  />
                )}
              </Field>
              {detail.bots.length ? (
                <DataTable
                  caption="Organization bots"
                  rows={detail.bots}
                  rowKey={(bot) => bot.id}
                  columns={[
                    {
                      key: "name",
                      header: "Name",
                      cell: (bot) => bot.name,
                    },
                    {
                      key: "status",
                      header: "Status",
                      cell: (bot) => (
                        <>
                          <StatusBadge
                            value={bot.status}
                            data-status={bot.status}
                          />
                          {bot.status === "draft" && (
                            <small className="cell-note">
                              {draftNote(bot)}
                            </small>
                          )}
                        </>
                      ),
                    },
                    {
                      key: "widget",
                      header: "Widget",
                      cell: (bot) =>
                        bot.widget_state === "configured"
                          ? "Configured"
                          : "Not configured",
                    },
                    {
                      key: "knowledge",
                      header: "Knowledge",
                      cell: (bot) =>
                        bot.published
                          ? "knowledge published"
                          : "nothing published",
                    },
                    {
                      key: "actions",
                      header: "Actions",
                      cell: (bot) => (
                        <div className="row-actions">
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
                        </div>
                      ),
                    },
                  ]}
                />
              ) : (
                <p className="muted">No bots yet.</p>
              )}
            </section>
          </TabPanel>
          <TabPanel
            idPrefix="org"
            tabId="Knowledge"
            active={tab === "Knowledge"}
          >
            <section
              aria-label="Failed jobs"
              data-testid="client-detail-jobs"
              className="form-section"
            >
              <header>
                <h2>Knowledge/ingest failures</h2>
              </header>
              {detail.failed_jobs.length === 0 ? (
                <p className="muted">No failed jobs.</p>
              ) : (
                <ul className="plain-list">
                  {detail.failed_jobs.map((job) => (
                    <li key={job.id}>
                      {job.type}: {job.error ?? "failed"}
                    </li>
                  ))}
                </ul>
              )}
            </section>
            {detail.bots.length ? (
              <Card title="Knowledge by bot">
                <DataTable
                  caption="Knowledge by bot"
                  rows={detail.bots}
                  rowKey={(bot) => bot.id}
                  columns={[
                    { key: "bot", header: "Bot", cell: (bot) => bot.name },
                    {
                      key: "sources",
                      header: "Sources",
                      className: "num",
                      cell: (bot) => bot.source_count,
                    },
                    {
                      key: "ingestion",
                      header: "Last ingestion",
                      cell: (bot) => bot.last_ingestion_job_status ?? "None",
                    },
                    {
                      key: "revision",
                      header: "Published revision",
                      cell: (bot) =>
                        bot.published_revision_id ? (
                          <>
                            <span className="mono" dir="ltr">
                              {bot.published_revision_id}
                            </span>{" "}
                            ·{" "}
                            {bot.published_at
                              ? new Date(bot.published_at).toLocaleDateString()
                              : "Date unavailable"}
                          </>
                        ) : (
                          "None"
                        ),
                    },
                    {
                      key: "open",
                      header: "Open",
                      cell: (bot) => (
                        <a href={`/app/${clientId}/bots/${bot.id}/knowledge`}>
                          Open Knowledge
                        </a>
                      ),
                    },
                  ]}
                />
              </Card>
            ) : (
              <p>No bots in this organization yet.</p>
            )}
          </TabPanel>
        </>
      )}
    </main>
  );
}
