"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { humanLabel, LabelBadge } from "@/lib/labels";
import * as api from "@/lib/api";
import type { InboxConversation } from "@/lib/api";
import { roleSatisfies, useSession } from "@/lib/session";
import { Empty, Loading, Notice } from "@/lib/ui";

export function InboxList({
  compact = false,
  selectedId,
}: {
  compact?: boolean;
  selectedId?: string;
}) {
  const params = useParams<{ tenant: string }>();
  const search = useSearchParams();
  const tenantId = params.tenant;
  const { roleIn } = useSession();
  const role = roleIn(tenantId);
  const canEdit = roleSatisfies(role, "editor");
  const [rows, setRows] = useState<InboxConversation[] | null>(null);
  const [total, setTotal] = useState(0);
  const [counts, setCounts] = useState<api.InboxCounts | null>(null);
  const Root = compact ? "section" : "main";
  const [contacts, setContacts] = useState<api.Contact[]>([]);
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
        .listContacts(tenantId)
        .then(setContacts)
        .catch(() => setContacts([]));
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
    <Root className={`inbox-list-panel ${compact ? "compact" : ""}`}>
      {compact ? (
        <h2>Inbox</h2>
      ) : (
        <>
          <h1>Inbox</h1>
          <p className="page-purpose">
            Find conversations that need attention and continue them with your
            team.
          </p>
        </>
      )}
      {counts && (
        <section aria-label="Inbox notifications" className="inbox-counts">
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
      <section aria-label="Inbox filters" className="filter-toolbar">
        <label>
          Search{" "}
          <input
            aria-label="Search conversations"
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
            value={filters.status}
            onChange={(e) => updateFilter("status", e.target.value)}
          >
            <option value="">All</option>
            <option value="waiting_human">Waiting for human</option>
            <option value="open">Open</option>
            <option value="resolved">Resolved</option>
          </select>
        </label>
        <details
          className="advanced-filters"
          onKeyDown={(event) => {
            if (event.key === "Escape") {
              event.currentTarget.open = false;
              event.currentTarget.querySelector("summary")?.focus();
            }
          }}
        >
          <summary>More filters</summary>
          <div className="advanced-filter-fields">
            <label>
              Mode{" "}
              <select
                data-testid="inbox-mode-filter"
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
                aria-label={compact ? "Filter assignee" : "Assignee"}
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
                value={filters.tag}
                onChange={(e) => updateFilter("tag", e.target.value)}
              />
            </label>
            <label>
              Unread{" "}
              <select
                value={filters.unread}
                onChange={(e) => updateFilter("unread", e.target.value)}
              >
                <option value="">Any</option>
                <option value="true">Unread</option>
                <option value="false">Read</option>
              </select>
            </label>
          </div>
        </details>
      </section>
      <div className="filter-chips" aria-label="Active filters">
        {Object.entries(filters)
          .filter(([, value]) => value)
          .map(([key, value]) => (
            <button
              className="quiet-button"
              type="button"
              key={key}
              aria-label={`Remove ${key} filter`}
              onClick={() => updateFilter(key as keyof typeof filters, "")}
            >
              {humanLabel(key)}: {humanLabel(value)}{" "}
              <span aria-hidden="true">×</span>
            </button>
          ))}
      </div>
      {error && (
        <Notice message={error} tone="error" onRetry={() => void load()} />
      )}
      <section aria-label="Conversations" data-testid="inbox-list">
        {rows === null ? (
          <Loading label="Loading inbox…" />
        ) : rows.length === 0 ? (
          <Empty>No conversations match these filters.</Empty>
        ) : (
          <ul>
            {rows.map((row) => (
              <li
                key={row.id}
                className="inbox-row"
                data-selected={selectedId === row.id}
              >
                <Link
                  href={`/app/${tenantId}/inbox/${row.id}${search.toString() ? `?${search.toString()}` : ""}`}
                >
                  <div className="inbox-row-heading">
                    <strong dir="auto">
                      {contacts.find((contact) => contact.id === row.contact_id)
                        ?.display_name ||
                        `Visitor ${row.contact_id?.slice(0, 6) ?? row.id.slice(0, 6)}`}
                    </strong>
                    <time>
                      {row.last_message_at
                        ? new Date(row.last_message_at).toLocaleDateString()
                        : "No activity"}
                    </time>
                  </div>
                  <p dir="auto" className="message-snippet">
                    {row.last_message?.slice(0, 120) || "New conversation"}
                  </p>
                  <div className="inbox-row-meta">
                    <span className="channel-label" title={row.channel}>
                      <span aria-hidden="true">◎</span>{" "}
                      {humanLabel(row.channel)}
                    </span>
                    <LabelBadge value={row.status} />
                    {(row.unread_count ?? 0) > 0 && (
                      <span
                        className="unread-count"
                        aria-label={`${row.unread_count} unread`}
                      >
                        <span aria-hidden="true">●</span> {row.unread_count}
                      </span>
                    )}
                  </div>
                  <small
                    className="muted"
                    data-value={row.mode}
                    data-handoff-reason={row.handoff_reason ?? undefined}
                    title={row.handoff_reason ?? row.mode}
                  >
                    {humanLabel(row.mode)}
                    {row.handoff_reason
                      ? ` · ${humanLabel(row.handoff_reason)}`
                      : ""}
                  </small>
                  {(row.tags?.length ?? 0) > 0 && (
                    <div className="row-tags">
                      {row.tags?.map((tag) => (
                        <span className="badge" key={tag} dir="auto">
                          {tag}
                        </span>
                      ))}
                    </div>
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
    </Root>
  );
}
