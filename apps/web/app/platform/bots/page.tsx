"use client";

import { useCallback, useEffect, useState } from "react";
import * as api from "@/lib/api";
import { BotLinks, CreateBotForm } from "@/lib/staff-bots";
import { OrganizationSelect } from "@/lib/staff-members";
import { Loading, Notice } from "@/lib/ui";

export default function BotsPage() {
  const [bots, setBots] = useState<api.PlatformBotRow[] | null>(null);
  const [total, setTotal] = useState(0);
  const [query, setQuery] = useState("");
  const [organization, setOrganization] = useState("");
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    const params = new URLSearchParams({
      q: query,
      limit: "25",
      offset: String(offset),
    });
    if (organization) params.set("organization_id", organization);
    const result = await api.platformBots(params.toString());
    setBots(result.bots);
    setTotal(result.total);
    setError("");
  }, [query, organization, offset]);
  useEffect(() => {
    const timer = setTimeout(() => {
      void load().catch(() => setError("Could not load bots."));
    }, 200);
    return () => clearTimeout(timer);
  }, [load]);
  return (
    <main>
      <h1>Bots</h1>
      {error && <Notice tone="error" message={error} />}
      <section aria-label="Filter bots">
        <label>
          Search bots
          <input
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setOffset(0);
            }}
          />
        </label>
        <OrganizationSelect
          optional
          activeOnly={false}
          emptyLabel="All organizations"
          value={organization}
          onChange={(id) => {
            setOrganization(id);
            setOffset(0);
          }}
        />
      </section>
      {bots === null ? (
        <Loading />
      ) : (
        <table>
          <thead>
            <tr>
              <th>Bot</th>
              <th>Organization</th>
              <th>Status</th>
              <th>Widget</th>
              <th>Sources</th>
              <th>Last ingestion</th>
              <th>Published revision</th>
              <th>Links</th>
            </tr>
          </thead>
          <tbody>
            {bots.map((bot) => (
              <tr key={bot.id}>
                <td>{bot.name}</td>
                <td>{bot.organization.name}</td>
                <td>{bot.status}</td>
                <td>{bot.widget_state}</td>
                <td>{bot.source_count}</td>
                <td>{bot.last_ingestion_job_status ?? "None"}</td>
                <td>{bot.published_revision_id ?? "None"}</td>
                <td>
                  <BotLinks organization={bot.organization.id} bot={bot.id} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p>{total} bots</p>
      <button disabled={!offset} onClick={() => setOffset(offset - 25)}>
        Previous
      </button>
      <button
        disabled={offset + 25 >= total}
        onClick={() => setOffset(offset + 25)}
      >
        Next
      </button>
      <CreateBotForm onCreated={load} />
    </main>
  );
}
