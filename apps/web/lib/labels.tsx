import type { ReactNode } from "react";
const LABELS: Record<string, string> = {
  waiting_human: "Waiting for human",
  manual_takeover: "Manual takeover",
  visitor_requested: "Visitor requested a person",
  unanswered_threshold: "Repeated unanswered questions",
  provider_failure: "Assistant unavailable",
  staff_keyword: "Team keyword",
  order_account: "Order or account help",
  ai: "AI",
  human: "Human",
  open: "Open",
  resolved: "Resolved",
  website: "Website",
  whatsapp: "WhatsApp",
  messenger: "Messenger",
  instagram: "Instagram",
  draft: "Draft",
  active: "Active",
  paused: "Paused",
  archived: "Archived",
  stored: "Uploaded",
  queued: "Queued",
  ingested: "Processed",
  failed: "Failed",
  pending: "Queued",
  running: "Processing",
  succeeded: "Completed",
  cancelled: "Cancelled",
  published: "Published",
};
export function humanLabel(value: string): string {
  return (
    LABELS[value] ??
    value.replaceAll("_", " ").replace(/^./, (c) => c.toUpperCase())
  );
}
export function LabelBadge({
  value,
  children,
}: {
  value: string;
  children?: ReactNode;
}) {
  return (
    <span className="badge" data-value={value} title={value}>
      {children ?? humanLabel(value)}
    </span>
  );
}
