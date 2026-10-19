"use client";

import { useCallback, useEffect, useState } from "react";

import * as api from "@/lib/api";
import { humanLabel, LabelBadge } from "@/lib/labels";
import { ConfirmAction, Loading, Notice } from "@/lib/ui";

/** Staff Channels management (P6-05, PLAN D10/D11): create with a copy-once
 * secret, pause/resume/revoke, AI toggle, secret rotation and an explicit
 * "Check now" signed health pull. Many URLs, refs and secrets never leave
 * this staff page. */

const CHANNELS = ["whatsapp", "messenger", "instagram"];

function ConnectionRow({
  connection,
  busy,
  onAction,
  onToggle,
  onRotate,
  onCheck,
}: {
  connection: api.PlatformChannelConnection;
  busy: boolean;
  onAction: (id: string, action: "pause" | "resume" | "revoke") => void;
  onToggle: (id: string, enabled: boolean) => void;
  onRotate: (id: string) => void;
  onCheck: (id: string) => void;
}) {
  return (
    <li data-testid="channel-row" data-channel={connection.channel}>
      <strong>{connection.display_name}</strong>{" "}
      <span className="badge">{humanLabel(connection.channel)}</span>{" "}
      <LabelBadge value={connection.status} />
      <div data-testid="channel-health">
        {humanLabel(connection.health_status)}
        {connection.health_reason
          ? ` · ${humanLabel(connection.health_reason)}`
          : ""}
        {connection.health_detail ? ` · ${connection.health_detail}` : ""}
      </div>
      <div className="muted">
        <span dir="ltr" className="muted">
          {connection.many_base_url}
        </span>
        {connection.many_channel_ref
          ? ` · ref ${connection.many_channel_ref}`
          : ""}
        {" · "}
        {connection.health_updated_at
          ? `health ${new Date(connection.health_updated_at).toLocaleString()}`
          : "no health signal yet"}
        {" · "}
        {connection.last_event_at
          ? `last event ${new Date(connection.last_event_at).toLocaleString()}`
          : "no events yet"}
        {" · "}
        secret version {connection.secret_key_version}
      </div>
      <label>
        <input
          type="checkbox"
          checked={connection.ai_enabled}
          disabled={busy || connection.status === "revoked"}
          aria-label={`Allow AI replies on ${connection.display_name}`}
          onChange={(event) => onToggle(connection.id, event.target.checked)}
        />{" "}
        Allow AI replies
      </label>
      <div className="action-row">
        {connection.status === "active" && (
          <button
            type="button"
            disabled={busy}
            onClick={() => onAction(connection.id, "pause")}
          >
            Pause
          </button>
        )}
        {connection.status === "paused" && (
          <button
            type="button"
            disabled={busy}
            onClick={() => onAction(connection.id, "resume")}
          >
            Resume
          </button>
        )}
        {connection.status !== "revoked" && (
          <>
            <button
              type="button"
              disabled={busy}
              onClick={() => onCheck(connection.id)}
            >
              Check now
            </button>
            <ConfirmAction
              title="Rotate the connection secret?"
              description="Many keeps accepting the previous secret for 24 hours. The new secret is shown once and must be stored in Many."
              confirmLabel="Rotate"
              onConfirm={() => onRotate(connection.id)}
            >
              Rotate secret
            </ConfirmAction>
            <ConfirmAction
              title="Revoke this connection?"
              description="A revoked connection stops processing events permanently and cannot be resumed."
              confirmLabel="Revoke"
              onConfirm={() => onAction(connection.id, "revoke")}
            >
              Revoke
            </ConfirmAction>
          </>
        )}
      </div>
    </li>
  );
}

