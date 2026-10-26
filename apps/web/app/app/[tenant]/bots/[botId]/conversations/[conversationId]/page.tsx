"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import * as api from "@/lib/api";
import BotWorkspaceNav from "@/lib/bot-workspace-nav";
import { useSession } from "@/lib/session";
import { Card, LinkButton, Loading, Notice, StatusBadge } from "@/lib/ui";

import "@/app/convo-screen.css";

/** P4-04: one thread view with citations (title + source link). */

export default function ConversationDetailPage() {
  const { me } = useSession();
  const params = useParams<{
    tenant: string;
    botId: string;
    conversationId: string;
  }>();
  const tenantId = params.tenant;
  const botId = params.botId;
  const conversationId = params.conversationId;

  const isStaff = Boolean(me?.is_platform_staff);
  const backHref = isStaff
    ? `/app/${tenantId}/bots/${botId}/conversations`
    : `/app/${tenantId}/conversations`;

  const [detail, setDetail] = useState<api.ConversationDetailResponse | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const timer = setTimeout(() => {
      void (async () => {
        try {
          setDetail(await api.getConversation(tenantId, botId, conversationId));
          setError(null);
        } catch (caught) {
          setError(
            caught instanceof Error
              ? caught.message
              : "Could not load the conversation.",
          );
        }
      })();
    }, 0);
    return () => clearTimeout(timer);
  }, [tenantId, botId, conversationId]);

  return (
    <div className="convo-page">
      {isStaff && <BotWorkspaceNav tenantId={tenantId} botId={botId} />}
      <div className="convo-detail-head">
        <LinkButton variant="ghost" icon="arrow-left" href={backHref}>
          Back to conversations
        </LinkButton>
        <h2 data-testid="conversation-detail-title">Conversation</h2>
      </div>
      {error && <Notice message={error} tone="error" />}
      {detail ? (
        <Card aria-label="Thread" data-testid="conversation-thread">
          <p className="convo-meta">
            <span>
              {detail.conversation.contact_name ? (
                <>
                  Lead: <bdi dir="auto">{detail.conversation.contact_name}</bdi>
                </>
              ) : (
                "Anonymous visitor"
              )}
            </span>{" "}
            · <bdi>{detail.conversation.channel}</bdi> ·{" "}
            <span data-status={detail.conversation.status}>
              <StatusBadge value={detail.conversation.status} />
            </span>
          </p>
          <ul className="convo-thread">
            {detail.messages.map((message) => (
              <li key={message.id} data-role={message.sender_type}>
                <div dir="auto" className="convo-text">
                  {message.text}
                </div>
                {isStaff && message.citations.length > 0 && (
                  <ul data-testid="thread-citations" aria-label="Sources">
                    {message.citations.map((citation) => (
                      <li key={citation.chunk_id}>
                        <bdi dir="auto">{citation.title}</bdi>
                        {citation.source_url ? (
                          <>
                            {" — "}
                            <a
                              href={citation.source_url ?? "#"}
                              rel="noreferrer noopener"
                              target="_blank"
                              dir="ltr"
                            >
                              {citation.source_url}
                            </a>
                          </>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                )}
                {message.needs_human && (
                  <Notice message="The assistant could not confirm an answer." />
                )}
              </li>
            ))}
          </ul>
        </Card>
      ) : (
        !error && <Loading label="Loading the conversation…" />
      )}
    </div>
  );
}
