"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import * as api from "@/lib/api";
import { useSession } from "@/lib/session";
import {
  Button,
  DataTable,
  Field,
  Loading,
  Notice,
  PageHeader,
  StatusBadge,
} from "@/lib/ui";
import "@/app/staff-screens.css";

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
    <main className="platform-clients staff-page">
      <PageHeader
        title="Platform — Organizations"
        eyebrow={
          <span data-testid="platform-staff-badge">Platform staff console</span>
        }
        purpose="Find and manage organizations."
        actions={
          <a className="primary-link" href="/platform/operations">
            Operations, analytics, and audit review
          </a>
        }
      />
      <form
        aria-label="Organization search"
        data-testid="platform-search"
        className="filter-bar"
        onSubmit={(event) => {
          event.preventDefault();
          setSearch({ q: query, status });
        }}
      >
        <Field label="Search">
          {(control) => (
            <input
              {...control}
              data-testid="platform-query"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="name, slug…"
            />
          )}
        </Field>
        <Field label="Status">
          {(control) => (
            <select
              {...control}
              data-testid="platform-status"
              value={status}
              onChange={(e) => setStatus(e.target.value)}
            >
              <option value="">All</option>
              <option value="active">active</option>
              <option value="archived">archived</option>
            </select>
          )}
        </Field>
        <Button type="submit">Search</Button>
      </form>
      {error && <Notice message={error} tone="error" />}
      <section aria-label="Organizations" data-testid="platform-tenants">
        {rows === null ? (
          <Loading label="Loading organizations…" />
        ) : (
          <DataTable
            caption="Organization directory"
            rows={rows}
            rowKey={(row) => row.id}
            empty={<p className="muted">No organizations match.</p>}
            columns={[
              {
                key: "organization",
                header: "Organization",
                cell: (row) => (
                  <a
                    href={`/platform/clients/${row.id}`}
                    data-testid={`client-${row.slug}`}
                  >
                    {row.name}
                  </a>
                ),
              },
              { key: "plan", header: "Plan", cell: (row) => row.plan_label },
              {
                key: "status",
                header: "Status",
                cell: (row) => (
                  <StatusBadge value={row.status} data-status={row.status} />
                ),
              },
              {
                key: "bots",
                header: "Bots",
                className: "num",
                cell: (row) => row.bots,
              },
              {
                key: "seats",
                header: "Seats",
                className: "num",
                cell: (row) => row.seats,
              },
              {
                key: "messages",
                header: "Messages (this month)",
                className: "num",
                cell: (row) => row.messages_this_month,
              },
              {
                key: "activity",
                header: "Last activity",
                cell: (row) => row.last_activity ?? "—",
              },
            ]}
          />
        )}
      </section>
      <section
        aria-label="Create an organization"
        data-testid="organization-form"
        className="form-section"
      >
        <header>
          <h2 id="create-organization">New organization</h2>
          <p>Creates the organization and opens its detail page.</p>
        </header>
        <form onSubmit={(event) => void create(event)}>
          <Field label="Organization name">
            {(control) => (
              <input
                {...control}
                data-testid="organization-name"
                required
                maxLength={200}
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            )}
          </Field>
          <Field label="Plan">
            {(control) => (
              <select
                {...control}
                data-testid="organization-plan"
                value={plan}
                onChange={(e) => setPlan(e.target.value)}
              >
                {["free", "starter", "pro", "business"].map((value) => (
                  <option key={value}>{value}</option>
                ))}
              </select>
            )}
          </Field>
          {formError && <Notice message={formError} tone="error" />}
          <Button
            type="submit"
            data-testid="organization-submit"
            disabled={pending}
          >
            {pending ? "Creating…" : "Create organization"}
          </Button>
        </form>
      </section>
    </main>
  );
}
