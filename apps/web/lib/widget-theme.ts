/**
 * Widget theme (#14): slots, curated presets and contrast helpers, shared by
 * the sandboxed widget frame and the dashboard settings editor/preview.
 *
 * Pure TypeScript: no React, no dashboard assets, safe to import in the frame.
 * Preset ids must match THEME_PRESET_IDS in apps/api/app/bots/schemas.py (an
 * API test keeps the two lists in step). Unset slots keep today's look.
 */

export const THEME_SLOTS = [
  "header",
  "send_button",
  "user_bubble",
  "bot_bubble",
  "text",
  "launcher",
] as const;
export type ThemeSlot = (typeof THEME_SLOTS)[number];

export type ThemeSlots = Partial<Record<ThemeSlot, string>>;
/** What the API stores and `widget_config` returns. */
export interface WidgetTheme extends ThemeSlots {
  preset?: string;
}

export const SLOT_LABELS: Record<ThemeSlot, string> = {
  header: "Header",
  send_button: "Send button",
  user_bubble: "Visitor message bubble",
  bot_bubble: "Assistant message bubble",
  text: "Assistant message text",
  launcher: "Chat launcher",
};

export const DEFAULT_BRAND = "#1f7a5c";
/** Fallbacks used only to show the picker's starting value and to check
 * contrast for slots that stay at the design-token default. */
export const TOKEN_DEFAULTS = {
  bot_bubble: { light: "#edf2f9", dark: "#172231" },
  text: { light: "#19263a", dark: "#edf3fa" },
} as const;

export interface ThemePreset {
  id: string;
  name: string;
  description: string;
  slots: ThemeSlots;
  /** Extra styling that is not a colour slot (kept with the preset id). */
  variant?: "glass";
}

export const THEME_PRESETS: ThemePreset[] = [
  {
    id: "classic",
    name: "Classic",
    description: "Today's look: your brand colour on the design defaults.",
    slots: {},
  },
  {
    id: "ocean",
    name: "Ocean",
    description: "Clean blue with soft light bubbles.",
    slots: {
      header: "#0b5ea8",
      send_button: "#0b5ea8",
      user_bubble: "#0b5ea8",
      bot_bubble: "#eaf3fb",
      text: "#0f2a43",
      launcher: "#0b5ea8",
    },
  },
  {
    id: "sunset",
    name: "Sunset",
    description: "Warm orange with cream bubbles.",
    slots: {
      header: "#c2410c",
      send_button: "#c2410c",
      user_bubble: "#c2410c",
      bot_bubble: "#fff4ec",
      text: "#3b1d0d",
      launcher: "#c2410c",
    },
  },
  {
    id: "forest",
    name: "Forest",
    description: "Deep green, calm and professional.",
    slots: {
      header: "#14532d",
      send_button: "#166534",
      user_bubble: "#166534",
      bot_bubble: "#ecf8f0",
      text: "#0f2a1a",
      launcher: "#14532d",
    },
  },
  {
    id: "midnight-glass",
    name: "Midnight glass",
    description: "Modern dark glass: translucent bubbles on a deep gradient.",
    slots: {
      header: "#1e1b4b",
      send_button: "#818cf8",
      user_bubble: "#4f46e5",
      bot_bubble: "#1e293b",
      text: "#f1f5f9",
      launcher: "#4f46e5",
    },
    variant: "glass",
  },
];

/** A small palette next to the native picker (never a hex text box alone). */
export const PALETTE = [
  "#1f7a5c",
  "#0b5ea8",
  "#4f46e5",
  "#7c3aed",
  "#be185d",
  "#c2410c",
  "#b45309",
  "#166534",
  "#0f172a",
  "#475569",
  "#ffffff",
  "#f1f5f9",
] as const;

export const HEX6 = /^#[0-9a-f]{6}$/i;

export function isHex(value: unknown): value is string {
  return typeof value === "string" && HEX6.test(value);
}

function channels(hex: string): [number, number, number] {
  return [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255) as [
    number,
    number,
    number,
  ];
}

