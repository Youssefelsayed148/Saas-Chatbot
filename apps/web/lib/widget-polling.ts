/**
 * Widget thread polling rules (H5). Pure functions so the rules are unit-tested
 * without a browser.
 *
 * The widget only polls while something can still arrive without the visitor
 * acting: a human agent's reply (conversation waiting_human/human) or a
 * scheduled follow-up. The API says which with the `X-Poll-Hint` response
 * header on GET .../messages; until the first hint arrives, a handoff seen in
 * a turn response keeps polling on.
 */

export const POLL_BASE_MS = 2000;
export const POLL_MAX_MS = 30000;
export const POLL_HINT_HEADER = "X-Poll-Hint";

export type PollHint = "active" | "idle";

export function parsePollHint(
  value: string | null | undefined,
): PollHint | null {
  const normalized = value?.trim().toLowerCase();
  return normalized === "active" || normalized === "idle" ? normalized : null;
}

/** A turn that handed the conversation to a human starts (resumes) polling. */
export function handoffFromTurn(
  kind: string | null | undefined,
  needsHuman: boolean | null | undefined,
): boolean {
  return kind === "waiting_human" || kind === "handoff" || needsHuman === true;
}

export function shouldPoll(state: {
  hint: PollHint | null;
  handoff: boolean;
  hidden: boolean;
}): boolean {
  if (state.hidden) return false;
  return (state.hint ?? (state.handoff ? "active" : "idle")) === "active";
}

/** Delay before the next poll: 2 s, doubling per consecutive error, capped. */
export function nextPollDelay(consecutiveErrors: number): number {
  const exponent = Math.min(Math.max(consecutiveErrors, 0), 10);
  return Math.min(POLL_BASE_MS * 2 ** exponent, POLL_MAX_MS);
}
