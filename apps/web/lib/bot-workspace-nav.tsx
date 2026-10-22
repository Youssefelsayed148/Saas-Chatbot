"use client";

/** Per-bot workspace navigation (P4-05, docs/10): one workspace per bot with
 * the tabs that exist TODAY — no placeholders for later phases (Inbox,
 * Contacts, Channels arrive in P5/P6). */

import { useSession } from "./session";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Icon } from "./icons";

const TABS = [
  { key: "overview", label: "Overview", segment: "overview" },
  { key: "conversations", label: "Conversations", segment: "conversations" },
  { key: "knowledge", label: "Knowledge", segment: "knowledge" },
  { key: "playground", label: "Playground", segment: "playground" },
  { key: "settings", label: "Settings", segment: "settings" },
  { key: "install", label: "Install", segment: "install" },
];

export default function BotWorkspaceNav({
  tenantId,
  botId,
  botName,
}: {
  tenantId: string;
  botId: string;
  botName?: string;
}) {
  const pathname = usePathname();
  const { me } = useSession();
  const base = `/app/${tenantId}/bots/${botId}`;
  if (!me?.is_platform_staff) return null;
  return (
    <nav
      className="bot-workspace-nav"
      aria-label="Bot workspace"
      data-testid="bot-workspace-nav"
    >
      <span className="bot-nav-bot">
        <Link href={`/app/${tenantId}/bots`}>
          <Icon name="chevron-left" /> Bots
        </Link>
        {botName && <strong> {botName}</strong>}
      </span>
      <span className="bot-nav-tabs">
        {TABS.map((tab) => {
          const href =
            tab.key === "overview"
              ? `${base}/overview`
              : `${base}/${tab.segment}`;
          const active =
            pathname === href || (pathname ?? "").startsWith(`${href}/`);
          return (
            <Link
              key={tab.key}
              href={href}
              data-active={active ? "true" : "false"}
              data-testid={`nav-${tab.key}`}
              aria-current={active ? "page" : undefined}
            >
              {tab.label}
            </Link>
          );
        })}
      </span>
    </nav>
  );
}
