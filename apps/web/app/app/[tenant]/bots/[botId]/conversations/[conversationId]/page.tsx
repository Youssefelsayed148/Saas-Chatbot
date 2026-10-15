"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import * as api from "@/lib/api";
import { Loading, Notice } from "@/lib/ui";

/** P4-04: one thread view with citations (title + source link). */

export default function ConversationDetailPage() {
  const params = useParams<{
    tenant: string;
    botId: string;
    conversationId: string;
  }>();
  const tenantId = params.tenant;
  const botId = params.botId;
  const conversationId = params.conversationId;

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
    <main>
      <p className="eyebrow">
        <Link href={`/app/${tenantId}/bots/${botId}/conversations`}>
          Back to conversations
        </Link>
      </p>
      <h1 data-testid="conversation-detail-title">Conversation</h1>
      <p className="page-purpose">
        Read this visitor’s conversation and the sources behind its answers.
      </p>
      {error && <Notice message={error} tone="error" />}
      {detail ? (
        <section aria-label="Thread" data-testid="conversation-thread">
          <p className="muted">
            {detail.conversation.contact_name
              ? `Lead: ${detail.conversation.contact_name}`
              : "Anonymous visitor"}{" "}
            · {detail.conversation.channel} ·{" "}
            <span data-status={detail.conversation.status}>
              {detail.conversation.status}
            </span>
          </p>
          <ul>
            {detail.messages.map((message) => (
              <li key={message.id} data-role={message.sender_type}>
                <div dir="auto">{message.text}</div>
                {message.citations.length > 0 && (
                  <ul data-testid="thread-citations" aria-label="Sources">
                    {message.citations.map((citation) => (
                      <li key={citation.chunk_id}>
                        {citation.title}
                        {citation.source_url ? (
                          <>
                            {" — "}
                            <a
                              href={citation.source_url ?? "#"}
                              rel="noreferrer noopener"
                              target="_blank"
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
                  <Notice message="The assistant could not answer this from the knowledge." />
                )}
              </li>
            ))}
          </ul>
        </section>
      ) : (
        !error && <Loading label="Loading the conversation…" />
      )}
    </main>
  );
}
