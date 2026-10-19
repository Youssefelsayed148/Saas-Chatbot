import type { ReactNode } from "react";
const LABELS: Record<string, string> = {
  bots: "Assistants",
  seats: "Team members",
  pages_per_bot: "Content pages",
  upload_file_mb: "Maximum file size (MB)",
  monthly_messages: "Messages this month",
  contacts: "Contacts",
  channel_connections: "Connected channels",
  sentiment_runs: "Sentiment analyses this month",
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
  healthy: "Healthy",
  degraded: "Degraded",
  unhealthy: "Unhealthy",
  unknown: "Unknown",
  stale: "No recent signal",
  revoked: "Revoked",
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

// Historical audit rows retain their original action; display both vocabularies.
export function auditActionLabel(action: string): string {
  const labels: Record<string, string> = {
    "platform.onboarding.owner_invited": "Admin invited",
    "platform.onboarding.admin_invited": "Admin invited",
    "self_service.owner_assigned": "Admin assigned",
    "self_service.admin_assigned": "Admin assigned",
    "channel_connection.created": "Channel created",
    "channel_connection.updated": "Channel updated",
    "channel_connection.paused": "Channel paused",
    "channel_connection.active": "Channel resumed",
    "channel_connection.revoked": "Channel revoked",
    "channel_connection.secret_rotated": "Channel secret rotated",
    "channel_connection.health_changed": "Channel health changed",
  };
  return labels[action] ?? action;
}
