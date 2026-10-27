"use client";

import { MessageBody } from "@/lib/message-body";
import { useParams, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  ChannelDelivery,
  ChannelReplyFields,
  connectionReplyBlock,
} from "@/lib/channel-delivery";
import { InboxList } from "@/lib/inbox-list";
import { humanLabel } from "@/lib/labels";
import * as api from "@/lib/api";
import type { InboxThread, Member } from "@/lib/api";
import { roleSatisfies, useSession } from "@/lib/session";
import { Button, LinkButton, Loading, Notice, StatusBadge } from "@/lib/ui";
import "@/app/inbox-screen.css";
import "@/app/channels-screen.css";

export default function InboxConversationPage() {
  const params = useParams<{ tenant: string; conversation: string }>();
  const search = useSearchParams();
  const tenantId = params.tenant;
  const conversationId = params.conversation;
  const { me, roleIn } = useSession();
  const canEdit =
    !me?.is_platform_staff &&
    roleSatisfies(roleIn(tenantId), "editor") &&
    !!me?.memberships.some((member) => member.tenant_id === tenantId);
  const [thread, setThread] = useState<InboxThread | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [reply, setReply] = useState("");
  const [note, setNote] = useState("");
  const [tag, setTag] = useState("");
  const [assignee, setAssignee] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await api.getInboxThread(tenantId, conversationId);
      setThread(data);
      setAssignee(data.conversation.assigned_user_id ?? "");
      setError(null);
      if (canEdit) await api.markInboxRead(tenantId, conversationId);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Could not load conversation.",
      );
    }
  }, [conversationId, tenantId, canEdit]);

  useEffect(() => {
    const timer = setTimeout(() => void load(), 0);
    const stream = new EventSource(`/api/v1/tenants/${tenantId}/inbox/events`);
    const refresh = () => void load();
    stream.addEventListener("inbox.update", refresh);
    return () => {
      clearTimeout(timer);
      stream.close();
    };
  }, [load, tenantId]);

  useEffect(() => {
    if (!canEdit) return;
    const timer = setTimeout(() => {
      void api
        .listAssignees(tenantId)
        .then(setMembers)
        .catch(() => setMembers([]));
    }, 0);
    return () => clearTimeout(timer);
  }, [tenantId, canEdit]);

  const threadRef = useRef<HTMLElement>(null);
  const messageCount = thread?.messages.length ?? 0;
  useEffect(() => {
    const el = threadRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messageCount]);

  async function run(action: () => Promise<unknown>) {
    if (busy) return;
    setBusy(true);
    try {
      await action();
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The action failed.");
    } finally {
      setBusy(false);
    }
  }

  const backHref = `/app/${tenantId}/inbox${search.toString() ? `?${search.toString()}` : ""}`;
  if (!thread)
    return (
      <div className="inbox-workspace">
        <div className="inbox-side">
          <InboxList compact selectedId={conversationId} />
        </div>
        <section className="conversation-pane" aria-label="Conversation">
          <div className="conversation-head">
            <LinkButton
              variant="ghost"
              size="sm"
              icon="arrow-left"
              href={backHref}
            >
              Back to inbox
            </LinkButton>
          </div>
          {error ? (
            <Notice message={error} tone="error" />
          ) : (
            <Loading label="Loading conversation…" />
          )}
        </section>
      </div>
    );
  const conversation = thread.conversation;
  const sendReply = () =>
    run(async () => {
      await api.sendAgentReply(tenantId, conversationId, reply);
      setReply("");
    });
  const saveNote = () =>
    run(async () => {
      await api.addConversationNote(tenantId, conversationId, note);
      setNote("");
    });
  const assign = (value: string) =>
    run(() =>
      api.inboxAction(tenantId, conversationId, "assign", {
        assigned_user_id: value || null,
      }),
    );

  return (
    <div className="inbox-workspace">
      <div className="inbox-side">
        <InboxList compact selectedId={conversationId} />
      </div>
      <section className="conversation-pane" aria-label="Conversation">
        <div className="conversation-head">
          <LinkButton
            variant="ghost"
            size="sm"
            icon="arrow-left"
            href={backHref}
          >
            Back to inbox
          </LinkButton>
          <h2 dir="auto">
            {conversation.contact_name?.trim() || "Conversation"}
          </h2>
        </div>
        {me?.is_platform_staff && (
          <p role="note" className="staff-note">
            Staff view is read-only; replies come from client team members
          </p>
        )}
        {error && <Notice message={error} tone="error" />}
        <section
          aria-label="Conversation controls"
          className="conversation-controls"
        >
          <span className="conversation-summary">
            <span className="channel-badge" data-testid="inbox-channel">
              {humanLabel(conversation.channel)}
            </span>
            {conversation.connection_name && (
              <>
                {" "}
                <span dir="auto" data-testid="inbox-connection">
                  {conversation.connection_name}
                </span>
              </>
            )}
            {conversation.campaign_name && (
              <>
                {" "}
                <span className="channel-badge" data-testid="inbox-campaign">
                  From campaign: <bdi>{conversation.campaign_name}</bdi>
                </span>
              </>
            )}{" "}
            ·{" "}
            <strong
              data-testid="inbox-status"
              title={conversation.status}
              data-value={conversation.status}
            >
              <StatusBadge value={conversation.status}>
                {humanLabel(conversation.status)}
              </StatusBadge>
            </strong>{" "}
            ·{" "}
            <span data-testid="inbox-mode">
              {conversation.mode === "human" ? "Human" : "AI"} mode
            </span>
          </span>
          {canEdit && conversation.status !== "resolved" && (
            <>
              {conversation.mode === "human" ? (
                <Button
                  disabled={busy}
                  onClick={() =>
                    void run(() =>
                      api.inboxAction(tenantId, conversationId, "return-to-ai"),
                    )
                  }
                >
                  Return to AI
                </Button>
              ) : (
                <Button
                  disabled={busy}
                  onClick={() =>
                    void run(() =>
                      api.inboxAction(tenantId, conversationId, "takeover"),
                    )
                  }
                >
                  Take over
                </Button>
              )}
              <Button
                variant="quiet"
                disabled={busy}
                onClick={() =>
                  void run(() =>
                    api.inboxAction(tenantId, conversationId, "resolve"),
                  )
                }
              >
                Resolve
              </Button>
            </>
          )}
          {canEdit && (
            <label>
              Assignee{" "}
              <select
                aria-label="Assignee"
                value={assignee}
                disabled={busy}
                onChange={(e) => void assign(e.target.value)}
              >
                <option value="">Unassigned</option>
                {members
                  .filter((member) => member.status === "active")
                  .map((member) => (
                    <option key={member.user_id} value={member.user_id}>
                      {member.email} ({member.role})
                    </option>
                  ))}
              </select>
            </label>
          )}
        </section>
        <section aria-label="Conversation tags" className="conversation-tags">
          <strong>Tags</strong>{" "}
          <span className="tag-list">
            {conversation.tags?.map((value) => (
              <span key={value} className="tag-item">
                <bdi>{value}</bdi>{" "}
                {canEdit && (
                  <Button
                    variant="quiet"
                    aria-label={`Remove ${value} tag`}
                    onClick={() =>
                      void run(() =>
                        api.removeInboxTag(tenantId, conversationId, value),
                      )
                    }
                  >
                    ×
                  </Button>
                )}
              </span>
            ))}
          </span>
          {canEdit && (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                if (tag.trim())
                  void run(async () => {
                    await api.addInboxTag(tenantId, conversationId, tag);
                    setTag("");
                  });
              }}
            >
              <label>
                Add tag{" "}
                <input
                  value={tag}
                  maxLength={32}
                  onChange={(e) => setTag(e.target.value)}
                />
              </label>
              <Button type="submit" disabled={!tag.trim() || busy}>
                Add
              </Button>
            </form>
          )}
        </section>
        <section
          ref={threadRef}
          aria-label="Thread"
          data-testid="inbox-thread"
          className="inbox-thread-scroll"
        >
          <ol className="chat-thread">
            {thread.messages.map((message) => {
              const isNote =
                message.sender_type === "system" &&
                message.text.startsWith("Internal note: ");
              const noteText = isNote
                ? message.text.slice("Internal note: ".length)
                : message.text;
              return (
                <li
                  key={message.id}
                  data-role={isNote ? "note" : message.sender_type}
                >
                  <strong>
                    {isNote
                      ? "Internal note"
                      : message.sender_type === "visitor"
                        ? "Visitor"
                        : message.sender_type === "ai"
                          ? "Assistant"
                          : message.sender_type === "agent"
                            ? "Agent"
                            : "Conversation event"}
                  </strong>
                  <time className="muted message-time">
                    {new Date(message.created_at).toLocaleString()}
                  </time>
                  <div dir="auto" className="message-text">
                    {message.sender_type === "ai" && !isNote ? (
                      <MessageBody text={noteText} />
                    ) : (
                      noteText
                    )}
                  </div>
                  {me?.is_platform_staff && message.citations.length > 0 && (
                    <details className="source-details" open>
                      <summary>Sources ({message.citations.length})</summary>
                      <ul aria-label="Sources" data-testid="thread-citations">
                        {message.citations.map((citation) => (
                          <li key={citation.chunk_id}>
                            {citation.title ?? citation.heading ?? "Source"}
                            {citation.page_ref ? ` · ${citation.page_ref}` : ""}
                            {citation.source_url &&
                            ["https:", "http:"].some((protocol) =>
                              citation.source_url?.startsWith(protocol),
                            ) ? (
                              <>
                                {" "}
                                ·{" "}
                                <a
                                  href={citation.source_url}
                                  target="_blank"
                                  rel="noreferrer noopener"
                                >
                                  Open source
                                </a>
                              </>
                            ) : null}
                          </li>
                        ))}
                      </ul>
                    </details>
                  )}
                  <ChannelDelivery
                    channel={conversation.channel}
                    message={message}
                    resendBusy={busy}
                    onResend={
                      canEdit && conversation.connection_status === "active"
                        ? () =>
                            void run(() =>
                              api.resendChannelMessage(
                                tenantId,
                                conversationId,
                                message.id,
                              ),
                            )
                        : undefined
                    }
                  />
                  {message.can_answer === true &&
                    message.sender_type === "ai" && (
                      <small>Assistant reply</small>
                    )}
                  {(message.feedback?.length ?? 0) > 0 && (
                    <p aria-label="Visitor feedback">
                      Visitor feedback:{" "}
                      {message.feedback
                        ?.map((rating) =>
                          rating === "up" ? "Helpful" : "Not helpful",
                        )
                        .join(", ")}
                    </p>
                  )}
                  {message.needs_human && (
                    <p role="note">Human follow-up requested</p>
                  )}
                </li>
              );
            })}
          </ol>
        </section>
        {canEdit && conversation.status !== "resolved" && (
          <section aria-label="Reply and notes" className="reply-notes">
            {conversation.mode === "human" && (
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  if (reply.trim()) void sendReply();
                }}
              >
                <ChannelReplyFields
                  value={reply}
                  busy={busy}
                  block={connectionReplyBlock(
                    conversation.channel,
                    conversation.connection_status,
                  )}
                  onChange={(e) => setReply(e.target.value)}
                />
              </form>
            )}
            <form
              onSubmit={(e) => {
                e.preventDefault();
                if (note.trim()) void saveNote();
              }}
            >
              <label>
                Internal note
                <textarea
                  dir="auto"
                  aria-label="Internal note"
                  value={note}
                  maxLength={4000}
                  onChange={(e) => setNote(e.target.value)}
                  rows={2}
                />
              </label>
              <Button type="submit" disabled={!note.trim() || busy}>
                Add note
              </Button>
            </form>
          </section>
        )}
        {!canEdit && !me?.is_platform_staff && (
          <p className="muted">
            Viewer access: replies and conversation changes are disabled.
          </p>
        )}
      </section>
    </div>
  );
}
