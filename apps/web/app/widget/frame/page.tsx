"use client";

/**
 * Widget frame (docs/09) — the sandboxed iframe chat UI served by the web app.
 *
 * Public API only (docs/05): config by locator, capability-token sessions, the
 * grounded message pipeline (docs/14 §6 states: ready/typing/citations,
 * paused, not-ready, quota, network error/reconnect). The dashboard code is
 * not shared on purpose: this page must stay free of dashboard assets and
 * carries its own scoped CSP (next.config `source: "/widget/:path*"`).
 */

import { useCallback, useEffect, useRef, useState } from "react";

type CitedSource = {
  chunk_id: string;
  title: string | null;
  source_url: string | null;
  page_ref: string | null;
};

type WidgetConfig = {
  bot_name: string;
  assistant_name: string;
  welcome_message: { en: string; ar: string };
  opening_questions: string[];
  colour: string;
  position: "left" | "right";
  default_language: "en" | "ar";
  dir: "ltr" | "rtl";
};

type LeadFormState = {
  open: boolean;
  name: string;
  email: string;
  phone: string;
  consent: boolean;
  status: "idle" | "saving" | "done" | "error";
  error: string | null;
};

interface Turn {
  id: string;
  role: "visitor" | "assistant";
  text: string;
  citations?: CitedSource[];
  needsHuman?: boolean;
  feedback?: "up" | "down";
}

function localized(key: string, lang: string): string {
  const texts: Record<string, { en: string; ar: string }> = {
    placeholder: { en: "Type your message…", ar: "اكتب رسالتك…" },
    send: { en: "Send", ar: "إرسال" },
    retry: { en: "Try again", ar: "حاول مجدداً" },
    unavailable: {
      en: "The assistant is not available right now. Please try again later.",
      ar: "المساعد غير متاح حالياً. يرجى المحاولة لاحقاً.",
    },
    paused: {
      en: "The assistant is paused at the moment.",
      ar: "المساعد متوقف في الوقت الحالي.",
    },
    notReady: {
      en: "The assistant is not set up yet. Please check back soon.",
      ar: "المساعد غير مهيأ بعد. عد قريباً.",
    },
    leadTitle: {
      en: "Leave your details",
      ar: "اترك بياناتك",
    },
    leadName: { en: "Name", ar: "الاسم" },
    leadEmail: { en: "Email", ar: "البريد الإلكتروني" },
    leadPhone: { en: "Phone", ar: "الهاتف" },
    leadConsentAr: {
      en: "",
      ar: "أوافق على أن تحفظ هذه الشركة اسمي وبيانات التواصل لمتابعة هذه المحادثة.",
    },
    leadConsentEn: {
      en:
        "I agree that this business may store my name and contact details to " +
        "follow up on this chat.",
      ar: "",
    },
    leadSubmit: { en: "Send my details", ar: "أرسل بياناتي" },
    leadDone: {
      en: "Thanks — our team will get back to you.",
      ar: "شكراً — سيتواصل معك فريقنا.",
    },
    quota: {
      en: "The assistant is temporarily unavailable. Please try again later.",
      ar: "وصل المساعد إلى حد الرسائل لهذا اليوم. يرجى المحاولة غداً.",
    },
    rateLimited: {
      en: "You are sending messages too quickly — a short pause helps.",
      ar: "ترسل الرسائل بسرعة كبيرة — توقف قليلاً ثم حاول.",
    },
    network: {
      en: "No connection to the assistant. Check back in a moment.",
      ar: "لا يوجد اتصال بالمساعد. عد بعد قليل.",
    },
    sessionExpired: {
      en: "Starting a fresh session…",
      ar: "نبدأ جلسة جديدة…",
    },
    typing: { en: "The assistant is typing…", ar: "المساعد يكتب…" },
    cite: { en: "Sources", ar: "المصادر" },
    open: { en: "Open chat window", ar: "افتح نافذة المحادثة" },
    scroll: { en: "Scroll to bottom", ar: "الانتقال إلى الأسفل" },
    leadHelpful: { en: "Was this helpful?", ar: "هل كان هذا مفيداً؟" },
    leadConsentRequired: {
      en: "Please accept the consent text to save your details.",
      ar: "يرجى الموافقة على نص الموافقة لحفظ بياناتك.",
    },
    leadIncomplete: {
      en: "Enter your name and an email address or phone number.",
      ar: "اكتب الاسم وبريداً إلكترونياً أو رقماً هاتفياً.",
    },
  };
  const entry = texts[key];
  if (!entry) return key;
  return lang === "ar" ? entry.ar : entry.en;
}

