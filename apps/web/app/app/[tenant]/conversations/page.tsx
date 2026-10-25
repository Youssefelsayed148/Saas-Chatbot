"use client";

import {
  useParams,
  usePathname,
  useRouter,
  useSearchParams,
} from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";

import * as api from "@/lib/api";
import {
  CHANNEL_OPTIONS,
  HistoryTable,
  RetentionPanel,
  STATUS_OPTIONS,
  rowFromInbox,
  type HistoryRow,
} from "@/lib/conversation-history";
import { HISTORY_PAGE_SIZE } from "@/lib/conversations-module";
import { roleSatisfies, useSession } from "@/lib/session";
import { Button, Card, Empty, Loading, Notice } from "@/lib/ui";

import "@/app/convo-screen.css";

/** Tenant-wide History tab (B5, gap I-5): every saved conversation, filtered
 * by URL params (contract in conversations-module.tsx). Rows come from
 * api.listInbox, which has no message count, so there is no Messages column. */

const FILTER_KEYS = ["q", "status", "channel", "from", "to"] as const;

function HistoryList() {
  const { tenant: tenantId } = useParams<{ tenant: string }>();
  const router = useRouter();
  const pathname = usePathname();
  const search = useSearchParams();
  const { roleIn } = useSession();
  const role = roleIn(tenantId);
  const canDelete = roleSatisfies(role, "admin");

  const q = search.get("q") ?? "";
  const status = search.get("status") ?? "";
  const channel = search.get("channel") ?? "";
  const from = search.get("from") ?? "";
  const to = search.get("to") ?? "";
  const page = Math.max(1, Number.parseInt(search.get("page") ?? "1", 10) || 1);

  const [draft, setDraft] = useState(q);
  const [rows, setRows] = useState<HistoryRow[] | null>(null);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [reload, setReload] = useState(0);

  const update = useCallback(
    (patch: Record<string, string>) => {
      const next = new URLSearchParams(search.toString());
      for (const [key, value] of Object.entries(patch)) {
        if (value) next.set(key, value);
        else next.delete(key);
      }
      if (!("page" in patch)) next.delete("page");
      const qs = next.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [router, pathname, search],
  );

  // Debounced search; Enter applies immediately.
  useEffect(() => {
    if (draft === q) return;
    const timer = setTimeout(() => update({ q: draft.trim() }), 400);
    return () => clearTimeout(timer);
  }, [draft, q, update]);

  useEffect(() => {
    let live = true;
    const timer = setTimeout(() => {
      void (async () => {
        try {
          const data = await api.listInbox(tenantId, {
            q,
            status,
            channel,
            created_from: from,
            created_to: to,
            limit: HISTORY_PAGE_SIZE,
            offset: (page - 1) * HISTORY_PAGE_SIZE,
          });
          if (!live) return;
          if (data.conversations.length === 0 && page > 1 && data.total > 0) {
            const last = Math.ceil(data.total / HISTORY_PAGE_SIZE);
            update({ page: String(Math.min(page - 1, last)) });
            return;
          }
          setRows(data.conversations.map(rowFromInbox));
          setTotal(data.total);
          setError(null);
        } catch (caught) {
          if (!live) return;
          setError(
            caught instanceof Error
              ? caught.message
              : "Could not load conversations.",
          );
        }
      })();
    }, 0);
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [tenantId, q, status, channel, from, to, page, reload, update]);

  async function remove(row: HistoryRow) {
    try {
      await api.deleteConversation(tenantId, row.botId, row.id);
      setReload((n) => n + 1);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Could not delete the conversation.",
      );
    }
  }

  const filtered = FILTER_KEYS.some((key) => search.get(key));
  const pages = Math.max(1, Math.ceil(total / HISTORY_PAGE_SIZE));

  return (
    <div className="convo-page">
      <RetentionPanel tenantId={tenantId} role={role} />
      <form
        className="history-toolbar"
        role="search"
        aria-label="Filter history"
        onSubmit={(event) => {
          event.preventDefault();
          update({ q: draft.trim() });
        }}
      >
        <label className="history-field history-search">
          <span>Search</span>
          <input
            type="search"
            aria-label="Search history"
            placeholder="Search visitor or message"
            dir="auto"
            maxLength={200}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
          />
        </label>
        <label className="history-field">
          <span>Status</span>
          <select
            value={status}
            onChange={(event) => update({ status: event.target.value })}
          >
            <option value="">All statuses</option>
            {STATUS_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label className="history-field">
          <span>Channel</span>
          <select
            value={channel}
            onChange={(event) => update({ channel: event.target.value })}
          >
            <option value="">All channels</option>
            {CHANNEL_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label className="history-field">
          <span>From</span>
          <input
            type="date"
            value={from}
            max={to || undefined}
            onChange={(event) => update({ from: event.target.value })}
          />
        </label>
        <label className="history-field">
          <span>To</span>
          <input
            type="date"
            value={to}
            min={from || undefined}
            onChange={(event) => update({ to: event.target.value })}
          />
        </label>
        {filtered && (
          <Button
            variant="quiet"
            onClick={() => {
              setDraft("");
              router.replace(pathname, { scroll: false });
            }}
          >
            Clear filters
          </Button>
        )}
      </form>
      {error && (
        <Notice
          message={error}
          tone="error"
          retryLabel="Try again"
          onRetry={() => setReload((n) => n + 1)}
        />
      )}
      <Card
        title="Saved conversations"
        aria-label="Conversation list"
        data-testid="conversations"
        actions={
          rows !== null ? (
            <span className="convo-count" data-testid="history-total">
              <bdi dir="ltr">{total}</bdi>{" "}
              {total === 1 ? "conversation" : "conversations"}
            </span>
          ) : undefined
        }
      >
        {rows === null ? (
          error ? null : (
            <Loading label="Loading conversations…" />
          )
        ) : rows.length === 0 ? (
          <Empty>
            {filtered
              ? "No conversations match these filters."
              : "No conversations yet — visitors see your widget on the installed site, and threads appear here."}
          </Empty>
        ) : (
          <HistoryTable
            rows={rows}
            tenantId={tenantId}
            canDelete={canDelete}
            showPreview
            onDelete={(row) => void remove(row)}
          />
        )}
        {rows !== null && rows.length > 0 && (
          <nav
            className="history-pagination"
            aria-label="Pagination"
            data-testid="history-pagination"
          >
            <Button
              variant="quiet"
              disabled={page <= 1}
              onClick={() => update({ page: String(page - 1) })}
            >
              Previous page
            </Button>
            <span className="convo-count">
              Page <bdi dir="ltr">{page}</bdi> of <bdi dir="ltr">{pages}</bdi>
            </span>
            <Button
              variant="quiet"
              disabled={page >= pages}
              onClick={() => update({ page: String(page + 1) })}
            >
              Next page
            </Button>
          </nav>
        )}
      </Card>
    </div>
  );
}

export default function ConversationsHistoryPage() {
  return (
    <Suspense fallback={<Loading label="Loading conversations…" />}>
      <HistoryList />
    </Suspense>
  );
}
