"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import * as api from "@/lib/api";
import type { PlaygroundMessage } from "@/lib/api";
import { useSession } from "@/lib/session";
import { Loading, Notice } from "@/lib/ui";
import BotWorkspaceNav from "@/lib/bot-workspace-nav";
import { Icon } from "@/lib/icons";

export default function PlaygroundPage() {
  const params = useParams<{ tenant: string; botId: string }>();
  const tenantId = params.tenant;
  const botId = params.botId;
  const { me } = useSession();
  const canChat = !!me?.is_platform_staff;

  const [messages, setMessages] = useState<PlaygroundMessage[] | null>(null);
  const [threadError, setThreadError] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  const [notReady, setNotReady] = useState(false);
  const [traces, setTraces] = useState<api.RagTrace[]>([]);
  const [traceError, setTraceError] = useState<string | null>(null);
  const [feedbackGiven, setFeedbackGiven] = useState<
    Record<string, "up" | "down">
  >({});
  const bottomRef = useRef<HTMLDivElement | null>(null);

  const loadThread = useCallback(async () => {
    try {
      const thread = await api.playgroundConversation(tenantId, botId);
      setMessages(thread.messages);
      setThreadError(null);
    } catch (caught) {
      setThreadError(
        caught instanceof Error
          ? caught.message
          : "Could not load the conversation.",
      );
    }
  }, [tenantId, botId]);

  const loadTraces = useCallback(async () => {
    try {
      setTraces(await api.ragTraces(tenantId, botId));
      setTraceError(null);
    } catch {
      setTraceError("Could not load answer traces.");
    }
  }, [tenantId, botId]);

  useEffect(() => {
    if (!me?.is_platform_staff) return;
    const timer = setTimeout(() => {
      void loadThread();
      void loadTraces();
    }, 0);
    return () => clearTimeout(timer);
  }, [loadThread, loadTraces, me?.is_platform_staff]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "nearest" });
  }, [messages]);

  async function onSend(event: React.FormEvent) {
    event.preventDefault();
    const text = draft.trim();
    if (!text || sending) return;
    setSendError(null);
    setSending(true);
    try {
      const turn = await api.playgroundTurn(tenantId, botId, text);
      void loadTraces();
      setDraft("");
      setNotReady(false);
      setMessages((current) => [
        ...(current ?? []),
        {
          id: turn.visitor_message.id,
          sender_type: "visitor",
          text: turn.visitor_message.text,
          citations: null,
          can_answer: null,
          needs_human: false,
          response_ms: null,
          created_at: turn.visitor_message.created_at,
        },
        {
          id: turn.ai_message.id,
          sender_type: "ai",
          text: turn.ai_message.text,
          citations: turn.ai_message.citations,
          can_answer: turn.ai_message.can_answer,
          needs_human: turn.ai_message.needs_human,
          response_ms: turn.ai_message.response_ms,
          created_at: turn.ai_message.created_at,
        },
      ]);
      if (turn.kind !== "answer") {
        setSendError(
          turn.kind === "smalltalk" ? null : `Assistant state: ${turn.kind}`,
        );
      }
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "Send failed.";
      if (/MODEL_NOT_CONFIGURED|No chat model/.test(message)) setNotReady(true);
      setSendError(message);
    } finally {
      setSending(false);
    }
  }

  async function giveFeedback(
    message: PlaygroundMessage,
    rating: "up" | "down",
  ) {
    try {
      await api.messageFeedback(tenantId, botId, message.id, rating);
      setFeedbackGiven((current) => ({ ...current, [message.id]: rating }));
    } catch (caught) {
      setSendError(
        caught instanceof Error ? caught.message : "Feedback failed.",
      );
    }
  }

  if (!me?.is_platform_staff) return null;

  return (
    <main>
      <BotWorkspaceNav tenantId={tenantId} botId={botId} />
      <h1>Playground</h1>
      <p className="page-purpose">
        Test answers against your published knowledge before visitors do.
      </p>
      {!canChat && (
        <Notice message="Only platform operators can use the playground." />
      )}
      {notReady && (
        <Notice
          message="The assistant is not configured for this deployment yet (no model key). Add the provider key, or run with the deterministic dev stub model."
          tone="error"
        />
      )}
      {threadError && <Notice message={threadError} tone="error" />}

      <section aria-label="Conversation" data-testid="thread">
        {messages === null ? (
          <Loading label="Loading the conversation…" />
        ) : messages.length === 0 ? (
          <p className="muted">
            No messages yet — ask something about the published knowledge.
          </p>
        ) : (
          <ul>
            {messages.map((message) =>
              message.sender_type === "visitor" ? (
                <li key={message.id} data-role="visitor">
                  {message.text}
                </li>
              ) : (
                <li key={message.id} data-role={message.sender_type}>
                  <div dir="auto">{message.text}</div>
                  {message.citations && message.citations.length > 0 && (
                    <ul data-testid="citations" aria-label="Sources">
                      {message.citations.map((citation) => (
                        <li key={citation.chunk_id}>
                          {citation.title}
                          {citation.source_url ? (
                            <>
                              {" — "}
                              <a
                                href={citation.source_url}
                                rel="noreferrer noopener"
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
                  {message.response_ms !== null && (
                    <span className="muted">{message.response_ms} ms</span>
                  )}
                  {canChat && message.sender_type === "ai" && (
                    <span>
                      <button
                        type="button"
                        aria-label="Thumbs up"
                        data-testid={`thumbs-up-${message.id}`}
                        disabled={feedbackGiven[message.id] !== undefined}
                        onClick={() => void giveFeedback(message, "up")}
                      >
                        <Icon name="thumbs-up" />
                      </button>
                      <button
                        type="button"
                        aria-label="Thumbs down"
                        data-testid={`thumbs-down-${message.id}`}
                        disabled={feedbackGiven[message.id] !== undefined}
                        onClick={() => void giveFeedback(message, "down")}
                      >
                        <Icon name="thumbs-down" />
                      </button>
                    </span>
                  )}
                </li>
              ),
            )}
          </ul>
        )}
        <div ref={bottomRef} />
      </section>

      <section aria-label="Answer traces" data-testid="answer-traces">
        <h2>Answer traces</h2>
        {traceError && <Notice message={traceError} tone="error" />}
        {traces.length === 0 && (
          <p className="muted">No recorded answers yet.</p>
        )}
        {traces.map(({ message_id, trace }) => (
          <details key={message_id}>
            <summary>
              {trace.retrieval_mode} · {trace.gate} ·{" "}
              {trace.rewrite_used ? "rewritten" : "original query"}
            </summary>
            <p>
              Model: {trace.model ?? "No generation"}; tokens:{" "}
              {trace.tokens?.total_tokens ?? "Unmeasured"}; cost:{" "}
              {trace.cost_usd === null ? "Unmeasured" : `$${trace.cost_usd}`}
            </p>
            <ul>
              {trace.chunks.map((chunk) => (
                <li key={chunk.chunk_id}>
                  {chunk.title} ({chunk.locator}) · cosine{" "}
                  {chunk.vector_similarity?.toFixed(3) ?? "—"} · FTS{" "}
                  {chunk.fts_match.toFixed(3)} ·{" "}
                  {chunk.accepted ? "used" : "excluded"}
                </li>
              ))}
            </ul>
          </details>
        ))}
      </section>

      {sendError && !notReady && <Notice message={sendError} tone="error" />}
      <form onSubmit={onSend} aria-label="Playground input">
        <label>
          Message
          <input
            data-testid="playground-input"
            dir="auto"
            value={draft}
            maxLength={1000}
            disabled={!canChat || sending}
            onChange={(event) => setDraft(event.target.value)}
          />
        </label>
        {canChat && (
          <button
            type="submit"
            data-testid="playground-send"
            disabled={sending || !draft.trim()}
          >
            {sending ? "Sending…" : "Send"}
          </button>
        )}
      </form>
    </main>
  );
}