export function luminance(hex: string): number {
  const [r, g, b] = channels(hex).map((v) =>
    v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4,
  );
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** WCAG 2.x contrast ratio, 1 to 21. */
export function contrastRatio(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

export const AA_TEXT = 4.5;

/** Readable ink for a coloured surface. Same threshold the widget has always
 * used, returned as the literal colour. */
export function inkFor(background: string): "#ffffff" | "#000000" {
  return luminance(background) > 0.179 ? "#000000" : "#ffffff";
}

/** Today's `brandInk`: token references so the default look is unchanged. */
export function brandInk(colour?: string): string {
  if (!isHex(colour)) return "var(--ink-light)";
  return luminance(colour) > 0.179 ? "var(--ink-dark)" : "var(--ink-light)";
}

/** Slots whose text colour is chosen automatically (always the better of
 * black or white for that background). */
export const AUTO_INK_SLOTS = [
  "header",
  "send_button",
  "user_bubble",
  "launcher",
] as const satisfies readonly ThemeSlot[];

export interface ContrastIssue {
  slot: ThemeSlot | "pair";
  message: string;
  ratio: number;
}

/** Text/background pairs below WCAG AA (4.5:1). Slots left at the token
 * default are checked against both light and dark defaults, because the
 * visitor's scheme is not known when staff edit the theme. */
export function contrastIssues(slots: ThemeSlots): ContrastIssue[] {
  const issues: ContrastIssue[] = [];
  const text = isHex(slots.text) ? slots.text : null;
  const bubble = isHex(slots.bot_bubble) ? slots.bot_bubble : null;
  if (text || bubble) {
    const pairs: Array<[string, string]> = [];
    const texts = text
      ? [text]
      : [TOKEN_DEFAULTS.text.light, TOKEN_DEFAULTS.text.dark];
    const bubbles = bubble
      ? [bubble]
      : [TOKEN_DEFAULTS.bot_bubble.light, TOKEN_DEFAULTS.bot_bubble.dark];
    // Pair like with like when both are defaults (light text with light bubble).
    if (!text && !bubble) return issues;
    if (text && !bubble) {
      for (const b of bubbles) pairs.push([text, b]);
    } else if (!text && bubble) {
      for (const t of texts) pairs.push([t, bubble]);
    } else {
      pairs.push([text as string, bubble as string]);
    }
    let worst = Infinity;
    for (const [t, b] of pairs) worst = Math.min(worst, contrastRatio(t, b));
    if (worst < AA_TEXT) {
      issues.push({
        slot: "pair",
        ratio: worst,
        message: `Assistant message text on its bubble has a contrast of ${worst.toFixed(
          1,
        )}:1; WCAG AA needs at least 4.5:1.`,
      });
    }
  }
  for (const slot of AUTO_INK_SLOTS) {
    const background = slots[slot];
    if (!isHex(background)) continue;
    const ratio = contrastRatio(background, inkFor(background));
    if (ratio < AA_TEXT) {
      issues.push({
        slot,
        ratio,
        message: `${SLOT_LABELS[slot]}: even the best text colour only reaches ${ratio.toFixed(
          1,
        )}:1 on this colour (WCAG AA needs 4.5:1). Pick a lighter or darker colour.`,
      });
    }
  }
  return issues;
}

/** Best text colour for the assistant bubble (one-click fix). */
export function readableTextFor(bubble: string): string {
  return inkFor(bubble) === "#ffffff" ? "#f8fafc" : "#0f172a";
}

export function presetById(id: string | undefined): ThemePreset | undefined {
  return THEME_PRESETS.find((preset) => preset.id === id);
}

export function themeVariant(theme?: WidgetTheme | null): "glass" | undefined {
  return presetById(theme?.preset)?.variant;
}

/** CSS custom properties for the widget frame / preview. Only slots that are
 * set produce a variable, so an empty theme leaves the stylesheet fallbacks
 * (today's look) in charge. */
export function themeStyleVars(
  theme?: WidgetTheme | null,
): Record<string, string> {
  const vars: Record<string, string> = {};
  if (!theme) return vars;
  const set = (name: string, value: string | undefined) => {
    if (isHex(value)) vars[name] = value.toLowerCase();
  };
  const ink = (name: string, value: string | undefined) => {
    if (isHex(value)) vars[name] = inkFor(value);
  };
  set("--w-header", theme.header);
  ink("--w-header-ink", theme.header);
  set("--w-send", theme.send_button);
  ink("--w-send-ink", theme.send_button);
  set("--w-user-bubble", theme.user_bubble);
  ink("--w-user-bubble-ink", theme.user_bubble);
  set("--w-bot-bubble", theme.bot_bubble);
  set("--w-text", theme.text);
  return vars;
}

/** The colour the host page's launcher button takes (the loader derives its
 * own readable icon colour from it). */
export function launcherColour(
  theme: WidgetTheme | null | undefined,
  colour: string,
): string {
  return isHex(theme?.launcher) ? (theme.launcher as string) : colour;
}
