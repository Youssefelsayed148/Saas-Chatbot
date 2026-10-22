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

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type CSSProperties,
} from "react";

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

function embedPageHost(): string | null {
  // The parent loader appends the EMBEDDING page's location.hostname to the
  // frame URL (docs/09 §host). It is a spoofable defence signal (docs/06),
  // not authentication; the frame CSP is the browser-enforced guard.
  const host = new URL(window.location.href).searchParams.get("host");
  const trimmed = host?.trim() ?? "";
  return trimmed.length > 0 ? trimmed : null;
}

function widgetDebugEnabled(): boolean {
  if (new URLSearchParams(window.location.search).get("debugWidget") === "1") {
    return true;
  }
  try {
    return (
      new URLSearchParams(window.parent.location.search).get("debugWidget") ===
      "1"
    );
  } catch {
    return false;
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
    body: JSON.stringify({ page_origin: embedPageHost() }),
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as {
      error?: { code?: string; message?: string };
    } | null;
    throw new ApiCodeError(
      payload?.error?.code ?? "NETWORK",
      payload?.error?.message,
    );
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
  constructor(code: string, message?: string) {
    super(message ?? code);
    this.code = code;
  }
}

function brandInk(colour?: string) {
  if (!colour || !/^#[0-9a-f]{6}$/i.test(colour)) return "var(--ink-light)";
  const rgb = [1, 3, 5]
    .map((i) => parseInt(colour.slice(i, i + 2), 16) / 255)
    .map((v) => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2] > 0.179
    ? "var(--ink-dark)"
    : "var(--ink-light)";
}
export default function WidgetFramePage() {
  const [status, setStatus] = useState<"loading" | "ready" | "error">(
    "loading",
  );
  const [serverMessage, setServerMessage] = useState<string | null>(null);
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
      if (!response.ok) {
        if (widgetDebugEnabled()) {
          console.debug("[widget-debug] poll response", response.status);
        }
        return;
      }
      const rows = (await response.json()) as Array<{
        id: string;
        sender_type: string;
        text: string;
        citations: CitedSource[] | null;
        needs_human: boolean;
        created_at: string;
      }>;
      if (widgetDebugEnabled()) {
        console.debug(
          "[widget-debug] poll rows",
          rows.length,
          rows.map((row) => row.sender_type),
        );
      }
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
      if (widgetDebugEnabled()) {
        console.debug("[widget-debug] poll failed");
      }
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

  function setTypedError(code: string, message?: string) {
    setServerMessage(message ?? null);
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
    setServerMessage(null);
    try {
      const response = await fetch(`/api/public/v1/widgets/${locator}/config`);
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as {
          error?: { message?: string };
        } | null;
        setServerMessage(payload?.error?.message ?? null);
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
          error?: { code?: string; message?: string };
        } | null;
        setTypedError(
          payload?.error?.code ?? "NETWORK",
          payload?.error?.message,
        );
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
      setServerMessage(null);
    } catch (caught) {
      if (caught instanceof ApiCodeError) {
        setTypedError(
          caught.code,
          caught.message === caught.code ? undefined : caught.message,
        );
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
          error?: { code?: string; message?: string };
        } | null;
        setLead((state) => ({
          ...state,
          status: "error",
          error:
            payloadResponse?.error?.message ??
            (payloadResponse?.error?.code === "CONSENT_REQUIRED"
              ? localized("leadConsentRequired", lang)
              : localized("network", lang)),
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
        closeWidget();
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  const blocked =
    reason === "paused" || reason === "notReady" || reason === "unavailable";

  return (
    <div
      dir={dir}
      lang={lang}
      className="widget-frame"
      data-testid="widget-frame-body"
      style={
        {
          "--widget-brand": config?.colour,
          "--widget-ink": brandInk(config?.colour),
        } as CSSProperties
      }
    >
      <style>{widgetStyles}</style>
      <header className="widget-header">
        <span aria-hidden="true" className="widget-brand-mark">
          ✧
        </span>
        <span className="widget-title" data-testid="widget-title">
          {status === "loading" ? "" : (config?.bot_name ?? "")}
        </span>
        <span className="widget-header-caption">
          {lang === "ar" ? "مساعد الموقع" : "Website assistant"}
        </span>
        <button
          type="button"
          className="widget-close"
          data-testid="widget-close"
          aria-label={lang === "ar" ? "إغلاق المحادثة" : "Close chat"}
          onClick={closeWidget}
        >
          ×
        </button>
      </header>

      <main className="widget-thread" aria-live="polite">
        {status === "loading" && (
          <p role="status" className="widget-note">
            {reason === "network" ? localized("network", lang) : "…"}
          </p>
        )}

        {status === "error" && (
          <p role="alert" className="widget-note error">
            {serverMessage ?? localized("network", lang)}
          </p>
        )}
        {status === "ready" && blocked && (
          <p role="status" className="widget-note">
            {serverMessage ??
              (reason === "paused"
                ? localized("paused", lang)
                : reason === "notReady"
                  ? localized("notReady", lang)
                  : localized("unavailable", lang))}
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
                {serverMessage ??
                  (reason === "quota"
                    ? localized("quota", lang)
                    : reason === "rateLimited"
                      ? localized("rateLimited", lang)
                      : reason === "sessionExpired"
                        ? localized("sessionExpired", lang)
                        : localized("network", lang))}
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
                  {turn.role === "assistant" &&
                    turn.id !== "welcome" &&
                    !turn.feedback && (
                      <span
                        className="widget-feedback"
                        aria-label={localized("leadHelpful", lang)}
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
                  {turn.needsHuman && (
                    <p className="widget-handoff" role="note">
                      {lang === "ar"
                        ? "تم طلب مساعدة الفريق"
                        : "Team assistance requested"}
                    </p>
                  )}
                  {turn.feedback && (
                    <span className="widget-feedback-done muted">
                      {localized("leadHelpful", lang)} ✓
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
                <span className="typing-dots" aria-hidden="true">
                  <i />
                  <i />
                  <i />
                </span>
                <span className="sr-only">{localized("typing", lang)}</span>
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
                  aria-label={
                    lang === "ar" ? "إغلاق النموذج" : "Close details form"
                  }
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

function closeWidget() {
  window.parent.postMessage({ type: "chatbot:close" }, window.location.origin);
}

const widgetStyles = `
html,body{height:100%}
.widget-frame{position:absolute;inset:0;display:flex;flex-direction:column;height:100%;background:var(--surface);color:var(--text);font-family:var(--font);font-size:14px;overflow:hidden}
.widget-header{display:grid;grid-template-columns:32px 1fr 44px;column-gap:.6rem;align-items:center;padding:1rem 1.1rem;background:var(--widget-brand);color:var(--widget-ink,var(--ink-light));flex-shrink:0}
.widget-header-caption{grid-column:2;grid-row:2}.widget-close{grid-column:3;grid-row:1/3;background:transparent;color:inherit;border:1px solid currentColor;min-inline-size:44px;min-block-size:44px;padding:0;font-size:1.3rem}.widget-close:focus-visible{outline-color:currentColor}
.widget-brand-mark{grid-row:1/3;font-size:1.8rem;line-height:1}.widget-title{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-weight:650;font-size:.95rem}.widget-header-caption{font-size:.7rem;opacity:.9}
.widget-frame .widget-thread{flex:1;overflow-y:auto;padding:1.1rem;display:flex;flex-direction:column;gap:.8rem;min-height:0;inline-size:100%;max-inline-size:none;margin:0}
.widget-turns{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:.85rem}
.widget-bubble{background:var(--surface-raised);border:1px solid var(--border);border-radius:var(--radius) var(--radius) var(--radius) 4px;padding:.75rem .9rem;max-inline-size:88%;align-self:flex-start;overflow-wrap:anywhere;line-height:1.65}
.widget-bubble.visitor{background:var(--widget-brand);color:var(--widget-ink,var(--ink-light));align-self:flex-end;border-color:transparent;border-radius:var(--radius) var(--radius) 4px var(--radius)}
[dir=rtl] .widget-bubble{border-radius:var(--radius) var(--radius) 4px var(--radius)}[dir=rtl] .widget-bubble.visitor{border-radius:var(--radius) var(--radius) var(--radius) 4px}
.widget-citations{list-style:none;margin:.6rem 0 0;padding:0;display:flex;flex-wrap:wrap;gap:.3rem}.widget-source-chip{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-sm);padding:.2rem .5rem;font-size:.7rem}.widget-source-chip a{color:var(--accent);text-decoration:none}
.widget-feedback{display:flex;gap:.4rem;margin-block-start:.5rem}.widget-feedback button{background:transparent;color:var(--text);border:1px solid var(--border);border-radius:var(--radius-sm);cursor:pointer;font-size:.85rem;padding:.25rem .45rem;min-block-size:32px}.widget-feedback-done{display:block;font-size:.7rem;margin-block-start:.4rem}.widget-handoff{font-size:.75rem;color:var(--warning);border-block-start:1px solid var(--border);padding-block-start:.4rem;margin-block:.5rem 0}
.widget-note{padding:.5rem .2rem;color:var(--muted);font-size:.85rem;margin:0}.widget-note.error{color:var(--danger);background:var(--danger-soft);border:1px solid var(--border);border-radius:var(--radius-sm);padding:.7rem}.widget-note.error button{display:block;margin-block-start:.5rem;font-size:.75rem}
.widget-chips{display:flex;flex-wrap:wrap;gap:.5rem;margin-block-start:.5rem}.widget-chip{background:var(--surface);color:var(--accent);border:1px solid var(--border);border-radius:999px;padding:.5rem .8rem;font-size:.8rem;cursor:pointer;min-block-size:40px}
.widget-frame .widget-composer{display:flex;flex-direction:row;gap:.5rem;padding:.85rem 1rem;border-block-start:1px solid var(--border);background:var(--surface);margin:0;max-inline-size:none;flex-shrink:0;inline-size:100%}
.widget-composer-label{position:absolute;inline-size:1px;block-size:1px;overflow:hidden;clip-path:inset(50%)}.widget-composer input{flex:1;border:1px solid var(--border);border-radius:var(--radius-sm);padding:.65rem .8rem;font:inherit;min-inline-size:0;background:var(--bg);color:var(--text)}.widget-composer button{background:var(--widget-brand);color:var(--widget-ink,var(--ink-light));border:0;border-radius:var(--radius-sm);padding:.65rem .9rem;cursor:pointer;align-self:stretch}.widget-composer button:disabled{opacity:.6;cursor:progress}
.widget-lead{padding:.75rem 1rem;border-block-start:1px solid var(--border);display:flex;gap:.5rem;flex-wrap:wrap;align-items:center;max-block-size:55%;overflow-y:auto;flex-shrink:0;background:var(--surface)}.widget-lead>button{font-size:.8rem;background:var(--surface-raised);color:var(--accent);border:1px solid var(--border);inline-size:100%}
.widget-lead-form{display:flex;flex-direction:column;gap:.6rem;inline-size:100%;max-inline-size:none}.widget-lead-form label{display:flex;flex-direction:column;gap:.25rem;font-size:.8rem;color:var(--muted)}.widget-lead-form input{inline-size:100%;padding:.5rem .7rem}.widget-lead-title{font-size:.9rem;margin:.1rem 0}.widget-lead-form .widget-lead-consent{flex-direction:row;align-items:flex-start;gap:.5rem}.widget-lead-consent input{inline-size:20px;flex-shrink:0}.widget-lead-actions{display:flex;gap:.5rem}.widget-lead-actions button:last-child{background:transparent;border:1px solid var(--border);color:var(--text)}
.typing-dots{display:inline-flex;gap:4px;padding:.65rem .8rem;border:1px solid var(--border);border-radius:999px;background:var(--surface-raised)}.typing-dots i{inline-size:5px;block-size:5px;background:var(--muted);border-radius:50%;animation:widget-pulse .8s ease-in-out infinite alternate}.typing-dots i:nth-child(2){animation-delay:.15s}.typing-dots i:nth-child(3){animation-delay:.3s}@keyframes widget-pulse{to{opacity:.3;transform:translateY(-3px)}}
@media(prefers-reduced-motion:reduce){.typing-dots i{animation:none}}
`;
