"use client";

import { useCallback, useEffect, useId, useState } from "react";
import * as api from "@/lib/api";
import type { TierTarget } from "@/lib/api";
import { ConfirmAction, Notice } from "@/lib/ui";
import "@/app/bot-settings-c.css";

function TierTargetRow({
  label,
  target,
}: {
  label: string;
  target: TierTarget;
}) {
  return (
    <>
      <dt>{label}</dt>
      <dd>
        {target.model
          ? `${target.provider} ${target.model}`
          : `${target.provider} — not configured`}
      </dd>
    </>
  );
}

// Rendered only for platform staff; the API enforces the same rule. Part of the
// AI section of the settings page. Its actions save immediately and give
// inline feedback; they are not part of the Save settings form.
export default function RagTierControl({
  tenantId,
  botId,
}: {
  tenantId: string;
  botId: string;
}) {
  const [status, setStatus] = useState<api.RagStatus | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const tierId = useId();
  const load = useCallback(async () => {
    try {
      setStatus(await api.ragStatus(tenantId, botId));
    } catch {
      setNotice("Could not load AI tier status.");
    }
  }, [tenantId, botId]);
  useEffect(() => {
    const timer = setTimeout(() => void load(), 0);
    return () => clearTimeout(timer);
  }, [load]);
  async function run(action: () => Promise<void>, done: string) {
    setBusy(true);
    setNotice(null);
    try {
      await action();
      await load();
      setNotice(done);
    } catch {
      setNotice("Could not update AI tier settings.");
    } finally {
      setBusy(false);
    }
  }
  const backfill = status?.backfill;
  // Nothing to backfill once every chunk has the active embedding model (#13).
  const needsBackfill = status ? !status.embedding_ready : false;
  const backfillRunning =
    backfill?.status === "pending" || backfill?.status === "running";
  return (
    <section
      aria-label="Staff AI tier"
      data-testid="rag-tier-control"
      className="rag-tier"
      aria-busy={busy}
    >
      <h3>AI tier</h3>
      {notice && <Notice message={notice} scope="item" />}
      {!status && !notice && <p className="muted">Loading AI tier…</p>}
      {status && (
        <>
          <div className="field rag-tier-field">
            <label htmlFor={tierId}>Tier</label>
            <select
              id={tierId}
              name="tier"
              value={status.tier}
              disabled={busy}
              aria-describedby={`${tierId}-hint`}
              onChange={(event) =>
                void run(
                  () =>
                    api.patchRagTier(
                      tenantId,
                      botId,
                      event.target.value as api.RagTier,
                    ),
                  "AI tier saved.",
                )
              }
            >
              <option value="standard">Standard</option>
              <option value="premium">Premium</option>
            </select>
            <p id={`${tierId}-hint`} className="field-hint">
              Saves immediately; it does not need Save settings. Standard uses
              free models and may be slower or unavailable.
            </p>
          </div>
          {/* Provider/model each tier maps to — read from the API (ADR-013). */}
          <dl data-testid="rag-tier-targets" className="rag-facts">
            <TierTargetRow
              label="Standard maps to"
              target={status.tier_targets.standard}
            />
            <TierTargetRow
              label="Premium maps to"
              target={status.tier_targets.premium}
            />
          </dl>
          <details className="rag-diagnostics" data-testid="rag-diagnostics">
            <summary>Diagnostics</summary>
            <dl className="rag-facts">
              <dt>Retrieval mode</dt>
              <dd data-testid="rag-retrieval-mode">{status.retrieval_mode}</dd>
              <dt>Active embedding model</dt>
              <dd data-testid="rag-embedding-model">
                {status.active_embedding_model ?? "none"}
              </dd>
              <dt>Backfill</dt>
              <dd data-testid="rag-backfill-status">
                {backfill
                  ? `${backfill.status}${
                      backfill.total
                        ? ` (${backfill.done ?? 0}/${backfill.total})`
                        : ""
                    }`
                  : "never run"}
              </dd>
            </dl>
          </details>
          {needsBackfill ? (
            <div className="backfill-action" data-testid="rag-backfill-action">
              <ConfirmAction
                title="Start embedding backfill?"
                description={
                  "A background job will generate embeddings for published knowledge. This can use embedding tokens and incur provider costs within configured limits."
                }
                disabled={busy || backfillRunning}
                onConfirm={() =>
                  void run(
                    () => api.startRagBackfill(tenantId, botId),
                    "Backfill requested.",
                  )
                }
              >
                Start embedding backfill
              </ConfirmAction>
              <p className="field-hint">
                Runs immediately once confirmed; it does not need Save settings.
              </p>
            </div>
          ) : (
            <p className="muted" data-testid="rag-backfill-uptodate">
              Embeddings are up to date. Nothing to backfill.
            </p>
          )}
        </>
      )}
    </section>
  );
}
