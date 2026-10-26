/**
 * Shared domain-entry normalization (A1.4): mirrors the server validator in
 * apps/api/app/bots/schemas.py so the widget allow-list stores bare hostnames
 * no matter where the entry was typed.
 */
export function normalizeDomainEntry(input: string): string {
  let entry = input.trim().toLowerCase();
  if (entry.startsWith("http://")) entry = entry.slice("http://".length);
  else if (entry.startsWith("https://")) entry = entry.slice("https://".length);
  // Credentials before the host never belong in the allow-list.
  if (entry.includes("@")) entry = entry.slice(entry.lastIndexOf("@") + 1);
  // Everything from the first path/query/fragment marker is not the host.
  const marker = [...entry].findIndex(
    (char) => char === "/" || char === "?" || char === "#",
  );
  if (marker !== -1) entry = entry.slice(0, marker);
  // Bare IPv6 keeps its brackets; everything else drops a numeric port.
  if (entry.startsWith("[") && entry.includes("]")) {
    entry = entry.slice(1, entry.indexOf("]"));
  } else {
    const colon = entry.lastIndexOf(":");
    if (colon !== -1 && /^\d*$/.test(entry.slice(colon + 1)))
      entry = entry.slice(0, colon);
  }
  while (entry.endsWith(".")) entry = entry.slice(0, -1);
  return entry;
}

/** Normalize every non-empty line and drop duplicates, preserving order. */
export function normalizeDomainLines(text: string): string[] {
  const entries: string[] = [];
  for (const line of text.split("\n")) {
    const entry = normalizeDomainEntry(line);
    if (entry && !entries.includes(entry)) entries.push(entry);
  }
  return entries;
}
