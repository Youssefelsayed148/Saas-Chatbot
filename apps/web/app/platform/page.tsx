"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import * as api from "@/lib/api";
import { useSession } from "@/lib/session";
import { Loading, Notice } from "@/lib/ui";

export default function PlatformHomePage() {
  const router = useRouter();
  const { refresh } = useSession();
  const [rows, setRows] = useState<api.PlatformTenantRow[] | null>(null);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState({ q: "", status: "" });
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [plan, setPlan] = useState("starter");
  const [pending, setPending] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const load = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      if (search.q) params.set("q", search.q);
      if (search.status) params.set("status", search.status);
      setRows((await api.platformTenants(params.toString())).tenants);
      setError(null);
    } catch {
      setError("Could not load organizations.");
    }
  }, [search]);
  useEffect(() => {
    const timer = setTimeout(() => {
      void load();
    }, 0);
    return () => clearTimeout(timer);
  }, [load]);

  async function create(event: React.FormEvent) {
    event.preventDefault();
    if (pending) return;
    setPending(true);
    setFormError(null);
    try {
      const created = await api.platformCreateOrganization({
        name: name.trim(),
        plan_label: plan,
      });
      await Promise.all([load(), refresh()]);
      router.push(`/platform/clients/${created.id}`);
    } catch {
      setFormError(
        "Could not create the organization. Check the name and plan, then try again.",
      );
    } finally {
      setPending(false);
    }
  }

  return (
    <main className="platform-clients">
      <h1>Platform — Organizations</h1>
      <p className="page-purpose">Find and manage organizations.</p>
      <p className="eyebrow" data-testid="platform-staff-badge">
        Platform staff console
      </p>
      <p>
        <a href="/platform/operations">
          Operations, analytics, and audit review
        </a>
      </p>
      <form
        aria-label="Organization search"
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
            onChange={(e) => setQuery(e.target.value)}
            placeholder="name, slug…"
          />
        </label>
        <label>
          Status
          <select
            data-testid="platform-status"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
          >
            <option value="">All</option>
            <option value="active">active</option>
            <option value="archived">archived</option>
          </select>
        </label>
        <button type="submit">Search</button>
      </form>
      {error && <Notice message={error} tone="error" />}
      <section aria-label="Organizations" data-testid="platform-tenants">
        {rows === null ? (
          <Loading label="Loading organizations…" />
        ) : rows.length === 0 ? (
          <p className="muted">No organizations match.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Organization</th>
                <th>Plan</th>
                <th>Status</th>
                <th>Bots</th>
                <th>Seats</th>
                <th>Messages (this month)</th>
                <th>Last activity</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
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
      <section
        aria-label="Create an organization"
        data-testid="organization-form"
      >
        <h2 id="create-organization">New organization</h2>
        <form onSubmit={(event) => void create(event)}>
          <label>
            Organization name
            <input
              data-testid="organization-name"
              required
              maxLength={200}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <label>
            Plan
            <select
              data-testid="organization-plan"
              value={plan}
              onChange={(e) => setPlan(e.target.value)}
            >
              {["free", "starter", "pro", "business"].map((value) => (
                <option key={value}>{value}</option>
              ))}
            </select>
          </label>
          {formError && <Notice message={formError} tone="error" />}
          <button
            type="submit"
            data-testid="organization-submit"
            disabled={pending}
          >
            {pending ? "Creating…" : "Create organization"}
          </button>
        </form>
      </section>
    </main>
  );
}
