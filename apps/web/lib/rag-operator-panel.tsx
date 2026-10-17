"use client";

import { useEffect, useState } from "react";
import * as api from "@/lib/api";
import { ConfirmAction, Notice } from "@/lib/ui";

const LABELS: Record<api.RagLimitName, string> = {
  documents: "Documents per revision",
  chunks: "Chunks per revision",
  storage_bytes: "Stored upload bytes",
  monthly_messages: "AI messages per month",
  monthly_tokens: "AI tokens per month",
  monthly_embedding_tokens: "Embedding tokens per month",
  monthly_ocr_pages: "OCR pages per month",
};

export default function RagOperatorPanel({ tenantId }: { tenantId: string }) {
  const [bots, setBots] = useState<api.Bot[]>([]);
  const [botId, setBotId] = useState("");
  const [readyBotId, setReadyBotId] = useState("");
  const [limits, setLimits] = useState<api.RagLimits>({});
  const [effective, setEffective] = useState<api.RagLimits>({});
  const [usage, setUsage] = useState<Record<string, number>>({});
  const [costs, setCosts] = useState<api.RagCost[]>([]);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let cancelled = false;
    void api
      .listBots(tenantId)
      .then((rows) => {
        if (!cancelled) {
          setBots(rows);
          setBotId(rows[0]?.id ?? "");
        }
      })
      .catch(() => {
        if (!cancelled) setNotice("Could not load AI analytics.");
      });
    return () => {
      cancelled = true;
    };
  }, [tenantId]);
  useEffect(() => {
    if (!botId) return;
    let cancelled = false;
    void Promise.all([
      api.ragLimits(tenantId, botId),
      api.ragCosts(tenantId, botId),
    ])
      .then(([status, rows]) => {
        if (!cancelled) {
          setLimits(status.limits);
          setEffective(status.effective_limits);
          setUsage(status.usage);
          setCosts(rows);
          setNotice(null);
          setReadyBotId(botId);
        }
      })
      .catch(() => {
        if (!cancelled) setNotice("Could not load AI analytics.");
      });
    return () => {
      cancelled = true;
    };
  }, [tenantId, botId]);
  async function save(reset = false) {
    setBusy(true);
    try {
      await api.patchRagLimits(tenantId, botId, reset ? null : limits);
      const status = await api.ragLimits(tenantId, botId);
      setLimits(status.limits);
      setEffective(status.effective_limits);
      setUsage(status.usage);
      setNotice("AI limits saved.");
    } catch {
      setNotice("Could not save AI limits.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section
      aria-label="Staff AI costs and limits"
      data-testid="rag-operator-panel"
      className="card"
    >
      <h2>AI costs and limits</h2>
      <p>
        Current calendar month (UTC). Measured cost excludes events with
        unreported cost.
      </p>
      {notice && <Notice message={notice} />}
      <label>
        Bot{" "}
        <select
          value={botId}
          disabled={busy}
          onChange={(e) => setBotId(e.target.value)}
        >
          {bots.map((bot) => (
            <option key={bot.id} value={bot.id}>
              {bot.name}
            </option>
          ))}
        </select>
      </label>
      {botId && readyBotId !== botId && <p>Loading AI costs and limits…</p>}
      {botId && readyBotId === botId && (
        <>
          <ul aria-label="AI cost breakdown">
            {costs.map((cost) => (
              <li key={`${cost.channel}/${cost.model}/${cost.event_type}`}>
                {cost.channel} · {cost.model} · {cost.event_type}: measured $
                {cost.cost_usd}; {cost.measured_tokens} reported tokens;{" "}
                {cost.unmeasured_events} events with unreported cost
              </li>
            ))}
          </ul>
          {!costs.length && <p>No AI usage events recorded.</p>}
          <p>
            Blank overrides are uncapped. Reset restores plan defaults. Existing
            data is retained when limits are lowered.
          </p>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              void save();
            }}
          >
            {api.RAG_LIMIT_NAMES.map((name) => (
              <label key={name}>
                {LABELS[name]}{" "}
                <input
                  type="number"
                  min="0"
                  step="1"
                  value={limits[name] ?? ""}
                  disabled={busy}
                  onChange={(event) =>
                    setLimits({
                      ...limits,
                      [name]:
                        event.target.value === ""
                          ? null
                          : Number(event.target.value),
                    })
                  }
                />
                <span>
                  {" "}
                  Used: {usage[name] ?? 0}; effective limit:{" "}
                  {effective[name] ?? "Uncapped"}
                </span>
              </label>
            ))}
            <button disabled={busy} type="submit">
              Save AI limits
            </button>
            <ConfirmAction
              disabled={busy}
              title="Reset to plan defaults?"
              description={
                "Custom AI limit overrides for this bot will be removed and the current plan defaults will apply. Existing data is retained."
              }
              onConfirm={() => void save(true)}
            >
              Reset to plan defaults
            </ConfirmAction>
          </form>
        </>
      )}
    </section>
  );
}
