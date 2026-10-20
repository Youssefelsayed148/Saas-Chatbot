"use client";

import Link from "next/link";
import { useState } from "react";
import * as api from "./api";
import { OrganizationSelect } from "./staff-members";
import { Notice } from "./ui";

export function BotLinks({
  organization,
  bot,
}: {
  organization: string;
  bot: string;
}) {
  return (
    <span>
      <Link href={`/app/${organization}/bots/${bot}/knowledge`}>Knowledge</Link>
      {" · "}
      <Link href={`/app/${organization}/bots/${bot}/settings`}>Settings</Link>
    </span>
  );
}

export function CreateBotForm({
  organization,
  onCreated,
}: {
  organization?: { id: string; name: string };
  onCreated: () => Promise<void>;
}) {
  const [selected, setSelected] = useState("");
  const [name, setName] = useState("");
  const [created, setCreated] = useState<api.Bot | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    setCreated(null);
    try {
      const bot = await api.platformCreateBot(
        organization?.id ?? selected,
        name.trim(),
      );
      setCreated(bot);
      setName("");
      await onCreated();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create bot.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section aria-label="Create bot">
      <h2>Create bot</h2>
      {error && <Notice tone="error" message={error} />}
      <form
        onSubmit={(e) => {
          void submit(e);
        }}
      >
        {organization ? (
          <p>
            Organization: <strong>{organization.name}</strong> (fixed)
          </p>
        ) : (
          <OrganizationSelect value={selected} onChange={setSelected} />
        )}
        <label>
          Bot name
          <input
            required
            minLength={1}
            maxLength={100}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <button disabled={busy}>{busy ? "Creating…" : "Create bot"}</button>
      </form>
      {created && (
        <div role="status">
          <h3>Bot created — next steps</h3>
          <p>
            Upload and publish knowledge, then configure the allowed website
            domains in Settings.
          </p>
          <BotLinks organization={created.tenant_id} bot={created.id} />
        </div>
      )}
    </section>
  );
}
