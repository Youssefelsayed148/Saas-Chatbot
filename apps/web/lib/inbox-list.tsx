"use client";

import Link from "next/link";
import {
  useParams,
  usePathname,
  useRouter,
  useSearchParams,
} from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { humanLabel } from "@/lib/labels";
import * as api from "@/lib/api";
import type { InboxConversation } from "@/lib/api";
import { roleSatisfies, useSession } from "@/lib/session";
import { Button, Empty, Loading, Notice, StatusBadge } from "@/lib/ui";
import { Icon } from "./icons";
import { InboxRowAvatar, formatRowTime } from "./inbox-row";
import "@/app/inbox-screen.css";

/* Filters live in the URL (contract: lib/conversations-module.tsx). */
const FILTER_KEYS = [
  "status",
  "mode",
  "channel",
  "assignee",
  "tag",
  "unread",
  "q",
] as const;
type FilterKey = (typeof FILTER_KEYS)[number];
type Filters = Record<FilterKey, string>;
const ADVANCED_KEYS: FilterKey[] = [
  "mode",
  "channel",
  "assignee",
  "tag",
  "unread",
];
const PRESET_KEYS: FilterKey[] = ["status", "assignee", "unread"];

export function InboxList({
  compact = false,
  selectedId,
}: {
  compact?: boolean;
  selectedId?: string;
}) {
  const params = useParams<{ tenant: string }>();
  const search = useSearchParams();
  const pathname = usePathname();
  const router = useRouter();
  const tenantId = params.tenant;
  const { roleIn } = useSession();
  const role = roleIn(tenantId);
  const canEdit = roleSatisfies(role, "editor");
  const [rows, setRows] = useState<InboxConversation[] | null>(null);
  const [total, setTotal] = useState(0);
  const [counts, setCounts] = useState<api.InboxCounts | null>(null);
  const Root = "section";
  const [members, setMembers] = useState<api.Member[]>([]);
  const [error, setError] = useState<string | null>(null);
  const detailsRef = useRef<HTMLDetailsElement>(null);

  const status = search.get("status") ?? "";
  const mode = search.get("mode") ?? "";
  const channel = search.get("channel") ?? "";
  const assignee = search.get("assignee") ?? "";
  const tag = search.get("tag") ?? "";
  const unread = search.get("unread") ?? "";
  const q = search.get("q") ?? "";
  const filters: Filters = { status, mode, channel, assignee, tag, unread, q };
  const anyFilter = FILTER_KEYS.some((key) => filters[key] !== "");
  const advancedCount = ADVANCED_KEYS.filter((key) => filters[key]).length;

  const setParams = useCallback(
    (updates: Partial<Filters>) => {
      const next = new URLSearchParams(search.toString());
      for (const [key, value] of Object.entries(updates)) {
        if (value) next.set(key, value);
        else next.delete(key);
      }
      const qs = next.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [pathname, router, search],
  );

  /* Search box: local text, debounced into the URL. lastPushed stops a late
   * URL echo from clobbering what the user typed meanwhile. */
  const [qInput, setQInput] = useState(q);
  const lastPushed = useRef(q);
  useEffect(() => {
    if (q === lastPushed.current) return;
    lastPushed.current = q;
    const timer = setTimeout(() => setQInput(q), 0);
    return () => clearTimeout(timer);
  }, [q]);
  useEffect(() => {
    if (qInput === lastPushed.current) return;
    const timer = setTimeout(() => {
      lastPushed.current = qInput;
      setParams({ q: qInput });
    }, 350);
    return () => clearTimeout(timer);
  }, [qInput, setParams]);

  const [reloadTick, setReloadTick] = useState(0);
  useEffect(() => {
    async function load() {
      try {
        const [page, nextCounts] = await Promise.all([
          api.listInbox(tenantId, {
            status,
            mode,
            channel,
            assignee,
            tag,
            q,
            unread: unread === "" ? undefined : unread === "true",
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
    }
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
  }, [status, mode, channel, assignee, tag, unread, q, tenantId, reloadTick]);

  useEffect(() => {
    const timer = setTimeout(() => {
      void api
        .listMembers(tenantId)
        .then(setMembers)
        .catch(() => setMembers([]));
    }, 0);
    return () => clearTimeout(timer);
  }, [tenantId]);

  /* Popover: close on a press outside it. */
  useEffect(() => {
    function onPointerDown(event: PointerEvent) {
      const el = detailsRef.current;
      if (
        el?.open &&
        event.target instanceof Node &&
        !el.contains(event.target)
      )
        el.open = false;
    }
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, []);

  function applyPreset(key: FilterKey | null, value: string, active: boolean) {
    const cleared: Partial<Filters> = { status: "", assignee: "", unread: "" };
    if (key && !active) cleared[key] = value;
    setParams(cleared);
  }
  const presets: Array<{
    id: string;
    label: string;
    key: FilterKey | null;
    value: string;
    active: boolean;
    count: number | null;
  }> = [
    {
      id: "waiting",
      label: "Waiting for a reply",
      key: "status",
      value: "waiting_human",
      active: status === "waiting_human",
      count: counts?.waiting_human ?? null,
    },
    {
      id: "mine",
      label: "Assigned to me",
      key: "assignee",
      value: "me",
      active: assignee === "me",
      count: counts?.assigned_to_me ?? null,
    },
    {
      id: "unread",
      label: "Unread",
      key: "unread",
      value: "true",
      active: unread === "true",
      count: counts?.unread_conversations ?? null,
    },
    {
      id: "all",
      label: "All",
      key: null,
      value: "",
      active: !PRESET_KEYS.some((key) => filters[key]),
      count: !anyFilter && rows !== null ? total : null,
    },
  ];
  const qsSuffix = search.toString() ? `?${search.toString()}` : "";

  return (
    <Root className={`inbox-list-panel ${compact ? "compact" : ""}`}>
      <div
        className="inbox-filter-chips"
        role="group"
        aria-label="Quick filters"
      >
        {presets.map((preset) => (
          <Button
            key={preset.id}
            variant="quiet"
            className="inbox-chip"
            data-testid={`inbox-filter-${preset.id}`}
            aria-pressed={preset.active}
            onClick={() => applyPreset(preset.key, preset.value, preset.active)}
          >
            {preset.label}
            {preset.count !== null && (
              <span className="inbox-chip-count">{preset.count}</span>
            )}
          </Button>
        ))}
      </div>
      <section aria-label="Inbox filters" className="filter-toolbar">
        <div className="inbox-search">
          <Icon name="search" size={16} className="inbox-search-icon" />
          <input
            aria-label="Search conversations"
            placeholder="Search conversations"
            value={qInput}
            onChange={(e) => setQInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                lastPushed.current = qInput;
                setParams({ q: qInput });
              }
            }}
          />
        </div>
        <select
          aria-label="Status"
          className="inbox-status-select"
          value={status}
          onChange={(e) => setParams({ status: e.target.value })}
        >
          <option value="">All</option>
          <option value="waiting_human">Waiting for human</option>
          <option value="open">Open</option>
          <option value="resolved">Resolved</option>
        </select>
        <details
          ref={detailsRef}
          className="advanced-filters"
          onKeyDown={(event) => {
            if (event.key === "Escape") {
              event.currentTarget.open = false;
              event.currentTarget.querySelector("summary")?.focus();
            }
          }}
        >
          <summary>
            <span>More filters</span>
            {advancedCount > 0 && (
              <span
                className="inbox-chip-count"
                data-testid="inbox-advanced-count"
              >
                {advancedCount}
              </span>
            )}
          </summary>
          <div className="advanced-filter-fields">
            <label>
              Mode
              <select
                data-testid="inbox-mode-filter"
                value={mode}
                onChange={(e) => setParams({ mode: e.target.value })}
              >
                <option value="">All</option>
                <option value="ai">AI</option>
                <option value="human">Human</option>
              </select>
            </label>
            <label>
              Channel
              <select
                value={channel}
                onChange={(e) => setParams({ channel: e.target.value })}
              >
                <option value="">All</option>
                <option value="website">Website</option>
                <option value="whatsapp">WhatsApp</option>
                <option value="messenger">Messenger</option>
                <option value="instagram">Instagram</option>
              </select>
            </label>
            <label>
              Assignee
              <select
                aria-label={compact ? "Filter assignee" : "Assignee"}
                value={assignee}
                onChange={(e) => setParams({ assignee: e.target.value })}
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
              Tag
              <input
                aria-label="Filter by tag"
                value={tag}
                maxLength={32}
                onChange={(e) => setParams({ tag: e.target.value })}
              />
            </label>
            <label>
              Unread
              <select
                value={unread}
                onChange={(e) => setParams({ unread: e.target.value })}
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
        {FILTER_KEYS.filter((key) => filters[key]).map((key) => (
          <Button
            variant="quiet"
            key={key}
            aria-label={`Remove ${key} filter`}
            onClick={() => setParams({ [key]: "" })}
          >
            {humanLabel(key)}:{" "}
            {key === "q" || key === "tag" ? (
              <bdi>{filters[key]}</bdi>
            ) : (
              humanLabel(filters[key])
            )}{" "}
            <span aria-hidden="true">×</span>
          </Button>
        ))}
      </div>
      {error && (
        <Notice
          message={error}
          tone="error"
          onRetry={() => setReloadTick((n) => n + 1)}
        />
      )}
      <section aria-label="Conversations" data-testid="inbox-list">
        {rows === null ? (
          <Loading label="Loading inbox…" />
        ) : rows.length === 0 ? (
          <Empty>No conversations match these filters.</Empty>
        ) : (
          <ul>
            {rows.map((row) => {
              const name = row.contact_name?.trim() || "";
              const unreadCount = row.unread_count ?? 0;
              return (
                <li
                  key={row.id}
                  className="inbox-row"
                  data-selected={selectedId === row.id}
                  data-unread={unreadCount > 0}
                >
                  <Link
                    href={`/app/${tenantId}/inbox/${row.id}${qsSuffix}`}
                    aria-current={selectedId === row.id ? "true" : undefined}
                  >
                    <InboxRowAvatar name={name} />
                    <div className="inbox-row-body">
                      <div className="inbox-row-heading">
                        <strong dir="auto">
                          {name ||
                            `Visitor ${row.contact_id?.slice(0, 6) ?? row.id.slice(0, 6)}`}
                        </strong>
                        <time
                          dateTime={row.last_message_at ?? undefined}
                          title={
                            row.last_message_at
                              ? new Date(row.last_message_at).toLocaleString()
                              : undefined
                          }
                        >
                          {formatRowTime(row.last_message_at)}
                        </time>
                      </div>
                      <p dir="auto" className="message-snippet">
                        {row.last_message || "New conversation"}
                      </p>
                      <div className="inbox-row-meta">
                        <StatusBadge value={row.status} title={row.status}>
                          {humanLabel(row.status)}
                        </StatusBadge>
                        <span className="channel-label" title={row.channel}>
                          {humanLabel(row.channel)}
                        </span>
                        <small
                          className="muted inbox-row-mode"
                          data-value={row.mode}
                          data-handoff-reason={row.handoff_reason ?? undefined}
                          title={row.handoff_reason ?? row.mode}
                        >
                          {humanLabel(row.mode)}
                          {row.handoff_reason
                            ? ` · ${humanLabel(row.handoff_reason)}`
                            : ""}
                        </small>
                        {unreadCount > 0 && (
                          <span
                            className="unread-count"
                            aria-label={`${unreadCount} unread`}
                          >
                            <Icon name="dot" size={14} /> {unreadCount}
                          </span>
                        )}
                      </div>
                      {(row.tags?.length ?? 0) > 0 && (
                        <div className="row-tags">
                          {row.tags?.map((value) => (
                            <span className="badge" key={value}>
                              <bdi>{value}</bdi>
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
        {rows && (
          <p className="muted inbox-list-footer">
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