function localTurnId(): string {
  return `local-${Date.now()}-${Math.floor(Math.random() * 1_000_000)}`;
}

function safeSourceUrl(sourceUrl: string | null): string | null {
  if (!sourceUrl) return null;
  try {
    const parsed = new URL(sourceUrl);
    return parsed.protocol === "http:" || parsed.protocol === "https:"
      ? parsed.href
      : null;
  } catch {
    return null;
  }
}

function restoreSession(locator: string): { id: string; token: string } | null {
  try {
    const raw = window.localStorage.getItem(`chatbot-session-${locator}`);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as {
      id: string;
      token: string;
      expires: number;
    };
    if (parsed.token && parsed.expires > Date.now()) {
      return { id: parsed.id, token: parsed.token };
    }
    window.localStorage.removeItem(`chatbot-session-${locator}`);
  } catch {
    // Broken storage — treat as missing.
  }
  return null;
}

function dropStoredSession(locator: string | null) {
  if (!locator) return;
  try {
    window.localStorage.removeItem(`chatbot-session-${locator}`);
  } catch {
    // Ignore storage failures.
  }
}

function storeSession(
  locator: string,
  session: { id: string; token: string; expires: string },
) {
  try {
    window.localStorage.setItem(
      `chatbot-session-${locator}`,
      JSON.stringify({ ...session, expires: Date.parse(session.expires) }),
    );
  } catch {
    // Ignore storage failures (private mode).
  }
}

