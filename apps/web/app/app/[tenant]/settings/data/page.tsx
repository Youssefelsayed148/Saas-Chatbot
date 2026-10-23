"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { auditActionLabel } from "@/lib/labels";
import * as api from "@/lib/api";
import { roleSatisfies, useSession } from "@/lib/session";
import {
  Button,
  Card,
  DataTable,
  Field,
  Loading,
  Notice,
  PageHeader,
} from "@/lib/ui";

import "@/app/team-screen.css";

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

  const PURPOSE = "Export workspace data and review activity.";
  const backLink = (
    <Link className="quiet-button" href={`/app/${tenantId}`}>
      Back to overview
    </Link>
  );

  if (!canAdmin) {
    return (
      <main className="tenant-data-page team-page">
        <PageHeader
          title="Tenant data and audit"
          purpose={PURPOSE}
          actions={backLink}
        />
        <Notice message="Administrator access is required." />
      </main>
    );
  }

  const deletionReady =
    !!tenant && confirmName === tenant.name && reason.trim().length >= 3;

  return (
    <main className="tenant-data-page team-page">
      <PageHeader
        title="Tenant data and audit"
        purpose={PURPOSE}
        actions={backLink}
      />
      {error && <Notice message={error} tone="error" />}
      {!tenant ? (
        <Loading label="Loading tenant data…" />
      ) : (
        <>
          <Card title="Export tenant data" aria-label="Tenant export">
            <p className="team-copy">
              Downloads contacts, identities, conversations, messages, usage,
              and audit history as JSON.
              {isOperator &&
                " Platform staff exports also include knowledge, jobs and bot configuration."}
            </p>
            <div className="row-actions">
              <Button disabled={busy} onClick={() => void downloadExport()}>
                {busy ? "Working…" : "Download export"}
              </Button>
            </div>
          </Card>
          <Card title="Audit review" aria-label="Tenant audit review">
            <form
              className="team-invite"
              onSubmit={(event) => {
                event.preventDefault();
                void load();
              }}
            >
              <Field label="Search actions">
                {(control) => (
                  <input
                    {...control}
                    dir="auto"
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                    maxLength={100}
                  />
                )}
              </Field>
              <Button type="submit">Search</Button>
            </form>
            <DataTable
              caption="Audit events"
              rows={audit}
              rowKey={(event) => event.id}
              empty={
                <p className="muted">No audit actions match this search.</p>
              }
              columns={[
                {
                  key: "when",
                  header: "When",
                  cell: (event) => (
                    <span dir="ltr">{event.created_at.slice(0, 19)}</span>
                  ),
                },
                {
                  key: "action",
                  header: "Action",
                  cell: (event) => auditActionLabel(event.action),
                },
                {
                  key: "target",
                  header: "Target",
                  cell: (event) => (
                    <span dir="ltr">
                      {event.target_type ?? "tenant"}:{event.target_id ?? ""}
                    </span>
                  ),
                },
              ]}
            />
          </Card>
          {isOperator && (
            <Card
              title="Delete organization and data"
              aria-label="Delete tenant data"
              className="danger-zone"
            >
              <p className="team-copy">
                This permanently removes the organization’s bots, knowledge,
                contacts, identities, conversations, and messages. The deletion
                request is audited.
              </p>
              <form
                className="team-stack"
                onSubmit={(event) => {
                  event.preventDefault();
                  if (deletionReady) {
                    setConfirmName("");
                    deleteDialog.current?.showModal();
                  }
                }}
              >
                <Field
                  label={
                    <>
                      Type <strong dir="auto">{tenant.name}</strong> to confirm
                    </>
                  }
                >
                  {(control) => (
                    <input
                      {...control}
                      dir="auto"
                      value={confirmName}
                      onChange={(event) => setConfirmName(event.target.value)}
                      required
                    />
                  )}
                </Field>
                <Field label="Reason for deletion">
                  {(control) => (
                    <input
                      {...control}
                      dir="auto"
                      value={reason}
                      onChange={(event) => setReason(event.target.value)}
                      minLength={3}
                      maxLength={500}
                      required
                    />
                  )}
                </Field>
                <div className="row-actions">
                  <Button
                    type="submit"
                    variant="danger"
                    disabled={busy || !deletionReady}
                  >
                    Schedule organization deletion
                  </Button>
                </div>
              </form>
              <dialog
                ref={deleteDialog}
                className="team-dialog"
                aria-labelledby="delete-tenant-title"
              >
                <h2 id="delete-tenant-title">Delete this organization?</h2>
                <p>
                  This disables <bdi>{tenant.name}</bdi> immediately and
                  schedules data and storage removal after the grace period.
                </p>
                <ul className="team-counts">
                  {Object.entries(counts).map(([kind, count]) => (
                    <li key={kind}>
                      {kind}: {count}
                    </li>
                  ))}
                </ul>
                <Field label="Type the organization name">
                  {(control) => (
                    <input
                      {...control}
                      dir="auto"
                      aria-label="Confirm organization name"
                      value={confirmName}
                      onChange={(event) => setConfirmName(event.target.value)}
                    />
                  )}
                </Field>
                <div className="action-row">
                  <Button
                    variant="quiet"
                    autoFocus
                    onClick={() => deleteDialog.current?.close()}
                  >
                    Cancel
                  </Button>
                  <Button
                    variant="danger"
                    disabled={busy || !deletionReady}
                    onClick={(event) => {
                      deleteDialog.current?.close();
                      void deleteData(event);
                    }}
                  >
                    Delete organization now
                  </Button>
                </div>
              </dialog>
            </Card>
          )}
        </>
      )}
    </main>
  );
}
