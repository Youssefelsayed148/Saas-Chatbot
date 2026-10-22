"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import * as api from "@/lib/api";
import type { PlaygroundMessage } from "@/lib/api";
import { useSession } from "@/lib/session";
import {
  Button,
  Field,
  Loading,
  Notice,
  PageHeader,
  StatusBadge,
} from "@/lib/ui";
import BotWorkspaceNav from "@/lib/bot-workspace-nav";
import { Icon } from "@/lib/icons";
import "@/app/playground-screen.css";

type Chunk = api.RagTrace["trace"]["chunks"][number];

function TraceChunk({ chunk }: { chunk: Chunk }) {
  const gate = chunk.gate;
  return (
    <li className="trace-chunk" data-accepted={chunk.accepted}>
      <p className="trace-chunk-title">
        {chunk.title} ({chunk.locator}) · cosine{" "}
        {chunk.vector_similarity?.toFixed(3) ?? "—"} · FTS{" "}
        {chunk.fts_match.toFixed(3)} ·{" "}
        <StatusBadge
          value={chunk.accepted ? "used" : "excluded"}
          tone={chunk.accepted ? "success" : "neutral"}
        />
      </p>
      {(gate || chunk.query_terms || chunk.matched_terms) && (
        <dl className="trace-facts">
          {gate && (
            <>
              <dt>Gate verdict</dt>
              <dd>
                {gate.passed
                  ? `Passed${gate.accepted_by ? ` by ${gate.accepted_by}` : ""}`
                  : "Rejected"}
                {gate.reason ? `: ${gate.reason}` : ""}
              </dd>
            </>
          )}
          {chunk.query_terms && chunk.query_terms.length > 0 && (
            <>
              <dt>Query terms</dt>
              <dd dir="auto">{chunk.query_terms.join(", ")}</dd>
            </>
          )}
          {chunk.matched_terms && (
            <>
              <dt>Matched terms</dt>
              <dd dir="auto">
                {chunk.matched_terms.length > 0
                  ? chunk.matched_terms.join(", ")
                  : "none"}
                {gate
                  ? ` (${gate.terms.matched} of ${gate.terms.required} required)`
                  : ""}
              </dd>
            </>
          )}
          {gate?.cosine.floor != null && (
            <>
              <dt>Cosine floor</dt>
              <dd>{gate.cosine.floor.toFixed(2)}</dd>
            </>
          )}
        </dl>
      )}
    </li>
  );
}

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

  // A failed send keeps the typed message in the box, so the existing send
  // handler can run again as a real retry. Other errors (feedback failure, an
  // assistant-state note after a successful turn) have nothing to resend and
  // keep the default page reload, labelled as such.
  const canRetryTurn = !!draft.trim() && !sending;

  return (
    <main className="playground-page">
      <BotWorkspaceNav tenantId={tenantId} botId={botId} />
      <PageHeader
        title="Playground"
        purpose="Test answers against your published knowledge before visitors do."
      />
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

      <section
        aria-label="Conversation"
        data-testid="thread"
        className="ui-card"
      >
        {messages === null ? (
          <Loading label="Loading the conversation…" />
        ) : messages.length === 0 ? (
          <p className="muted">
            No messages yet — ask something about the published knowledge.
          </p>
        ) : (
          <ul className="chat-list">
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
                  <div className="message-meta">
                    {message.response_ms !== null && (
                      <span className="muted">{message.response_ms} ms</span>
                    )}
                    {canChat && message.sender_type === "ai" && (
                      <span className="feedback-buttons">
                        <button
                          type="button"
                          className="icon-button"
                          aria-label="Thumbs up"
                          data-testid={`thumbs-up-${message.id}`}
                          disabled={feedbackGiven[message.id] !== undefined}
                          onClick={() => void giveFeedback(message, "up")}
                        >
                          <Icon name="thumbs-up" />
                        </button>
                        <button
                          type="button"
                          className="icon-button"
                          aria-label="Thumbs down"
                          data-testid={`thumbs-down-${message.id}`}
                          disabled={feedbackGiven[message.id] !== undefined}
                          onClick={() => void giveFeedback(message, "down")}
                        >
                          <Icon name="thumbs-down" />
                        </button>
                      </span>
                    )}
                  </div>
                </li>
              ),
            )}
          </ul>
        )}
        <div ref={bottomRef} />
      </section>

      {sendError && !notReady && (
        <Notice
          message={sendError}
          tone="error"
          {...(canRetryTurn
            ? {
                onRetry: () =>
                  void onSend({
                    preventDefault() {},
                  } as React.FormEvent),
                retryLabel: "Retry message",
              }
            : { retryLabel: "Reload page" })}
        />
      )}
      <form
        onSubmit={onSend}
        aria-label="Playground input"
        className="composer"
      >
        <Field label="Message">
          {(control) => (
            <input
              {...control}
              data-testid="playground-input"
              dir="auto"
              value={draft}
              maxLength={1000}
              disabled={!canChat || sending}
              onChange={(event) => setDraft(event.target.value)}
            />
          )}
        </Field>
        {canChat && (
          <Button
            type="submit"
            data-testid="playground-send"
            disabled={sending || !draft.trim()}
          >
            {sending ? "Sending…" : "Send"}
          </Button>
        )}
      </form>

      <section
        aria-label="Answer traces"
        data-testid="answer-traces"
        className="ui-card"
      >
        <header className="section-heading">
          <h2>Answer traces</h2>
        </header>
        {traceError && <Notice message={traceError} tone="error" />}
        {traces.length === 0 && (
          <p className="muted">No recorded answers yet.</p>
        )}
        {traces.map(({ message_id, trace }) => (
          <details key={message_id} className="trace">
            <summary>
              {trace.retrieval_mode} · {trace.gate} ·{" "}
              {trace.rewrite_used ? "rewritten" : "original query"}
            </summary>
            {trace.provider_error && (
              <p className="trace-error" role="note">
                Provider error: status{" "}
                {trace.provider_error.status ?? "unknown"}
                {trace.provider_error.model
                  ? ` on ${trace.provider_error.model}`
                  : ""}
                . The visitor saw the temporary-unavailable message.
              </p>
            )}
            <p>
              Model: {trace.model ?? "No generation"}; tokens:{" "}
              {trace.tokens?.total_tokens ?? "Unmeasured"}; cost:{" "}
              {trace.cost_usd === null ? "Unmeasured" : `$${trace.cost_usd}`}
            </p>
            {(trace.streamed !== undefined ||
              trace.degradation_reason ||
              trace.stream_invalid_reason) && (
              <dl className="trace-facts">
                {trace.streamed !== undefined && (
                  <>
                    <dt>Delivery</dt>
                    <dd>
                      {trace.streamed ? "Streamed" : "Not streamed"}
                      {trace.stream_mode ? ` (${trace.stream_mode})` : ""}
                      {trace.time_to_first_token_ms != null
                        ? ` · first token after ${trace.time_to_first_token_ms} ms`
                        : ""}
                    </dd>
                  </>
                )}
                {trace.stream_invalid_reason && (
                  <>
                    <dt>Stream fallback</dt>
                    <dd>{trace.stream_invalid_reason}</dd>
                  </>
                )}
                {trace.degradation_reason && (
                  <>
                    <dt>Retrieval degraded</dt>
                    <dd>{trace.degradation_reason}</dd>
                  </>
                )}
              </dl>
            )}
            <ul className="trace-chunks">
              {trace.chunks.map((chunk) => (
                <TraceChunk key={chunk.chunk_id} chunk={chunk} />
              ))}
            </ul>
          </details>
        ))}
      </section>
    </main>
  );
}
