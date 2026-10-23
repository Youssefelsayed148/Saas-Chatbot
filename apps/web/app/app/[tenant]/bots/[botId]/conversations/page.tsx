"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import * as api from "@/lib/api";
import type { Conversation } from "@/lib/api";
import { roleSatisfies, useSession } from "@/lib/session";
import {
  Button,
  Card,
  ConfirmAction,
  DataTable,
  Empty,
  Field,
  FormSection,
  Loading,
  Notice,
  PageHeader,
  StatusBadge,
} from "@/lib/ui";
import BotWorkspaceNav from "@/lib/bot-workspace-nav";

import "@/app/convo-screen.css";

/** P4-04: read-only conversations view (docs/10 Conversations tab) with the
 * tenant retention control (docs/14 §7). Live inbox views arrive in P5. */

export default function ConversationsPage() {
  const params = useParams<{ tenant: string; botId: string }>();
  const tenantId = params.tenant;
  const botId = params.botId;
  const { roleIn } = useSession();
  const role = roleIn(tenantId);
  const canDelete = roleSatisfies(role, "admin");
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
    <main className="convo-page">
      <BotWorkspaceNav tenantId={tenantId} botId={botId} />
      <PageHeader
        title="Conversations"
        purpose="Review saved visitor conversations and manage retention."
      />
      {error && <Notice message={error} tone="error" />}
      {canTenant && (
        <FormSection
          title="Retention"
          description="How long saved messages are kept before the background purge removes them."
        >
          <div className="convo-retention">
            <Field
              label="Message retention (days, tenant-wide, 1–365)"
              hint="Applies to every conversation in this organization."
            >
              {(control) => (
                <input
                  {...control}
                  data-testid="retention-input"
                  dir="ltr"
                  inputMode="numeric"
                  value={retentionDraft}
                  placeholder="30"
                  onChange={(event) => setRetentionDraft(event.target.value)}
                />
              )}
            </Field>
            <Button
              data-testid="retention-save"
              onClick={() => void saveRetention()}
            >
              Save retention
            </Button>
          </div>
          {retentionSaved && (
            <p
              role="status"
              data-testid="retention-saved"
              className="convo-saved"
            >
              Retention updated. The background purge applies it on its next
              run.
            </p>
          )}
        </FormSection>
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
          <Loading label="Loading conversations…" />
        ) : rows.length === 0 ? (
          <Empty>
            No conversations yet — visitors see your widget on the installed
            site, and threads appear here.
          </Empty>
        ) : (
          <DataTable
            caption="Conversations"
            rows={rows}
            rowKey={(row) => row.id}
            columns={[
              {
                key: "activity",
                header: "Last activity",
                className: "convo-date",
                cell: (row) => (
                  <Link
                    href={`/app/${tenantId}/bots/${botId}/conversations/${row.id}`}
                  >
                    <bdi dir="ltr">
                      {row.last_message_at
                        ? new Date(row.last_message_at).toLocaleString()
                        : new Date(row.created_at).toLocaleString()}
                    </bdi>
                  </Link>
                ),
              },
              {
                key: "channel",
                header: "Channel",
                cell: (row) => <bdi>{row.channel}</bdi>,
              },
              {
                key: "status",
                header: "Status",
                cell: (row) => (
                  <span data-status={row.status}>
                    <StatusBadge value={row.status} />
                  </span>
                ),
              },
              {
                key: "lead",
                header: "Lead",
                cell: (row) => <bdi dir="auto">{row.contact_name ?? "—"}</bdi>,
              },
              {
                key: "messages",
                header: "Messages",
                cell: (row) => <bdi dir="ltr">{row.message_count}</bdi>,
              },
              {
                key: "actions",
                header: <span className="sr-only">Actions</span>,
                cell: (row) =>
                  canDelete && (
                    <ConfirmAction
                      title="Delete conversation?"
                      description={
                        "This conversation and its messages will be permanently deleted."
                      }
                      testId={`delete-${row.id}`}
                      onConfirm={() => void removeThread(row.id)}
                    >
                      Delete
                    </ConfirmAction>
                  ),
              },
            ]}
          />
        )}
        {total !== null && rows !== null && total > rows.length && (
          <p className="convo-more">
            Showing {rows.length} of {total} conversations (newest first).
          </p>
        )}
      </Card>
    </main>
  );
}
