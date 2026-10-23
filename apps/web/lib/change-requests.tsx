"use client";

import { useCallback, useEffect, useState } from "react";
import * as api from "./api";
import { useSession } from "./session";
import {
  Button,
  Empty,
  Field,
  FormSection,
  Loading,
  Notice,
  PageHeader,
  StatusBadge,
  type StatusTone,
} from "./ui";

import "@/app/team-screen.css";

const STATUS_TONES: Record<string, StatusTone> = {
  pending: "warning",
  triaged: "info",
  in_progress: "warning",
  completed: "success",
  rejected: "danger",
};

export function ChangeRequests({ tenantId }: { tenantId?: string }) {
  const { me, roleIn } = useSession();
  const allowed = tenantId
    ? roleIn(tenantId) === "admin"
    : !!me?.is_platform_staff;
  const [rows, setRows] = useState<api.ChangeRequest[] | null>(null);
  const [type, setType] = useState<api.ChangeRequest["type"]>("knowledge");
  const [text, setText] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    try {
      setRows(await api.listChangeRequests(tenantId));
      setError(null);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Could not load requests.",
      );
    }
  }, [tenantId]);
  useEffect(() => {
    if (!allowed) return;
    const timer = setTimeout(() => void load(), 0);
    return () => clearTimeout(timer);
  }, [allowed, load]);
  if (!allowed)
    return (
      <main className="team-page">
        <PageHeader title="Change requests" />
        <Notice message="Administrator access required." />
      </main>
    );
  return (
    <main className="team-page cr-page">
      <PageHeader
        title={tenantId ? "Request a change" : "Operator change queue"}
        purpose={
          tenantId
            ? "Request content or website updates, or an organization deletion review."
            : "Review and triage client requests."
        }
      />
      {error && <Notice message={error} tone="error" />}
      {tenantId && (
        <FormSection title="New request">
          <form
            className="team-stack"
            onSubmit={async (event) => {
              event.preventDefault();
              const form = event.currentTarget;
              setBusy(true);
              setError(null);
              try {
                await api.createChangeRequest(tenantId, type, text, files);
                setText("");
                setFiles([]);
                form.reset();
                await load();
              } catch (caught) {
                setError(
                  caught instanceof Error
                    ? caught.message
                    : "Could not save request.",
                );
              } finally {
                setBusy(false);
              }
            }}
          >
            <Field label="Request type">
              {(control) => (
                <select
                  {...control}
                  value={type}
                  onChange={(event) =>
                    setType(event.target.value as api.ChangeRequest["type"])
                  }
                >
                  <option value="knowledge">Content update</option>
                  <option value="text_change">Text change</option>
                  <option value="domain">Website update</option>
                  <option value="delete_org">Delete organization</option>
                  <option value="other">Other</option>
                </select>
              )}
            </Field>
            <Field label="Describe the change">
              {(control) => (
                <textarea
                  {...control}
                  dir="auto"
                  required
                  maxLength={10000}
                  value={text}
                  onChange={(event) => setText(event.target.value)}
                />
              )}
            </Field>
            <Field label="Attachments">
              {(control) => (
                <input
                  {...control}
                  type="file"
                  multiple
                  onChange={(event) =>
                    setFiles(Array.from(event.target.files ?? []))
                  }
                />
              )}
            </Field>
            <div className="row-actions">
              <Button disabled={busy || !text.trim()} type="submit">
                {busy ? "Submitting…" : "Submit request"}
              </Button>
            </div>
          </form>
        </FormSection>
      )}
      {rows === null ? (
        <Loading label="Loading requests…" />
      ) : rows.length === 0 ? (
        <Empty>No change requests yet.</Empty>
      ) : (
        <ul className="cr-list">
          {rows.map((row) => (
            <li key={row.id}>
              <h2>
                {tenantId
                  ? {
                      knowledge: "Content update",
                      text_change: "Text change",
                      domain: "Website update",
                      delete_org: "Delete organization",
                      other: "Other",
                    }[row.type]
                  : row.type.replaceAll("_", " ")}
              </h2>
              <p className="cr-text" dir="auto">
                {row.text}
              </p>
              <p className="cr-meta">
                Status:{" "}
                <StatusBadge
                  value={row.status}
                  tone={STATUS_TONES[row.status]}
                />{" "}
                · <span dir="ltr">{row.created_at.slice(0, 10)}</span>
              </p>
              {!tenantId && (
                <p className="cr-meta">
                  <a href={`/app/${row.tenant_id}/settings/data`}>
                    Organization data and deletion
                  </a>{" "}
                  · Requester: <bdi dir="ltr">{row.requester_id}</bdi>
                </p>
              )}
              {row.attachments.length > 0 && (
                <ul className="cr-files">
                  {row.attachments.map((file) => (
                    <li key={file.id}>
                      <a
                        href={`/api/v1/tenants/${row.tenant_id}/change-requests/${row.id}/attachments/${file.id}`}
                      >
                        <bdi>{file.name}</bdi> ({file.size_bytes} bytes)
                      </a>
                    </li>
                  ))}
                </ul>
              )}
              {!tenantId && (
                <Field label="Triage status" className="cr-triage">
                  {(control) => (
                    <select
                      {...control}
                      aria-label={`Status for ${row.id}`}
                      disabled={busy}
                      value={row.status}
                      onChange={async (event) => {
                        setBusy(true);
                        try {
                          await api.triageChangeRequest(
                            row.id,
                            event.target.value as api.ChangeRequest["status"],
                          );
                          await load();
                        } catch (caught) {
                          setError(
                            caught instanceof Error
                              ? caught.message
                              : "Could not triage request.",
                          );
                        } finally {
                          setBusy(false);
                        }
                      }}
                    >
                      {[
                        "pending",
                        "triaged",
                        "in_progress",
                        "completed",
                        "rejected",
                      ].map((status) => (
                        <option key={status} value={status}>
                          {status.replaceAll("_", " ")}
                        </option>
                      ))}
                    </select>
                  )}
                </Field>
              )}
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
