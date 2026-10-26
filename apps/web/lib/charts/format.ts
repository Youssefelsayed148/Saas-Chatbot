import type { StatDelta } from "@/lib/ui";

/** Shared number/time formatters for dashboards and charts (B4). English UI;
 * numbers stay LTR (wrap in <bdi dir="ltr"> next to Arabic text). */

const NUMBER = new Intl.NumberFormat("en-US");
const DASH = "—";

export function formatCount(value: number | null | undefined): string {
  return value == null || !Number.isFinite(value) ? DASH : NUMBER.format(value);
}

/** 0..1 ratio -> "42%" (one decimal under 10% so 4.5% is not shown as 5%). */
export function formatPercent(ratio: number | null | undefined): string {
  if (ratio == null || !Number.isFinite(ratio)) return DASH;
  const pct = ratio * 100;
  const text = Math.abs(pct) < 10 ? pct.toFixed(1) : String(Math.round(pct));
  return `${text.replace(/\.0$/, "")}%`;
}

/** Seconds -> "2.4 s", "45 s", "3 min", "1.5 h". null = no data. */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds)) return DASH;
  if (seconds < 10) return `${seconds.toFixed(1).replace(/\.0$/, "")} s`;
  if (seconds < 60) return `${Math.round(seconds)} s`;
  if (seconds < 600) return `${(seconds / 60).toFixed(1).replace(/\.0$/, "")} min`;
  if (seconds < 3600) return `${Math.round(seconds / 60)} min`;
  return `${(seconds / 3600).toFixed(1).replace(/\.0$/, "")} h`;
}

export function formatMsAsSeconds(ms: number | null | undefined): string {
  return ms == null ? DASH : formatDuration(ms / 1000);
}

const RELATIVE = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
const UNITS: Array<[Intl.RelativeTimeFormatUnit, number]> = [
  ["year", 365 * 86400],
  ["month", 30 * 86400],
  ["day", 86400],
  ["hour", 3600],
  ["minute", 60],
];

/** ISO timestamp -> "5 minutes ago", "yesterday". `now` is injectable for tests. */
export function formatRelativeTime(
  iso: string | null | undefined,
  now: number = Date.now(),
): string {
  if (!iso) return "No activity";
  const time = new Date(iso).getTime();
  if (Number.isNaN(time)) return DASH;
  const seconds = Math.round((time - now) / 1000);
  if (Math.abs(seconds) < 45) return "just now";
  for (const [unit, size] of UNITS) {
    if (Math.abs(seconds) >= size)
      return RELATIVE.format(Math.round(seconds / size), unit);
  }
  return RELATIVE.format(Math.round(seconds / 60), "minute");
}

/** "2026-10-05" -> "Oct 5" (UTC, the API day boundary). */
export function formatDay(day: string): string {
  const date = new Date(`${day}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return day;
  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });
}

/** Inclusive ISO dates for a "last N days" window ending today (UTC). */
export function lastDaysRange(days: number): { from: string; to: string } {
  const end = new Date();
  const start = new Date(end);
  start.setUTCDate(start.getUTCDate() - (days - 1));
  return {
    from: start.toISOString().slice(0, 10),
    to: end.toISOString().slice(0, 10),
  };
}

type DeltaOptions = {
  /** Whether an increase is good (default true). */
  upIsGood?: boolean;
  /** Label read by screen readers, e.g. "vs previous 30 days". */
  label?: string;
};

/** Count change: percentage when the previous value is > 0, otherwise the absolute
 * difference. undefined (no delta shown) when there is no previous value. */
export function countDelta(
  current: number | null | undefined,
  previous: number | null | undefined,
  options: DeltaOptions = {},
): StatDelta | undefined {
  if (current == null || previous == null) return undefined;
  const diff = current - previous;
  const direction = diff === 0 ? "flat" : diff > 0 ? "up" : "down";
  const sign = diff > 0 ? "+" : "-";
  const value =
    diff === 0
      ? "0%"
      : previous > 0
        ? `${sign}${Math.round((Math.abs(diff) / previous) * 100)}%`
        : `${sign}${formatCount(Math.abs(diff))}`;
  return { value, direction, ...options };
}

/** Rate change in percentage points ("+3 pts"). Both ratios are 0..1. */
export function rateDelta(
  current: number | null | undefined,
  previous: number | null | undefined,
  options: DeltaOptions = {},
): StatDelta | undefined {
  if (current == null || previous == null) return undefined;
  const points = Math.round((current - previous) * 100);
  const direction = points === 0 ? "flat" : points > 0 ? "up" : "down";
  return {
    value:
      points === 0
        ? "0 pts"
        : `${points > 0 ? "+" : "-"}${Math.abs(points)} pts`,
    direction,
    ...options,
  };
}

/** Duration change ("-1.2 s"). Lower is better unless the caller overrides upIsGood. */
export function durationDelta(
  current: number | null | undefined,
  previous: number | null | undefined,
  options: DeltaOptions = {},
): StatDelta | undefined {
  if (current == null || previous == null) return undefined;
  const diff = current - previous;
  const direction = Math.abs(diff) < 0.05 ? "flat" : diff > 0 ? "up" : "down";
  return {
    value:
      direction === "flat"
        ? "0 s"
        : `${diff > 0 ? "+" : "-"}${formatDuration(Math.abs(diff))}`,
    direction,
    upIsGood: false,
    ...options,
  };
}

/** True when at least one value is a positive number: the "show the card" test. */
export function hasChartData(
  values: ReadonlyArray<number | null | undefined>,
): boolean {
  return values.some((value) => typeof value === "number" && value > 0);
}
