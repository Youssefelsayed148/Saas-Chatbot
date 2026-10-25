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

/** Staff-only wording for a turn whose model call failed (the visitor text is
 * unchanged): the provider's error code, or the HTTP status / outcome when it
 * sent none, and the model it came from. */
function providerFailureNotice(failure: api.ProviderError): string {
  if (failure.status === "not_configured") {
    return "The model call failed: no chat model is configured for this bot.";
  }
  const last = failure.attempts?.[failure.attempts.length - 1];
  const reason =
    failure.error_code ??
    (failure.http_status ? `HTTP ${failure.http_status}` : null) ??
    last?.outcome ??
    "no response";
  const where = failure.model ? ` on ${failure.model}` : "";
  return `The model call failed: ${reason}${where}.`;
}

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
  // The turn in flight: the question and the answer text streamed so far.
  const [pending, setPending] = useState<{
    question: string;
    answer: string;
  } | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const [notReady, setNotReady] = useState(false);
  const [traces, setTraces] = useState<api.RagTrace[]>([]);
  const [traceError, setTraceError] = useState<string | null>(null);
  const [feedbackGiven, setFeedbackGiven] = useState<
    Record<string, "up" | "down">
  >({});
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

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

  // The input is disabled while an answer is pending, which drops keyboard
  // focus to the page body; hand it back once the reply (or error) is in.
  const wasSending = useRef(false);
  useEffect(() => {
    if (
      wasSending.current &&
      !sending &&
      document.activeElement === document.body
    )
      inputRef.current?.focus();
    wasSending.current = sending;
  }, [sending]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "nearest" });
  }, [messages]);

  async function onSend(event: React.FormEvent) {
    event.preventDefault();
    const text = draft.trim();
    if (!text || sending) return;
    setSendError(null);
    setSending(true);
    const controller = new AbortController();
    abortRef.current = controller;
    setPending({ question: text, answer: "" });
    try {
      let turn: api.PlaygroundTurnResponse;
      try {
        turn = await api.playgroundTurnStream(tenantId, botId, text, {
          signal: controller.signal,
          onDelta: (piece) =>
            setPending((current) =>
              current
                ? { ...current, answer: current.answer + piece }
                : current,
            ),
          onCannotConfirm: (canned) =>
            setPending((current) =>
              current ? { ...current, answer: canned } : current,
            ),
        });
      } catch (caught) {
        // A broken stream falls back to the buffered turn; HTTP refusals and
        // a user stop do not.
        if (!(caught instanceof api.PlaygroundStreamFailure)) throw caught;
        setPending((current) =>
          current ? { ...current, answer: "" } : current,
        );
        turn = await api.playgroundTurn(tenantId, botId, text);
      }
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
          turn.kind === "smalltalk"
            ? null
            : turn.kind === "invalid_output"
              ? "The model replied, but the reply was unusable, so the visitor got the standard can't-confirm message. See the answer trace for the reason."
              : `Assistant state: ${turn.kind}`,
        );
      }
    } catch (caught) {
      // Stop: the server persists nothing for a cancelled stream; the draft stays.
      if (!controller.signal.aborted) {
        const message =
          caught instanceof Error ? caught.message : "Send failed.";
        if (/MODEL_NOT_CONFIGURED|No chat model/.test(message))
          setNotReady(true);
        setSendError(message);
      }
    } finally {
      abortRef.current = null;
      setPending(null);
      setSending(false);
    }
  }

  async function onNewSession() {
    if (sending) return;
    setSendError(null);
    try {
      const thread = await api.playgroundNewSession(tenantId, botId);
      setMessages(thread.messages);
      setFeedbackGiven({});
      setDraft("");
    } catch (caught) {
      setSendError(
        caught instanceof Error ? caught.message : "Could not start a session.",
      );
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
          threadError ? null : (
            <Loading label="Loading the conversation…" />
          )
        ) : messages.length === 0 && !pending ? (
          <p className="muted">
            No messages yet — ask something about the published knowledge.
          </p>
        ) : (
          <ul
            className="chat-list"
            role="log"
            aria-live="polite"
            aria-relevant="additions"
          >
            {messages.map((message) =>
              message.sender_type === "visitor" ? (
                <li key={message.id} data-role="visitor">
                  <div dir="auto" className="message-text">
                    {message.text}
                  </div>
                </li>
              ) : (
                <li key={message.id} data-role={message.sender_type}>
                  <div dir="auto" className="message-text">
                    {message.text}
                  </div>
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
                  {message.needs_human &&
                    (() => {
                      const failure = traces.find(
                        (item) => item.message_id === message.id,
                      )?.trace.provider_error;
                      return failure ? (
                        <Notice
                          message={providerFailureNotice(failure)}
                          tone="error"
                          scope="item"
                        />
                      ) : (
                        <Notice message="The assistant could not answer this from the knowledge." />
                      );
                    })()}
                  <div className="message-meta">
                    {message.response_ms !== null && (
                      <span className="muted">{message.response_ms} ms</span>
                    )}
                    {canChat && message.sender_type === "ai" && (
                      <span
                        className="feedback-buttons"
                        role="group"
                        aria-label="Rate this answer"
                      >
                        <button
                          type="button"
                          className="icon-button"
                          aria-label="Thumbs up"
                          aria-pressed={feedbackGiven[message.id] === "up"}
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
                          aria-pressed={feedbackGiven[message.id] === "down"}
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
            {pending && (
              <>
                <li data-role="visitor" data-pending="true">
                  <div dir="auto" className="message-text">
                    {pending.question}
                  </div>
                </li>
                <li data-role="ai" data-pending="true">
                  <div
                    dir="auto"
                    className="message-text"
                    data-testid="pending-answer"
                  >
                    {pending.answer || "…"}
                  </div>
                </li>
              </>
            )}
          </ul>
        )}
        <p className="sr-only" role="status">
          {sending ? "The assistant is answering…" : ""}
        </p>
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
              ref={inputRef}
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
        {canChat && sending && (
          <Button
            variant="quiet"
            data-testid="playground-stop"
            onClick={() => abortRef.current?.abort()}
          >
            Stop
          </Button>
        )}
        {canChat && (
          <Button
            variant="quiet"
            data-testid="playground-new-session"
            disabled={sending}
            onClick={() => void onNewSession()}
          >
            New session
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
        {traces.length === 0 && !traceError && (
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
              trace.stream_invalid_reason ||
              trace.prompt_version) && (
              <dl className="trace-facts">
                {trace.prompt_version && (
                  <>
                    <dt>Prompt</dt>
                    <dd>
                      {trace.prompt_version} · history{" "}
                      {trace.history_count ?? 0} exchange(s)
                      {trace.history_skipped_count
                        ? `, ${trace.history_skipped_count} skipped`
                        : ""}
                    </dd>
                    <dt>Model reply</dt>
                    <dd>
                      {trace.parsed_ok ? "parsed" : "not parsed"}
                      {trace.invalid_output_reason
                        ? ` (unusable: ${trace.invalid_output_reason})`
                        : ""}{" "}
                      · can answer {String(trace.model_can_answer ?? "n/a")} ·{" "}
                      {trace.model_source_count ?? 0} source(s) cited,{" "}
                      {trace.kept_source_count ?? 0} kept
                      {trace.reconciled ? " · replaced by canned refusal" : ""}
                    </dd>
                  </>
                )}
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
            {(trace.revision_id !== undefined || trace.retrieval_query) && (
              <dl className="trace-facts" data-testid="trace-context">
                <dt>Knowledge revision</dt>
                <dd>{trace.revision_id ?? "None published"}</dd>
                <dt>Tier / provider</dt>
                <dd>
                  {trace.tier ?? "n/a"} · {trace.generation_provider ?? "n/a"}
                </dd>
                {trace.applied_language && (
                  <>
                    <dt>Search language</dt>
                    <dd>{trace.applied_language}</dd>
                  </>
                )}
                {trace.retrieval_query && (
                  <>
                    <dt>Search query</dt>
                    <dd dir="auto">{trace.retrieval_query}</dd>
                  </>
                )}
                {trace.fallback_query && (
                  <>
                    <dt>Translated query</dt>
                    <dd dir="auto">{trace.fallback_query}</dd>
                  </>
                )}
                {trace.rewrite_text && (
                  <>
                    <dt>Rewrite</dt>
                    <dd dir="auto">{trace.rewrite_text}</dd>
                  </>
                )}
                {trace.skipped_steps && trace.skipped_steps.length > 0 && (
                  <>
                    <dt>Skipped (time budget)</dt>
                    <dd>{trace.skipped_steps.join(", ")}</dd>
                  </>
                )}
                {trace.handoff_reason && (
                  <>
                    <dt>Handoff</dt>
                    <dd>{trace.handoff_reason}</dd>
                  </>
                )}
              </dl>
            )}
            {trace.refusal_diagnosis && (
              <p data-testid="trace-diagnosis">
                {trace.refusal_diagnosis.nearest
                  ? `Refused: nearest candidate failed ${
                      trace.refusal_diagnosis.failed_rules.join(", ") ||
                      "no rule"
                    } (cosine ${
                      trace.refusal_diagnosis.nearest.cosine?.toFixed(3) ??
                      "n/a"
                    } vs floor ${
                      trace.refusal_diagnosis.nearest.cosine_floor?.toFixed(
                        2,
                      ) ?? "n/a"
                    }; terms ${trace.refusal_diagnosis.nearest.matched_terms}/${
                      trace.refusal_diagnosis.nearest.required_terms ?? "?"
                    }; fts ${trace.refusal_diagnosis.nearest.fts_match.toFixed(3)} vs ${
                      trace.refusal_diagnosis.nearest.fts_minimum ?? "?"
                    }).`
                  : "Refused: retrieval returned no candidates."}
              </p>
            )}
            {trace.rejected_candidates &&
              trace.rejected_candidates.length > 0 && (
                <div data-testid="trace-rejected">
                  <p>
                    No evidence reached the model. Closest rejected candidates:
                  </p>
                  <ul className="trace-chunks">
                    {trace.rejected_candidates.map((candidate) => (
                      <li key={candidate.chunk_id}>
                        {candidate.document_title}
                        {candidate.locator ? ` (${candidate.locator})` : ""} ·
                        cosine{" "}
                        {candidate.vector_similarity?.toFixed(3) ?? "n/a"} · fts{" "}
                        {candidate.fts_match.toFixed(3)} · rrf{" "}
                        {candidate.rrf_score.toFixed(4)} — {candidate.reason}
                      </li>
                    ))}
                  </ul>
                </div>
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
