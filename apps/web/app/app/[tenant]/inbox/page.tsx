"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import * as api from "@/lib/api";
import type { InboxConversation } from "@/lib/api";
import { roleSatisfies, useSession } from "@/lib/session";
import { Empty, Loading, Notice } from "@/lib/ui";

const controlStyle = { margin: "0.25rem", maxWidth: "12rem" };

export default function InboxPage() {
  const params = useParams<{ tenant: string }>();
  const search = useSearchParams();
  const tenantId = params.tenant;
  const { roleIn } = useSession();
  const role = roleIn(tenantId);
  const canEdit = roleSatisfies(role, "editor");
  const [rows, setRows] = useState<InboxConversation[] | null>(null);
  const [total, setTotal] = useState(0);
  const [counts, setCounts] = useState<api.InboxCounts | null>(null);
  const [members, setMembers] = useState<api.Member[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFilters] = useState({
    status: search.get("status") ?? "",
    mode: "",
    channel: "",
    assignee: "",
    tag: "",
    unread: "",
    q: "",
  });

  const load = useCallback(async () => {
    try {
      const [page, nextCounts] = await Promise.all([
        api.listInbox(tenantId, {
          ...filters,
          unread: filters.unread === "" ? undefined : filters.unread === "true",
        }),
        api.inboxCounts(tenantId),
      ]);
      setRows(page.conversations);
      setTotal(page.total);
      setCounts(nextCounts);
      setError(null);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Could not load inbox.",
      );
    }
  }, [filters, tenantId]);

  useEffect(() => {
    const timer = setTimeout(() => void load(), 0);
    const stream = new EventSource(`/api/v1/tenants/${tenantId}/inbox/events`);
    const refresh = () => void load();
    stream.addEventListener("inbox.update", refresh);
    stream.addEventListener("inbox.ready", refresh);
    stream.addEventListener("inbox.access_revoked", refresh);
    return () => {
      clearTimeout(timer);
      stream.close();
    };
  }, [load, tenantId]);

  useEffect(() => {
    const timer = setTimeout(() => {
      void api
        .listMembers(tenantId)
        .then(setMembers)
        .catch(() => setMembers([]));
    }, 0);
    return () => clearTimeout(timer);
  }, [tenantId]);

  function updateFilter(key: keyof typeof filters, value: string) {
    setFilters((current) => ({ ...current, [key]: value }));
  }

  return (
    <main>
      <h1>Inbox</h1>
      {counts && (
        <section
          aria-label="Inbox notifications"
          style={{ display: "flex", gap: "1.5rem", flexWrap: "wrap" }}
        >
          <span>
            Waiting for a reply <strong>{counts.waiting_human}</strong>
          </span>
          <span>
            Assigned to me <strong>{counts.assigned_to_me}</strong>
          </span>
          <span>
            Unread conversations <strong>{counts.unread_conversations}</strong>
          </span>
          <span>
            Unread messages <strong>{counts.unread_messages}</strong>
          </span>
        </section>
      )}
      <section aria-label="Inbox filters" style={{ margin: "1rem 0" }}>
        <label>
          Search{" "}
          <input
            aria-label="Search conversations"
            style={controlStyle}
            value={filters.q}
            onChange={(e) => updateFilter("q", e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void load();
            }}
          />
        </label>
        <label>
          Status{" "}
          <select
            style={controlStyle}
            value={filters.status}
            onChange={(e) => updateFilter("status", e.target.value)}
          >
            <option value="">All</option>
            <option value="waiting_human">Waiting for human</option>
            <option value="open">Open</option>
            <option value="resolved">Resolved</option>
          </select>
        </label>
        <label>
          Mode{" "}
          <select
            style={controlStyle}
            value={filters.mode}
            onChange={(e) => updateFilter("mode", e.target.value)}
          >
            <option value="">All</option>
            <option value="ai">AI</option>
            <option value="human">Human</option>
          </select>
        </label>
        <label>
          Channel{" "}
          <select
            style={controlStyle}
            value={filters.channel}
            onChange={(e) => updateFilter("channel", e.target.value)}
          >
            <option value="">All</option>
            <option value="website">Website</option>
            <option value="whatsapp">WhatsApp</option>
            <option value="messenger">Messenger</option>
            <option value="instagram">Instagram</option>
          </select>
        </label>
        <label>
          Assignee{" "}
          <select
            style={controlStyle}
            value={filters.assignee}
            onChange={(e) => updateFilter("assignee", e.target.value)}
          >
            <option value="">Anyone</option>
            <option value="me">Assigned to me</option>
            <option value="unassigned">Unassigned</option>
            {members
              .filter((member) => member.status === "active")
              .map((member) => (
                <option key={member.user_id} value={member.user_id}>
                  {member.email}
                </option>
              ))}
          </select>
        </label>
        <label>
          Tag{" "}
          <input
            aria-label="Filter by tag"
            style={controlStyle}
            value={filters.tag}
            onChange={(e) => updateFilter("tag", e.target.value)}
          />
        </label>
        <label>
          Unread{" "}
          <select
            style={controlStyle}
            value={filters.unread}
            onChange={(e) => updateFilter("unread", e.target.value)}
          >
            <option value="">Any</option>
            <option value="true">Unread</option>
            <option value="false">Read</option>
          </select>
        </label>
      </section>
      {error && <Notice message={error} tone="error" />}
      <section aria-label="Conversations" data-testid="inbox-list">
        {rows === null ? (
          <Loading label="Loading inbox…" />
        ) : rows.length === 0 ? (
          <Empty>No conversations match these filters.</Empty>
        ) : (
          <ul style={{ listStyle: "none", padding: 0 }}>
            {rows.map((row) => (
              <li
                key={row.id}
                style={{ borderBottom: "1px solid #ddd", padding: "0.85rem 0" }}
              >
                <Link
                  href={`/app/${tenantId}/inbox/${row.id}`}
                  style={{ display: "block" }}
                >
                  <strong>
                    {row.last_message?.slice(0, 120) || "New conversation"}
                  </strong>
                  {(row.unread_count ?? 0) > 0 && (
                    <span
                      aria-label={`${row.unread_count} unread`}
                      style={{ marginLeft: "0.6rem" }}
                    >
                      ● {row.unread_count}
                    </span>
                  )}
                  <div className="muted">
                    {row.channel} · {row.mode} · {row.status}
                    {row.handoff_reason
                      ? ` · ${row.handoff_reason.replaceAll("_", " ")}`
                      : ""}{" "}
                    ·{" "}
                    {row.last_message_at
                      ? new Date(row.last_message_at).toLocaleString()
                      : "No activity"}
                  </div>
                  {(row.tags?.length ?? 0) > 0 && (
                    <div>Tags: {row.tags?.join(", ")}</div>
                  )}
                </Link>
              </li>
            ))}
          </ul>
        )}
        {rows && (
          <p className="muted">
            Showing {rows.length} of {total} conversations
          </p>
        )}
      </section>
      {!canEdit && (
        <p className="muted">
          Viewer access: you can read conversations, but cannot reply or change
          their status.
        </p>
      )}
    </main>
  );
}
