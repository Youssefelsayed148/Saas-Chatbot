"use client";

import { useEffect, useState } from "react";

import * as api from "@/lib/api";
import { LinkButton, StatusPill, type StatusTone } from "@/lib/ui";
import "@/app/bot-settings-c.css";

const STATUS_TEXT: Record<api.ReadinessStatus, string> = {
  ok: "Done",
  todo: "To do",
  warning: "Check",
};
const STATUS_TONE: Record<api.ReadinessStatus, StatusTone> = {
  ok: "success",
  todo: "danger",
  warning: "warning",
};
/** Failing items first, then ones to check, then done; API order within each. */
const STATUS_ORDER: Record<api.ReadinessStatus, number> = {
  todo: 0,
  warning: 1,
  ok: 2,
};
/** The recent-model-calls check is promoted to a banner at the top. */
const MODEL_CALLS_ID = "model_reachable";

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
  const items = readiness?.items ?? [];
  const modelCalls = items.find(
    (item) => item.id === MODEL_CALLS_ID && item.status !== "ok",
  );
  const rows = items
    .filter((item) => item !== modelCalls)
    .map((item, index) => ({ item, index }))
    .sort(
      (a, b) =>
        STATUS_ORDER[a.item.status] - STATUS_ORDER[b.item.status] ||
        a.index - b.index,
    )
    .map(({ item }) => item);
  const readyCount = items.filter((item) => item.status === "ok").length;
  const total = items.length;

  return (
    <section
      aria-label="Launch readiness"
      data-testid="bot-readiness"
      className="ui-card readiness-card"
    >
      <header className="section-heading">
        <h2>Launch readiness</h2>
        {readiness && total > 0 && (
          <span className="readiness-count" data-testid="readiness-count">
            {readyCount}/{total} ready
          </span>
        )}
      </header>
      {failed && <p className="muted">Could not load the checklist.</p>}
      {!readiness && !failed && <p className="muted">Loading checklist…</p>}
      {readiness && (
        <>
          <p data-testid="readiness-summary">
            {readiness.ready
              ? "Everything required is in place."
              : "Some required items are still missing."}
          </p>
          {total > 0 && (
            <div
              className="readiness-progress"
              role="progressbar"
              aria-label="Launch readiness"
              aria-valuemin={0}
              aria-valuemax={total}
              aria-valuenow={readyCount}
              aria-valuetext={`${readyCount} of ${total} ready`}
              data-complete={readyCount === total ? "true" : "false"}
            >
              <span style={{ inlineSize: `${(readyCount / total) * 100}%` }} />
            </div>
          )}
          {modelCalls && (
            <div
              className="readiness-banner"
              data-testid={`readiness-${modelCalls.id}`}
              data-status={modelCalls.status}
              role="alert"
            >
              <div>
                <strong>{modelCalls.label}</strong>
                <p>{modelCalls.detail}</p>
              </div>
              <LinkButton
                href={sectionHref(modelCalls.section, base)}
                variant="secondary"
                size="sm"
              >
                Fix
              </LinkButton>
            </div>
          )}
          <ul className="readiness-list">
            {rows.map((item) => (
              <li
                key={item.id}
                data-testid={`readiness-${item.id}`}
                data-status={item.status}
              >
                <StatusPill tone={STATUS_TONE[item.status]}>
                  {STATUS_TEXT[item.status]}
                </StatusPill>
                <span className="readiness-text">
                  <strong>{item.label}</strong>
                  <span className="muted"> {item.detail}</span>
                </span>
                {item.status !== "ok" && (
                  <LinkButton
                    href={sectionHref(item.section, base)}
                    variant="secondary"
                    size="sm"
                  >
                    Fix
                  </LinkButton>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
