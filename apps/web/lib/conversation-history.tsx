"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type ReactNode } from "react";

import * as api from "./api";
import { roleSatisfies } from "./session";
import {
  Button,
  ConfirmAction,
  DataTable,
  Field,
  Notice,
  StatusBadge,
} from "./ui";

/* Shared pieces of the History tab (B5): HistoryRow view model, the table, the
 * row overflow menu (delete) and the collapsible retention panel. Used by the
 * tenant-wide list and the per-bot list. See the contract in
 * conversations-module.tsx. */

export type HistoryRow = {
  id: string;
  botId: string;
  /** last_message_at ?? created_at (ISO). */
  lastActivity: string | null;
  visitor: string | null;
  preview?: string | null;
  status: string;
  channel: string;
  /** Channel rows only: the Many connection and the campaign it came from. */
  connectionName?: string | null;
  campaignName?: string | null;
  messageCount?: number;
};

export function rowFromInbox(row: api.InboxConversation): HistoryRow {
  return {
    id: row.id,
    botId: row.bot_id,
    lastActivity: row.last_message_at ?? row.created_at ?? null,
    visitor: row.contact_name ?? null,
    preview: row.last_message ?? null,
    status: row.status,
    channel: row.channel,
    connectionName: row.connection_name ?? null,
    campaignName: row.campaign_name ?? null,
  };
}

export function rowFromConversation(
  row: api.Conversation,
  botId: string,
): HistoryRow {
  return {
    id: row.id,
    botId,
    lastActivity: row.last_message_at ?? row.created_at,
    visitor: row.contact_name,
    status: row.status,
    channel: row.channel,
    messageCount: row.message_count,
  };
}

export const STATUS_OPTIONS = [
  { value: "open", label: "Open" },
  { value: "waiting_human", label: "Waiting for a reply" },
  { value: "resolved", label: "Resolved" },
];

export const CHANNEL_OPTIONS = [
  { value: "website", label: "Website" },
  { value: "whatsapp", label: "WhatsApp" },
  { value: "messenger", label: "Messenger" },
  { value: "instagram", label: "Instagram" },
];

export function formatChannel(channel: string): string {
  return (
    CHANNEL_OPTIONS.find((option) => option.value === channel)?.label ?? channel
  );
}

export function formatActivity(iso: string | null): string {
  return iso ? new Date(iso).toLocaleString() : "—";
}

/* ---- Row overflow menu ---------------------------------------------------- */

export function RowMenu({
  id,
  onDelete,
}: {
  id: string;
  onDelete: () => void;
}) {
  const details = useRef<HTMLDetailsElement>(null);
  const summary = useRef<HTMLElement>(null);
  const panel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onPointer(event: PointerEvent) {
      const el = details.current;
      if (
        el?.open &&
        event.target instanceof Node &&
        !el.contains(event.target)
      )
        el.open = false;
    }
    function onDismiss() {
      if (details.current?.open) details.current.open = false;
    }
    document.addEventListener("pointerdown", onPointer);
    window.addEventListener("resize", onDismiss);
    window.addEventListener("scroll", onDismiss, true);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      window.removeEventListener("resize", onDismiss);
      window.removeEventListener("scroll", onDismiss, true);
    };
  }, []);

  /* The table scrolls inside an overflow container, so the panel is fixed and
   * placed from the trigger's rectangle (logical inline-end edge). */
  function place() {
    const trigger = summary.current;
    const el = panel.current;
    if (!trigger || !el || !details.current?.open) return;
    const rect = trigger.getBoundingClientRect();
    const rtl = getComputedStyle(trigger).direction === "rtl";
    el.style.insetBlockStart = `${rect.bottom + 4}px`;
    el.style.insetInlineEnd = `${
      rtl ? rect.left : document.documentElement.clientWidth - rect.right
    }px`;
  }

  return (
    <details
      ref={details}
      className="row-menu"
      onToggle={place}
      onKeyDown={(event) => {
        if (event.key === "Escape" && details.current?.open) {
          details.current.open = false;
          summary.current?.focus();
        }
      }}
    >
      <summary
        ref={summary}
        aria-label="More actions"
        data-testid={`row-menu-${id}`}
        className="row-menu-trigger"
      >
        <svg
          viewBox="0 0 24 24"
          width="18"
          height="18"
          fill="currentColor"
          aria-hidden="true"
        >
          <circle cx="5" cy="12" r="1.8" />
          <circle cx="12" cy="12" r="1.8" />
          <circle cx="19" cy="12" r="1.8" />
        </svg>
      </summary>
      <div ref={panel} className="row-menu-panel">
        <ConfirmAction
          title="Delete conversation?"
          description="This conversation and its messages will be permanently deleted."
          testId={`delete-${id}`}
          onConfirm={() => {
            if (details.current) details.current.open = false;
            onDelete();
          }}
        >
          Delete conversation
        </ConfirmAction>
      </div>
    </details>
  );
}

/* ---- Table ---------------------------------------------------------------- */

