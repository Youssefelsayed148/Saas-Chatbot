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

import { MessageBody } from "@/lib/message-body";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type CSSProperties,
} from "react";

import {
  brandInk,
  launcherColour,
  themeStyleVars,
  themeVariant,
  type WidgetTheme,
} from "@/lib/widget-theme";
import { widgetStyles } from "@/lib/widget-styles";
import {
  handoffFromTurn,
  nextPollDelay,
  parsePollHint,
  POLL_HINT_HEADER,
  shouldPoll,
  type PollHint,
} from "@/lib/widget-polling";

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
  /** Optional per-slot colours (#14); absent = today's look. */
  theme?: WidgetTheme;
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
      en: "Contact us",
      ar: "تواصل معنا",
    },
    leadIntro: {
      en: "Leave your details and our team will get back to you.",
      ar: "اترك بياناتك وسيتواصل معك فريقنا.",
    },
    leadEmailInvalid: {
      en: "Please enter a valid email address.",
      ar: "يرجى إدخال بريد إلكتروني صحيح.",
    },
    leadClose: { en: "Close contact form", ar: "إغلاق النموذج" },
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
    leadSubmit: { en: "Send to our team", ar: "أرسل إلى الفريق" },
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
    stop: { en: "Stop", ar: "إيقاف" },
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

// The in-flight assistant bubble while a reply streams in (S.5). It is
// replaced by the persisted message id when the server sends `done`.
const STREAMING_TURN_ID = "streaming-reply";

interface DonePayload {
  kind?: string;
  visitor_message: { id: string; created_at: string };
  ai_message: {
    id: string;
    text: string;
    citations: CitedSource[];
    needs_human: boolean;
    created_at: string;
  } | null;
}

/** Parse one SSE block ("event: x\ndata: {...}"); comments yield null. */
function parseSseBlock(block: string): { event: string; data: unknown } | null {
  let event = "";
  const dataLines: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:"))
      dataLines.push(line.slice(5).trimStart());
  }
  if (!event || dataLines.length === 0) return null;
  try {
    return { event, data: JSON.parse(dataLines.join("\n")) };
  } catch {
    return null;
  }
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

