"use client";

import { useCallback, useEffect, useState } from "react";

import * as api from "@/lib/api";
import { Loading, Notice } from "@/lib/ui";

/** Staff onboarding form (P4-06, docs/11): one form → ProvisioningService
 * (tenant + owner one-time invite link + optional bot + skill-output files).
 * Idempotency-Key is generated per submit; a retry reuses the SAME key so the
 * durable record cannot be duplicated. The invite link is shown ONCE. */

export default function PlatformHomePage() {
  const [rows, setRows] = useState<api.PlatformTenantRow[] | null>(null);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState<{ q: string; status: string }>({
    q: "",
    status: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [clientName, setClientName] = useState("");
  const [ownerEmail, setOwnerEmail] = useState("");
  const [botName, setBotName] = useState("Website assistant");
  const [files, setFiles] = useState<FileList | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [inviteLink, setInviteLink] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [requestId, setRequestId] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      if (search.q) params.set("q", search.q);
      if (search.status) params.set("status", search.status);
      const payload = await api.platformTenants(params.toString());
      setRows(payload.tenants);
      setError(null);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Could not load clients.",
      );
    } finally {
      setLoading(false);
    }
  }, [search]);

  useEffect(() => {
    const timer = setTimeout(() => {
      void load();
    }, 0);
    return () => clearTimeout(timer);
  }, [load]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setFormError(null);
    setSubmitting(true);
    const key = crypto.randomUUID();
    try {
      const result = await api.platformOnboard(
        {
          client_name: clientName.trim(),
          owner_email: ownerEmail.trim(),
          bot_name: botName.trim() || null,
        },
        key,
        files,
      );
      setInviteLink(result.result?.owner_invite?.link_path ?? null);
      setRequestId(result.request_id);
      await load();
    } catch (caught) {
      setFormError(
        caught instanceof Error ? caught.message : "Onboarding failed.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="platform-clients">
      <h1>Platform — clients</h1>
      <p className="page-purpose">
        Find client workspaces and onboard a new organization.
      </p>
      <p className="eyebrow" data-testid="platform-staff-badge">
        Platform staff console
      </p>
      <p>
        <a href="/platform/operations">
          Operations, analytics, and audit review
        </a>
      </p>

      <form
        aria-label="Client search"
        data-testid="platform-search"
        onSubmit={(event) => {
          event.preventDefault();
          setSearch({ q: query, status });
        }}
      >
        <label>
          Search
          <input
            data-testid="platform-query"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="name, slug…"
          />
        </label>
        <label>
          Status
          <select
            data-testid="platform-status"
            value={status}
            onChange={(event) => setStatus(event.target.value)}
          >
            <option value="">All</option>
            <option value="active">active</option>
            <option value="archived">archived</option>
          </select>
        </label>
        <button type="submit">Search</button>
      </form>

      {error && <Notice message={error} tone="error" />}
      <section aria-label="Clients" data-testid="platform-tenants">
        {rows === null && loading ? (
          <Loading label="Loading clients…" />
        ) : (rows ?? []).length === 0 ? (
          <p className="muted">No clients match.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Client</th>
                <th>Plan</th>
                <th>Status</th>
                <th>Bots</th>
                <th>Seats</th>
                <th>Messages (this month)</th>
                <th>Last activity</th>
              </tr>
            </thead>
            <tbody>
              {(rows ?? []).map((row) => (
                <tr key={row.id}>
                  <td>
                    <a
                      href={`/platform/clients/${row.id}`}
                      data-testid={`client-${row.slug}`}
                    >
                      {row.name}
                    </a>
                  </td>
                  <td>{row.plan_label}</td>
                  <td data-status={row.status}>{row.status}</td>
                  <td>{row.bots}</td>
                  <td>{row.seats}</td>
                  <td>{row.messages_this_month}</td>
                  <td>{row.last_activity ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section aria-label="Onboard a new client" data-testid="onboarding-form">
        <h2>Onboard a new client</h2>
        <form onSubmit={(event) => void submit(event)}>
          <label>
            Client name
            <input
              data-testid="ob-client-name"
              required
              maxLength={200}
              value={clientName}
              onChange={(event) => setClientName(event.target.value)}
            />
          </label>
          <label>
            Admin email (one-time invite link, no email)
            <input
              data-testid="ob-owner-email"
              type="email"
              required
              value={ownerEmail}
              onChange={(event) => setOwnerEmail(event.target.value)}
            />
          </label>
          <label>
            Bot name
            <input
              data-testid="ob-bot-name"
              required
              maxLength={100}
              value={botName}
              onChange={(event) => setBotName(event.target.value)}
            />
          </label>
          <label>
            Website-to-knowledge skill output (optional files)
            <input
              data-testid="ob-files"
              type="file"
              multiple
              accept=".md,.txt,.csv,.pdf,.docx"
              onChange={(event) => setFiles(event.target.files)}
            />
          </label>
          {formError && <Notice message={formError} tone="error" />}
          <button type="submit" data-testid="ob-submit" disabled={submitting}>
            {submitting ? "Provisioning…" : "Onboard client"}
          </button>
        </form>
        {inviteLink && (
          <div data-testid="ob-invite-link">
            <p>
              Admin one-time invite link (copy and send it yourself; shown
              once):
            </p>
            <code>{inviteLink}</code>
            {requestId && <p className="muted">Durable request: {requestId}</p>}
          </div>
        )}
      </section>
    </main>
  );
}
