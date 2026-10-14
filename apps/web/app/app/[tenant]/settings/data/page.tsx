"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import * as api from "@/lib/api";
import { roleSatisfies, useSession } from "@/lib/session";
import { Loading, Notice } from "@/lib/ui";

export default function TenantDataPage() {
  const params = useParams<{ tenant: string }>();
  const tenantId = params.tenant;
  const router = useRouter();
  const { me, refresh, roleIn } = useSession();
  const role = roleIn(tenantId);
  const canAdmin = roleSatisfies(role, "admin");
  const isOwner = role === "owner";
  const [tenant, setTenant] = useState<api.Tenant | null>(null);
  const [audit, setAudit] = useState<api.TenantAuditEvent[]>([]);
  const [query, setQuery] = useState("");
  const [confirmName, setConfirmName] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [nextTenant, nextAudit] = await Promise.all([
        api.getTenant(tenantId),
        canAdmin
          ? api.tenantAudit(tenantId, query)
          : Promise.resolve({ events: [] }),
      ]);
      setTenant(nextTenant);
      setAudit(nextAudit.events);
      setError(null);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Could not load tenant data.",
      );
    }
  }, [tenantId, canAdmin, query]);

  useEffect(() => {
    if (!me || !canAdmin) return;
    const timer = setTimeout(() => void load(), 0);
    return () => clearTimeout(timer);
  }, [me, canAdmin, load]);

  async function downloadExport() {
    setBusy(true);
    try {
      const data = await api.exportTenantData(tenantId);
      const blob = new Blob([JSON.stringify(data, null, 2)], {
        type: "application/json;charset=utf-8",
      });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `tenant-${tenantId}-export.json`;
      link.click();
      URL.revokeObjectURL(url);
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Export failed.");
    } finally {
      setBusy(false);
    }
  }

  async function deleteData(event: React.FormEvent) {
    event.preventDefault();
    if (
      !tenant ||
      !isOwner ||
      confirmName !== tenant.name ||
      reason.trim().length < 3
    ) {
      return;
    }
    setBusy(true);
    try {
      await api.deleteTenantData(tenantId, confirmName, reason);
      await refresh();
      router.replace("/app");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Deletion failed.");
    } finally {
      setBusy(false);
    }
  }

  if (!canAdmin) {
    return (
      <main>
        <h1>Tenant data and audit</h1>
        <p>Administrator access is required.</p>
        <Link href={`/app/${tenantId}/bots`}>Back to bots</Link>
      </main>
    );
  }

  return (
    <main>
      <h1>Tenant data and audit</h1>
      <p>
        <Link href={`/app/${tenantId}/bots`}>Back to bots</Link>
      </p>
      {error && <Notice message={error} tone="error" />}
      {!tenant ? (
        <Loading label="Loading tenant data…" />
      ) : (
        <>
          <section aria-label="Tenant export">
            <h2>Export tenant data</h2>
            <p>
              Downloads contacts, identities, conversations, messages,
              knowledge, jobs, usage, and audit history as JSON.
            </p>
            <button
              type="button"
              disabled={busy}
              onClick={() => void downloadExport()}
            >
              {busy ? "Working…" : "Download export"}
            </button>
          </section>
          <section aria-label="Tenant audit review">
            <h2>Audit review</h2>
            <form
              onSubmit={(event) => {
                event.preventDefault();
                void load();
              }}
            >
              <label>
                Search actions
                <input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  maxLength={100}
                />
              </label>
              <button type="submit">Search</button>
            </form>
            <ul>
              {audit.map((event) => (
                <li key={event.id}>
                  {event.created_at.slice(0, 19)} · {event.action} ·{" "}
                  {event.target_type ?? "tenant"}:{event.target_id ?? ""}
                </li>
              ))}
            </ul>
          </section>
          {isOwner && (
            <section aria-label="Delete tenant data">
              <h2>Delete organization and data</h2>
              <p>
                This permanently removes the organization’s bots, knowledge,
                contacts, identities, conversations, and messages. The deletion
                request is audited.
              </p>
              <form onSubmit={(event) => void deleteData(event)}>
                <label>
                  Type <strong>{tenant.name}</strong> to confirm
                  <input
                    value={confirmName}
                    onChange={(event) => setConfirmName(event.target.value)}
                    required
                  />
                </label>
                <label>
                  Reason for deletion
                  <input
                    value={reason}
                    onChange={(event) => setReason(event.target.value)}
                    minLength={3}
                    maxLength={500}
                    required
                  />
                </label>
                <button
                  type="submit"
                  disabled={
                    busy ||
                    confirmName !== tenant.name ||
                    reason.trim().length < 3
                  }
                >
                  Permanently delete organization
                </button>
              </form>
            </section>
          )}
        </>
      )}
    </main>
  );
}
