import { formatRelativeTime } from "@/lib/charts";
import { humanLabel } from "@/lib/labels";
import type { TenantChannel } from "@/lib/api";
import { Card, StatusBadge, type StatusTone } from "@/lib/ui";
import "@/app/channels-screen.css";

const HEALTH_TONE: Record<string, StatusTone> = {
  healthy: "success",
  degraded: "warning",
  unhealthy: "danger",
  unknown: "neutral",
};

/** Read-only "Connected channels" card for client roles (Overview only).
 * No Many URL, reference or secret is ever part of this model. */
export function ConnectedChannelsCard({ items }: { items: TenantChannel[] }) {
  // Website-only organizations see no card at all.
  if (!items.length) return null;
  return (
    <Card title="Connected channels" data-testid="connected-channels">
      <ul className="channel-list-plain">
        {items.map((item, index) => (
          <li
            key={`${item.channel}-${item.display_name}-${index}`}
            data-testid="connected-channel"
            data-channel={item.channel}
          >
            <span className="channel-meta">
              <strong dir="auto">{item.display_name}</strong>
              <span className="channel-badge">{humanLabel(item.channel)}</span>
              {item.status !== "active" && (
                <StatusBadge
                  value={item.status}
                  tone={item.status === "paused" ? "warning" : "danger"}
                >
                  {humanLabel(item.status)}
                </StatusBadge>
              )}
              <StatusBadge
                value={item.health_status}
                tone={HEALTH_TONE[item.health_status]}
              >
                {humanLabel(item.health_status)}
              </StatusBadge>
            </span>
            <small className="muted">
              {item.last_event_at
                ? `Last message ${formatRelativeTime(item.last_event_at)}`
                : "No messages yet"}
            </small>
          </li>
        ))}
      </ul>
    </Card>
  );
}
