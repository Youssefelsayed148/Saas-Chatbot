"use client";

import { useId } from "react";

import { contrastRatio } from "@/lib/ui";
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

/** Widget brand colour: picker + hex box + contrast result, in the look of the
 * shared ColorField. Built here because the shared one cannot be used as is:
 * the colour is optional (empty is allowed, so it can be cleared), every typed
 * value still reaches the form (the server validates it and its inline error
 * shows under the field), and the picker's name must not repeat the field label
 * (specs address the hex box by that label). Contrast is checked against the
 * text colour the widget puts on the brand colour. */
export function BrandColourField({
  label,
  value,
  onChange,
  disabled,
  error,
  errorTestId,
}: {
  label: string;
  value: string;
  onChange: (next: string) => void;
  disabled: boolean;
  error: string | null;
  errorTestId: string;
}) {
  const id = useId();
  const valid = isHex(value);
  const empty = value.trim() === "";
  const ink = valid ? inkFor(value) : "#ffffff";
  const ratio = valid ? contrastRatio(value, ink) : 0;
  const message = empty
    ? "Optional. Leave empty to use the default colour."
    : !valid
      ? "Enter a colour as #rrggbb."
      : ratio >= 4.5
        ? `Contrast ${ratio.toFixed(1)}:1 with ${ink === "#ffffff" ? "white" : "black"} text. Passes.`
        : `Contrast ${ratio.toFixed(1)}:1 with ${ink === "#ffffff" ? "white" : "black"} text is too low (4.5:1 needed).`;
  const tone = empty
    ? "neutral"
    : !valid
      ? "danger"
      : ratio >= 4.5
        ? "success"
        : "warning";
  return (
    <div
      className="field brand-colour"
      data-invalid={error || (!valid && !empty) ? "true" : undefined}
      data-testid="brand-colour-field"
    >
      <label htmlFor={`${id}-hex`}>{label}</label>
      <div className="brand-colour-inputs">
        <input
          type="color"
          aria-label="Widget colour picker"
          disabled={disabled}
          value={valid ? value.toLowerCase() : DEFAULT_BRAND}
          onChange={(event) => onChange(event.target.value)}
        />
        <input
          id={`${id}-hex`}
          type="text"
          name="colour"
          spellCheck={false}
          autoComplete="off"
          placeholder="#1a2b3c"
          disabled={disabled}
          value={value}
          aria-invalid={error || (!valid && !empty) ? true : undefined}
          aria-describedby={`${id}-msg`}
          onChange={(event) => onChange(event.target.value)}
        />
      </div>
      <p
        id={`${id}-msg`}
        className="field-hint"
        data-testid="brand-colour-message"
        data-tone={tone}
        role={!valid && !empty ? "alert" : undefined}
      >
        {message}
      </p>
      {error && (
        <p className="field-error" role="alert" data-testid={errorTestId}>
          {error}
        </p>
      )}
    </div>
  );
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
                    aria-pressed={
                      shown.toLowerCase() === colour && isHex(value)
                    }
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
