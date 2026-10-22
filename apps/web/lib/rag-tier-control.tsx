"use client";

import { useCallback, useEffect, useState } from "react";
import * as api from "@/lib/api";
import type { TierTarget } from "@/lib/api";
import { ConfirmAction, Notice } from "@/lib/ui";

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

// Rendered only for platform staff; the API enforces the same rule.
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
  return (
    <section
      aria-label="Staff AI tier"
      data-testid="rag-tier-control"
      className="card"
    >
      <h2>AI tier</h2>
      {notice && <Notice message={notice} />}
      {!status && !notice && <p>Loading AI tier…</p>}
      {status && (
        <>
          <label>
            Tier{" "}
            <select
              name="tier"
              value={status.tier}
              disabled={busy}
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
          </label>
          {/* Provider/model each tier maps to — read from the API (ADR-013). */}
          <dl data-testid="rag-tier-targets">
            <TierTargetRow
              label="Standard maps to"
              target={status.tier_targets.standard}
            />
            <TierTargetRow
              label="Premium maps to"
              target={status.tier_targets.premium}
            />
          </dl>
          <p className="muted">
            Standard uses free models and may be slower or unavailable.
          </p>
          <dl>
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
          <ConfirmAction
            title="Start embedding backfill?"
            description={
              "A background job will generate embeddings for published knowledge. This can use embedding tokens and incur provider costs within configured limits."
            }
            disabled={busy}
            onConfirm={() =>
              void run(
                () => api.startRagBackfill(tenantId, botId),
                "Backfill requested.",
              )
            }
          >
            Start embedding backfill
          </ConfirmAction>
        </>
      )}
    </section>
  );
}