export function HistoryTable({
  rows,
  tenantId,
  canDelete,
  onDelete,
  showPreview,
  showMessages,
}: {
  rows: HistoryRow[];
  tenantId: string;
  canDelete: boolean;
  onDelete: (row: HistoryRow) => void;
  showPreview?: boolean;
  showMessages?: boolean;
}) {
  const columns = [
    {
      key: "activity",
      header: "Last activity",
      className: "convo-date",
      cell: (row: HistoryRow): ReactNode => (
        <Link
          href={`/app/${tenantId}/bots/${row.botId}/conversations/${row.id}`}
        >
          <bdi dir="ltr">{formatActivity(row.lastActivity)}</bdi>
        </Link>
      ),
    },
    {
      key: "visitor",
      header: "Visitor",
      cell: (row: HistoryRow): ReactNode => (
        <bdi dir="auto">{row.visitor ?? "Visitor"}</bdi>
      ),
    },
    ...(showPreview
      ? [
          {
            key: "preview",
            header: "Preview",
            className: "history-preview",
            cell: (row: HistoryRow): ReactNode => (
              <span dir="auto" className="history-preview-text">
                {row.preview ?? ""}
              </span>
            ),
          },
        ]
      : []),
    {
      key: "status",
      header: "Status",
      cell: (row: HistoryRow): ReactNode => (
        <span data-status={row.status}>
          <StatusBadge value={row.status} />
        </span>
      ),
    },
    {
      key: "channel",
      header: "Channel",
      cell: (row: HistoryRow): ReactNode => (
        <>
          <bdi>{formatChannel(row.channel)}</bdi>
          {row.connectionName && (
            <small
              className="muted"
              dir="auto"
              data-testid="history-connection"
            >
              <br />
              {row.connectionName}
            </small>
          )}
          {row.campaignName && (
            <small className="muted" dir="auto" data-testid="history-campaign">
              <br />
              From campaign: <bdi>{row.campaignName}</bdi>
            </small>
          )}
        </>
      ),
    },
    ...(showMessages
      ? [
          {
            key: "messages",
            header: "Messages",
            cell: (row: HistoryRow): ReactNode => (
              <bdi dir="ltr">{row.messageCount}</bdi>
            ),
          },
        ]
      : []),
    {
      key: "actions",
      header: <span className="sr-only">Actions</span>,
      className: "history-actions",
      cell: (row: HistoryRow): ReactNode =>
        canDelete ? (
          <RowMenu id={row.id} onDelete={() => onDelete(row)} />
        ) : null,
    },
  ];
  return (
    <DataTable
      caption="Conversations"
      rows={rows}
      rowKey={(row) => row.id}
      columns={columns}
    />
  );
}

/* ---- Retention ------------------------------------------------------------ */

export function RetentionPanel({
  tenantId,
  role,
}: {
  tenantId: string;
  role: Parameters<typeof roleSatisfies>[0];
}) {
  const allowed = roleSatisfies(role, "admin");
  const [saved, setSaved] = useState<number | null | undefined>(undefined);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [justSaved, setJustSaved] = useState(false);

  useEffect(() => {
    if (!allowed) return;
    let live = true;
    const timer = setTimeout(() => {
      void api
        .getTenant(tenantId)
        .then((tenant) => {
          if (!live) return;
          const value = tenant.retention_days ?? null;
          setSaved(value);
          setDraft((current) =>
            current === "" && value ? String(value) : current,
          );
        })
        .catch(() => {
          if (live) setSaved(null);
        });
    }, 0);
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [allowed, tenantId]);

  if (!allowed) return null;

  async function save() {
    const text = draft.trim();
    const value = Number(text);
    if (
      !text ||
      Number.isNaN(value) ||
      !Number.isInteger(value) ||
      value < 1 ||
      value > 365
    ) {
      setError("Enter a retention value between 1 and 365 days.");
      setJustSaved(false);
      return;
    }
    try {
      const tenant = await api.updateTenant(tenantId, {
        retention_days: value,
      });
      setSaved(tenant.retention_days ?? value);
      setDraft(String(tenant.retention_days ?? value));
      setJustSaved(true);
      setError(null);
    } catch (caught) {
      setJustSaved(false);
      setError(
        caught instanceof Error
          ? caught.message
          : "Could not save the retention setting.",
      );
    }
  }

  const summaryValue =
    saved === undefined ? "" : saved === null ? "Default" : `${saved} days`;

  return (
    <details className="retention-panel" data-testid="retention-panel">
      <summary>
        <span className="retention-title">Data retention</span>
        {summaryValue && (
          <span className="retention-value">
            {" · "}
            <bdi dir="ltr">{summaryValue}</bdi>
          </span>
        )}
      </summary>
      <div className="retention-body">
        <p className="retention-hint">
          How long saved messages are kept before the background purge removes
          them. Applies to every conversation in this organization.
        </p>
        <div className="convo-retention">
          <Field label="Message retention (days, 1–365)">
            {(control) => (
              <input
                {...control}
                data-testid="retention-input"
                dir="ltr"
                inputMode="numeric"
                value={draft}
                placeholder="30"
                onChange={(event) => {
                  setDraft(event.target.value);
                }}
              />
            )}
          </Field>
          <Button data-testid="retention-save" onClick={() => void save()}>
            Save retention
          </Button>
        </div>
        {error && <Notice message={error} tone="error" scope="item" />}
        {justSaved && !error && (
          <p
            role="status"
            data-testid="retention-saved"
            className="convo-saved"
          >
            Retention updated. The background purge applies it on its next run.
          </p>
        )}
      </div>
    </details>
  );
}
