"use client";

import { useMemo, useState } from "react";

import { widgetStyles } from "@/lib/widget-styles";
import {
  brandInk,
  DEFAULT_BRAND,
  inkFor,
  isHex,
  launcherColour,
  themeStyleVars,
  themeVariant,
  type WidgetTheme,
} from "@/lib/widget-theme";
import "@/app/bot-settings-c.css";

/** Canonical widget tokens (same values as the generated loader tokens), so
 * the preview resolves the frame's `var(--surface)` etc. identically. */
const DARK_TOKENS =
  "--bg:#0b1018;--surface:#111925;--surface-raised:#172231;--text:#edf3fa;--muted:#a3b2c6;--border:#2b3a4e;--accent:#8aafff;--danger:#ffaaa5;--danger-soft:#382022;--warning:#f2ce8e;--focus:#b9d0ff;--radius:16px;--radius-sm:9px;--font:ui-sans-serif,system-ui,-apple-system,'Segoe UI',sans-serif;--ink-light:#ffffff;--ink-dark:#000000;color-scheme:dark";
const LIGHT_TOKENS =
  "--bg:#f3f6fb;--surface:#ffffff;--surface-raised:#edf2f9;--text:#19263a;--muted:#52647c;--border:#cbd6e5;--accent:#2459b4;--danger:#a62631;--danger-soft:#fff0f0;--warning:#745015;--focus:#2459b4;--radius:16px;--radius-sm:9px;--font:ui-sans-serif,system-ui,-apple-system,'Segoe UI',sans-serif;--ink-light:#ffffff;--ink-dark:#000000;color-scheme:light";

function esc(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

export interface PreviewInput {
  theme: WidgetTheme;
  colour: string;
  lang: "en" | "ar";
  name: string;
  welcome: string;
  scheme: "light" | "dark";
}

/** Static document with the widget's own class names and stylesheet. Only the
 * presentation is mirrored; no behaviour, scripts or network. */
export function widgetPreviewHtml(input: PreviewInput): string {
  const { theme, lang, scheme } = input;
  const dir = lang === "ar" ? "rtl" : "ltr";
  const colour = isHex(input.colour) ? input.colour : DEFAULT_BRAND;
  const vars: Record<string, string> = {
    "--widget-brand": colour,
    "--widget-ink": brandInk(colour),
    ...themeStyleVars(theme),
  };
  const style = Object.entries(vars)
    .map(([key, value]) => `${key}:${value}`)
    .join(";");
  const variant = themeVariant(theme);
  const t =
    lang === "ar"
      ? {
          caption: "مساعد الموقع",
          placeholder: "اكتب رسالتك…",
          send: "إرسال",
          question: "ما هي ساعات العمل؟",
          answer: "نعمل يومياً من التاسعة صباحاً حتى الخامسة مساءً.",
          close: "إغلاق المحادثة",
        }
      : {
          caption: "Website assistant",
          placeholder: "Type your message…",
          send: "Send",
          question: "What are your opening hours?",
          answer: "We are open every day from 9:00 to 17:00.",
          close: "Close chat",
        };
  const welcome = input.welcome || (lang === "ar" ? "أهلاً بك!" : "Hello!");
  return `<!doctype html><html lang="${lang}" dir="${dir}"><head><meta charset="utf-8"><style>:root{${
    scheme === "dark" ? DARK_TOKENS : LIGHT_TOKENS
  }}*{box-sizing:border-box}body{margin:0;overflow:hidden;background:var(--bg);color:var(--text);font-family:var(--font);line-height:1.6}button,input{font:inherit}button{min-block-size:42px;padding:.55rem 1rem}${widgetStyles}</style></head><body>
<div class="widget-frame" dir="${dir}" lang="${lang}"${
    variant ? ` data-widget-variant="${variant}"` : ""
  } style="${esc(style)}">
<header class="widget-header"><span aria-hidden="true" class="widget-brand-mark">✧</span><span class="widget-title">${esc(
    input.name,
  )}</span><span class="widget-header-caption">${t.caption}</span><button type="button" class="widget-close" aria-label="${t.close}">×</button></header>
<main class="widget-thread"><ul class="widget-turns">
<li class="widget-bubble"><div dir="auto">${esc(welcome)}</div></li>
<li class="widget-bubble visitor"><div dir="auto">${t.question}</div></li>
<li class="widget-bubble"><div dir="auto">${t.answer}</div></li>
</ul></main>
<form class="widget-composer"><input dir="auto" placeholder="${t.placeholder}" aria-label="${t.placeholder}" readonly><button type="button" tabindex="-1">${t.send}</button></form>
</div></body></html>`;
}

/** Live preview beside the settings form (#14): the widget's real stylesheet
 * and class names rendered from the draft values inside a script-less
 * sandboxed iframe, plus the launcher button that lives on the host page. */
export default function WidgetPreview({
  theme,
  colour,
  lang,
  name,
  welcome,
}: {
  theme: WidgetTheme;
  colour: string;
  lang: "en" | "ar";
  name: string;
  welcome: string;
}) {
  const [scheme, setScheme] = useState<"light" | "dark">("light");
  const html = useMemo(
    () => widgetPreviewHtml({ theme, colour, lang, name, welcome, scheme }),
    [theme, colour, lang, name, welcome, scheme],
  );
  const launcher = launcherColour(
    theme,
    isHex(colour) ? colour : DEFAULT_BRAND,
  );
  return (
    <section
      aria-label="Widget preview"
      className="widget-preview"
      data-testid="widget-preview"
    >
      <h3>Live preview</h3>
      <div
        className="widget-preview-scheme"
        role="group"
        aria-label="Preview mode"
      >
        {(["light", "dark"] as const).map((mode) => (
          <button
            key={mode}
            type="button"
            className="quiet-button"
            aria-pressed={scheme === mode}
            onClick={() => setScheme(mode)}
          >
            {mode === "light" ? "Light page" : "Dark page"}
          </button>
        ))}
      </div>
      <iframe
        title="Widget preview"
        sandbox=""
        srcDoc={html}
        className="widget-preview-frame"
        data-testid="widget-preview-frame"
      />
      <div className="widget-preview-launcher-row">
        <span className="muted">Launcher on the website:</span>
        <span
          className="widget-preview-launcher"
          data-testid="widget-preview-launcher"
          style={{ background: launcher, color: inkFor(launcher) }}
          aria-hidden="true"
        >
          💬
        </span>
      </div>
    </section>
  );
}