export default function PlatformChannelsPage() {
  const [connections, setConnections] = useState<
    api.PlatformChannelConnection[] | null
  >(null);
  const [tenants, setTenants] = useState<api.PlatformTenantRow[]>([]);
  const [bots, setBots] = useState<api.Bot[]>([]);
  const [tenantFilter, setTenantFilter] = useState("");
  // Create wizard state; the secret is held until the operator dismisses it.
  const [wizardTenant, setWizardTenant] = useState("");
  const [wizardBot, setWizardBot] = useState("");
  const [wizardChannel, setWizardChannel] = useState("whatsapp");
  const [wizardName, setWizardName] = useState("");
  const [wizardUrl, setWizardUrl] = useState("");
  const [wizardRef, setWizardRef] = useState("");
  const [secretShown, setSecretShown] = useState<{
    key: string;
    secret: string;
  } | null>(null);
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [listing, tenants] = await Promise.all([
        api.listChannelConnections(),
        api.platformTenants(""),
      ]);
      setConnections(listing.items);
      setTenants(
        tenants.tenants.filter((tenant) => tenant.status === "active"),
      );
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

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const rows = wizardTenant ? await api.listBots(wizardTenant, true) : [];
        if (!cancelled) {
          setBots(rows.filter((bot) => bot.status === "active"));
          setWizardBot("");
        }
      } catch {
        if (!cancelled) setBots([]);
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [wizardTenant]);

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

  async function copySecret(value: string) {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  if (connections === null) {
    return (
      <main className="platform-channels">
        <p className="eyebrow">
          <a href="/platform">← Back to clients</a>
        </p>
        <h1>Channels</h1>
        {error ? (
          <Notice message={error} tone="error" onRetry={() => void load()} />
        ) : (
          <Loading label="Loading channels…" />
        )}
      </main>
    );
  }

  const shown = tenantFilter
    ? connections.filter((connection) => connection.tenant_id === tenantFilter)
    : connections;
  const connectable = connections.filter(
    (connection) => connection.status !== "revoked",
  );
  return (
    <main className="platform-channels">
      <p className="eyebrow">
        <a href="/platform">← Back to clients</a>
      </p>
      <h1>Channels</h1>
      <p className="page-purpose">
        Manage the delegated ManyOsirisChat connections, their secrets and their
        connection health.
      </p>
      {error && (
        <Notice message={error} tone="error" onRetry={() => void load()} />
      )}
      {notice && <Notice message={notice} />}
      <section aria-label="Connection summary" data-testid="channels-summary">
        <p>
          {connectable.length} active or paused connection
          {connectable.length === 1 ? "" : "s"} · {shown.length} shown
        </p>
        <label>
          Client{" "}
          <select
            aria-label="Filter by client"
            data-testid="channels-tenant-filter"
            value={tenantFilter}
            onChange={(event) => setTenantFilter(event.target.value)}
          >
            <option value="">All clients</option>
            {tenants.map((tenant) => (
              <option key={tenant.id} value={tenant.id}>
                {tenant.name}
              </option>
            ))}
          </select>
        </label>
      </section>
      <section aria-label="Create connection" data-testid="channels-create">
        <h2>Create a channel connection</h2>
        <form
          className="channel-create-form"
          onSubmit={(event) => {
            event.preventDefault();
            if (!wizardTenant || !wizardBot) return;
            void run(async () => {
              const created = await api.createChannelConnection({
                tenant_id: wizardTenant,
                bot_id: wizardBot,
                channel: wizardChannel,
                display_name: wizardName.trim(),
                many_base_url: wizardUrl.trim(),
                many_channel_ref: wizardRef.trim() || undefined,
              });
              setSecretShown({ key: created.id, secret: created.secret });
              setWizardName("");
              setWizardUrl("");
              setWizardRef("");
              setCopied(false);
            }, "Connection created; store the secret in Many now.");
          }}
        >
          <label>
            Client{" "}
            <select
              required
              value={wizardTenant}
              onChange={(event) => {
                setWizardTenant(event.target.value);
                setWizardBot("");
              }}
            >
              <option value="">Select a client</option>
              {tenants.map((tenant) => (
                <option key={tenant.id} value={tenant.id}>
                  {tenant.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Assistant{" "}
            <select
              required
              value={wizardBot}
              onChange={(event) => setWizardBot(event.target.value)}
              disabled={!wizardTenant}
            >
              <option value="">Select an assistant</option>
              {bots.map((bot) => (
                <option key={bot.id} value={bot.id}>
                  {bot.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Channel{" "}
            <select
              value={wizardChannel}
              onChange={(event) => setWizardChannel(event.target.value)}
            >
              {CHANNELS.map((channel) => (
                <option key={channel} value={channel}>
                  {humanLabel(channel)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Connection name{" "}
            <input
              required
              dir="auto"
              value={wizardName}
              maxLength={120}
              onChange={(event) => setWizardName(event.target.value)}
              placeholder="Support WhatsApp"
            />
          </label>
          <label>
            Many base URL{" "}
            <input
              required
              dir="ltr"
              type="url"
              value={wizardUrl}
              maxLength={500}
              onChange={(event) => setWizardUrl(event.target.value)}
              placeholder="https://chat.example.com"
            />
          </label>
          <label>
            Many channel reference{" "}
            <input
              dir="ltr"
              value={wizardRef}
              maxLength={128}
              onChange={(event) => setWizardRef(event.target.value)}
              placeholder="optional"
            />
          </label>
          <button type="submit" disabled={busy || !wizardTenant || !wizardBot}>
            Create connection
          </button>
        </form>
        {secretShown && (
          <div data-testid="channel-secret-reveal">
            <p>
              Signing secret for Many (copy and store it in Many now; it is
              shown <strong>only once</strong>):
            </p>
            <code dir="ltr" data-testid="channel-secret">
              {secretShown.secret}
            </code>
            <div className="action-row">
              <button
                type="button"
                onClick={() => void copySecret(secretShown.secret)}
              >
                {copied ? "Copied" : "Copy secret"}
              </button>
              <button
                type="button"
                className="quiet-button"
                onClick={() => {
                  setSecretShown(null);
                  setCopied(false);
                }}
              >
                I saved the secret
              </button>
            </div>
            {!copied && (
              <small>
                Copying requires browser permission; the manual copy also works.
              </small>
            )}
          </div>
        )}
      </section>
      <section aria-label="Channel connections" data-testid="channels-list">
        <h2>Connections</h2>
        {!shown.length ? (
          <p className="muted">No channel connections yet.</p>
        ) : (
          <ul className="channel-list">
            {shown.map((connection) => (
              <ConnectionRow
                key={connection.id}
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
                onToggle={(id, enabled) =>
                  void run(
                    () =>
                      api.updateChannelConnection(id, { ai_enabled: enabled }),
                    enabled ? "AI replies allowed." : "AI replies paused.",
                  )
                }
                onRotate={(id) =>
                  void run(async () => {
                    const rotated = await api.rotateChannelSecret(id);
                    setSecretShown({ key: id, secret: rotated.secret });
                    setCopied(false);
                  }, "Secret rotated; store it in Many now.")
                }
                onCheck={(id) =>
                  void run(
                    () => api.checkChannelHealth(id),
                    "Health check completed.",
                  )
                }
              />
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
