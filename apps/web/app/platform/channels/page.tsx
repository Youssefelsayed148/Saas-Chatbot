"use client";

import { ChannelsOverview } from "@/lib/staff-channels";
import { LinkButton, PageHeader } from "@/lib/ui";
import "@/app/staff-screens.css";

/** Staff overview of every channel connection (P6). Connections are created
 * and managed inside each organization workspace (Channels tab). */
export default function PlatformChannelsPage() {
  return (
    <main className="platform-channels staff-page">
      <PageHeader
        title="Channels"
        eyebrow={
          <LinkButton variant="ghost" icon="arrow-left" href="/platform">
            Back to Organizations
          </LinkButton>
        }
        purpose="See every delegated ManyOsirisChat connection and its health. Create and manage connections inside each organization."
      />
      <ChannelsOverview />
    </main>
  );
}
