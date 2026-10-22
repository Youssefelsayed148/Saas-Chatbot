"use client";

import {
  contrastIssues,
  DEFAULT_BRAND,
  inkFor,
  isHex,
  PALETTE,
  readableTextFor,
  SLOT_LABELS,
  THEME_PRESETS,
  THEME_SLOTS,
  TOKEN_DEFAULTS,
  type ThemeSlot,
  type ThemeSlots,
} from "@/lib/widget-theme";
import "@/app/bot-settings-c.css";

export interface ThemeDraft {
  /** A preset id, or "custom" once a slot was edited by hand. */
  preset: string;
  slots: ThemeSlots;
}

/** The colour a picker starts from when its slot is unset (today's look). */
function slotDefault(slot: ThemeSlot, brand: string): string {
  if (slot === "bot_bubble") return TOKEN_DEFAULTS.bot_bubble.light;
  if (slot === "text") return TOKEN_DEFAULTS.text.light;
  return isHex(brand) ? brand : DEFAULT_BRAND;
}

/** Presets, per-slot pickers (palette plus the native colour input, never a
 * bare hex box) and the WCAG AA contrast check. Controlled; the settings page
 * owns the draft and saves it with the rest of the form. */
export default function WidgetThemeEditor({
  draft,
  brand,
  disabled,
  onChange,
}: {
  draft: ThemeDraft;
  brand: string;
  disabled: boolean;
  onChange: (next: ThemeDraft) => void;
}) {
  const issues = contrastIssues(draft.slots);

  function setSlot(slot: ThemeSlot, value: string | undefined) {
    const slots = { ...draft.slots };
    if (value === undefined) delete slots[slot];
    else slots[slot] = value.toLowerCase();
    onChange({ preset: "custom", slots });
  }

  function fixContrast() {
    const bubble = draft.slots.bot_bubble;
    if (isHex(bubble)) setSlot("text", readableTextFor(bubble));
    else setSlot("text", undefined);
  }

  return (
    <div className="theme-editor" data-testid="widget-theme-editor">
      <fieldset disabled={disabled} className="theme-presets">
        <legend>Theme preset</legend>
        <div className="theme-preset-grid">
          {THEME_PRESETS.map((preset) => {
            const swatches = THEME_SLOTS.map(
              (slot) => preset.slots[slot] ?? slotDefault(slot, brand),
            );
            return (
              <label key={preset.id} className="theme-preset">
                <input
                  type="radio"
                  name="theme_preset"
                  value={preset.id}
                  checked={draft.preset === preset.id}
                  onChange={() =>
                    onChange({ preset: preset.id, slots: { ...preset.slots } })
                  }
                />
                <span className="theme-preset-name">{preset.name}</span>
                <span className="theme-preset-strip" aria-hidden="true">
                  {swatches.slice(0, 4).map((colour, index) => (
                    <i key={index} style={{ background: colour }} />
                  ))}
                </span>
                <span className="muted">{preset.description}</span>
              </label>
            );
          })}
        </div>
        {draft.preset === "custom" && (
          <p className="muted" data-testid="theme-custom-note">
            Custom colours (edited from a preset).
          </p>
        )}
      </fieldset>

      <fieldset disabled={disabled} className="theme-slots">
        <legend>Widget colours</legend>
        {THEME_SLOTS.map((slot) => {
          const label = SLOT_LABELS[slot];
          const value = draft.slots[slot];
          const shown = isHex(value) ? value : slotDefault(slot, brand);
          return (
            <div
              key={slot}
              role="group"
              aria-label={label}
              className="theme-slot"
              data-testid={`theme-slot-${slot}`}
              data-set={isHex(value) ? "true" : "false"}
            >
              <span className="theme-slot-label">{label}</span>
              <span className="theme-palette">
                {PALETTE.map((colour) => (
                  <button
                    key={colour}
                    type="button"
                    className="theme-swatch"
                    style={{ background: colour }}
                    aria-label={`${label}: ${colour}`}
                    aria-pressed={shown.toLowerCase() === colour && isHex(value)}
                    onClick={() => setSlot(slot, colour)}
                  />
                ))}
              </span>
              <input
                type="color"
                aria-label={`${label} custom colour`}
                value={shown.toLowerCase()}
                onChange={(event) => setSlot(slot, event.target.value)}
              />
              <code
                className="theme-slot-value"
                data-testid={`theme-value-${slot}`}
                aria-label={`${label} value`}
              >
                {isHex(value) ? value.toLowerCase() : "default"}
              </code>
              {isHex(value) && (
                <button
                  type="button"
                  className="quiet-button"
                  aria-label={`Reset ${label} to default`}
                  onClick={() => setSlot(slot, undefined)}
                >
                  Reset
                </button>
              )}
              {slot !== "bot_bubble" && slot !== "text" && isHex(value) && (
                <span className="muted theme-ink-note">
                  Text on it: {inkFor(value) === "#ffffff" ? "white" : "black"}{" "}
                  (automatic)
                </span>
              )}
            </div>
          );
        })}
      </fieldset>

      <div
        role="status"
        data-testid="theme-contrast"
        data-issues={issues.length}
        className="theme-contrast"
      >
        {issues.length === 0 ? (
          <p className="muted">Contrast check passed (WCAG AA, 4.5:1).</p>
        ) : (
          <>
            {issues.map((issue, index) => (
              <p key={index} className="theme-contrast-warning">
                Warning: {issue.message}
              </p>
            ))}
            {issues.some((issue) => issue.slot === "pair") && !disabled && (
              <button
                type="button"
                className="quiet-button"
                data-testid="theme-fix-contrast"
                onClick={fixContrast}
              >
                Use a readable text colour
              </button>
            )}
          </>
        )}
      </div>
    </div>
  );
}
