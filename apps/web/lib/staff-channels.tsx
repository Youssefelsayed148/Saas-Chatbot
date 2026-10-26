"use client";

import { useCallback, useEffect, useState } from "react";

import * as api from "@/lib/api";
import { humanLabel } from "@/lib/labels";
import {
  Button,
  Card,
  ConfirmAction,
  DataTable,
  Field,
  FormSection,
  LinkButton,
  Loading,
  Notice,
  StatusBadge,
  Switch,
  type StatusTone,
} from "@/lib/ui";
import "@/app/channels-screen.css";

/** Staff Channels (P6, docs/17): connections of ONE organization (create with
 * a copy-once secret, pause/resume/revoke, AI toggle, rotate, check now) and
 * the staff overview list across all organizations. Many URLs, refs and
 * secrets never reach client roles. */

const CHANNELS = ["whatsapp", "messenger", "instagram"];

const HEALTH_TONE: Record<string, StatusTone> = {
  healthy: "success",
  degraded: "warning",
  unhealthy: "danger",
  unknown: "neutral",
};

const STATUS_TONE: Record<string, StatusTone> = {
  active: "success",
  paused: "warning",
  revoked: "danger",
};

function when(value: string | null, none: string): string {
  return value ? new Date(value).toLocaleString() : none;
}

/** Health with its reason, e.g. "Degraded · Token expiring". */
export function HealthBadge({
  connection,
}: {
  connection: Pick<
    api.PlatformChannelConnection,
    "health_status" | "health_reason" | "health_detail"
  >;
}) {
  return (
    <span data-testid="channel-health">
      <StatusBadge
        value={connection.health_status}
        tone={HEALTH_TONE[connection.health_status]}
      >
        {humanLabel(connection.health_status)}
      </StatusBadge>
      {connection.health_reason && (
        <small className="muted">
          {" "}
          {humanLabel(connection.health_reason)}
          {connection.health_detail ? ` · ${connection.health_detail}` : ""}
        </small>
      )}
    </span>
  );
}

function ConnectionActions({
  connection,
  busy,
  onAction,
  onRotate,
  onCheck,
}: {
  connection: api.PlatformChannelConnection;
  busy: boolean;
  onAction: (id: string, action: "pause" | "resume" | "revoke") => void;
  onRotate: (id: string) => void;
  onCheck: (id: string) => void;
}) {
  if (connection.status === "revoked") {
    return <span className="muted">No actions</span>;
  }
  return (
    <div className="action-row">
      {connection.status === "active" && (
        <Button
          variant="quiet"
          disabled={busy}
          onClick={() => onAction(connection.id, "pause")}
        >
          Pause
        </Button>
      )}
      {connection.status === "paused" && (
        <Button
          variant="quiet"
          disabled={busy}
          onClick={() => onAction(connection.id, "resume")}
        >
          Resume
        </Button>
      )}
      <Button
        variant="quiet"
        disabled={busy}
        onClick={() => onCheck(connection.id)}
      >
        Check now
      </Button>
      <ConfirmAction
        title="Rotate the connection secret?"
        description="Many keeps accepting the previous secret for 24 hours. The new secret is shown once and must be stored in Many."
        confirmLabel="Rotate"
        disabled={busy}
        onConfirm={() => onRotate(connection.id)}
      >
        Rotate secret
      </ConfirmAction>
      <ConfirmAction
        title="Revoke this connection?"
        description="A revoked connection stops processing events permanently and cannot be resumed."
        confirmLabel="Revoke"
        disabled={busy}
        onConfirm={() => onAction(connection.id, "revoke")}
      >
        Revoke
      </ConfirmAction>
    </div>
  );
}

function SecretReveal({
  secret,
  onDone,
}: {
  secret: string;
  onDone: () => void;
}) {
  const [copied, setCopied] = useState(false);
  return (
    <Card title="Signing secret" data-testid="channel-secret-reveal">
      <p>
        Copy this secret into Many now. It is shown <strong>only once</strong>.
      </p>
      <code dir="ltr" data-testid="channel-secret" className="mono">
        {secret}
      </code>
      <div className="action-row">
        <Button
          onClick={() => {
            navigator.clipboard
              .writeText(secret)
              .then(() => setCopied(true))
              .catch(() => setCopied(false));
          }}
        >
          {copied ? "Copied" : "Copy secret"}
        </Button>
        <Button variant="quiet" onClick={onDone}>
          I saved the secret
        </Button>
      </div>
      {!copied && (
        <small className="muted">
          Copying needs browser permission; selecting the text works too.
        </small>
      )}
    </Card>
  );
}

