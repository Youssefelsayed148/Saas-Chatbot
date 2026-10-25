/* Small presentational helpers for the inbox list rows (B5, gap I-4). */

/** Up to two initials from a contact name; "V" (visitor) when unknown. */
export function initialsOf(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return "V";
  const letters = words
    .slice(0, 2)
    .map((word) => Array.from(word)[0] ?? "")
    .join("");
  return letters.toUpperCase() || "V";
}

export function InboxRowAvatar({ name }: { name: string }) {
  return (
    <span className="inbox-avatar" aria-hidden="true">
      {initialsOf(name)}
    </span>
  );
}

/** Short relative time: now, 5m, 3h, otherwise a short date. */
export function formatRowTime(iso: string | null): string {
  if (!iso) return "No activity";
  const then = new Date(iso);
  const minutes = Math.floor((Date.now() - then.getTime()) / 60000);
  if (minutes < 1) return "Now";
  if (minutes < 60) return `${minutes}m`;
  if (minutes < 60 * 24) return `${Math.floor(minutes / 60)}h`;
  return then.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}
