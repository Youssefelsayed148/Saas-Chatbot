"use client";

import { useCallback, useEffect, useState } from "react";
import * as api from "./api";
import { useSession } from "./session";
import { Loading, Notice } from "./ui";

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
      <main>
        <h1>Change requests</h1>
        <Notice message="Administrator access required." />
      </main>
    );
  return (
    <main>
      <h1>{tenantId ? "Request a change" : "Operator change queue"}</h1>
      <p className="page-purpose">
        {tenantId
          ? "Ask your operator to update knowledge, text or domains, or review an organization deletion request."
          : "Review and triage client requests."}
      </p>
      {error && <Notice message={error} tone="error" />}
      {tenantId && (
        <form
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
          <label>
            Request type
            <select
              value={type}
              onChange={(event) =>
                setType(event.target.value as api.ChangeRequest["type"])
              }
            >
              <option value="knowledge">Knowledge</option>
              <option value="text_change">Text change</option>
              <option value="domain">Domain</option>
              <option value="delete_org">Delete organization</option>
              <option value="other">Other</option>
            </select>
          </label>
          <label>
            Describe the change
            <textarea
              required
              maxLength={10000}
              value={text}
              onChange={(event) => setText(event.target.value)}
            />
          </label>
          <label>
            Attachments
            <input
              type="file"
              multiple
              onChange={(event) =>
                setFiles(Array.from(event.target.files ?? []))
              }
            />
          </label>
          <button disabled={busy || !text.trim()} type="submit">
            {busy ? "Submitting…" : "Submit request"}
          </button>
        </form>
      )}
      {rows === null ? (
        <Loading label="Loading requests…" />
      ) : rows.length === 0 ? (
        <p>No change requests yet.</p>
      ) : (
        <ul>
          {rows.map((row) => (
            <li key={row.id}>
              <h2>{row.type.replaceAll("_", " ")}</h2>
              <p>{row.text}</p>
              <p>
                Status: {row.status} · {row.created_at.slice(0, 10)}
              </p>
              {!tenantId && (
                <p>
                  <a href={`/app/${row.tenant_id}/settings/data`}>
                    Organization data and deletion
                  </a>{" "}
                  · Requester: {row.requester_id}
                </p>
              )}
              <ul>
                {row.attachments.map((file) => (
                  <li key={file.id}>
                    <a
                      href={`/api/v1/tenants/${row.tenant_id}/change-requests/${row.id}/attachments/${file.id}`}
                    >
                      {file.name} ({file.size_bytes} bytes)
                    </a>
                  </li>
                ))}
              </ul>
              {!tenantId && (
                <label>
                  Triage status
                  <select
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
                </label>
              )}
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