function CreateConnection({
  tenantId,
  bots,
  busy,
  onCreate,
}: {
  tenantId: string;
  bots: { id: string; name: string; status?: string }[];
  busy: boolean;
  onCreate: (
    payload: Parameters<typeof api.createChannelConnection>[0],
  ) => void;
}) {
  const [bot, setBot] = useState("");
  const [channel, setChannel] = useState("whatsapp");
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [ref, setRef] = useState("");
  const usable = bots.filter((item) => item.status !== "archived");
  return (
    <FormSection
      title="Create a channel connection"
      description="Connect one assistant to one Many channel. The signing secret is shown once after creation."
      data-testid="channels-create"
    >
      <form
        className="stack"
        onSubmit={(event) => {
          event.preventDefault();
          if (!bot) return;
          onCreate({
            tenant_id: tenantId,
            bot_id: bot,
            channel,
            display_name: name.trim(),
            many_base_url: url.trim(),
            many_channel_ref: ref.trim() || undefined,
          });
          setName("");
          setUrl("");
          setRef("");
        }}
      >
        <Field label="Assistant" required>
          {(control) => (
            <select
              {...control}
              required
              value={bot}
              onChange={(event) => setBot(event.target.value)}
            >
              <option value="">Select an assistant</option>
              {usable.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          )}
        </Field>
        <Field label="Channel">
          {(control) => (
            <select
              {...control}
              value={channel}
              onChange={(event) => setChannel(event.target.value)}
            >
              {CHANNELS.map((value) => (
                <option key={value} value={value}>
                  {humanLabel(value)}
                </option>
              ))}
            </select>
          )}
        </Field>
        <Field label="Connection name" required>
          {(control) => (
            <input
              {...control}
              required
              dir="auto"
              maxLength={120}
              value={name}
              placeholder="Support WhatsApp"
              onChange={(event) => setName(event.target.value)}
            />
          )}
        </Field>
        <Field label="Many base URL" required>
          {(control) => (
            <input
              {...control}
              required
              dir="ltr"
              type="url"
              maxLength={500}
              value={url}
              placeholder="https://chat.example.com"
              onChange={(event) => setUrl(event.target.value)}
            />
          )}
        </Field>
        <Field
          label="Many channel reference"
          hint="Optional. One live connection per channel reference."
        >
          {(control) => (
            <input
              {...control}
              dir="ltr"
              maxLength={128}
              value={ref}
              onChange={(event) => setRef(event.target.value)}
            />
          )}
        </Field>
        <div>
          <Button type="submit" disabled={busy || !bot}>
            Create connection
          </Button>
        </div>
      </form>
    </FormSection>
  );
}

/** The Channels tab of one organization workspace. */
export function OrganizationChannels({
  tenantId,
  bots,
}: {
  tenantId: string;
  bots: { id: string; name: string; status?: string }[];
}) {
  const [connections, setConnections] = useState<
    api.PlatformChannelConnection[] | null
  >(null);
  const [secret, setSecret] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const listing = await api.listChannelConnections(tenantId);
      setConnections(listing.items);
      setError(null);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Could not load channels.",
      );
    }
  }, [tenantId]);

  useEffect(() => {
    const timer = setTimeout(() => void load(), 0);
    return () => clearTimeout(timer);
  }, [load]);

  async function run(action: () => Promise<unknown>, message: string) {
    if (busy) return;
    setBusy(true);
    try {
      await action();
      await load();
      setError(null);
      setNotice(message);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The action failed.");
    } finally {
      setBusy(false);
    }
  }

  const botName = (id: string) =>
    bots.find((bot) => bot.id === id)?.name ?? "Assistant";

  return (
    <div className="stack" data-testid="org-channels">
      {error && (
        <Notice message={error} tone="error" onRetry={() => void load()} />
      )}
      {notice && <Notice message={notice} />}
      {secret && (
        <SecretReveal secret={secret} onDone={() => setSecret(null)} />
      )}
      <Card title="Connections" data-testid="channels-list">
        {connections === null ? (
          !error && <Loading label="Loading channels…" />
        ) : (
          <DataTable
            caption="Channel connections"
            rows={connections}
            rowKey={(connection) => connection.id}
            empty={<p className="muted">No channel connections yet.</p>}
            columns={[
              {
                key: "name",
                header: "Connection",
                cell: (connection) => (
                  <span
                    data-testid="channel-row"
                    data-channel={connection.channel}
                  >
                    <strong dir="auto">{connection.display_name}</strong>
                    <br />
                    <small className="muted">
                      {humanLabel(connection.channel)} ·{" "}
                      {botName(connection.bot_id)}
                    </small>
                  </span>
                ),
              },
              {
                key: "status",
                header: "Status",
                cell: (connection) => (
                  <StatusBadge
                    value={connection.status}
                    tone={STATUS_TONE[connection.status]}
                  >
                    {humanLabel(connection.status)}
                  </StatusBadge>
                ),
              },
              {
                key: "health",
                header: "Health",
                cell: (connection) => <HealthBadge connection={connection} />,
              },
              {
                key: "signals",
                header: "Signals",
                cell: (connection) => (
                  <small className="muted">
                    Health: {when(connection.health_updated_at, "none yet")}
                    <br />
                    Last event: {when(connection.last_event_at, "none yet")}
                    <br />
                    <span dir="ltr">{connection.many_base_url}</span>
                    {connection.many_channel_ref && (
                      <>
                        {" "}
                        · ref{" "}
                        <span dir="ltr">{connection.many_channel_ref}</span>
                      </>
                    )}
                  </small>
                ),
              },
              {
                key: "ai",
                header: "AI replies",
                cell: (connection) => (
                  <Switch
                    checked={connection.ai_enabled}
                    disabled={busy || connection.status === "revoked"}
                    aria-label={`Allow AI replies on ${connection.display_name}`}
                    label="Allow AI"
                    onChange={(enabled) =>
                      void run(
                        () =>
                          api.updateChannelConnection(connection.id, {
                            ai_enabled: enabled,
                          }),
                        enabled ? "AI replies allowed." : "AI replies paused.",
                      )
                    }
                  />
                ),
              },
              {
                key: "actions",
                header: "Actions",
                cell: (connection) => (
                  <ConnectionActions
                    connection={connection}
                    busy={busy}
                    onAction={(id, action) =>
                      void run(
                        () => api.channelConnectionStatusAction(id, action),
                        action === "pause"
                          ? "Connection paused."
                          : action === "resume"
                            ? "Connection resumed."
                            : "Connection revoked.",
                      )
                    }
                    onRotate={(id) =>
                      void run(async () => {
                        const rotated = await api.rotateChannelSecret(id);
                        setSecret(rotated.secret);
                      }, "Secret rotated; store it in Many now.")
                    }
                    onCheck={(id) =>
                      void run(
                        () => api.checkChannelHealth(id),
                        "Health check completed.",
                      )
                    }
                  />
                ),
              },
            ]}
          />
        )}
      </Card>
      <CreateConnection
        tenantId={tenantId}
        bots={bots}
        busy={busy}
        onCreate={(payload) =>
          void run(async () => {
            const created = await api.createChannelConnection(payload);
            setSecret(created.secret);
          }, "Connection created; store the secret in Many now.")
        }
      />
    </div>
  );
}

