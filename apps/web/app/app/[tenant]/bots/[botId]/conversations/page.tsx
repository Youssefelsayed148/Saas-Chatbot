"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import * as api from "@/lib/api";
import BotWorkspaceNav from "@/lib/bot-workspace-nav";
import {
  HistoryTable,
  RetentionPanel,
  rowFromConversation,
  type HistoryRow,
} from "@/lib/conversation-history";
import { roleSatisfies, useSession } from "@/lib/session";
import { Card, Empty, Loading, Notice } from "@/lib/ui";

import "@/app/convo-screen.css";

/** Per-bot History (P4-04, B5): saved conversations of one bot with the tenant
 * retention control (docs/14 §7). Uses api.listConversations (message count,
 * no preview, no pagination). */

export default function ConversationsPage() {
  const params = useParams<{ tenant: string; botId: string }>();
  const tenantId = params.tenant;
  const botId = params.botId;
  const { roleIn } = useSession();
  const role = roleIn(tenantId);
  const canDelete = roleSatisfies(role, "admin");

  const [rows, setRows] = useState<HistoryRow[] | null>(null);
  const [total, setTotal] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await api.listConversations(tenantId, botId);
      setRows(data.conversations.map((row) => rowFromConversation(row, botId)));
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
    <div className="convo-page">
      <BotWorkspaceNav tenantId={tenantId} botId={botId} />
      <RetentionPanel tenantId={tenantId} role={role} />
      {error && (
        <Notice
          message={error}
          tone="error"
          retryLabel="Try again"
          onRetry={() => void load()}
        />
      )}
      <Card
        title="Saved conversations"
        aria-label="Conversation list"
        data-testid="conversations"
        actions={
          total !== null ? (
            <span className="convo-count">
              <bdi dir="ltr">{total}</bdi> in total
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
            No conversations yet — visitors see your widget on the installed
            site, and threads appear here.
          </Empty>
        ) : (
          <HistoryTable
            rows={rows}
            tenantId={tenantId}
            canDelete={canDelete}
            showMessages
            onDelete={(row) => void removeThread(row.id)}
          />
        )}
        {total !== null && rows !== null && total > rows.length && (
          <p className="convo-more">
            Showing {rows.length} of {total} conversations (newest first).
          </p>
        )}
      </Card>
    </div>
  );
}
