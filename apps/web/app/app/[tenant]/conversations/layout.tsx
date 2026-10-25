import type { ReactNode } from "react";

import { ConversationsShell } from "@/lib/conversations-module";

export default function ConversationsLayout({
  children,
}: {
  children: ReactNode;
}) {
  return <ConversationsShell>{children}</ConversationsShell>;
}
