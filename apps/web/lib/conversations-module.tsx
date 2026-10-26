"use client";

import { useParams, usePathname, useRouter } from "next/navigation";
import type { ReactNode } from "react";

import { PageHeader, TabPanel, Tabs } from "./ui";

import "@/app/conversations-module.css";

/* Conversations module (B5, gaps I-1..I-7): one module, two tabs.
 *
 *   Inbox   /app/T/inbox, /app/T/inbox/[conversation]   live work
 *   History /app/T/conversations, /app/T/bots/B/conversations(/[id])
 *                                                       all saved conversations
 *
 * The shell is mounted by a layout.tsx in each of those route segments, so the
 * page header and tab bar are shared and a pages below it must NOT render their
 * own <h1>/PageHeader. Pages render only their content; the shell supplies the
 * active TabPanel (id `conv-panel-<tab>`) around it.
 *
 * ---- Inbox filter query-param contract (URL is the source of truth) --------
 *   status    open | waiting_human | resolved
 *   assignee  me | unassigned | <user uuid>
 *   unread    true | false
 *   mode      ai | human
 *   channel   website | whatsapp | messenger | instagram
 *   tag       free text (<= 32)
 *   q         free text search (<= 200)
 * Filter chips are presets of those params and are active when the URL
 * matches: Waiting for a reply = status=waiting_human; Assigned to me =
 * assignee=me; Unread = unread=true; All = none of the three. Every param is
 * forwarded unchanged to api.listInbox. Links from the list to a thread keep
 * the query string, so the thread view keeps the list context.
 *
 * ---- History query-param contract (tenant-wide /app/T/conversations) -------
 *   q         search text
 *   status    open | waiting_human | resolved
 *   channel   website | whatsapp | messenger | instagram
 *   from, to  YYYY-MM-DD, sent to the API as created_from / created_to
 *   page      1-based page number, HISTORY_PAGE_SIZE rows per page
 * Rows come from api.listInbox (limit, offset, total). A row opens the
 * read-only saved thread at /app/T/bots/<row.bot_id>/conversations/<row.id>.
 * The per-bot page /app/T/bots/B/conversations keeps using
 * api.listConversations (no preview, has message_count).
 *
 * ---- Row view model shared by History (tenant-wide and per-bot) ------------
 *   HistoryRow = {
 *     id: string; botId: string;
 *     lastActivity: string;          // last_message_at ?? created_at (ISO)
 *     visitor: string | null;        // contact_name, shown dir="auto"
 *     preview?: string | null;       // last_message, dir="auto" (tenant-wide only)
 *     status: string; channel: string;
 *     messageCount?: number;         // per-bot listing only
 *   }
 * Role rules (unchanged): everyone who can open the page reads; delete
 * (`delete-${id}` through ConfirmAction, reachable from the row overflow menu)
 * and retention (`retention-input`, `retention-save`, `retention-saved`) are
 * admin only.
 */

export type ConversationsTab = "inbox" | "history";
export const HISTORY_PAGE_SIZE = 25;
const PREFIX = "conv";

export function ConversationsShell({ children }: { children: ReactNode }) {
  const { tenant } = useParams<{ tenant: string }>();
  const pathname = usePathname();
  const router = useRouter();
  const tab: ConversationsTab = pathname.startsWith(`/app/${tenant}/inbox`)
    ? "inbox"
    : "history";
  const tabs = [
    { id: "inbox", label: "Inbox", testId: "conversations-tab-inbox" },
    { id: "history", label: "History", testId: "conversations-tab-history" },
  ];
  return (
    <main className="conv-module" data-tab={tab}>
      <PageHeader
        title="Conversations"
        purpose={
          tab === "history"
            ? "Every saved visitor conversation, with retention and deletion."
            : undefined
        }
      />
      <Tabs
        idPrefix={PREFIX}
        aria-label="Conversations sections"
        tabs={tabs}
        value={tab}
        onChange={(id) =>
          router.push(
            id === "inbox"
              ? `/app/${tenant}/inbox`
              : `/app/${tenant}/conversations`,
          )
        }
      />
      {tabs.map((item) => (
        <TabPanel
          key={item.id}
          idPrefix={PREFIX}
          tabId={item.id}
          active={item.id === tab}
          className="conv-module-panel"
        >
          {children}
        </TabPanel>
      ))}
    </main>
  );
}