async function ensureSessionFor(
  locator: string,
): Promise<{ id: string; token: string } | null> {
  const response = await fetch(`/api/public/v1/widgets/${locator}/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ page_origin: null }),
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as {
      error?: { code?: string };
    } | null;
    throw new ApiCodeError(payload?.error?.code ?? "NETWORK");
  }
  const payload = (await response.json()) as {
    session_id: string;
    token: string;
    expires_at: string;
  };
  storeSession(locator, {
    id: payload.session_id,
    token: payload.token,
    expires: payload.expires_at,
  });
  return { id: payload.session_id, token: payload.token };
}

const CONSENT_TEXT_EN =
  "I agree that this business may store my name and contact details to " +
  "follow up on this chat.";
const CONSENT_TEXT_AR =
  "أوافق على أن تحفظ هذه الشركة اسمي وبيانات التواصل لمتابعة هذه المحادثة.";

class ApiCodeError extends Error {
  code: string;
  constructor(code: string) {
    super(code);
    this.code = code;
  }
}

export default function WidgetFramePage() {
  const [status, setStatus] = useState<"loading" | "ready" | "error">(
    "loading",
  );
  const [reason, setReason] = useState<string | null>(null);
  const [config, setConfig] = useState<WidgetConfig | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const [lead, setLead] = useState<LeadFormState>({
    open: false,
    name: "",
    email: "",
    phone: "",
    consent: false,
    status: "idle",
    error: null,
  });
  const [typing, setTyping] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const locatorRef = useRef<string | null>(null);
  const sessionRef = useRef<{ id: string; token: string } | null>(null);
  const lastPollAtRef = useRef<string | null>(null);
  const pollingRef = useRef(false);
  const lang = config?.default_language ?? "en";
  const dir = config?.dir ?? "ltr";
  const bottomRef = useRef<HTMLDivElement | null>(null);

  function greet(configLocal: WidgetConfig | null) {
    if (!configLocal) return;
    const text =
      lang === "ar"
        ? configLocal.welcome_message.ar || configLocal.welcome_message.en
        : configLocal.welcome_message.en || configLocal.welcome_message.ar;
    if (text) {
      setTurns([{ id: "welcome", role: "assistant", text }]);
    }
  }

  async function resumeHistory(
    session: { id: string; token: string },
    configLocal: WidgetConfig | null,
  ) {
    const response = await fetch(
      `/api/public/v1/sessions/${session.id}/messages`,
      {
        headers: { "X-Session-Token": session.token },
      },
    );
    if (!response.ok) {
      // Expired/invalid: start fresh silently (docs/09 graceful recovery).
      dropStoredSession(locatorRef.current);
      sessionRef.current = null;
      greet(configLocal);
      return;
    }
    const rows = (await response.json()) as Array<{
      id: string;
      sender_type: string;
      text: string;
      citations: CitedSource[] | null;
      can_answer: boolean | null;
      needs_human: boolean;
      created_at: string;
    }>;
    lastPollAtRef.current = rows.at(-1)?.created_at ?? null;
    const restored: Turn[] = rows.map((row) => ({
      id: row.id,
      role: row.sender_type === "visitor" ? "visitor" : "assistant",
      text: row.text,
      citations: row.citations ?? undefined,
      needsHuman: row.needs_human,
    }));
    if (restored.length === 0) {
      greet(configLocal);
    } else {
      setTurns(restored);
    }
  }

  async function pollSession() {
    const session = sessionRef.current;
    if (!session || pollingRef.current) return;
    pollingRef.current = true;
    try {
      const since = lastPollAtRef.current
        ? new Date(Date.parse(lastPollAtRef.current) - 1).toISOString()
        : null;
      const query = since ? `?since=${encodeURIComponent(since)}` : "";
      const response = await fetch(
        `/api/public/v1/sessions/${session.id}/messages${query}`,
        { headers: { "X-Session-Token": session.token } },
      );
      if (!response.ok) return;
      const rows = (await response.json()) as Array<{
        id: string;
        sender_type: string;
        text: string;
        citations: CitedSource[] | null;
        needs_human: boolean;
        created_at: string;
      }>;
      if (rows.length === 0) return;
      lastPollAtRef.current = rows.at(-1)?.created_at ?? lastPollAtRef.current;
      setTurns((current) => {
        const known = new Set(current.map((turn) => turn.id));
        return [
          ...current,
          ...rows
            .filter((row) => !known.has(row.id))
            .map((row) => ({
              id: row.id,
              role:
                row.sender_type === "visitor"
                  ? ("visitor" as const)
                  : ("assistant" as const),
              text: row.text,
              // Agent messages are plain text; citations are only returned for AI rows.
              citations:
                row.sender_type === "ai"
                  ? (row.citations ?? undefined)
                  : undefined,
              needsHuman: row.needs_human,
            })),
        ];
      });
    } catch {
      // Polling is best effort; the next interval retries without changing the thread.
    } finally {
      pollingRef.current = false;
    }
  }

  useEffect(() => {
    if (status !== "ready" || !config) return;
    const timer = window.setInterval(() => void pollSession(), 2000);
    return () => window.clearInterval(timer);
    // Session refs change without a render; the interval reads the latest ref.
  }, [status, config]);

  function setTypedError(code: string) {
    if (code === "BOT_PAUSED") setReason("paused");
    else if (code === "BOT_NOT_READY") setReason("notReady");
    else if (code === "QUOTA_EXCEEDED") setReason("quota");
    else if (code === "RATE_LIMITED") setReason("rateLimited");
    else if (code === "SESSION_EXPIRED" || code === "SESSION_INVALID") {
      dropStoredSession(locatorRef.current);
      sessionRef.current = null;
    } else setReason("network");
  }

  async function bootstrap(locator: string) {
    setStatus("loading");
    setError(null);
    try {
      const response = await fetch(`/api/public/v1/widgets/${locator}/config`);
      if (!response.ok) {
        setStatus("error");
        setReason(response.status === 404 ? "notfound" : "network");
        return;
      }
      const payload = (await response.json()) as {
        available: boolean;
        reason: string | null;
        config: WidgetConfig;
      };
      const cfg = payload.config;
      setConfig(cfg);
      window.parent.postMessage(
        {
          type: "chatbot:brand",
          colour: cfg.colour,
          position: cfg.position,
          dir: cfg.dir,
        },
        window.location.origin,
      );
      if (!payload.available) {
        setReason(payload.reason ?? "unavailable");
        setStatus("ready"); // controlled message instead of an error
      } else {
        setStatus("ready");
        const stored = restoreSession(locator);
        sessionRef.current = stored;
        if (stored) {
          await resumeHistory(stored, cfg);
        } else {
          greet(cfg);
        }
      }
    } catch {
      setStatus("error");
      setReason("network");
    }
  }

  // Parent handshake: the loader script is the single source of the locator.
  useEffect(() => {
    function onMessage(event: MessageEvent) {
      if (event.origin !== window.location.origin) return;
      const data = (event.data ?? {}) as { type?: string; locator?: string };
      if (data.type === "chatbot:locator" && data.locator) {
        locatorRef.current = data.locator;
        void bootstrap(data.locator);
      }
    }
    window.addEventListener("message", onMessage);
    // Fallback for the sample page / direct loads: locator in the query.
    const url = new URL(window.location.href);
    const directLocator = url.searchParams.get("locator");
    if (directLocator && !locatorRef.current) {
      locatorRef.current = directLocator;
      void bootstrap(directLocator);
    }
    return () => window.removeEventListener("message", onMessage);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const announceSize = useCallback(() => {
    const height = document.documentElement.scrollHeight;
    window.parent.postMessage(
      { type: "chatbot:size", height },
      window.location.origin,
    );
  }, []);

  useEffect(() => {
    announceSize();
  }, [turns, status, typing, error, announceSize]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [turns, typing]);

  async function onSend(event: React.FormEvent, presetText?: string) {
    event.preventDefault();
    const locator = locatorRef.current;
    const text = (presetText ?? draft).trim();
    if (!text || typing) return;
    if (!locator) return;
    setDraft("");
    setError(null);
    const localTurn: Turn = {
      id: localTurnId(),
      role: "visitor",
      text,
    };
    setTurns((current) => [...current, localTurn]);
    setTyping(true);
    try {
      if (sessionRef.current === null) {
        sessionRef.current = await ensureSessionFor(locator);
      }
      if (!sessionRef.current) {
        setTyping(false);
        return;
      }
      const response = await fetch(
        `/api/public/v1/sessions/${sessionRef.current.id}/messages`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Session-Token": sessionRef.current.token,
          },
          body: JSON.stringify({ text, language: lang }),
        },
      );
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as {
          error?: { code?: string };
        } | null;
        setTypedError(payload?.error?.code ?? "NETWORK");
        setTyping(false);
        return;
      }
      const payload = (await response.json()) as {
        visitor_message: { id: string; created_at: string };
        ai_message: {
          id: string;
          text: string;
          citations: CitedSource[];
          needs_human: boolean;
          created_at: string;
        } | null;
      };
      lastPollAtRef.current =
        payload.ai_message?.created_at ?? payload.visitor_message.created_at;
      setTurns((current) => {
        const withVisitorId = current.map((turn) =>
          turn.id === localTurn.id
            ? { ...turn, id: payload.visitor_message.id }
            : turn,
        );
        if (
          !payload.ai_message ||
          withVisitorId.some((turn) => turn.id === payload.ai_message?.id)
        ) {
          return withVisitorId;
        }
        return [
          ...withVisitorId,
          {
            id: payload.ai_message.id,
            role: "assistant",
            text: payload.ai_message.text,
            citations: payload.ai_message.citations,
            needsHuman: payload.ai_message.needs_human,
          },
        ];
      });
      setReason(null);
    } catch (caught) {
      if (caught instanceof ApiCodeError) {
        setTypedError(caught.code);
      } else {
        setReason("network");
      }
    } finally {
      setTyping(false);
    }
  }

  async function giveFeedback(turn: Turn, rating: "up" | "down") {
    if (
      turn.role !== "assistant" ||
      turn.id.startsWith("local-") ||
      turn.id === "welcome"
    )
      return;
    setTurns((current) =>
      current.map((item) =>
        item.id === turn.id ? { ...item, feedback: rating } : item,
      ),
    );
    const session = sessionRef.current;
    if (!session) return;
    try {
      await fetch(
        `/api/public/v1/sessions/${session.id}/messages/${turn.id}/feedback`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Session-Token": session.token,
          },
          body: JSON.stringify({ rating }),
        },
      );
    } catch {
      // Feedback is best-effort; the answer stays on screen.
    }
  }

  async function submitLead() {
    if (!lead.consent) {
      setLead((state) => ({
        ...state,
        status: "error",
        error: localized("leadConsentRequired", lang),
      }));
      return;
    }
    if (!lead.name.trim() || (!lead.email.trim() && !lead.phone.trim())) {
      setLead((state) => ({
        ...state,
        status: "error",
        error: localized("leadIncomplete", lang),
      }));
      return;
    }
    const session = sessionRef.current;
    if (!session) {
      const locator = locatorRef.current;
      if (!locator) return;
      setLead((state) => ({ ...state, status: "saving" }));
      sessionRef.current = await ensureSessionFor(locator);
    }
    const bound = sessionRef.current;
    if (!bound) {
      setLead((state) => ({ ...state, status: "error", error: null }));
      return;
    }
    setLead((state) => ({ ...state, status: "saving", error: null }));
    try {
      const response = await fetch(`/api/public/v1/sessions/${bound.id}/lead`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Session-Token": bound.token,
        },
        body: JSON.stringify({
          name: lead.name.trim(),
          email: lead.email.trim() || null,
          phone: lead.phone.trim() || null,
          consent_accepted: true,
          consent_language: lang,
        }),
      });
      if (response.ok) {
        setLead((state) => ({
          ...state,
          status: "done",
          open: false,
          error: null,
        }));
      } else {
        const payloadResponse = (await response.json().catch(() => null)) as {
          error?: { code?: string };
        } | null;
        setLead((state) => ({
          ...state,
          status: "error",
          error:
            payloadResponse?.error?.code === "CONSENT_REQUIRED"
              ? localized("leadConsentRequired", lang)
              : localized("network", lang),
        }));
      }
    } catch {
      setLead((state) => ({
        ...state,
        status: "error",
        error: localized("network", lang),
      }));
    }
  }

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        window.parent.postMessage(
          { type: "chatbot:close" },
          window.location.origin,
        );
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  const blocked =
    reason === "paused" || reason === "notReady" || reason === "unavailable";

  return (
    <div dir={dir} className="widget-frame" data-testid="widget-frame-body">
      <style>{widgetStyles}</style>
      <header
        className="widget-header"
        style={{ background: config?.colour ?? "#1f7a5c" }}
      >
        <span className="widget-title" data-testid="widget-title">
          {status === "loading" ? "" : (config?.bot_name ?? "")}
        </span>
      </header>

      <main className="widget-thread" aria-live="polite">
        {status === "loading" && (
          <p role="status" className="widget-note">
            {reason === "network" ? localized("network", lang) : "…"}
          </p>
        )}

        {status === "error" && (
          <p role="alert" className="widget-note error">
            {localized("network", lang)}
          </p>
        )}
        {status === "ready" && blocked && (
          <p role="status" className="widget-note">
            {reason === "paused"
              ? localized("paused", lang)
              : reason === "notReady"
                ? localized("notReady", lang)
                : localized("unavailable", lang)}
          </p>
        )}

        {status === "ready" && !blocked && (
          <>
            {reason && reason !== "paused" && reason !== "notReady" && (
              <p
                role="alert"
                className="widget-note error"
                data-testid="widget-error"
              >
                {reason === "quota"
                  ? localized("quota", lang)
                  : reason === "rateLimited"
                    ? localized("rateLimited", lang)
                    : reason === "sessionExpired"
                      ? localized("sessionExpired", lang)
                      : localized("network", lang)}
                {reason === "network" && (
                  <button
                    type="button"
                    onClick={() => void bootstrap(locatorRef.current ?? "")}
                  >
                    {localized("retry", lang)}
                  </button>
                )}
              </p>
            )}
            <ul className="widget-turns">
              {turns.map((turn) => (
                <li
                  key={turn.id}
                  className={
                    turn.role === "visitor"
                      ? "widget-bubble visitor"
                      : "widget-bubble"
                  }
                  data-testid={
                    turn.role === "visitor"
                      ? "widget-visitor-msg"
                      : "widget-ai-msg"
                  }
                >
                  <div dir="auto">{turn.text}</div>
                  {turn.citations && turn.citations.length > 0 && (
                    <ul
                      className="widget-citations"
                      aria-label={localized("cite", lang)}
                    >
                      {turn.citations.map((citation) => {
                        const sourceUrl = safeSourceUrl(citation.source_url);
                        return (
                          <li
                            key={citation.chunk_id}
                            className="widget-source-chip"
                          >
                            {sourceUrl ? (
                              <a
                                href={sourceUrl}
                                rel="noreferrer noopener"
                                target="_blank"
                              >
                                {citation.title ?? localized("cite", lang)}
                              </a>
                            ) : (
                              <span>{citation.title ?? ""}</span>
                            )}
                          </li>
                        );
                      })}
                    </ul>
                  )}
                  {turn.role === "assistant" &&
                    turn.id !== "welcome" &&
                    !turn.feedback && (
                      <span
                        className="widget-feedback"
                        aria-label={localized("helpful", lang)}
                      >
                        <button
                          type="button"
                          aria-label="Thumbs up"
                          data-testid={`widget-thumbs-up-${turn.id}`}
                          onClick={() => void giveFeedback(turn, "up")}
                        >
                          👍
                        </button>
                        <button
                          type="button"
                          aria-label="Thumbs down"
                          data-testid={`widget-thumbs-down-${turn.id}`}
                          onClick={() => void giveFeedback(turn, "down")}
                        >
                          👎
                        </button>
                      </span>
                    )}
                  {turn.feedback && (
                    <span className="widget-feedback-done muted">
                      {localized("helpful", lang)} ✓
                    </span>
                  )}
                </li>
              ))}
            </ul>
            {typing && (
              <p
                role="status"
                className="widget-note typing"
                data-testid="widget-typing"
              >
                {localized("typing", lang)}
              </p>
            )}
            {turns.length === 1 &&
              turns[0].id === "welcome" &&
              (config?.opening_questions?.length ?? 0) > 0 && (
                <div className="widget-chips" data-testid="widget-chips">
                  {config?.opening_questions.slice(0, 6).map((question) => (
                    <button
                      key={question}
                      type="button"
                      className="widget-chip"
                      onClick={(clickEvent) =>
                        void onSend(clickEvent, question)
                      }
                    >
                      {question}
                    </button>
                  ))}
                </div>
              )}
            <div ref={bottomRef} />
          </>
        )}
      </main>

      {status === "ready" && !blocked && lead.status === "done" && (
        <p role="status" className="widget-note" data-testid="widget-lead-done">
          {localized("leadDone", lang)}
        </p>
      )}
      {status === "ready" && !blocked && (
        <section
          className="widget-lead"
          aria-label={localized("leadTitle", lang)}
        >
          {!lead.open ? (
            <button
              type="button"
              className="widget-chip"
              data-testid="widget-lead-open"
              onClick={() => setLead((state) => ({ ...state, open: true }))}
            >
              {localized("leadTitle", lang)}
            </button>
          ) : (
            <form
              className="widget-lead-form"
              data-testid="widget-lead-form"
              onSubmit={(leadEvent) => {
                leadEvent.preventDefault();
                void submitLead();
              }}
            >
              <h2 dir="auto" className="widget-lead-title">
                {localized("leadTitle", lang)}
              </h2>
              <label dir="auto">
                <span>{localized("leadName", lang)}</span>
                <input
                  dir="auto"
                  data-testid="widget-lead-name"
                  maxLength={200}
                  value={lead.name}
                  onChange={(leadEvent) =>
                    setLead((state) => ({
                      ...state,
                      name: leadEvent.target.value,
                    }))
                  }
                />
              </label>
              <label dir="auto">
                <span>{localized("leadEmail", lang)}</span>
                <input
                  dir="auto"
                  type="email"
                  data-testid="widget-lead-email"
                  maxLength={320}
                  value={lead.email}
                  onChange={(leadEvent) =>
                    setLead((state) => ({
                      ...state,
                      email: leadEvent.target.value,
                    }))
                  }
                />
              </label>
              <label dir="auto">
                <span>{localized("leadPhone", lang)}</span>
                <input
                  dir="auto"
                  data-testid="widget-lead-phone"
                  maxLength={40}
                  value={lead.phone}
                  onChange={(leadEvent) =>
                    setLead((state) => ({
                      ...state,
                      phone: leadEvent.target.value,
                    }))
                  }
                />
              </label>
              <label dir={dir} className="widget-lead-consent">
                <input
                  type="checkbox"
                  data-testid="widget-lead-consent"
                  checked={lead.consent}
                  onChange={(leadEvent) =>
                    setLead((state) => ({
                      ...state,
                      consent: leadEvent.target.checked,
                    }))
                  }
                />
                <span dir="auto">
                  {lang === "ar" ? CONSENT_TEXT_AR : CONSENT_TEXT_EN}
                </span>
              </label>
              {lead.error && (
                <p
                  role="alert"
                  className="widget-note error"
                  data-testid="widget-lead-error"
                >
                  {lead.error}
                </p>
              )}
              <div className="widget-lead-actions">
                <button
                  type="submit"
                  data-testid="widget-lead-submit"
                  disabled={lead.status === "saving"}
                >
                  {lead.status === "saving"
                    ? "…"
                    : localized("leadSubmit", lang)}
                </button>
                <button
                  type="button"
                  onClick={() =>
                    setLead((state) => ({ ...state, open: false, error: null }))
                  }
                >
                  ✕
                </button>
              </div>
            </form>
          )}
        </section>
      )}
      {status === "ready" && !blocked && (
        <form
          className="widget-composer"
          onSubmit={(formEvent) => void onSend(formEvent)}
        >
          <label className="widget-composer-label" htmlFor="widget-input">
            {localized("placeholder", lang)}
          </label>
          <input
            id="widget-input"
            dir="auto"
            value={draft}
            maxLength={1000}
            disabled={typing}
            placeholder={localized("placeholder", lang)}
            data-testid="widget-input"
            onChange={(inputEvent) => setDraft(inputEvent.target.value)}
          />
          <button
            type="submit"
            disabled={typing || !draft.trim()}
            data-testid="widget-send"
          >
            {typing ? "…" : localized("send", lang)}
          </button>
        </form>
      )}
      <p className="sr-only">{localized("scroll", lang)}</p>
    </div>
  );
}

const widgetStyles = `
html,body{height:100%}
.widget-frame{position:absolute;inset:0;display:flex;flex-direction:column;height:100%;background:#ffffff;color:#182332;font-family:system-ui,-apple-system,Segoe UI,sans-serif;font-size:15px}
.widget-header{padding:0.85rem 1rem;color:#fff;font-weight:600}
.widget-title{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.widget-thread{flex:1;overflow-y:auto;padding:0.75rem 0.9rem;display:flex;flex-direction:column;gap:0.55rem;min-height:0}
.widget-turns{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:0.55rem}
.widget-bubble{background:#f1f5f9;border-radius:0.8rem;padding:0.55rem 0.8rem;max-width:85%;align-self:flex-start;overflow-wrap:anywhere}
.widget-bubble.visitor{background:#1f7a5c;color:#fff;align-self:flex-end}
.widget-citations{list-style:none;margin:0.4rem 0 0;padding:0;display:flex;flex-wrap:wrap;gap:0.3rem}
.widget-source-chip{background:#ffffff;border:1px solid #cdd8e4;border-radius:999px;padding:0.1rem 0.6rem;font-size:0.75rem}
.widget-source-chip a{color:#1d4ed8;text-decoration:none}
.widget-feedback{display:inline-flex;gap:0.4rem;margin-top:0.3rem}
.widget-feedback button{background:transparent;border:0;cursor:pointer;font-size:0.95rem;padding:0.1rem}
.widget-feedback-done{font-size:0.75rem;margin-top:0.25rem}
.widget-note{padding:0.5rem 0.2rem;color:#5a6b85;font-size:0.9rem}
.widget-note.error{color:#b42318}
.widget-note.typing{font-style:italic}
.widget-chips{display:flex;flex-wrap:wrap;gap:0.4rem;margin-top:0.5rem}
.widget-chip{background:#fff;border:1px solid #cdd8e4;border-radius:999px;padding:0.35rem 0.8rem;font-size:0.85rem;cursor:pointer}
.widget-composer{display:flex;gap:0.5rem;padding:0.6rem 0.75rem;border-top:1px solid #e4e9f2;position:sticky;bottom:0;background:#fff}
.widget-composer .widget-composer-label{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}
.widget-composer input{flex:1;border:1px solid #b8c4d8;border-radius:0.5rem;padding:0.55rem 0.7rem;font:inherit;min-width:0}
.widget-composer button{background:#1f7a5c;color:#fff;border:0;border-radius:0.5rem;padding:0.55rem 0.9rem;cursor:pointer}
.widget-composer button:disabled{opacity:0.6;cursor:progress}
.widget-lead{padding:0.5rem 0.8rem;border-top:1px solid #e4e9f2;display:flex;gap:0.4rem;flex-wrap:wrap;align-items:center}
.widget-lead-form{display:flex;flex-direction:column;gap:0.45rem;width:100%}
.widget-lead-form label{display:flex;flex-direction:column;gap:0.2rem;font-size:0.85rem;color:#344b75}
.widget-lead-title{font-size:0.95rem;margin:0.1rem 0}
.widget-lead-consent{flex-direction:row!important;align-items:flex-start;gap:0.4rem}
.widget-lead-actions{display:flex;gap:0.5rem}
.widget-lead-actions button:last-child{background:transparent;border:1px solid #b8c4d8;color:#182332}
.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}
`;
