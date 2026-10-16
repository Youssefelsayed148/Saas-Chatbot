"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

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
  const isOperator = !!me?.is_platform_staff;
  const [counts, setCounts] = useState<Record<string, number>>({});
  const deleteDialog = useRef<HTMLDialogElement>(null);
  const [tenant, setTenant] = useState<api.Tenant | null>(null);
  const [audit, setAudit] = useState<api.TenantAuditEvent[]>([]);
  const [query, setQuery] = useState("");
  const [confirmName, setConfirmName] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      if (isOperator) {
        const preview = await api.deletionPreview(tenantId);
        setCounts(preview.counts);
      }
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
  }, [tenantId, canAdmin, query, isOperator]);

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
      !isOperator ||
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
      <main className="tenant-data-page">
        <h1>Tenant data and audit</h1>
        <p className="page-purpose">
          Export workspace data, review activity and manage organization
          deletion.
        </p>
        <p>Administrator access is required.</p>
        <Link href={`/app/${tenantId}/bots`}>Back to bots</Link>
      </main>
    );
  }

  return (
    <main className="tenant-data-page">
      <h1>Tenant data and audit</h1>
      <p className="page-purpose">
        Export workspace data, review activity and manage organization deletion.
      </p>
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
              Downloads contacts, identities, conversations, messages, usage,
              and audit history as JSON. Platform staff exports also include
              knowledge, jobs and bot configuration.
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
            {audit.length === 0 && (
              <p className="muted">No audit actions match this search.</p>
            )}
            <ul className="audit-list">
              {audit.map((event) => (
                <li key={event.id}>
                  {event.created_at.slice(0, 19)} · {event.action} ·{" "}
                  {event.target_type ?? "tenant"}:{event.target_id ?? ""}
                </li>
              ))}
            </ul>
          </section>
          {isOperator && (
            <section aria-label="Delete tenant data" className="danger-zone">
              <h2>Delete organization and data</h2>
              <p>
                This permanently removes the organization’s bots, knowledge,
                contacts, identities, conversations, and messages. The deletion
                request is audited.
              </p>
              <form
                onSubmit={(event) => {
                  event.preventDefault();
                  if (
                    tenant &&
                    isOperator &&
                    confirmName === tenant.name &&
                    reason.trim().length >= 3
                  ) {
                    setConfirmName("");
                    deleteDialog.current?.showModal();
                  }
                }}
              >
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
                  Schedule organization deletion
                </button>
              </form>
              <dialog ref={deleteDialog} aria-labelledby="delete-tenant-title">
                <h2 id="delete-tenant-title">Delete this organization?</h2>
                <p>
                  This disables {tenant.name} immediately and schedules data and
                  storage removal after the grace period.
                </p>
                <ul>
                  {Object.entries(counts).map(([kind, count]) => (
                    <li key={kind}>
                      {kind}: {count}
                    </li>
                  ))}
                </ul>
                <label>
                  Type the organization name
                  <input
                    aria-label="Confirm organization name"
                    value={confirmName}
                    onChange={(event) => setConfirmName(event.target.value)}
                  />
                </label>
                <div className="action-row">
                  <button
                    className="quiet-button"
                    type="button"
                    autoFocus
                    onClick={() => deleteDialog.current?.close()}
                  >
                    Cancel
                  </button>
                  <button
                    className="danger-button"
                    type="button"
                    disabled={
                      busy ||
                      confirmName !== tenant.name ||
                      reason.trim().length < 3
                    }
                    onClick={(event) => {
                      deleteDialog.current?.close();
                      void deleteData(event);
                    }}
                  >
                    Delete organization now
                  </button>
                </div>
              </dialog>
            </section>
          )}
        </>
      )}
    </main>
  );
}
