"use client";

export const TONE_MAX = 2000;

/** Staff-only tone and rules (#15). The settings page itself is staff-only and
 * the API returns 403 to members; this is just the form control. */
export default function BotToneField({
  value,
  onChange,
  disabled,
  error,
}: {
  value: string;
  onChange: (next: string) => void;
  disabled: boolean;
  error: string | null;
}) {
  return (
    <section
      aria-label="Tone and rules"
      data-testid="tone-and-rules-section"
      className="bot-tone"
    >
      <h3>Tone and rules (platform staff only)</h3>
      <p className="muted">
        Short notes on how the assistant should sound, for example &ldquo;Warm,
        brief, use the customer&rsquo;s name&rdquo;. These notes only change
        wording and style. They cannot override the grounding, safety or answer
        format rules, and customers and organization members never see them.
      </p>
      <label className="field">
        Tone and rules
        <textarea
          dir="auto"
          name="tone_and_rules"
          disabled={disabled}
          rows={5}
          maxLength={TONE_MAX}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          aria-describedby="tone-counter"
        />
      </label>
      <p
        id="tone-counter"
        className="muted"
        data-testid="tone-counter"
        aria-live="polite"
      >
        {value.length} / {TONE_MAX} characters
      </p>
      {error && (
        <p
          role="alert"
          className="field-error"
          data-testid="field-error-tone_and_rules"
        >
          {error}
        </p>
      )}
    </section>
  );
}
