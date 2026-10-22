"use client";

import { useCallback, useEffect, useState } from "react";
import * as api from "@/lib/api";
import { BotLinks, CreateBotForm } from "@/lib/staff-bots";
import { OrganizationSelect } from "@/lib/staff-members";
import {
  Button,
  DataTable,
  Field,
  Loading,
  Notice,
  PageHeader,
  StatusBadge,
} from "@/lib/ui";
import "@/app/staff-screens.css";

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
    <main className="staff-page">
      <PageHeader
        title="Bots"
        purpose="Every bot across all organizations, with its knowledge and widget state."
      />
      {error && <Notice tone="error" message={error} />}
      <section aria-label="Filter bots" className="filter-bar">
        <Field label="Search bots">
          {(control) => (
            <input
              {...control}
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setOffset(0);
              }}
            />
          )}
        </Field>
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
        <DataTable
          caption="Bot directory"
          rows={bots}
          rowKey={(bot) => bot.id}
          columns={[
            { key: "bot", header: "Bot", cell: (bot) => bot.name },
            {
              key: "organization",
              header: "Organization",
              cell: (bot) => bot.organization.name,
            },
            {
              key: "status",
              header: "Status",
              cell: (bot) => (
                <StatusBadge value={bot.status}>{bot.status}</StatusBadge>
              ),
            },
            {
              key: "widget",
              header: "Widget",
              cell: (bot) => bot.widget_state,
            },
            {
              key: "sources",
              header: "Sources",
              className: "num",
              cell: (bot) => bot.source_count,
            },
            {
              key: "ingestion",
              header: "Last ingestion",
              cell: (bot) => bot.last_ingestion_job_status ?? "None",
            },
            {
              key: "revision",
              header: "Published revision",
              cell: (bot) =>
                bot.published_revision_id ? (
                  <span className="mono" dir="ltr">
                    {bot.published_revision_id}
                  </span>
                ) : (
                  "None"
                ),
            },
            {
              key: "links",
              header: "Links",
              cell: (bot) => (
                <BotLinks organization={bot.organization.id} bot={bot.id} />
              ),
            },
          ]}
        />
      )}
      <div className="pager">
        <p>{total} bots</p>
        <div className="action-row">
          <Button
            variant="quiet"
            disabled={!offset}
            onClick={() => setOffset(offset - 25)}
          >
            Previous
          </Button>
          <Button
            variant="quiet"
            disabled={offset + 25 >= total}
            onClick={() => setOffset(offset + 25)}
          >
            Next
          </Button>
        </div>
      </div>
      <CreateBotForm onCreated={load} />
    </main>
  );
}