/** Staff overview across organizations; managing happens in the organization. */
export function ChannelsOverview() {
  const [connections, setConnections] = useState<
    api.PlatformChannelConnection[] | null
  >(null);
  const [tenants, setTenants] = useState<api.PlatformTenantRow[]>([]);
  const [filter, setFilter] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [listing, rows] = await Promise.all([
        api.listChannelConnections(),
        api.platformTenants("limit=200"),
      ]);
      setConnections(listing.items);
      setTenants(rows.tenants);
      setError(null);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Could not load channels.",
      );
    }
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => void load(), 0);
    return () => clearTimeout(timer);
  }, [load]);

  if (connections === null) {
    return error ? (
      <Notice message={error} tone="error" onRetry={() => void load()} />
    ) : (
      <Loading label="Loading channels…" />
    );
  }
  const shown = filter
    ? connections.filter((connection) => connection.tenant_id === filter)
    : connections;
  const live = connections.filter(
    (connection) => connection.status !== "revoked",
  ).length;
  const tenantName = (id: string) =>
    tenants.find((tenant) => tenant.id === id)?.name ?? "Organization";
  return (
    <div className="stack">
      <Card title="Connections" data-testid="channels-list">
        <p data-testid="channels-summary">
          {live} active or paused connection{live === 1 ? "" : "s"} ·{" "}
          {shown.length} shown
        </p>
        <Field label="Organization">
          {(control) => (
            <select
              {...control}
              data-testid="channels-tenant-filter"
              value={filter}
              onChange={(event) => setFilter(event.target.value)}
            >
              <option value="">All organizations</option>
              {tenants.map((tenant) => (
                <option key={tenant.id} value={tenant.id}>
                  {tenant.name}
                </option>
              ))}
            </select>
          )}
        </Field>
        <DataTable
          caption="All channel connections"
          rows={shown}
          rowKey={(connection) => connection.id}
          empty={<p className="muted">No channel connections yet.</p>}
          columns={[
            {
              key: "name",
              header: "Connection",
              cell: (connection) => (
                <span
                  data-testid="channel-row"
                  data-channel={connection.channel}
                >
                  <strong dir="auto">{connection.display_name}</strong>
                  <br />
                  <small className="muted">
                    {humanLabel(connection.channel)}
                  </small>
                </span>
              ),
            },
            {
              key: "org",
              header: "Organization",
              cell: (connection) => tenantName(connection.tenant_id),
            },
            {
              key: "status",
              header: "Status",
              cell: (connection) => (
                <StatusBadge
                  value={connection.status}
                  tone={STATUS_TONE[connection.status]}
                >
                  {humanLabel(connection.status)}
                </StatusBadge>
              ),
            },
            {
              key: "health",
              header: "Health",
              cell: (connection) => <HealthBadge connection={connection} />,
            },
            {
              key: "event",
              header: "Last event",
              cell: (connection) => when(connection.last_event_at, "None yet"),
            },
            {
              key: "manage",
              header: "Manage",
              cell: (connection) => (
                <LinkButton
                  variant="secondary"
                  size="sm"
                  href={`/platform/clients/${connection.tenant_id}?tab=Channels`}
                >
                  Open organization
                </LinkButton>
              ),
            },
          ]}
        />
      </Card>
    </div>
  );
}
