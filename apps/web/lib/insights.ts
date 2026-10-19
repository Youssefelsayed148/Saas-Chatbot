/** P6-05b shared channel/insights helpers (pure functions, unit-tested). */

export const CHANNEL_VALUES = [
  "website",
  "instagram",
  "whatsapp",
  "messenger",
] as const;

export type ChannelValue = (typeof CHANNEL_VALUES)[number];

/** The channel dropdown used by the inbox and contacts filters. */
export function channelOptions(
  includeWebsite = true,
): Array<{ value: string; label: string }> {
  const options = [{ value: "", label: "All" }];
  for (const value of CHANNEL_VALUES) {
    if (value === "website" && !includeWebsite) continue;
    options.push({ value, label: humanChannel(value) });
  }
  return options;
}

export function humanChannel(channel: string): string {
  switch (channel) {
    case "whatsapp":
      return "WhatsApp";
    case "messenger":
      return "Messenger";
    case "instagram":
      return "Instagram";
    case "website":
      return "Website";
    default:
      return channel;
  }
}

/** Row label for a conversation channel with its connection (P6-05b).
 *
 * Website rows (and channel rows without a connection name) stay unchanged,
 * so a website-only tenant's inbox looks exactly as before P6-05b. */
export function connectionSuffix(
  channel: string,
  connectionName?: string | null,
): string | null {
  if (channel === "website" || !connectionName?.trim()) return null;
  return connectionName.trim();
}

export function formatRate(rate: number | null | undefined): string {
  if (rate === null || rate === undefined) return "—";
  return `${(rate * 100).toFixed(1)}%`;
}

export function formatMedian(
  seconds: number | null | undefined,
): string {
  if (seconds === null || seconds === undefined) return "—";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)} min`;
  return `${(seconds / 3600).toFixed(1)} h`;
}

/** Campaign rows sorted by conversations then name (measured order preserved). */
export function sortedCampaigns(
  byCampaign: Record<string, number>,
): Array<{ campaign: string; conversations: number }> {
  return Object.entries(byCampaign)
    .map(([campaign, conversations]) => ({ campaign, conversations }))
    .sort(
      (a, b) => b.conversations - a.conversations || a.campaign.localeCompare(b.campaign),
    );
}