const EMAIL_SHAPE = /^\S+@\S+\.\S+$/;

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
  // True from the first streamed character until the turn ends (S.5).
  const [streaming, setStreaming] = useState(false);
  // Final text of a streamed reply, announced once at `done` (not per token).
  const [announce, setAnnounce] = useState("");
  const abortRef = useRef<AbortController | null>(null);
  const turnActiveRef = useRef(false);
  const [error, setError] = useState<string | null>(null);
  const locatorRef = useRef<string | null>(null);
  const sessionRef = useRef<{ id: string; token: string } | null>(null);
  const lastPollAtRef = useRef<string | null>(null);
  const pollingRef = useRef(false);
  // Polling rules (H5): the server's X-Poll-Hint wins; a handoff seen in a turn
  // keeps polling on until the first hint arrives. Errors back off exponentially.
  const pollHintRef = useRef<PollHint | null>(null);
  const handoffRef = useRef(false);
  const pollErrorsRef = useRef(0);
  const pollTimerRef = useRef<number | null>(null);
  const schedulePollRef = useRef<(delayMs?: number) => void>(() => undefined);
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

  function applyPollHint(response: Response) {
    const hint = parsePollHint(response.headers.get(POLL_HINT_HEADER));
    if (hint) pollHintRef.current = hint;
  }

  /** A turn that handed over to a human (re)starts polling until the server says idle. */
  function noteHandoff(kind?: string | null, needsHuman?: boolean | null) {
    if (!handoffFromTurn(kind, needsHuman)) return;
    handoffRef.current = true;
    pollHintRef.current = null;
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
    applyPollHint(response);
    schedulePollRef.current();
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
    if (!session || pollingRef.current || turnActiveRef.current) return;
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
        pollErrorsRef.current += 1;
        if (widgetDebugEnabled()) {
          console.debug("[widget-debug] poll response", response.status);
        }
        return;
      }
      pollErrorsRef.current = 0;
      applyPollHint(response);
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
      pollErrorsRef.current += 1;
      if (widgetDebugEnabled()) {
        console.debug("[widget-debug] poll failed");
      }
      // Polling is best effort; the next attempt backs off without changing the thread.
    } finally {
      pollingRef.current = false;
    }
  }

  // Poll only while a reply can arrive without the visitor acting (human
  // agent, scheduled follow-up); back off on errors; stop when idle or hidden.
  useEffect(() => {
    if (status !== "ready" || !config) return;
    let cancelled = false;
    const clear = () => {
      if (pollTimerRef.current !== null) {
        window.clearTimeout(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };
    const wanted = () =>
      shouldPoll({
        hint: pollHintRef.current,
        handoff: handoffRef.current,
        hidden: document.hidden,
      });
    const schedule = (delayMs?: number) => {
      clear();
      if (cancelled || !wanted()) return;
      pollTimerRef.current = window.setTimeout(
        () => void tick(),
        delayMs ?? nextPollDelay(pollErrorsRef.current),
      );
    };
    const tick = async () => {
      pollTimerRef.current = null;
      if (cancelled || !wanted()) return;
      await pollSession();
      schedule();
    };
    // One immediate look (turn finished, tab visible again), then the hint decides.
    const probe = async () => {
      clear();
      if (cancelled || !sessionRef.current) return;
      await pollSession();
      schedule();
    };
    schedulePollRef.current = (delayMs) => {
      if (delayMs === 0) void probe();
      else schedule(delayMs);
    };
    const onVisibility = () => {
      if (!document.hidden) void probe();
      else clear();
    };
    document.addEventListener("visibilitychange", onVisibility);
    schedule();
    return () => {
      cancelled = true;
      clear();
      document.removeEventListener("visibilitychange", onVisibility);
      schedulePollRef.current = () => undefined;
    };
    // Session refs change without a render; the loop reads the latest refs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
          colour: launcherColour(cfg.theme, cfg.colour),
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
    // Intrinsic content height, NOT documentElement.scrollHeight: the root is
    // html,body{height:100%} so that equals this iframe's own current height and
    // an older loader that follows it would stick at the first small value
    // (150px -> 200px). Fixed chrome + the thread's content, never below 600.
    const root = document.querySelector<HTMLElement>(".widget-frame");
    let height = 600;
    if (root) {
      let intrinsic = 0;
      for (const child of Array.from(root.children) as HTMLElement[]) {
        intrinsic += child.classList.contains("widget-thread")
          ? child.scrollHeight
          : child.offsetHeight;
      }
      height = Math.max(height, intrinsic);
    }
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

  function stopStream() {
    abortRef.current?.abort();
  }

  /**
   * Streamed turn (S.5): POST .../messages/stream and read Server-Sent Events
   * with fetch + ReadableStream. Resolves to:
   * - "done"     the turn finished (persisted by the server at `done`);
   * - "fallback" the stream failed before any text: the caller makes ONE
   *              request to the buffered endpoint;
   * - "failed"   a typed error was shown (same handling as the buffered path);
   * - "aborted"  the visitor pressed Stop (nothing is persisted server-side).
   */
  async function streamTurn(
    session: { id: string; token: string },
    text: string,
    localTurn: Turn,
    signal: AbortSignal,
  ): Promise<"done" | "fallback" | "failed" | "aborted"> {
    let response: Response;
    try {
      response = await fetch(
        `/api/public/v1/sessions/${session.id}/messages/stream`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Accept: "text/event-stream",
            "X-Session-Token": session.token,
          },
          body: JSON.stringify({ text, language: lang }),
          signal,
        },
      );
    } catch {
      return signal.aborted ? "aborted" : "fallback";
    }
    if (!response.ok) {
      const payload = (await response.json().catch(() => null)) as {
        error?: { code?: string; message?: string };
      } | null;
      if (payload?.error?.code) {
        // An application refusal (paused, rate limit, expired session...):
        // the buffered endpoint would answer the same, so show it directly.
        setTypedError(payload.error.code, payload.error.message);
        return "failed";
      }
      return "fallback"; // proxy or transport error
    }
    const type = response.headers.get("content-type") ?? "";
    if (!response.body || !type.includes("text/event-stream")) {
      return "fallback";
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let text_ = "";
    let started = false;
    const result: {
      outcome: "done" | "fallback" | "failed" | "aborted" | null;
    } = {
      outcome: null,
    };

    const showStreamed = (next: string) => {
      text_ = next;
      if (!started) {
        started = true;
        setStreaming(true);
        setTurns((current) => [
          ...current,
          { id: STREAMING_TURN_ID, role: "assistant", text: next },
        ]);
      } else {
        setTurns((current) =>
          current.map((turn) =>
            turn.id === STREAMING_TURN_ID ? { ...turn, text: next } : turn,
          ),
        );
      }
    };

    const finish = (payload: DonePayload) => {
      noteHandoff(payload.kind, payload.ai_message?.needs_human);
      lastPollAtRef.current =
        payload.ai_message?.created_at ?? payload.visitor_message.created_at;
      setTurns((current) => {
        const withVisitorId = current.map((turn) =>
          turn.id === localTurn.id
            ? { ...turn, id: payload.visitor_message.id }
            : turn,
        );
        const ai = payload.ai_message;
        if (!ai) {
          return withVisitorId.filter((turn) => turn.id !== STREAMING_TURN_ID);
        }
        const final: Turn = {
          id: ai.id,
          role: "assistant",
          text: ai.text, // authoritative: replaces whatever streamed
          citations: ai.citations,
          needsHuman: ai.needs_human,
        };
        const rest = withVisitorId.filter(
          (turn) => turn.id !== STREAMING_TURN_ID && turn.id !== ai.id,
        );
        return [...rest, final];
      });
      if (started && payload.ai_message) setAnnounce(payload.ai_message.text);
      setReason(null);
      setServerMessage(null);
    };

    const dropPartial = () => {
      setTurns((current) =>
        current.filter((turn) => turn.id !== STREAMING_TURN_ID),
      );
    };

    const handle = (block: string) => {
      const parsed = parseSseBlock(block);
      if (!parsed) return;
      const data = parsed.data as Record<string, unknown>;
      if (parsed.event === "delta" && typeof data.text === "string") {
        showStreamed(text_ + data.text);
      } else if (
        parsed.event === "cannot_confirm" &&
        typeof data.text === "string"
      ) {
        showStreamed(data.text);
      } else if (parsed.event === "done") {
        finish(data as unknown as DonePayload);
        result.outcome = "done";
      } else if (parsed.event === "error") {
        if (started) {
          dropPartial();
          setTypedError(String(data.code ?? "NETWORK"));
          result.outcome = "failed";
        } else {
          result.outcome = "fallback";
        }
      }
    };

    try {
      while (result.outcome === null) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder
          .decode(value, { stream: true })
          .replace(/\r\n/g, "\n");
        let boundary = buffer.indexOf("\n\n");
        while (boundary >= 0 && result.outcome === null) {
          handle(buffer.slice(0, boundary));
          buffer = buffer.slice(boundary + 2);
          boundary = buffer.indexOf("\n\n");
        }
      }
    } catch {
      if (signal.aborted) {
        dropPartial();
        return "aborted";
      }
      if (!started) return "fallback";
      dropPartial();
      setReason("network");
      return "failed";
    } finally {
      void reader.cancel().catch(() => undefined);
    }
    if (result.outcome !== null) return result.outcome;
    // The stream ended without `done`.
    if (!started) return "fallback";
    dropPartial();
    setReason("network");
    return "failed";
  }

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
    setAnnounce("");
    setTyping(true);
    turnActiveRef.current = true;
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      if (sessionRef.current === null) {
        sessionRef.current = await ensureSessionFor(locator);
      }
      if (!sessionRef.current) {
        setTyping(false);
        return;
      }
      const outcome = await streamTurn(
        sessionRef.current,
        text,
        localTurn,
        controller.signal,
      );
      if (outcome === "aborted") {
        // Nothing was persisted: put the visitor's text back in the input.
        setTurns((current) =>
          current.filter((turn) => turn.id !== localTurn.id),
        );
        setDraft(text);
        return;
      }
      if (outcome !== "fallback") return;
      // The stream failed before any text: ONE request to the buffered endpoint.
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
        kind?: string;
        visitor_message: { id: string; created_at: string };
        ai_message: {
          id: string;
          text: string;
          citations: CitedSource[];
          needs_human: boolean;
          created_at: string;
        } | null;
      };
      noteHandoff(payload.kind, payload.ai_message?.needs_human);
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
      turnActiveRef.current = false;
      abortRef.current = null;
      setStreaming(false);
      setTyping(false);
      // One look right after the turn: a handoff / scheduled follow-up resumes polling.
      schedulePollRef.current(0);
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
    if (lead.email.trim() && !EMAIL_SHAPE.test(lead.email.trim())) {
      setLead((state) => ({
        ...state,
        status: "error",
        error: localized("leadEmailInvalid", lang),
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

  const leadOpenRef = useRef(false);
  useEffect(() => {
    leadOpenRef.current = lead.open;
  }, [lead.open]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      if (leadOpenRef.current) {
        setLead((state) => ({ ...state, open: false, error: null }));
      } else {
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
      data-widget-variant={themeVariant(config?.theme)}
      style={
        {
          "--widget-brand": config?.colour,
          "--widget-ink": brandInk(config?.colour),
          ...themeStyleVars(config?.theme),
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

      <main
        className="widget-thread"
        aria-live={streaming ? "off" : "polite"}
        aria-busy={streaming}
      >
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
                  aria-busy={turn.id === STREAMING_TURN_ID ? true : undefined}
                >
                  {turn.role === "visitor" ? (
                    <div dir="auto">{turn.text}</div>
                  ) : (
                    <MessageBody text={turn.text} />
                  )}
                  {turn.role === "assistant" &&
                    turn.id !== "welcome" &&
                    turn.id !== STREAMING_TURN_ID &&
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
            {typing && !streaming && (
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
          <span aria-hidden="true" className="widget-done-mark">
            ✓
          </span>
          {localized("leadDone", lang)}
        </p>
      )}
      {status === "ready" && !blocked && lead.status !== "done" && (
        <div className="widget-contact-bar">
          <button
            type="button"
            className="widget-contact-btn"
            data-testid="widget-lead-open"
            onClick={() => setLead((state) => ({ ...state, open: true }))}
          >
            <svg
              aria-hidden="true"
              viewBox="0 0 24 24"
              width="16"
              height="16"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <rect x="3" y="5" width="18" height="14" rx="2" />
              <path d="m3 7 9 6 9-6" />
            </svg>
            {localized("leadTitle", lang)}
          </button>
        </div>
      )}
      {status === "ready" && !blocked && lead.open && (
        <div className="widget-sheet-layer">
          <button
            type="button"
            className="widget-sheet-backdrop"
            aria-label={localized("leadClose", lang)}
            tabIndex={-1}
            onClick={() =>
              setLead((state) => ({ ...state, open: false, error: null }))
            }
          />
          <section
            className="widget-sheet"
            role="dialog"
            aria-modal="true"
            aria-labelledby="widget-lead-title"
          >
            <header className="widget-sheet-head">
              <div>
                <h2 id="widget-lead-title" dir="auto">
                  {localized("leadTitle", lang)}
                </h2>
                <p dir="auto">{localized("leadIntro", lang)}</p>
              </div>
              <button
                type="button"
                className="widget-sheet-close"
                aria-label={localized("leadClose", lang)}
                onClick={() =>
                  setLead((state) => ({ ...state, open: false, error: null }))
                }
              >
                ✕
              </button>
            </header>
            <form
              className="widget-lead-form"
              data-testid="widget-lead-form"
              noValidate
              onSubmit={(leadEvent) => {
                leadEvent.preventDefault();
                void submitLead();
              }}
            >
              <label className="widget-field" dir="auto">
                <input
                  dir="auto"
                  autoFocus
                  placeholder=" "
                  autoComplete="name"
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
                <span>{localized("leadName", lang)}</span>
              </label>
              <label className="widget-field" dir="auto">
                <input
                  dir="auto"
                  type="email"
                  placeholder=" "
                  autoComplete="email"
                  aria-invalid={
                    lead.email.trim() !== "" &&
                    !EMAIL_SHAPE.test(lead.email.trim())
                  }
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
                <span>{localized("leadEmail", lang)}</span>
              </label>
              <label className="widget-field" dir="auto">
                <input
                  dir="auto"
                  type="tel"
                  placeholder=" "
                  autoComplete="tel"
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
                <span>{localized("leadPhone", lang)}</span>
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
              <button
                type="submit"
                className="widget-lead-submit"
                data-testid="widget-lead-submit"
                disabled={lead.status === "saving"}
              >
                {lead.status === "saving" ? (
                  <span className="widget-spinner" aria-hidden="true" />
                ) : (
                  localized("leadSubmit", lang)
                )}
              </button>
            </form>
          </section>
        </div>
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
          {typing && (
            <button
              type="button"
              onClick={stopStream}
              data-testid="widget-stop"
            >
              {localized("stop", lang)}
            </button>
          )}
        </form>
      )}
      <p
        className="sr-only"
        role="status"
        aria-live="polite"
        data-testid="widget-announce"
      >
        {announce}
      </p>
      <p className="sr-only">{localized("scroll", lang)}</p>
    </div>
  );
}

function closeWidget() {
  window.parent.postMessage({ type: "chatbot:close" }, window.location.origin);
}
