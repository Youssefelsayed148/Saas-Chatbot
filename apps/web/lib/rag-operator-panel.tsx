"use client";

import { useEffect, useState } from "react";
import * as api from "@/lib/api";
import {
  Button,
  ConfirmAction,
  DataTable,
  LimitField,
  Meter,
  Notice,
  StatusPill,
  StickyActionBar,
  type Column,
} from "@/lib/ui";

import "@/app/rag-operator-panel.css";

const LABELS: Record<api.RagLimitName, string> = {
  documents: "Documents per revision",
  chunks: "Chunks per revision",
  storage_bytes: "Stored upload bytes",
  monthly_messages: "AI messages per month",
  monthly_tokens: "AI tokens per month",
  monthly_embedding_tokens: "Embedding tokens per month",
  monthly_ocr_pages: "OCR pages per month",
};

const UNITS: Record<api.RagLimitName, string> = {
  documents: "documents",
  chunks: "chunks",
  storage_bytes: "bytes",
  monthly_messages: "messages",
  monthly_tokens: "tokens",
  monthly_embedding_tokens: "tokens",
  monthly_ocr_pages: "pages",
};

const GROUPS: { title: string; names: api.RagLimitName[] }[] = [
  { title: "Content", names: ["documents", "chunks", "storage_bytes"] },
  {
    title: "Monthly usage",
    names: ["monthly_messages", "monthly_tokens"],
  },
  {
    title: "Embedding and OCR",
    names: ["monthly_embedding_tokens", "monthly_ocr_pages"],
  },
];

type Draft = Record<api.RagLimitName, string>;

function toDraft(limits: api.RagLimits): Draft {
  const draft = {} as Draft;
  for (const name of api.RAG_LIMIT_NAMES) {
    const value = limits[name];
    draft[name] = value == null ? "" : String(value);
  }
  return draft;
}

function toLimits(draft: Draft): api.RagLimits {
  const limits: api.RagLimits = {};
  for (const name of api.RAG_LIMIT_NAMES) {
    limits[name] = draft[name] === "" ? null : Number(draft[name]);
  }
  return limits;
}

const fmt = (n: number) => n.toLocaleString("en-US");

function isZeroCost(cost: string) {
  const n = Number(cost);
  return Number.isFinite(n) && n === 0;
}

function CostCell({ cost }: { cost: api.RagCost }) {
  if (
    cost.unmeasured_events > 0 &&
    cost.measured_tokens === 0 &&
    isZeroCost(cost.cost_usd)
  ) {
    return <span className="rag-panel-muted">Not reported</span>;
  }
  if (cost.unmeasured_events > 0) {
    return (
      <>
        ${cost.cost_usd} <span className="rag-panel-muted">measured</span>
      </>
    );
  }
  return <>${cost.cost_usd}</>;
}

const COST_COLUMNS: Column<api.RagCost>[] = [
  { key: "stage", header: "Stage", cell: (c) => c.event_type },
  { key: "model", header: "Model", cell: (c) => c.model },
  { key: "channel", header: "Channel", cell: (c) => c.channel },
  {
    key: "tokens",
    header: "Tokens",
    className: "rag-panel-num",
    cell: (c) => fmt(c.measured_tokens),
  },
  {
    key: "cost",
    header: "Cost",
    className: "rag-panel-num",
    cell: (c) => <CostCell cost={c} />,
  },
  {
    key: "unreported",
    header: "Unreported cost",
    cell: (c) =>
      c.unmeasured_events > 0 ? (
        <StatusPill tone="warning">
          {fmt(c.unmeasured_events)}{" "}
          {c.unmeasured_events === 1 ? "event" : "events"} cost unreported
        </StatusPill>
      ) : (
        <span className="rag-panel-muted">None</span>
      ),
  },
];

export default function RagOperatorPanel({ tenantId }: { tenantId: string }) {
  const [bots, setBots] = useState<api.Bot[]>([]);
  const [botId, setBotId] = useState("");
  const [readyBotId, setReadyBotId] = useState("");
  const [saved, setSaved] = useState<Draft>(() => toDraft({}));
  const [draft, setDraft] = useState<Draft>(() => toDraft({}));
  const [effective, setEffective] = useState<api.RagLimits>({});
  const [usage, setUsage] = useState<Record<string, number>>({});
  const [costs, setCosts] = useState<api.RagCost[]>([]);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const dirty = api.RAG_LIMIT_NAMES.some((name) => draft[name] !== saved[name]);
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
          const loaded = toDraft(status.limits);
          setSaved(loaded);
          setDraft(loaded);
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
      await api.patchRagLimits(tenantId, botId, reset ? null : toLimits(draft));
      const status = await api.ragLimits(tenantId, botId);
      const loaded = toDraft(status.limits);
      setSaved(loaded);
      setDraft(loaded);
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
      className="card rag-panel"
    >
      <header className="rag-panel-head">
        <div>
          <h2>AI costs and limits</h2>
          <p className="rag-panel-muted">
            Current calendar month (UTC). Measured cost excludes events with
            unreported cost.
          </p>
        </div>
        {botId && readyBotId === botId && (
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
        )}
      </header>
      {notice && <Notice message={notice} />}
      <label className="rag-panel-bot">
        <span>Bot</span>
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
          <h3>Cost telemetry</h3>
          <DataTable
            caption="AI cost breakdown"
            aria-label="AI cost breakdown"
            className="rag-panel-table"
            columns={COST_COLUMNS}
            rows={costs}
            rowKey={(c) => `${c.channel}/${c.model}/${c.event_type}`}
            empty={<p>No AI usage events recorded.</p>}
          />
          <h3>Limits</h3>
          <p className="rag-panel-muted">
            Blank overrides are uncapped. Reset restores plan defaults. Existing
            data is retained when limits are lowered.
          </p>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              if (dirty) void save();
            }}
          >
            {GROUPS.map((group) => (
              <fieldset
                key={group.title}
                className="rag-panel-group"
                disabled={busy}
              >
                <legend>{group.title}</legend>
                <div className="rag-panel-fields">
                  {group.names.map((name) => {
                    const override = draft[name] !== "";
                    const plan = effective[name];
                    const showPlanMeter = !override && plan != null;
                    return (
                      <div key={name} className="rag-panel-field">
                        <LimitField
                          label={LABELS[name]}
                          unit={UNITS[name]}
                          value={draft[name]}
                          used={showPlanMeter ? undefined : (usage[name] ?? 0)}
                          step={1}
                          min={0}
                          onChange={(next) =>
                            setDraft((prev) => ({ ...prev, [name]: next }))
                          }
                        />
                        {showPlanMeter && (
                          <Meter
                            used={usage[name] ?? 0}
                            limit={plan}
                            label={`${LABELS[name]} used`}
                            unit={UNITS[name]}
                          />
                        )}
                        <p className="rag-panel-muted rag-panel-effective">
                          {override
                            ? "Override set."
                            : `No override. Effective limit: ${
                                plan == null
                                  ? "Uncapped"
                                  : `${fmt(plan)} ${UNITS[name]}`
                              }.`}
                        </p>
                      </div>
                    );
                  })}
                </div>
              </fieldset>
            ))}
            <StickyActionBar dirty={dirty}>
              <Button type="submit" disabled={busy}>
                {busy ? "Saving…" : "Save AI limits"}
              </Button>
              <Button
                variant="quiet"
                disabled={busy}
                onClick={() => setDraft(saved)}
              >
                Discard changes
              </Button>
            </StickyActionBar>
          </form>
        </>
      )}
    </section>
  );
}
