"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import * as api from "@/lib/api";
import "@/app/bot-settings-c.css";

const STATUS_TEXT: Record<api.ReadinessStatus, string> = {
  ok: "Done",
  todo: "To do",
  warning: "Check",
};

/** Where each check is fixed: a settings field on this page, or another tab. */
function sectionHref(
  section: api.ReadinessItem["section"],
  base: string,
): string {
  switch (section) {
    case "contact":
      return "#field-support_email";
    case "messages":
      return "#field-welcome_en";
    case "access":
      return "#field-allowed_domains";
    case "tier":
      return "#settings-ai-tier";
    case "knowledge":
      return `${base}/knowledge`;
  }
}

/** Read-only launch checklist (#26), computed on the API from real state.
 * Staff-only: the API returns 403 to members and the page is staff-only. */
export default function BotReadinessCard({
  tenantId,
  botId,
  refreshKey,
}: {
  tenantId: string;
  botId: string;
  /** Changes after a save so the card re-reads the saved state. */
  refreshKey: number;
}) {
  const [readiness, setReadiness] = useState<api.Readiness | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let live = true;
    api
      .getBotReadiness(tenantId, botId)
      .then((value) => {
        if (live) {
          setReadiness(value);
          setFailed(false);
        }
      })
      .catch(() => {
        if (live) setFailed(true);
      });
    return () => {
      live = false;
    };
  }, [tenantId, botId, refreshKey]);

  const base = `/app/${tenantId}/bots/${botId}`;
  return (
    <section
      aria-label="Launch readiness"
      data-testid="bot-readiness"
      className="card readiness-card"
    >
      <h2>Launch readiness</h2>
      {failed && <p className="muted">Could not load the checklist.</p>}
      {!readiness && !failed && <p className="muted">Loading checklist…</p>}
      {readiness && (
        <>
          <p data-testid="readiness-summary">
            {readiness.ready
              ? "Everything required is in place."
              : "Some required items are still missing."}
          </p>
          <ul className="readiness-list">
            {readiness.items.map((item) => (
              <li
                key={item.id}
                data-testid={`readiness-${item.id}`}
                data-status={item.status}
              >
                <span className={`readiness-status readiness-${item.status}`}>
                  {STATUS_TEXT[item.status]}
                </span>{" "}
                <strong>{item.label}</strong>
                <span className="muted"> {item.detail}</span>{" "}
                {item.status !== "ok" && (
                  <Link href={sectionHref(item.section, base)}>Fix</Link>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
