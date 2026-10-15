"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import * as api from "@/lib/api";
import type { Conversation } from "@/lib/api";
import { roleSatisfies, useSession } from "@/lib/session";
import { Empty, Loading, Notice } from "@/lib/ui";
import BotWorkspaceNav from "@/lib/bot-workspace-nav";

/** P4-04: read-only conversations view (docs/10 Conversations tab) with the
 * tenant retention control (docs/14 §7). Live inbox views arrive in P5. */

export default function ConversationsPage() {
  const params = useParams<{ tenant: string; botId: string }>();
  const tenantId = params.tenant;
  const botId = params.botId;
  const { roleIn } = useSession();
  const role = roleIn(tenantId);
  const canDelete = roleSatisfies(role, "editor");
  const canTenant = roleSatisfies(role, "admin");

  const [rows, setRows] = useState<Conversation[] | null>(null);
  const [total, setTotal] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retentionDraft, setRetentionDraft] = useState("");
  const [retentionSaved, setRetentionSaved] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await api.listConversations(tenantId, botId);
      setRows(data.conversations);
      setTotal(data.total);
      setError(null);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Could not load conversations.",
      );
    }
  }, [tenantId, botId]);

  useEffect(() => {
    const timer = setTimeout(() => {
      void load();
    }, 0);
    return () => clearTimeout(timer);
  }, [load]);

  async function saveRetention() {
    const value = Number(retentionDraft);
    if (!retentionDraft.trim() || Number.isNaN(value)) {
      setError("Enter a retention value between 1 and 365 days.");
      return;
    }
    try {
      await api.updateTenant(tenantId, { retention_days: value });
      setRetentionSaved(true);
      setError(null);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Could not save the retention setting.",
      );
    }
  }

  async function removeThread(id: string) {
    try {
      await api.deleteConversation(tenantId, botId, id);
      await load();
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Could not delete the conversation.",
      );
    }
  }

  return (
    <main>
      <BotWorkspaceNav tenantId={tenantId} botId={botId} />
      <h1>Conversations</h1>
      <p className="page-purpose">
        Review saved visitor conversations and manage retention.
      </p>
      {error && <Notice message={error} tone="error" />}
      {canTenant && (
        <section aria-label="Retention" style={{ margin: "0.6rem 0" }}>
          <label>
            Message retention (days, tenant-wide, 1–365)
            <input
              data-testid="retention-input"
              style={{ maxWidth: "10rem" }}
              value={retentionDraft}
              placeholder="30"
              onChange={(event) => setRetentionDraft(event.target.value)}
            />
          </label>
          <button
            type="button"
            data-testid="retention-save"
            style={{ marginInlineStart: "0.5rem" }}
            onClick={() => void saveRetention()}
          >
            Save retention
          </button>
          {retentionSaved && (
            <p role="status" data-testid="retention-saved">
              Retention updated. The background purge applies it on its next
              run.
            </p>
          )}
        </section>
      )}
      <section aria-label="Conversation list" data-testid="conversations">
        {rows === null ? (
          <Loading label="Loading conversations…" />
        ) : rows.length === 0 ? (
          <Empty>
            No conversations yet — visitors see your widget on the installed
            site, and threads appear here.
          </Empty>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Last activity</th>
                <th>Channel</th>
                <th>Status</th>
                <th>Lead</th>
                <th>Messages</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id}>
                  <td>
                    <Link
                      href={`/app/${tenantId}/bots/${botId}/conversations/${row.id}`}
                    >
                      {row.last_message_at
                        ? new Date(row.last_message_at).toLocaleString()
                        : new Date(row.created_at).toLocaleString()}
                    </Link>
                  </td>
                  <td>{row.channel}</td>
                  <td data-status={row.status}>{row.status}</td>
                  <td>{row.contact_name ?? "—"}</td>
                  <td>{row.message_count}</td>
                  <td>
                    {canDelete && (
                      <button
                        type="button"
                        data-testid={`delete-${row.id}`}
                        onClick={() => void removeThread(row.id)}
                      >
                        Delete
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {total !== null && rows !== null && total > rows.length && (
          <p className="muted">
            Showing {rows.length} of {total} conversations (newest first).
          </p>
        )}
      </section>
    </main>
  );
}
