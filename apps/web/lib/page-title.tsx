"use client";

import { usePathname } from "next/navigation";

const ROUTES: [RegExp, string][] = [
  [/^\/platform\/members\/[^/]+$/, "Member details"],
  [/^\/platform\/members$/, "Members"],
  [/^\/$/, "Welcome"],
  [/^\/login$/, "Sign in"],
  [/^\/privacy$/, "Privacy"],
  [/^\/terms$/, "Terms of use"],
  [/^\/register$/, "Create account"],
  [/^\/accept-invite$/, "Accept invitation"],
  [/^\/widget\/sample$/, "Widget sample"],
  [/^\/widget\/frame$/, "Chat"],
  [/^\/platform\/clients\/[^/]+$/, "Organization details"],
  [/^\/platform\/operations$/, "Platform operations"],
  [/^\/platform\/change-requests$/, "Change requests"],
  [/^\/platform$/, "Organizations"],
  [/^\/app$/, "Workspaces"],
  [/^\/app\/[^/]+$/, "Overview"],
  [/\/settings\/members$/, "Team"],
  [/\/settings\/data$/, "Data and audit"],
  [/\/settings\/requests$/, "Request a change"],
  [/\/inbox\/[^/]+$/, "Conversation · Inbox"],
  [/\/inbox$/, "Inbox"],
  [/\/contacts\/[^/]+$/, "Contact details"],
  [/\/contacts$/, "Contacts"],
  [/\/analytics$/, "Insights"],
  [/\/conversations\/[^/]+$/, "Conversation"],
  [/\/conversations$/, "Conversations"],
  [/\/bots$/, "Bots"],
  [/\/overview$/, "Bot overview"],
  [/\/knowledge$/, "Knowledge"],
  [/\/playground$/, "Playground"],
  [/\/settings$/, "Bot settings"],
  [/\/install$/, "Install"],
  [/\/channels$/, "Channels"],
];

export default function PageTitle() {
  const pathname = usePathname();
  const label = ROUTES.find(([pattern]) => pattern.test(pathname))?.[1];
  return (
    <title>
      {label ? `${label} · Website Chatbot SaaS` : "Website Chatbot SaaS"}
    </title>
  );
}
